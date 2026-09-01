"""
Import seed data into MongoDB.

Supported sources:
- seed_data.txt: one JSON document in the merged seed schema.
- data1/data: JSONL files grouped by profile directory.

Đồng bộ theo schema merged: experts, enterprises, projects, funders, products, datasets.
"""
import copy
import hashlib
import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo import ReplaceOne

from expert_identity_utils import (
    build_expert_name_index,
    paper_authors_from_product,
    resolve_author_names_to_expert_ids,
)
from skill_identity_utils import (
    build_skill_taxonomy_maps,
    normalize_skill_dict,
    resolve_skill_record,
)

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(SCRIPT_DIR / ".env")

DB_NAME = os.getenv("MONGO_DB_NAME", "rd_recommendation_system")
DEFAULT_DATA_FILE = SCRIPT_DIR / "seed_data.txt"
DEFAULT_DATA1_DIR = SCRIPT_DIR / "data1" / "data"
DEFAULT_MONGO_BATCH_SIZE = int(os.getenv("SEED_MONGO_BATCH_SIZE", "1000"))
DEFAULT_DATA1_PROGRESS_INTERVAL = int(os.getenv("SEED_DATA1_PROGRESS_INTERVAL", "50000"))


def _build_mongo_uri() -> str:
    explicit_uri = os.getenv("MONGO_URI")
    if explicit_uri:
        return explicit_uri

    username = os.getenv("MONGO_USERNAME")
    password = os.getenv("MONGO_PASSWORD")
    host = os.getenv("MONGO_HOST", "localhost")
    port = os.getenv("MONGO_PORT", "27017")
    auth_source = os.getenv("MONGO_AUTH_SOURCE", "admin")
    if username and password:
        return f"mongodb://{username}:{password}@{host}:{port}/{DB_NAME}?authSource={auth_source}"

    return f"mongodb://{host}:{port}"


MONGO_URI = _build_mongo_uri()

MERGED_COLLECTIONS = ["experts", "enterprises", "projects", "funders", "products", "datasets"]
COLLECTION_ID_KEYS = {
    "experts": "expert_id",
    "enterprises": "enterprise_id",
    "projects": "project_id",
    "funders": "funder_id",
    "products": "product_id",
    "datasets": "dataset_id",
}
DATA1_JSONL_TO_COLLECTION = {
    "expert.jsonl": "experts",
    "enterprise.jsonl": "enterprises",
    "enterprises.jsonl": "enterprises",
    "project.jsonl": "projects",
    "funder.jsonl": "funders",
    "product.jsonl": "products",
    "papers.jsonl": "products",
}
DATA1_WRAPPER_KEYS = {
    "expert.jsonl": "expert",
    "enterprise.jsonl": "enterprise",
    "project.jsonl": "project",
    "funder.jsonl": "funder",
    "product.jsonl": "product",
    "papers.jsonl": "output_asset",
}
_VN_LOCATION_RE = re.compile(r"^(?P<cc>[A-Za-z]{2})-(?P<region>.+)$")


def _norm(s: str) -> str:
    if s is None:
        return ""
    return re.sub(r"[^a-zA-Z0-9]+", "", str(s)).lower()


def _safe_int(x, default=None):
    try:
        return int(x)
    except Exception:
        return default


def _slug_id(s: str, prefix: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9]+", "_", str(s)).strip("_")
    base = base.upper() if base else "UNKNOWN"
    return f"{prefix}_{base}"


def _as_path(value):
    if value is None:
        return None
    return Path(value).expanduser().resolve()


def _resolve_data1_dir(path):
    data_dir = _as_path(path) or DEFAULT_DATA1_DIR
    if data_dir.name.lower() == "data1" and (data_dir / "data").is_dir():
        data_dir = data_dir / "data"
    if not data_dir.exists() or not data_dir.is_dir():
        raise FileNotFoundError(f"Không tìm thấy thư mục data1 hợp lệ: {data_dir}")
    return data_dir


def _unwrap_data1_document(file_name, doc):
    if not isinstance(doc, dict):
        return None
    wrapper_key = DATA1_WRAPPER_KEYS.get(file_name)
    if wrapper_key and isinstance(doc.get(wrapper_key), dict):
        return doc[wrapper_key]
    return doc


def _append_unique_by_id(items_by_id, fallback_items, collection_name, doc):
    if not isinstance(doc, dict):
        return
    id_key = COLLECTION_ID_KEYS.get(collection_name)
    doc_id = doc.get(id_key) if id_key else None
    if doc_id:
        items_by_id[collection_name][str(doc_id)] = doc
    else:
        fallback_items[collection_name].append(doc)


def _normalize_keywords(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        parts = re.split(r"[;,|]", value)
        return [x.strip() for x in parts if x.strip()]
    return [str(value).strip()] if str(value).strip() else []


def _data1_product_signature(doc):
    if not isinstance(doc, dict):
        return None
    name = doc.get("name") or doc.get("title")
    year = doc.get("year") or (doc.get("metadata") or {}).get("year")
    linked_project_id = doc.get("linked_project_id")
    developer_ids = doc.get("developer_ids") or doc.get("developed_by") or []
    if isinstance(developer_ids, str):
        developer_ids = [developer_ids]
    developer_key = "|".join(sorted(str(x) for x in developer_ids if x))
    raw = "|".join([_norm(name), str(year or ""), str(linked_project_id or ""), developer_key])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest() if raw.strip("|") else None


def _merge_product_metadata(primary, secondary):
    merged = copy.deepcopy(primary)
    secondary_metadata = secondary.get("metadata") if isinstance(secondary, dict) else None
    if isinstance(secondary_metadata, dict):
        metadata = merged.setdefault("metadata", {})
        if isinstance(metadata, dict):
            for key, value in secondary_metadata.items():
                if key not in metadata or metadata.get(key) in (None, "", []):
                    metadata[key] = copy.deepcopy(value)
    for key in ("description", "source_file"):
        if not merged.get(key) and isinstance(secondary, dict) and secondary.get(key):
            merged[key] = secondary.get(key)
    return merged


def _normalize_data1_product(doc, file_name):
    if file_name != "papers.jsonl":
        product = copy.deepcopy(doc)
        product.setdefault("source_file", file_name)
        return product

    metadata = doc.get("metadata") or {}
    links = doc.get("links") or {}
    expert_id = links.get("produced_by_expert")
    developer_ids = [expert_id] if expert_id else []
    authors = metadata.get("authors") if isinstance(metadata.get("authors"), list) else []

    return {
        "product_id": doc.get("asset_id") or _slug_id(doc.get("title") or "paper", "PAPER"),
        "name": doc.get("title"),
        "type": "scientific_paper",
        "trl": 1,
        "year": _safe_int(metadata.get("year"), metadata.get("year")),
        "linked_project_id": links.get("produced_by_project"),
        "developer_ids": developer_ids,
        "developed_by": developer_ids,
        "license": None,
        "access_url": None,
        "description": metadata.get("abstract"),
        "metadata": {
            "source_type": doc.get("type"),
            "source_file": file_name,
            "publisher": metadata.get("publisher"),
            "status": metadata.get("status"),
            "abstract": metadata.get("abstract"),
            "keywords": _normalize_keywords(metadata.get("keywords")),
            "authors": authors,
            "commercialized_by": links.get("commercialized_by"),
        },
        "source_file": file_name,
    }


def _enrich_data1_product_developer_ids(experts, products):
    name_index = build_expert_name_index(experts or [])
    enriched = 0
    for product in products or []:
        if not isinstance(product, dict):
            continue
        seed_ids = product.get("developer_ids") or product.get("developed_by") or []
        resolved = resolve_author_names_to_expert_ids(
            paper_authors_from_product(product),
            name_index=name_index,
            seed_ids=seed_ids,
        )
        if resolved and resolved != list(seed_ids):
            product["developer_ids"] = resolved
            product["developed_by"] = resolved
            enriched += 1
    return enriched


def _safe_print(message):
    text = str(message)
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="backslashreplace").decode("ascii"), flush=True)


def _parse_location(value):
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    raw = str(value).strip()
    m = _VN_LOCATION_RE.match(raw)
    if m:
        cc = m.group("cc").upper()
        region = m.group("region")
        return {
            "country_code": cc,
            "country_name": "Vietnam" if cc == "VN" else None,
            "region": region,
            "city": region,
            "coordinates": {},
        }
    cc = _norm(raw)[:2].upper() if raw else "UNK"
    return {
        "country_code": cc,
        "country_name": raw,
        "region": None,
        "city": raw,
        "coordinates": {},
    }


def _parse_trl_range_focus(value):
    if isinstance(value, dict):
        return {
            "min": _safe_int(value.get("min")),
            "max": _safe_int(value.get("max")),
        }
    if not value:
        return {"min": None, "max": None}
    m = re.search(r"(?P<min>\d+)\s*-\s*(?P<max>\d+)", str(value))
    if not m:
        return {"min": _safe_int(value), "max": None}
    return {"min": _safe_int(m.group("min")), "max": _safe_int(m.group("max"))}


def _merge_directions_from_sources(directions, topics):
    merged = []
    seen = set()

    for d in (directions or []):
        if not isinstance(d, str):
            continue
        name = d.strip()
        if not name:
            continue
        key = _norm(name)
        if key in seen:
            continue
        seen.add(key)
        merged.append(name)

    for t in (topics or []):
        if not isinstance(t, dict):
            continue
        parent = t.get("parent_direction")
        if not isinstance(parent, str):
            continue
        name = parent.strip()
        if not name:
            continue
        key = _norm(name)
        if key in seen:
            continue
        seen.add(key)
        merged.append(name)

    return merged


def _normalize_topics(topics):
    normalized = []
    for t in (topics or []):
        if not isinstance(t, dict):
            continue
        name = t.get("name")
        parent = t.get("parent_direction")
        if not isinstance(name, str) or not name.strip():
            continue
        normalized.append(
            {
                "name": name.strip(),
                "parent_direction": parent.strip() if isinstance(parent, str) and parent.strip() else None,
            }
        )
    return normalized


def _build_lookup_maps(old_data: dict):
    fields = old_data.get("research_fields", []) or []
    industries = old_data.get("industries", []) or []
    methods = old_data.get("method_techniques", []) or []

    field_map = {}
    for f in fields:
        if f.get("field_id"):
            field_map[f["field_id"]] = {
                "id": f.get("field_id"),
                "name": f.get("label"),
                "description": f.get("description"),
                "level": (f.get("hierarchy") or {}).get("level"),
                "parent_id": (f.get("hierarchy") or {}).get("parent_id"),
                "ontology_ref": (f.get("mapping") or {}).get("standard_code") or (f.get("mapping") or {}).get("standard"),
            }

    industry_map = {}
    code_to_industry_id = {}
    for ind in industries:
        std = ind.get("standard_mapping") or {}
        item = {
            "id": ind.get("industry_id"),
            "name": ind.get("industry_name"),
            "code": std.get("code"),
            "standard": std.get("type"),
        }
        if item["id"]:
            industry_map[item["id"]] = item
        if item["code"]:
            code_to_industry_id[item["code"]] = item["id"]

    skill_map, skill_by_compact, skill_by_norm_key = build_skill_taxonomy_maps(methods)
    skill_by_norm = {compact: sid for compact, sid in skill_by_compact.items()}

    return field_map, industry_map, code_to_industry_id, skill_map, skill_by_norm, skill_by_compact, skill_by_norm_key


def _make_resolvers(old_data):
    field_map, industry_map, code_to_industry_id, skill_map, skill_by_norm, skill_by_compact, skill_by_norm_key = _build_lookup_maps(old_data)

    def resolve_field(fid):
        return field_map.get(fid, {"id": fid, "name": fid, "description": None, "level": None, "parent_id": None, "ontology_ref": None})

    def resolve_industry(industry_id_or_code):
        if isinstance(industry_id_or_code, dict):
            code = industry_id_or_code.get("code")
            name = industry_id_or_code.get("name")
            if code or name:
                return {
                    "id": industry_id_or_code.get("id") or code or name,
                    "name": name or code,
                    "code": code,
                    "standard": industry_id_or_code.get("standard"),
                }
        if industry_id_or_code in industry_map:
            return industry_map[industry_id_or_code]
        mapped_id = code_to_industry_id.get(industry_id_or_code)
        if mapped_id and mapped_id in industry_map:
            return industry_map[mapped_id]
        return {"id": industry_id_or_code, "name": industry_id_or_code, "code": None, "standard": None}

    def resolve_skill_by_name(skill_name, category=None):
        return resolve_skill_record(
            skill_name,
            skill_map=skill_map,
            by_compact=skill_by_compact,
            by_norm_key=skill_by_norm_key,
            category=category,
        )

    return resolve_field, resolve_industry, resolve_skill_by_name


def _map_output_type_to_product_type(old_type: str):
    t = (old_type or "").lower()
    if "bằng sáng chế" in t or "bang sang che" in t:
        return "patent"
    if "nguyên mẫu" in t or "nguyen mau" in t:
        return "prototype"
    if "báo cáo" in t or "bao cao" in t:
        return "dataset"
    if "phần mềm" in t or "phan mem" in t or "giải pháp" in t or "giai phap" in t:
        return "software"
    return "prototype"


def _build_products(old_data: dict):
    # Preferred path: already in merged schema.
    products = old_data.get("products")
    if isinstance(products, list) and products:
        return [copy.deepcopy(p) for p in products if isinstance(p, dict)]

    # Backward-compatible path: legacy output_assets schema.
    docs = []
    for asset in old_data.get("output_assets", []) or []:
        metadata = asset.get("metadata") or {}
        links = asset.get("links") or {}
        docs.append(
            {
                "product_id": asset.get("asset_id"),
                "name": asset.get("title"),
                "type": _map_output_type_to_product_type(asset.get("type")),
                "trl": 1,
                "year": metadata.get("year"),
                "linked_project_id": links.get("produced_by_project"),
                "developed_by": [],
                "license": None,
                "access_url": None,
            }
        )
    return docs


def _build_datasets(old_data: dict):
    # Preferred path: already in merged schema.
    datasets = old_data.get("datasets")
    if isinstance(datasets, list) and datasets:
        return [copy.deepcopy(d) for d in datasets if isinstance(d, dict)]

    # Backward-compatible path: no legacy mapping available yet.
    return []


def _transform_expert(expert: dict, resolve_field, resolve_industry, resolve_skill, funder_name_to_id):
    e = copy.deepcopy(expert)
    
    # --- 1. BASIC INFO ---
    bi = e.get("basic_info") or {}
    bi["location"] = _parse_location(bi.pop("location", None))
    e["basic_info"] = bi

    # --- 2. IDENTIFIERS ---
    ids = e.get("identifiers") or {}
    if "ScopusID" in ids and "Scopus_ID" not in ids:
        ids["Scopus_ID"] = ids.pop("ScopusID")
    e["identifiers"] = ids

    # --- 3. RESEARCH CAPACITY ---
    rc = e.get("research_capacity") or {}
    existing_directions = rc.get("research_directions")
    existing_topics = rc.get("research_topics")
    field_ids = rc.pop("research_fields", None)

    if field_ids:
        # Hướng nghiên cứu vĩ mô (mảng String)
        computed_directions = [
            resolve_field(fid).get("name")
            for fid in field_ids
            if resolve_field(fid).get("name")
        ]

        # Khởi tạo chủ đề nghiên cứu chi tiết (Mảng Object có parent_direction)
        research_topics = []
        for fid in field_ids:
            field_data = resolve_field(fid)
            # Giả định level >= 2 là topic cụ thể
            if (field_data.get("level") or 0) >= 2:
                parent_id = field_data.get("parent_id")
                parent_name = resolve_field(parent_id).get("name") if parent_id else None
                research_topics.append({
                    "name": field_data.get("name"),
                    "parent_direction": parent_name
                })
        rc["research_topics"] = research_topics
        rc["research_directions"] = _merge_directions_from_sources(computed_directions, research_topics)
    else:
        # Giữ nguyên dữ liệu mới schema nếu không có research_fields (legacy)
        rc["research_topics"] = existing_topics if isinstance(existing_topics, list) else []
        base_directions = existing_directions if isinstance(existing_directions, list) else []
        rc["research_directions"] = _merge_directions_from_sources(base_directions, rc["research_topics"])

    interests = rc.get("research_interests") or []
    if interests:
        topics = list(rc.get("research_topics") or [])
        known = {
            str(t.get("name") or "").strip().lower()
            for t in topics
            if isinstance(t, dict) and str(t.get("name") or "").strip()
        }
        for item in interests:
            topic_name = str(item.get("name") if isinstance(item, dict) else item).strip()
            if topic_name and topic_name.lower() not in known:
                topics.append({"name": topic_name})
                known.add(topic_name.lower())
        rc["research_topics"] = topics
        rc["research_directions"] = _merge_directions_from_sources(rc.get("research_directions") or [], topics)

    # Kỹ năng
    skills = []
    for item in rc.get("skills_methods", []) or []:
        if not isinstance(item, dict):
            continue
        resolved = resolve_skill(item.get("name"), category=item.get("category"))
        skills.append(
            {
                "skill_id": resolved.get("skill_id"),
                "name": resolved.get("name"),
                "category": resolved.get("category"),
                "proficiency_level": item.get("proficiency_level"),
            }
        )
    rc["skills_methods"] = skills
    
    # Ngành ứng dụng
    transformed_industries = []
    for ind in (rc.pop("applied_industries", []) or []):
        if isinstance(ind, dict):
            code = ind.get("code")
            name = ind.get("name")
            if code or name:
                transformed_industries.append({"code": code, "name": name})
            continue

        resolved_ind = resolve_industry(ind)
        if resolved_ind.get("code") or resolved_ind.get("name"):
            transformed_industries.append(
                {
                    "code": resolved_ind.get("code"),
                    "name": resolved_ind.get("name"),
                }
            )
    rc["applied_industries"] = transformed_industries
    e["research_capacity"] = rc

    # --- 4. ACTIVITIES AND OUTPUTS ---
    aao = e.get("activities_and_outputs") or {}
    
    # Lịch sử nhận tài trợ
    grants = aao.get("grant_history") or []
    aao["grant_history"] = [
        {
            "grant_id": g.get("grant_id"),
            "funder_id": g.get("funder_id") or funder_name_to_id.get(_norm(g.get("funder_name"))),
            "amount": g.get("amount"),
            "year": g.get("year"),
            "linked_project_id": g.get("linked_project_id") or g.get("linked_project"),
        }
        for g in grants if isinstance(g, dict)
    ]
    
    aao.setdefault("owned_dataset_ids", [])
    aao.setdefault("accessible_dataset_ids", [])
    aao.setdefault("list_outputs", [])

    # Xử lý riêng biệt mảng collaborators theo schema
    collaborators = []
    for c in (aao.get("collaborators") or []):
        if not isinstance(c, dict):
            continue
        collaborators.append({
            "expert_id": c.get("expert_id"),
            "relation_type": c.get("relation_type"),
            "duration": c.get("duration")
        })
    aao["collaborators"] = collaborators

    # Xử lý riêng biệt mảng projects_participation theo schema
    projects_participation = []
    for p in (aao.get("projects_participation") or []):
        if not isinstance(p, dict):
            continue
        projects_participation.append({
            "project_id": p.get("project_id"),
            "role": p.get("role"),
            "duration": p.get("duration"),
            "status": p.get("status")
        })
    aao["projects_participation"] = projects_participation

    e["activities_and_outputs"] = aao
    
    return e


def _transform_enterprise(ent: dict, resolve_field, resolve_industry):
    e = copy.deepcopy(ent)
    bi = e.get("basic_info") or {}
    bi["location"] = _parse_location(bi.pop("location", None))
    mapped_industries = [resolve_industry(x) for x in (bi.pop("industry_codes", []) or [])]
    bi["industry"] = mapped_industries[0] if mapped_industries else {"id": None, "name": None}
    bi["industry_list"] = mapped_industries
    e["basic_info"] = bi

    rd = e.get("rd_profile") or {}
    focus_ids = rd.pop("rd_focus_fields", []) or []
    rd["rd_focus_directions"] = [resolve_field(fid).get("name") for fid in focus_ids]
    transformed_needs = []
    for need in (rd.get("technology_needs") or []):
        if not isinstance(need, dict):
            continue
        transformed_needs.append(
            {
                "need": need.get("need"),
                "desired_trl": need.get("desired_TRL"),
                "required_skill": {"id": None, "name": None},
                "proficiency_level": None,
            }
        )
    rd["technology_needs"] = transformed_needs
    e["rd_profile"] = rd

    rel = e.get("relations") or {}
    rel.setdefault("rd_projects", [])
    rel["sponsors_projects"] = [
        {"project_id": None, "funder_id": x.get("funder_id"), "year": x.get("year"), "amount": x.get("amount")}
        for x in (rel.get("funder_relations") or [])
        if isinstance(x, dict)
    ]
    rd_contact = (e.get("representatives") or {}).get("rd_contact") or {}
    rel["worked_experts"] = [{"expert_id": rd_contact.get("expert_id"), "role": "rd_contact", "period": None}] if rd_contact.get("expert_id") else []
    e["relations"] = rel
    return e


def _transform_enterprise(ent: dict, resolve_field, resolve_industry, resolve_skill=None):
    e = copy.deepcopy(ent)
    
    # --- 1. BASIC INFO ---
    bi = e.get("basic_info") or {}
    bi["location"] = _parse_location(bi.pop("location", None))
    
    # Đồng bộ mảng industries thành [{code, name}]
    existing_industries = bi.get("industries")
    mapped_industries = []
    industry_codes = bi.pop("industry_codes", []) or []
    for ind_code in industry_codes:
        industry_data = resolve_industry(ind_code)
        if industry_data.get("name") or industry_data.get("code"):
            mapped_industries.append({"code": industry_data.get("code"), "name": industry_data.get("name")})

    if mapped_industries:
        bi["industries"] = mapped_industries
    elif isinstance(existing_industries, list):
        bi["industries"] = [{"code": x.get("code"), "name": x.get("name")} for x in existing_industries if isinstance(x, dict)]
    else:
        bi["industries"] = []
    
    # Dọn rác do schema cũ
    bi.pop("industry", None)
    bi.pop("industry_list", None)
    e["basic_info"] = bi

    # --- 2. RD PROFILE ---
    rd = e.get("rd_profile") or {}
    existing_directions = rd.get("rd_focus_directions")
    existing_topics = rd.get("rd_focus_topics")
    focus_ids = rd.pop("rd_focus_fields", []) or []
    
    # Tách Directions (Vĩ mô - Mảng String) và Topics (Vi mô - Mảng Object)
    rd_focus_directions = set()
    rd_focus_topics = []
    
    for fid in focus_ids:
        field_data = resolve_field(fid)
        if (field_data.get("level") or 0) >= 2:
            parent_id = field_data.get("parent_id")
            parent_name = resolve_field(parent_id).get("name") if parent_id else None
            rd_focus_topics.append({
                "name": field_data.get("name"),
                "parent_direction": parent_name
            })
        else:
            if field_data.get("name"):
                rd_focus_directions.add(field_data.get("name"))
                
    if focus_ids:
        normalized_topics = _normalize_topics(rd_focus_topics)
        rd["rd_focus_topics"] = normalized_topics
        rd["rd_focus_directions"] = _merge_directions_from_sources(list(rd_focus_directions), normalized_topics)
    else:
        normalized_topics = _normalize_topics(existing_topics if isinstance(existing_topics, list) else [])
        base_directions = existing_directions if isinstance(existing_directions, list) else []
        rd["rd_focus_topics"] = normalized_topics
        rd["rd_focus_directions"] = _merge_directions_from_sources(base_directions, normalized_topics)

    # Chuẩn hóa technology_needs (Đổi thành required_skills)
    transformed_needs = []
    for need in (rd.get("technology_needs") or []):
        if not isinstance(need, dict):
            continue
            
        required_skills = []
        existing_required_skills = need.get("required_skills")
        if isinstance(existing_required_skills, list):
            for rs in existing_required_skills:
                if not isinstance(rs, dict):
                    continue
                if not rs.get("name"):
                    continue
                resolved = resolve_skill(rs.get("name"), category=rs.get("category")) if resolve_skill else rs
                required_skills.append(
                    {
                        "skill_id": resolved.get("skill_id"),
                        "name": resolved.get("name"),
                        "category": resolved.get("category"),
                        "proficiency_level": rs.get("proficiency_level"),
                    }
                )
        else:
            old_skill = need.get("required_skill")
            skill_name = old_skill.get("name") if isinstance(old_skill, dict) else old_skill
            if skill_name:
                resolved = resolve_skill(skill_name) if resolve_skill else {"name": skill_name, "category": None, "skill_id": None}
                required_skills.append(
                    {
                        "skill_id": resolved.get("skill_id"),
                        "name": resolved.get("name"),
                        "category": resolved.get("category"),
                        "proficiency_level": need.get("proficiency_level"),
                    }
                )

        transformed_needs.append(
            {
                "need": need.get("need"),
                "desired_TRL": need.get("desired_TRL") or need.get("desired_trl"),
                "required_skills": required_skills,
            }
        )
    rd["technology_needs"] = transformed_needs
    e["rd_profile"] = rd

    # --- 3. RELATIONS ---
    rel = e.get("relations") or {}
    rel.setdefault("rd_projects", [])

    # Chuyển đổi chuyên gia liên hệ thành worked_experts
    rd_contact = (e.get("representatives") or {}).get("rd_contact") or {}
    if rd_contact.get("expert_id"):
        rel["worked_experts"] = [
            {
                "expert_id": rd_contact.get("expert_id"),
                "role": "RD Contact",
                "period": None,
            }
        ]
    else:
        rel["worked_experts"] = [x for x in (rel.get("worked_experts") or []) if isinstance(x, dict)]
    
    e["relations"] = rel
    
    return e

def _transform_project(prj: dict, resolve_field, resolve_skill, resolve_industry=None):
    p = copy.deepcopy(prj)

    # --- 1. BASIC INFO ---
    bi = p.get("basic_info") or {}
    bi["location"] = _parse_location(bi.pop("location", None))

    # Tách Directions và Topics từ dữ liệu cũ
    # (Hỗ trợ cả trường hợp file cũ dùng list 'research_fields' hoặc chuỗi 'research_domain')
    # Nếu dữ liệu mới thiếu research_fields thì giữ nguyên research_directions/research_topics đã có,
    # tránh mất dữ liệu khi ghi đè record cũ.
    existing_directions = bi.get("research_directions")
    existing_topics = bi.get("research_topics")

    old_fields = bi.pop("research_fields", None)
    if not old_fields:
        rd = bi.pop("research_domain", None)
        if rd:
            old_fields = [rd] if isinstance(rd, str) else rd

    if old_fields:
        directions = set()
        topics = []

        for fid in old_fields:
            field_data = resolve_field(fid)
            if (field_data.get("level") or 0) >= 2:
                parent_id = field_data.get("parent_id")
                parent_name = resolve_field(parent_id).get("name") if parent_id else None
                topics.append({
                    "name": field_data.get("name"),
                    "parent_direction": parent_name
                })
            else:
                if field_data.get("name"):
                    directions.add(field_data.get("name"))

        bi["research_topics"] = topics
        bi["research_directions"] = _merge_directions_from_sources(list(directions), topics)
    else:
        bi["research_topics"] = existing_topics if isinstance(existing_topics, list) else []
        base_directions = existing_directions if isinstance(existing_directions, list) else []
        bi["research_directions"] = _merge_directions_from_sources(base_directions, bi["research_topics"])
    p["basic_info"] = bi

    # --- 2. REQUIREMENTS AND TIMELINE ---
    rat = p.get("requirements_and_timeline") or {}
    for key in list(rat.keys()):
        if "technology_readiness_level" in key and key != "technology_readiness_level":
            rat["technology_readiness_level"] = rat.pop(key)
    rat.setdefault("technology_readiness_level", None)

    # Chuẩn hóa required_skills (Bỏ ID, dùng name/category/proficiency_level)
    transformed_skills = []
    for s in (rat.pop("required_skills", []) or []):
        skill_name = s.get("name") if isinstance(s, dict) else s
        if not skill_name:
            continue
        resolved = resolve_skill(skill_name, category=s.get("category") if isinstance(s, dict) else None)
        transformed_skills.append({
            "skill_id": resolved.get("skill_id"),
            "name": resolved.get("name"),
            "category": resolved.get("category"),
            "proficiency_level": s.get("proficiency_level") if isinstance(s, dict) else None,
        })
    rat["required_skills"] = transformed_skills

    # Xóa funding_source_id bị dư thừa ở budget (Vì đã quản lý dưới relations)
    budget = rat.get("budget") or {}
    budget.pop("funding_source_id", None)
    rat["budget"] = budget

    p["requirements_and_timeline"] = rat

    # --- 3. RD PROFILE ---
    rdp = p.get("rd_profile") or {}
    rdp.setdefault("required_dataset_ids", [])
    p["rd_profile"] = rdp

    # --- 4. RELATIONS ---
    rel = p.get("relations") or {}
    rel.setdefault("participants", [])
    rel.setdefault("enterprise_partners", [])
    rel.setdefault("funders", [])

    # Chuẩn hóa target_industries về định dạng [{code, name}]
    target_inds = []
    old_inds = rel.pop("target_industries", []) or bi.pop("target_industries", [])
    if resolve_industry:
        for ind in old_inds:
            if isinstance(ind, dict) and (ind.get("code") or ind.get("name")):
                target_inds.append({"code": ind.get("code"), "name": ind.get("name")})
                continue
            ind_val = ind.get("code") if isinstance(ind, dict) else ind
            resolved_ind = resolve_industry(ind_val)
            if resolved_ind.get("name") or resolved_ind.get("code"):
                target_inds.append({
                    "code": resolved_ind.get("code"),
                    "name": resolved_ind.get("name")
                })
    rel["target_industries"] = target_inds
    p["relations"] = rel

    # --- 5. FOLLOW-UP OPPORTUNITIES ---
    fu = p.get("follow_up_opportunities") or {}
    if "next_phase_project" in fu and "next_phase_project_id" not in fu:
        fu["next_phase_project_id"] = fu.pop("next_phase_project")
    p["follow_up_opportunities"] = fu

    return p
def _transform_funder(funder: dict, resolve_field, resolve_industry=None):
    f = copy.deepcopy(funder)

    # --- 1. BASIC INFO & REPRESENTATIVES ---
    bi = f.get("basic_info") or {}
    bi["location"] = _parse_location(bi.pop("location", None))
    f["basic_info"] = bi

    # Đảm bảo representatives là một mảng (Array[Object])
    reps = f.get("representatives")
    if isinstance(reps, dict):
        f["representatives"] = [reps]
    elif not isinstance(reps, list):
        f["representatives"] = []

    # --- 2. FUNDING STRATEGY ---
    fs = f.get("funding_strategy") or {}
    existing_directions = fs.get("funding_directions")
    existing_topics = fs.get("funding_topics")
    direction_ids = fs.pop("funding_domains", []) or []

    # Tách Funding Directions (Mảng String) và Funding Topics (Mảng Object)
    directions = set()
    topics = []
    for fid in direction_ids:
        field_data = resolve_field(fid)
        if (field_data.get("level") or 0) >= 2:
            parent_id = field_data.get("parent_id")
            parent_name = resolve_field(parent_id).get("name") if parent_id else None
            topics.append({
                "name": field_data.get("name"),
                "parent_direction": parent_name
            })
        else:
            if field_data.get("name"):
                directions.add(field_data.get("name"))

    if direction_ids:
        normalized_topics = _normalize_topics(topics)
        fs["funding_topics"] = normalized_topics
        fs["funding_directions"] = _merge_directions_from_sources(list(directions), normalized_topics)
    else:
        normalized_topics = _normalize_topics(existing_topics if isinstance(existing_topics, list) else [])
        base_directions = existing_directions if isinstance(existing_directions, list) else []
        fs["funding_topics"] = normalized_topics
        fs["funding_directions"] = _merge_directions_from_sources(base_directions, normalized_topics)

    fs["trl_range_focus"] = _parse_trl_range_focus(fs.get("trl_range_focus"))
    region = (bi.get("location") or {}).get("region")
    fs.setdefault("focus_regions", [region] if region else [])

    # Chuẩn hóa focus_sectors [{code, name}]
    sectors = []
    old_sectors = fs.pop("focus_sectors", [])
    if resolve_industry:
        for ind in old_sectors:
            if isinstance(ind, dict) and (ind.get("code") or ind.get("name")):
                sectors.append({"code": ind.get("code"), "name": ind.get("name")})
                continue
            ind_val = ind.get("code") if isinstance(ind, dict) else ind
            resolved_ind = resolve_industry(ind_val)
            if resolved_ind.get("name") or resolved_ind.get("code"):
                sectors.append({
                    "code": resolved_ind.get("code"),
                    "name": resolved_ind.get("name")
                })
    fs["focus_sectors"] = sectors
    f["funding_strategy"] = fs

    # --- 3. RELATIONS ---
    rel = f.get("relations") or {}
    
    # ❌ Xóa funds_project_ids vì đã có funding_history.funded_projects
    rel.pop("funds_projects", None)
    rel.pop("funds_project_ids", None)

    rel["invests_in_enterprise_ids"] = rel.pop("invests_in", rel.get("invests_in_enterprise_ids", []))
    rel["collaborates_with_funder_ids"] = rel.pop("collaborates_with", rel.get("collaborates_with_funder_ids", []))
    f["relations"] = rel

    # --- 4. PROGRAMS ---
    new_programs = []
    for p in (f.get("programs") or []):
        if not isinstance(p, dict):
            continue
        item = copy.deepcopy(p)
        if "max_budget" in item and "budget" not in item:
            item["budget"] = {"max_amount": item.pop("max_budget"), "currency": None, "fiscal_year": None}

        # Chuẩn hóa target_industries [{code, name}]
        target_inds = []
        # Lấy từ cả key cũ (số ít) và key mới (số nhiều)
        old_inds = item.pop("target_industry", item.get("target_industries", []))
        if resolve_industry:
            for ind in old_inds:
                if isinstance(ind, dict) and (ind.get("code") or ind.get("name")):
                    target_inds.append({"code": ind.get("code"), "name": ind.get("name")})
                    continue
                ind_val = ind.get("code") if isinstance(ind, dict) else ind
                resolved_ind = resolve_industry(ind_val)
                if resolved_ind.get("name") or resolved_ind.get("code"):
                    target_inds.append({
                        "code": resolved_ind.get("code"),
                        "name": resolved_ind.get("name")
                    })
        item["target_industries"] = target_inds
        new_programs.append(item)
        
    f["programs"] = new_programs

    # --- 5. FUNDING HISTORY ---
    fh = f.get("funding_history") or {}
    fh.setdefault("funded_projects", [])
    f["funding_history"] = fh

    return f

def load_seed_data(file_path=None):
    path = file_path or DEFAULT_DATA_FILE
    path = _as_path(path)
    if not path.exists():
        raise FileNotFoundError(f"Không tìm thấy file dữ liệu: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_data1_seed_data(data_dir=None, limit_per_collection=0):
    root = _resolve_data1_dir(data_dir)
    limit = int(limit_per_collection or 0)
    progress_interval = max(1, DEFAULT_DATA1_PROGRESS_INTERVAL)
    items_by_id = {name: {} for name in MERGED_COLLECTIONS}
    fallback_items = {name: [] for name in MERGED_COLLECTIONS}
    product_signature_to_id = {}
    seen_files = 0
    read_lines = 0
    skipped_files = {}
    duplicate_products = 0

    for path in root.rglob("*.jsonl"):
        file_name = path.name
        collection_name = DATA1_JSONL_TO_COLLECTION.get(file_name)
        if not collection_name:
            skipped_files[file_name] = skipped_files.get(file_name, 0) + 1
            continue

        if limit and len(items_by_id[collection_name]) >= limit:
            continue

        seen_files += 1
        _safe_print(f"Reading {path.name}: {path.parent.name}")
        with path.open("r", encoding="utf-8") as f:
            for line_number, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    doc = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Lỗi JSON tại {path}:{line_number}: {exc}") from exc

                doc = _unwrap_data1_document(file_name, doc)
                if not isinstance(doc, dict):
                    continue

                if collection_name == "products":
                    doc = _normalize_data1_product(doc, file_name)
                    signature = _data1_product_signature(doc)
                    product_id = doc.get("product_id")
                    existing_id = product_signature_to_id.get(signature) if signature else None
                    if existing_id and existing_id != product_id:
                        duplicate_products += 1
                        if file_name == "product.jsonl":
                            existing_doc = items_by_id["products"].get(existing_id)
                            if existing_doc:
                                doc = _merge_product_metadata(doc, existing_doc)
                            items_by_id["products"].pop(existing_id, None)
                            product_signature_to_id[signature] = product_id
                        else:
                            existing_doc = items_by_id["products"].get(existing_id)
                            if existing_doc:
                                items_by_id["products"][existing_id] = _merge_product_metadata(existing_doc, doc)
                            read_lines += 1
                            if read_lines % progress_interval == 0:
                                _safe_print(
                                    f"  Reading data1: {read_lines} records, "
                                    f"products={len(items_by_id['products'])}, duplicates={duplicate_products}"
                                )
                            continue
                    elif signature and product_id:
                        product_signature_to_id[signature] = product_id

                _append_unique_by_id(items_by_id, fallback_items, collection_name, doc)
                read_lines += 1
                if read_lines % progress_interval == 0:
                    _safe_print(
                        f"  Reading data1: {read_lines} records, "
                        f"products={len(items_by_id['products'])}, duplicates={duplicate_products}"
                    )

                if limit and len(items_by_id[collection_name]) >= limit:
                    break

    data = {
        collection_name: list(items_by_id[collection_name].values()) + fallback_items[collection_name]
        for collection_name in MERGED_COLLECTIONS
    }
    # data1 không có taxonomy chuẩn riêng; resolver sẽ fallback bằng chính id/name.
    data.setdefault("research_fields", [])
    data.setdefault("industries", [])
    data.setdefault("method_techniques", [])

    enriched_products = _enrich_data1_product_developer_ids(
        data.get("experts") or [],
        data.get("products") or [],
    )
    if enriched_products:
        _safe_print(f"  enriched paper developer_ids from author names: {enriched_products}")

    _safe_print(f"Loaded data1 from: {root}")
    _safe_print(f"  JSONL files used: {seen_files}; records read before de-dup: {read_lines}")
    if duplicate_products:
        _safe_print(f"  duplicate products skipped/replaced by signature: {duplicate_products}")
    for collection_name in MERGED_COLLECTIONS:
        _safe_print(f"  {collection_name}: {len(data.get(collection_name, []))}")
    if skipped_files:
        skipped_summary = ", ".join(f"{name}={count}" for name, count in sorted(skipped_files.items()))
        _safe_print(f"  skipped auxiliary JSONL files: {skipped_summary}")

    return data


def convert_seed_data(old_data: dict):
    resolve_field, resolve_industry, resolve_skill = _make_resolvers(old_data)
    products_docs = _build_products(old_data)
    datasets_docs = _build_datasets(old_data)

    funders_old = old_data.get("funders", []) or []
    funder_name_to_id = {}
    for fun in funders_old:
        name = (fun.get("basic_info") or {}).get("name")
        fid = fun.get("funder_id")
        if name and fid:
            funder_name_to_id[_norm(name)] = fid

    experts_docs = [
        _transform_expert(x, resolve_field=resolve_field, resolve_industry=resolve_industry, resolve_skill=resolve_skill, funder_name_to_id=funder_name_to_id)
        for x in (old_data.get("experts", []) or [])
    ]
    enterprises_docs = [
        _transform_enterprise(
            x,
            resolve_field=resolve_field,
            resolve_industry=resolve_industry,
            resolve_skill=resolve_skill,
        )
        for x in (old_data.get("enterprises", []) or [])
    ]
    projects_docs = [_transform_project(x, resolve_field=resolve_field, resolve_skill=resolve_skill, resolve_industry=resolve_industry) for x in (old_data.get("projects", []) or [])]
    funders_docs = [_transform_funder(x, resolve_field=resolve_field, resolve_industry=resolve_industry) for x in funders_old]

    return {
        "experts": experts_docs,
        "enterprises": enterprises_docs,
        "projects": projects_docs,
        "funders": funders_docs,
        "products": products_docs,
        "datasets": datasets_docs,
    }


def _insert_many_in_batches(collection, items, batch_size, collection_name):
    inserted = 0
    total = len(items)
    for start in range(0, total, batch_size):
        batch = items[start:start + batch_size]
        if not batch:
            continue
        result = collection.insert_many(batch, ordered=False)
        inserted += len(result.inserted_ids)
        print(f"  {collection_name}: inserted {inserted}/{total}", flush=True)
    return inserted


def _bulk_write_batch(collection, ops, collection_name, total_ops, done_ops):
    result = collection.bulk_write(ops, ordered=False)
    done_ops += len(ops)
    print(f"  {collection_name}: synced {done_ops}/{total_ops}", flush=True)
    return result.matched_count, result.modified_count, result.upserted_count, done_ops


def import_to_mongodb(data_file=None, force=False, source="data1", data_dir=None, limit_per_collection=0, dry_run=False, batch_size=DEFAULT_MONGO_BATCH_SIZE, resume=False):
    if source == "data1":
        old_data = load_data1_seed_data(data_dir=data_dir, limit_per_collection=limit_per_collection)
    else:
        old_data = load_seed_data(data_file)
    new_data = convert_seed_data(old_data)

    if dry_run:
        print("Dry run only. MongoDB will not be modified.")
        for collection_name in MERGED_COLLECTIONS:
            print(f"  {collection_name}: {len(new_data.get(collection_name, []))}")
        return

    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    print(f"Connected to MongoDB database: {DB_NAME}")
    batch_size = max(1, int(batch_size or DEFAULT_MONGO_BATCH_SIZE))
    print(f"MongoDB write batch size: {batch_size}")
    if resume:
        print("Resume mode: skip documents whose IDs already exist in MongoDB")

    for collection_name in MERGED_COLLECTIONS:
        items = new_data.get(collection_name, [])
        collection = db[collection_name]
        count_before = collection.count_documents({})
        id_key = COLLECTION_ID_KEYS.get(collection_name)
        if force and count_before > 0:
            collection.delete_many({})
            count_before = 0
        if count_before == 0:
            if items:
                _insert_many_in_batches(collection, items, batch_size, collection_name)
                print(f"Inserted {len(items)} documents into {collection_name}")
            else:
                print(f"  [SKIP] '{collection_name}' rỗng, không insert.")
        else:
            if not items:
                print(f"  [SKIP] '{collection_name}' rỗng, không cập nhật.")
                continue

            # Mặc định đồng bộ theo ID để dễ cập nhật khi chỉnh seed_data.txt.
            existing_ids = set()
            if resume and id_key:
                print(f"  {collection_name}: loading existing {id_key} values for resume...", flush=True)
                existing_ids = {str(value) for value in collection.distinct(id_key) if value}
                print(f"  {collection_name}: resume will skip {len(existing_ids)} existing documents", flush=True)

            ops = []
            fallback_inserts = []
            matched = modified = upserted = inserted = skipped_existing = done_ops = 0
            total_ops = sum(
                1
                for item in items
                if isinstance(item, dict)
                and not (
                    resume
                    and id_key
                    and item.get(id_key)
                    and str(item.get(id_key)) in existing_ids
                )
            )
            for item in items:
                if not isinstance(item, dict):
                    continue
                item_id = item.get(id_key) if id_key else None
                if item_id:
                    if resume and str(item_id) in existing_ids:
                        skipped_existing += 1
                        continue
                    ops.append(ReplaceOne({id_key: item_id}, item, upsert=True))
                    if len(ops) >= batch_size:
                        batch_matched, batch_modified, batch_upserted, done_ops = _bulk_write_batch(
                            collection, ops, collection_name, total_ops, done_ops
                        )
                        matched += batch_matched
                        modified += batch_modified
                        upserted += batch_upserted
                        ops = []
                else:
                    fallback_inserts.append(item)
                    if len(fallback_inserts) >= batch_size:
                        inserted += _insert_many_in_batches(collection, fallback_inserts, batch_size, collection_name)
                        done_ops += len(fallback_inserts)
                        fallback_inserts = []

            if ops:
                batch_matched, batch_modified, batch_upserted, done_ops = _bulk_write_batch(
                    collection, ops, collection_name, total_ops, done_ops
                )
                matched += batch_matched
                modified += batch_modified
                upserted += batch_upserted
            if fallback_inserts:
                inserted += _insert_many_in_batches(collection, fallback_inserts, batch_size, collection_name)
                done_ops += len(fallback_inserts)

            print(
                f"Synced {collection_name}: matched={matched}, modified={modified}, "
                f"upserted={upserted}, inserted_without_id={inserted}, skipped_existing={skipped_existing}"
            )

    print("\nSeed data import completed successfully.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Import seed data vào MongoDB")
    parser.add_argument(
        "--source",
        choices=["file", "data1"],
        default="data1",
        help="Nguồn dữ liệu: data1=JSONL trong add_data/data1/data, file=seed_data.txt JSON",
    )
    parser.add_argument("--file", "-f", default=None, help="Đường dẫn file dữ liệu JSON (mặc định: seed_data.txt)")
    parser.add_argument("--data-dir", default=None, help="Đường dẫn thư mục data1 hoặc data1/data")
    parser.add_argument(
        "--limit-per-collection",
        type=int,
        default=0,
        help="Giới hạn số bản ghi mỗi collection khi đọc data1; 0 nghĩa là không giới hạn",
    )
    parser.add_argument("--force", action="store_true", help="Xóa dữ liệu cũ và ghi đè toàn bộ bằng dữ liệu từ nguồn đã chọn")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ đọc/convert dữ liệu và in số lượng, không ghi MongoDB")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_MONGO_BATCH_SIZE,
        help="MongoDB write batch size; default from SEED_MONGO_BATCH_SIZE or 1000",
    )
    parser.add_argument("--resume", action="store_true", help="Skip documents whose IDs already exist in MongoDB")
    args = parser.parse_args()
    import_to_mongodb(
        data_file=args.file,
        force=args.force,
        source=args.source,
        data_dir=args.data_dir,
        limit_per_collection=args.limit_per_collection,
        dry_run=args.dry_run,
        batch_size=args.batch_size,
        resume=args.resume,
    )
