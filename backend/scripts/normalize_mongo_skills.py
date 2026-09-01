"""Rewrite skill fields in existing MongoDB documents to canonical form.

Dry-run (default):

    cd backend
    python scripts/normalize_mongo_skills.py

Apply updates:

    python scripts/normalize_mongo_skills.py --apply

Limit to one collection:

    python scripts/normalize_mongo_skills.py --apply --only experts
"""
from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
ADD_DATA = ROOT.parent / "add_data"
for path in (ROOT, ADD_DATA):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from repositories.auth_repo import AuthRepository  # noqa: E402
from utils.skill_identity_utils import (  # noqa: E402
    build_skill_taxonomy_maps,
    dedupe_skill_names,
    normalize_skill_dict,
    normalize_skill_key,
    resolve_skill_record,
)

OUT = Path(__file__).resolve().parent / "normalize_mongo_skills_report.json"


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value) if value.__class__.__name__ == "ObjectId" else value


def _skill_maps(repo: AuthRepository) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str], Dict[str, str]]:
    methods = list(repo.db.method_techniques.find({}))
    return build_skill_taxonomy_maps(methods)


def _normalize_skill_objects(
    items: Any,
    *,
    skill_map: Dict[str, Dict[str, Any]],
    by_compact: Dict[str, str],
    by_norm_key: Dict[str, str],
) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        return []
    normalized: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        if isinstance(item, dict):
            record = normalize_skill_dict(
                item,
                skill_map=skill_map,
                by_compact=by_compact,
                by_norm_key=by_norm_key,
            )
        elif item:
            resolved = resolve_skill_record(
                str(item),
                skill_map=skill_map,
                by_compact=by_compact,
                by_norm_key=by_norm_key,
            )
            record = {
                "skill_id": resolved.get("skill_id"),
                "name": resolved.get("name"),
                "category": resolved.get("category") or "unknown",
            }
        else:
            continue
        if not record or not record.get("name"):
            continue
        key = normalize_skill_key(record["name"])
        if key in seen:
            continue
        seen.add(key)
        entry = {
            "skill_id": record.get("skill_id"),
            "name": record.get("name"),
            "category": record.get("category") or "unknown",
        }
        level = item.get("proficiency_level") or item.get("level") if isinstance(item, dict) else None
        if level:
            entry["proficiency_level"] = level
        normalized.append(entry)
    return normalized


def _normalize_string_skill_list(
    names: Any,
    *,
    skill_map: Dict[str, Dict[str, Any]],
    by_compact: Dict[str, str],
    by_norm_key: Dict[str, str],
    category: Optional[str] = None,
) -> List[str]:
    if not isinstance(names, list):
        return []
    return dedupe_skill_names(
        names,
        skill_map=skill_map,
        by_compact=by_compact,
        by_norm_key=by_norm_key,
        category=category,
    )


def _changed(before: Any, after: Any) -> bool:
    return json.dumps(json_safe(before), sort_keys=True) != json.dumps(json_safe(after), sort_keys=True)


def migrate_experts(
    repo: AuthRepository,
    *,
    skill_map: Dict[str, Dict[str, Any]],
    by_compact: Dict[str, str],
    by_norm_key: Dict[str, str],
    apply: bool,
) -> Dict[str, Any]:
    scanned = 0
    changed = 0
    updated = 0
    examples: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for doc in repo.experts.find({}):
        scanned += 1
        rc = deepcopy(doc.get("research_capacity") or {})
        before_rc = deepcopy(rc)

        skills_methods = _normalize_skill_objects(
            rc.get("skills_methods"),
            skill_map=skill_map,
            by_compact=by_compact,
            by_norm_key=by_norm_key,
        )
        technology = _normalize_string_skill_list(
            rc.get("technology"),
            skill_map=skill_map,
            by_compact=by_compact,
            by_norm_key=by_norm_key,
        )

        rc["skills_methods"] = skills_methods
        rc["technology"] = technology

        if not _changed(before_rc, rc):
            continue

        changed += 1
        entity_id = str(doc.get("expert_id") or doc.get("_id"))
        if len(examples) < 15:
            examples.append(
                {
                    "entity_id": entity_id,
                    "before": {
                        "skills_methods": before_rc.get("skills_methods"),
                        "technology": before_rc.get("technology"),
                    },
                    "after": {
                        "skills_methods": skills_methods,
                        "technology": technology,
                    },
                }
            )

        if apply:
            repo.experts.update_one(
                {"_id": doc["_id"]},
                {"$set": {"research_capacity": rc, "updated_at": now}},
            )
            updated += 1

    return {
        "collection": "experts",
        "scanned": scanned,
        "documents_changed": changed,
        "documents_updated": updated,
        "examples": examples,
    }


def migrate_projects(
    repo: AuthRepository,
    *,
    skill_map: Dict[str, Dict[str, Any]],
    by_compact: Dict[str, str],
    by_norm_key: Dict[str, str],
    apply: bool,
) -> Dict[str, Any]:
    scanned = 0
    changed = 0
    updated = 0
    examples: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for doc in repo.projects.find({}):
        scanned += 1
        req = deepcopy(doc.get("requirements_and_timeline") or {})
        before_skills = deepcopy(req.get("required_skills"))
        required_skills = _normalize_skill_objects(
            req.get("required_skills"),
            skill_map=skill_map,
            by_compact=by_compact,
            by_norm_key=by_norm_key,
        )
        if not _changed(before_skills, required_skills):
            continue

        changed += 1
        req["required_skills"] = required_skills
        entity_id = str(doc.get("project_id") or doc.get("_id"))
        if len(examples) < 15:
            examples.append(
                {
                    "entity_id": entity_id,
                    "before": before_skills,
                    "after": required_skills,
                }
            )

        if apply:
            repo.projects.update_one(
                {"_id": doc["_id"]},
                {"$set": {"requirements_and_timeline": req, "updated_at": now}},
            )
            updated += 1

    return {
        "collection": "projects",
        "scanned": scanned,
        "documents_changed": changed,
        "documents_updated": updated,
        "examples": examples,
    }


def migrate_enterprises(
    repo: AuthRepository,
    *,
    skill_map: Dict[str, Dict[str, Any]],
    by_compact: Dict[str, str],
    by_norm_key: Dict[str, str],
    apply: bool,
) -> Dict[str, Any]:
    scanned = 0
    changed = 0
    updated = 0
    examples: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for doc in repo.enterprises.find({}):
        scanned += 1
        rd = deepcopy(doc.get("rd_profile") or {})
        before_needs = deepcopy(rd.get("technology_needs"))
        technology_needs = []
        needs_changed = False

        for need in rd.get("technology_needs") or []:
            if not isinstance(need, dict):
                technology_needs.append(need)
                continue
            normalized_need = deepcopy(need)
            before_skills = need.get("required_skills")
            normalized_need["required_skills"] = _normalize_skill_objects(
                need.get("required_skills"),
                skill_map=skill_map,
                by_compact=by_compact,
                by_norm_key=by_norm_key,
            )
            if _changed(before_skills, normalized_need["required_skills"]):
                needs_changed = True
            technology_needs.append(normalized_need)

        if not needs_changed:
            continue

        changed += 1
        rd["technology_needs"] = technology_needs
        entity_id = str(doc.get("enterprise_id") or doc.get("_id"))
        if len(examples) < 15:
            examples.append(
                {
                    "entity_id": entity_id,
                    "before": before_needs,
                    "after": technology_needs,
                }
            )

        if apply:
            repo.enterprises.update_one(
                {"_id": doc["_id"]},
                {"$set": {"rd_profile": rd, "updated_at": now}},
            )
            updated += 1

    return {
        "collection": "enterprises",
        "scanned": scanned,
        "documents_changed": changed,
        "documents_updated": updated,
        "examples": examples,
    }


def migrate_app_users(repo: AuthRepository, *, apply: bool) -> Dict[str, Any]:
    scanned = 0
    changed = 0
    updated = 0
    examples: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for doc in repo.users.find({}):
        scanned += 1
        before_skills = list(doc.get("skills") or [])
        before_custom = list(doc.get("custom_skills") or [])
        skills = repo.normalize_skill_name_list(before_skills)
        custom_skills = repo.normalize_skill_name_list(before_custom, category="custom")
        if not _changed(before_skills, skills) and not _changed(before_custom, custom_skills):
            continue

        changed += 1
        entity_id = str(doc.get("_id"))
        if len(examples) < 15:
            examples.append(
                {
                    "entity_id": entity_id,
                    "before": {"skills": before_skills, "custom_skills": before_custom},
                    "after": {"skills": skills, "custom_skills": custom_skills},
                }
            )

        if apply:
            repo.users.update_one(
                {"_id": doc["_id"]},
                {
                    "$set": {
                        "skills": skills,
                        "custom_skills": custom_skills,
                        "updated_at": now,
                    }
                },
            )
            updated += 1

    return {
        "collection": "app_users",
        "scanned": scanned,
        "documents_changed": changed,
        "documents_updated": updated,
        "examples": examples,
    }


def migrate_method_techniques(
    repo: AuthRepository,
    *,
    skill_map: Dict[str, Dict[str, Any]],
    by_compact: Dict[str, str],
    by_norm_key: Dict[str, str],
    apply: bool,
) -> Dict[str, Any]:
    scanned = 0
    changed = 0
    updated = 0
    examples: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for doc in repo.db.method_techniques.find({}):
        scanned += 1
        tech_id = str(doc.get("tech_id") or doc.get("skill_id") or "").strip()
        before_name = doc.get("name")
        resolved = resolve_skill_record(
            before_name,
            skill_map=skill_map,
            by_compact=by_compact,
            by_norm_key=by_norm_key,
            category=doc.get("category"),
        )
        after_name = resolved.get("name")
        after_id = resolved.get("skill_id")
        if not after_name:
            continue
        if before_name == after_name and (not tech_id or tech_id == after_id):
            continue

        changed += 1
        if len(examples) < 15:
            examples.append(
                {
                    "entity_id": tech_id or str(doc.get("_id")),
                    "before": {"tech_id": tech_id, "name": before_name},
                    "after": {"tech_id": after_id, "name": after_name},
                }
            )

        if apply:
            payload = {
                "name": after_name,
                "updated_at": now,
            }
            if after_id and not tech_id:
                payload["tech_id"] = after_id
            repo.db.method_techniques.update_one({"_id": doc["_id"]}, {"$set": payload})
            updated += 1

    return {
        "collection": "method_techniques",
        "scanned": scanned,
        "documents_changed": changed,
        "documents_updated": updated,
        "examples": examples,
    }


COLLECTION_HANDLERS = {
    "experts": "experts",
    "projects": "projects",
    "enterprises": "enterprises",
    "app_users": "app_users",
    "method_techniques": "method_techniques",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize skill fields in existing MongoDB documents.")
    parser.add_argument("--apply", action="store_true", help="Apply updates. Default is dry-run.")
    parser.add_argument(
        "--only",
        choices=sorted(COLLECTION_HANDLERS.keys()),
        action="append",
        help="Limit migration to specific collection(s). Repeatable.",
    )
    parser.add_argument(
        "--output",
        default=str(OUT),
        help="Where to write the JSON report.",
    )
    args = parser.parse_args()

    repo = AuthRepository()
    skill_map, by_compact, by_norm_key = _skill_maps(repo)
    selected = args.only or sorted(COLLECTION_HANDLERS.keys())

    report: Dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "apply": bool(args.apply),
        "taxonomy_size": len(skill_map),
        "collections": [],
    }

    for collection in selected:
        if collection == "experts":
            result = migrate_experts(
                repo,
                skill_map=skill_map,
                by_compact=by_compact,
                by_norm_key=by_norm_key,
                apply=bool(args.apply),
            )
        elif collection == "projects":
            result = migrate_projects(
                repo,
                skill_map=skill_map,
                by_compact=by_compact,
                by_norm_key=by_norm_key,
                apply=bool(args.apply),
            )
        elif collection == "enterprises":
            result = migrate_enterprises(
                repo,
                skill_map=skill_map,
                by_compact=by_compact,
                by_norm_key=by_norm_key,
                apply=bool(args.apply),
            )
        elif collection == "app_users":
            result = migrate_app_users(repo, apply=bool(args.apply))
        elif collection == "method_techniques":
            result = migrate_method_techniques(
                repo,
                skill_map=skill_map,
                by_compact=by_compact,
                by_norm_key=by_norm_key,
                apply=bool(args.apply),
            )
        else:
            continue
        report["collections"].append(result)

    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["summary"] = {
        "scanned": sum(item["scanned"] for item in report["collections"]),
        "documents_changed": sum(item["documents_changed"] for item in report["collections"]),
        "documents_updated": sum(item["documents_updated"] for item in report["collections"]),
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(json_safe(report), ensure_ascii=False, indent=2), encoding="utf-8")

    summary = report["summary"]
    print(f"written {output_path.name}")
    print(
        "apply={apply} scanned={scanned} changed={changed} updated={updated}".format(
            apply=args.apply,
            scanned=summary["scanned"],
            changed=summary["documents_changed"],
            updated=summary["documents_updated"],
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
