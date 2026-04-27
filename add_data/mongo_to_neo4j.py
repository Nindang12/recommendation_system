from collections import defaultdict
from datetime import datetime
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from neo4j import GraphDatabase
from pymongo import MongoClient

load_dotenv()

SCRIPT_DIR = Path(__file__).resolve().parent
LOGS_DIR = SCRIPT_DIR / "logs"


def setup_logging():
    LOGS_DIR.mkdir(exist_ok=True)
    log_file = LOGS_DIR / f"sync_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
        force=True,
    )
    return logging.getLogger(__name__)


logger = setup_logging()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "rd_recommendation_system")
mongo_client = MongoClient(MONGO_URI)
mdb = mongo_client[MONGO_DB_NAME]

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


class SyncStats:
    def __init__(self):
        self.stats = defaultdict(lambda: {"success": 0, "failed": 0, "skipped": 0})
        self.errors = defaultdict(list)

    def record_success(self, entity_type: str):
        self.stats[entity_type]["success"] += 1

    def record_failure(self, entity_type: str, entity_id: str, error: Exception):
        self.stats[entity_type]["failed"] += 1
        self.errors[entity_type].append({"id": entity_id, "error": str(error)})

    def record_skip(self, entity_type: str, reason: str):
        self.stats[entity_type]["skipped"] += 1
        logger.debug("Skip %s: %s", entity_type, reason)

    def print_summary(self):
        logger.info("\n" + "=" * 60)
        logger.info("SYNC SUMMARY")
        logger.info("=" * 60)
        for entity_type, counts in self.stats.items():
            total = counts["success"] + counts["failed"] + counts["skipped"]
            logger.info("\n%s:", entity_type)
            logger.info("  Total: %s", total)
            logger.info("  [OK] Success: %s", counts["success"])
            logger.info("  [FAIL] Failed: %s", counts["failed"])
            logger.info("  [SKIP] Skipped: %s", counts["skipped"])
            if self.errors[entity_type]:
                logger.info("  Errors (%s):", len(self.errors[entity_type]))
                for err in self.errors[entity_type][:5]:
                    logger.info("    - %s: %s", err["id"], err["error"])
                if len(self.errors[entity_type]) > 5:
                    logger.info("    ... and %s more", len(self.errors[entity_type]) - 5)
        logger.info("=" * 60)


stats = SyncStats()


def clean_params(**params) -> Dict[str, Any]:
    cleaned: Dict[str, Any] = {}
    for key, value in params.items():
        cleaned[key] = None if isinstance(value, list) and len(value) == 0 else value
    return cleaned


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"[^a-zA-Z0-9]+", "_", str(value).strip()).strip("_").lower()


def make_key(prefix: str, value: Any) -> Optional[str]:
    norm = normalize_text(value)
    return f"{prefix}_{norm}" if norm else None


def make_location_id(location: Dict[str, Any]) -> Optional[str]:
    if not isinstance(location, dict):
        return None
    cc = (location.get("country_code") or "").strip()
    region = (location.get("region") or location.get("city") or "").strip()
    if not cc and not region:
        return None
    return f"{cc}-{region}" if region else cc


def skill_ref(skill_obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(skill_obj, dict):
        return None
    sid = skill_obj.get("skill_id") or make_key("skill", skill_obj.get("name"))
    if not sid:
        return None
    return {"skill_id": sid, "name": skill_obj.get("name"), "category": skill_obj.get("category")}


def direction_ref(name: str) -> Optional[Dict[str, str]]:
    did = make_key("direction", name)
    if not did:
        return None
    return {"direction_id": did, "name": name}


def topic_ref(topic_obj: Dict[str, Any]) -> Optional[Dict[str, str]]:
    if not isinstance(topic_obj, dict):
        return None
    name = topic_obj.get("name")
    tid = topic_obj.get("topic_id") or make_key("topic", name)
    if not tid:
        return None
    return {"topic_id": tid, "name": name, "parent_direction": topic_obj.get("parent_direction")}


def industry_ref(ind_obj: Dict[str, Any]) -> Optional[Dict[str, str]]:
    if not isinstance(ind_obj, dict):
        return None
    code = ind_obj.get("code")
    iid = code or make_key("industry", ind_obj.get("name"))
    if not iid:
        return None
    return {"industry_id": iid, "code": code, "name": ind_obj.get("name")}


def create_neo4j_constraints_and_indexes(session):
    logger.info("Creating Neo4j constraints and indexes...")
    statements = [
        "CREATE CONSTRAINT expert_id_unique IF NOT EXISTS FOR (e:Expert) REQUIRE e.expert_id IS UNIQUE",
        "CREATE CONSTRAINT project_id_unique IF NOT EXISTS FOR (p:Project) REQUIRE p.project_id IS UNIQUE",
        "CREATE CONSTRAINT enterprise_id_unique IF NOT EXISTS FOR (e:Enterprise) REQUIRE e.enterprise_id IS UNIQUE",
        "CREATE CONSTRAINT funder_id_unique IF NOT EXISTS FOR (f:Funder) REQUIRE f.funder_id IS UNIQUE",
        "CREATE CONSTRAINT product_id_unique IF NOT EXISTS FOR (p:Product) REQUIRE p.product_id IS UNIQUE",
        "CREATE CONSTRAINT dataset_id_unique IF NOT EXISTS FOR (d:Dataset) REQUIRE d.dataset_id IS UNIQUE",
        "CREATE CONSTRAINT skill_id_unique IF NOT EXISTS FOR (s:Skill) REQUIRE s.skill_id IS UNIQUE",
        "CREATE CONSTRAINT direction_id_unique IF NOT EXISTS FOR (d:ResearchDirection) REQUIRE d.direction_id IS UNIQUE",
        "CREATE CONSTRAINT topic_id_unique IF NOT EXISTS FOR (t:ResearchTopic) REQUIRE t.topic_id IS UNIQUE",
        "CREATE CONSTRAINT industry_id_unique IF NOT EXISTS FOR (i:Industry) REQUIRE i.industry_id IS UNIQUE",
        "CREATE CONSTRAINT location_id_unique IF NOT EXISTS FOR (l:Location) REQUIRE l.location_id IS UNIQUE",
        "CREATE INDEX expert_name IF NOT EXISTS FOR (e:Expert) ON (e.name)",
        "CREATE INDEX project_title IF NOT EXISTS FOR (p:Project) ON (p.title)",
        "CREATE INDEX enterprise_name IF NOT EXISTS FOR (e:Enterprise) ON (e.name)",
        "CREATE INDEX funder_name IF NOT EXISTS FOR (f:Funder) ON (f.name)",
        "CREATE INDEX skill_name IF NOT EXISTS FOR (s:Skill) ON (s.name)",
        "CREATE INDEX direction_name IF NOT EXISTS FOR (d:ResearchDirection) ON (d.name)",
        "CREATE INDEX topic_name IF NOT EXISTS FOR (t:ResearchTopic) ON (t.name)",
    ]
    for statement in statements:
        try:
            session.run(statement)
        except Exception as ex:
            logger.warning("Constraint/index error: %s", ex)


def merge_location(session, location: Dict[str, Any]) -> Optional[str]:
    location_id = make_location_id(location)
    if not location_id:
        return None
    session.run(
        """
        MERGE (l:Location {location_id: $location_id})
        SET l.country_code = $country_code,
            l.country_name = $country_name,
            l.region = $region,
            l.city = $city,
            l.updated_at = datetime()
        """,
        location_id=location_id,
        country_code=location.get("country_code"),
        country_name=location.get("country_name"),
        region=location.get("region"),
        city=location.get("city"),
    )
    return location_id


def sync_products(session):
    logger.info("Syncing Products...")
    products = list(mdb.products.find({}))
    for pr in products:
        product_id = pr.get("product_id")
        if not product_id:
            stats.record_skip("Product", "Missing product_id")
            continue
        try:
            dev_ids = pr.get("developer_ids") or pr.get("developed_by") or []
            session.run(
                """
                MERGE (o:Product {product_id: $product_id})
                SET o.name = $name, o.type = $type, o.trl = $trl, o.year = $year,
                    o.linked_project_id = $linked_project_id, o.license = $license,
                    o.access_url = $access_url, o.developer_ids = $developer_ids,
                    o.updated_at = datetime()
                """,
                **clean_params(
                    product_id=product_id,
                    name=pr.get("name"),
                    type=pr.get("type"),
                    trl=pr.get("trl"),
                    year=pr.get("year"),
                    linked_project_id=pr.get("linked_project_id"),
                    license=pr.get("license"),
                    access_url=pr.get("access_url"),
                    developer_ids=dev_ids,
                ),
            )
            stats.record_success("Product")
        except Exception as ex:
            stats.record_failure("Product", product_id, ex)


def sync_datasets(session):
    logger.info("Syncing Datasets...")
    datasets = list(mdb.datasets.find({}))
    for ds in datasets:
        dataset_id = ds.get("dataset_id")
        if not dataset_id:
            stats.record_skip("Dataset", "Missing dataset_id")
            continue
        try:
            owner_ids = ds.get("owner_ids")
            if owner_ids is None:
                owner_single = ds.get("owner_expert_id")
                owner_ids = [owner_single] if owner_single else []
            session.run(
                """
                MERGE (d:Dataset {dataset_id: $dataset_id})
                SET d.name = $name, d.description = $description, d.type = $type,
                    d.trl = $trl, d.year = $year, d.linked_project_id = $linked_project_id,
                    d.license = $license, d.access_url = $access_url, d.owner_ids = $owner_ids,
                    d.size_mb = $size_mb, d.domain_tags = $domain_tags, d.updated_at = datetime()
                """,
                **clean_params(
                    dataset_id=dataset_id,
                    name=ds.get("name"),
                    description=ds.get("description"),
                    type=ds.get("type") or ds.get("format"),
                    trl=ds.get("trl"),
                    year=ds.get("year"),
                    linked_project_id=ds.get("linked_project_id"),
                    license=ds.get("license"),
                    access_url=ds.get("access_url"),
                    owner_ids=owner_ids,
                    size_mb=ds.get("size_mb"),
                    domain_tags=ds.get("domain_tags"),
                ),
            )
            stats.record_success("Dataset")
        except Exception as ex:
            stats.record_failure("Dataset", dataset_id, ex)


def sync_experts(session):
    logger.info("Syncing Experts...")
    experts = list(mdb.experts.find({}))
    for ex in experts:
        expert_id = ex.get("expert_id")
        if not expert_id:
            stats.record_skip("Expert", "Missing expert_id")
            continue
        try:
            basic = ex.get("basic_info") or {}
            location = basic.get("location") or {}
            location_id = merge_location(session, location)
            metrics = (ex.get("research_capacity") or {}).get("academic_metrics") or {}
            session.run(
                """
                MERGE (e:Expert {expert_id: $expert_id})
                SET e.name = $name, e.birth_year = $birth_year, e.gender = $gender,
                    e.location_id = $location_id, e.location_country_code = $location_country_code,
                    e.location_region = $location_region, e.location_city = $location_city,
                    e.nationality = $nationality, e.preferred_language = $preferred_language,
                    e.publication_count = $publication_count, e.h_index = $h_index,
                    e.citation_count = $citation_count, e.i10_index = $i10_index,
                    e.altmetrics = $altmetrics, e.updated_at = datetime()
                """,
                **clean_params(
                    expert_id=expert_id,
                    name=basic.get("name"),
                    birth_year=basic.get("birth_year"),
                    gender=basic.get("gender"),
                    location_id=location_id,
                    location_country_code=location.get("country_code"),
                    location_region=location.get("region"),
                    location_city=location.get("city"),
                    nationality=basic.get("nationality"),
                    preferred_language=basic.get("preferred_language"),
                    publication_count=metrics.get("publication_count"),
                    h_index=metrics.get("h_index"),
                    citation_count=metrics.get("citation_count"),
                    i10_index=metrics.get("i10_index"),
                    altmetrics=metrics.get("altmetrics"),
                ),
            )
            if location_id:
                session.run(
                    """
                    MATCH (e:Expert {expert_id: $expert_id})
                    MATCH (l:Location {location_id: $location_id})
                    MERGE (e)-[:LOCATED_IN]->(l)
                    """,
                    expert_id=expert_id,
                    location_id=location_id,
                )

            rc = ex.get("research_capacity") or {}
            for sm in rc.get("skills_methods") or []:
                ref = skill_ref(sm if isinstance(sm, dict) else {})
                if not ref:
                    continue
                session.run(
                    """
                    MERGE (s:Skill {skill_id: $skill_id})
                    SET s.name = $name, s.category = $category, s.updated_at = datetime()
                    """,
                    **ref,
                )
                session.run(
                    """
                    MATCH (e:Expert {expert_id: $expert_id})
                    MATCH (s:Skill {skill_id: $skill_id})
                    MERGE (e)-[r:HAS_SKILL]->(s)
                    SET r.proficiency_level = $level
                    """,
                    expert_id=expert_id,
                    skill_id=ref["skill_id"],
                    level=sm.get("proficiency_level") if isinstance(sm, dict) else None,
                )

            for dname in rc.get("research_directions") or []:
                dref = direction_ref(dname)
                if not dref:
                    continue
                session.run("MERGE (d:ResearchDirection {direction_id: $direction_id}) SET d.name = $name, d.updated_at = datetime()", **dref)
                session.run(
                    """
                    MATCH (e:Expert {expert_id: $expert_id})
                    MATCH (d:ResearchDirection {direction_id: $direction_id})
                    MERGE (e)-[:RESEARCHES]->(d)
                    """,
                    expert_id=expert_id,
                    direction_id=dref["direction_id"],
                )

            for topic in rc.get("research_topics") or []:
                tref = topic_ref(topic if isinstance(topic, dict) else {})
                if not tref:
                    continue
                session.run(
                    "MERGE (t:ResearchTopic {topic_id: $topic_id}) SET t.name = $name, t.updated_at = datetime()",
                    topic_id=tref["topic_id"],
                    name=tref.get("name"),
                )
                session.run(
                    """
                    MATCH (e:Expert {expert_id: $expert_id})
                    MATCH (t:ResearchTopic {topic_id: $topic_id})
                    MERGE (e)-[:HAS_EXPERIENCE_IN]->(t)
                    """,
                    expert_id=expert_id,
                    topic_id=tref["topic_id"],
                )

            for ind in rc.get("applied_industries") or []:
                iref = industry_ref(ind if isinstance(ind, dict) else {})
                if not iref:
                    continue
                session.run(
                    """
                    MERGE (i:Industry {industry_id: $industry_id})
                    SET i.code = $code, i.name = $name, i.updated_at = datetime()
                    """,
                    **iref,
                )
                session.run(
                    """
                    MATCH (e:Expert {expert_id: $expert_id})
                    MATCH (i:Industry {industry_id: $industry_id})
                    MERGE (e)-[:HAS_APPLICATION_EXPERIENCE_IN]->(i)
                    """,
                    expert_id=expert_id,
                    industry_id=iref["industry_id"],
                )

            aao = ex.get("activities_and_outputs") or {}
            for ds_id in aao.get("owned_dataset_ids") or []:
                session.run(
                    """
                    MATCH (e:Expert {expert_id: $expert_id})
                    MATCH (d:Dataset {dataset_id: $dataset_id})
                    MERGE (e)-[:OWNS_DATA]->(d)
                    """,
                    expert_id=expert_id,
                    dataset_id=ds_id,
                )
            for ds_id in aao.get("accessible_dataset_ids") or []:
                session.run(
                    """
                    MATCH (e:Expert {expert_id: $expert_id})
                    MATCH (d:Dataset {dataset_id: $dataset_id})
                    MERGE (e)-[:HAS_ACCESS_TO]->(d)
                    """,
                    expert_id=expert_id,
                    dataset_id=ds_id,
                )
            for out in aao.get("list_outputs") or []:
                if isinstance(out, dict) and out.get("product_id"):
                    session.run(
                        """
                        MATCH (e:Expert {expert_id: $expert_id})
                        MATCH (o:Product {product_id: $product_id})
                        MERGE (e)-[:DEVELOPS]->(o)
                        """,
                        expert_id=expert_id,
                        product_id=out["product_id"],
                    )
            for part in aao.get("projects_participation") or []:
                if isinstance(part, dict) and part.get("project_id"):
                    session.run(
                        """
                        MATCH (e:Expert {expert_id: $expert_id})
                        MATCH (p:Project {project_id: $project_id})
                        MERGE (e)-[r:PARTICIPATES_IN]->(p)
                        SET r.role = $role, r.status = $status, r.duration = $duration
                        """,
                        expert_id=expert_id,
                        project_id=part.get("project_id"),
                        role=part.get("role"),
                        status=part.get("status"),
                        duration=part.get("duration"),
                    )

            stats.record_success("Expert")
        except Exception as ex_err:
            stats.record_failure("Expert", expert_id, ex_err)


def sync_enterprises(session):
    logger.info("Syncing Enterprises...")
    enterprises = list(mdb.enterprises.find({}))
    for ent in enterprises:
        enterprise_id = ent.get("enterprise_id")
        if not enterprise_id:
            stats.record_skip("Enterprise", "Missing enterprise_id")
            continue
        try:
            basic = ent.get("basic_info") or {}
            location = basic.get("location") or {}
            location_id = merge_location(session, location)
            org_metrics = basic.get("organization_metrics") or {}
            session.run(
                """
                MERGE (en:Enterprise {enterprise_id: $enterprise_id})
                SET en.name = $name, en.tax_code = $tax_code, en.founded_year = $founded_year,
                    en.location_id = $location_id, en.location_country_code = $location_country_code,
                    en.location_region = $location_region, en.location_city = $location_city,
                    en.size = $size, en.income = $income, en.employees = $employees,
                    en.updated_at = datetime()
                """,
                **clean_params(
                    enterprise_id=enterprise_id,
                    name=basic.get("name"),
                    tax_code=basic.get("tax_code"),
                    founded_year=basic.get("founded_year"),
                    location_id=location_id,
                    location_country_code=location.get("country_code"),
                    location_region=location.get("region"),
                    location_city=location.get("city"),
                    size=org_metrics.get("size"),
                    income=org_metrics.get("income"),
                    employees=org_metrics.get("employees"),
                ),
            )
            if location_id:
                session.run(
                    """
                    MATCH (en:Enterprise {enterprise_id: $enterprise_id})
                    MATCH (l:Location {location_id: $location_id})
                    MERGE (en)-[:LOCATED_IN]->(l)
                    """,
                    enterprise_id=enterprise_id,
                    location_id=location_id,
                )

            for ind in basic.get("industries") or []:
                iref = industry_ref(ind if isinstance(ind, dict) else {})
                if not iref:
                    continue
                session.run(
                    "MERGE (i:Industry {industry_id: $industry_id}) SET i.code = $code, i.name = $name, i.updated_at = datetime()",
                    **iref,
                )
                session.run(
                    """
                    MATCH (en:Enterprise {enterprise_id: $enterprise_id})
                    MATCH (i:Industry {industry_id: $industry_id})
                    MERGE (en)-[:OPERATES_IN]->(i)
                    """,
                    enterprise_id=enterprise_id,
                    industry_id=iref["industry_id"],
                )

            rd = ent.get("rd_profile") or {}
            for dname in rd.get("rd_focus_directions") or []:
                dref = direction_ref(dname)
                if not dref:
                    continue
                session.run("MERGE (d:ResearchDirection {direction_id: $direction_id}) SET d.name = $name, d.updated_at = datetime()", **dref)
                session.run(
                    """
                    MATCH (en:Enterprise {enterprise_id: $enterprise_id})
                    MATCH (d:ResearchDirection {direction_id: $direction_id})
                    MERGE (en)-[:FOCUSES_ON]->(d)
                    """,
                    enterprise_id=enterprise_id,
                    direction_id=dref["direction_id"],
                )
            for topic in rd.get("rd_focus_topics") or []:
                tref = topic_ref(topic if isinstance(topic, dict) else {})
                if not tref:
                    continue
                session.run("MERGE (t:ResearchTopic {topic_id: $topic_id}) SET t.name = $name, t.updated_at = datetime()", topic_id=tref["topic_id"], name=tref["name"])
                session.run(
                    """
                    MATCH (en:Enterprise {enterprise_id: $enterprise_id})
                    MATCH (t:ResearchTopic {topic_id: $topic_id})
                    MERGE (en)-[:FOCUSES_ON_TOPIC]->(t)
                    """,
                    enterprise_id=enterprise_id,
                    topic_id=tref["topic_id"],
                )
            for need in rd.get("technology_needs") or []:
                if not isinstance(need, dict):
                    continue
                for skill in need.get("required_skills") or []:
                    ref = skill_ref(skill if isinstance(skill, dict) else {})
                    if not ref:
                        continue
                    session.run("MERGE (s:Skill {skill_id: $skill_id}) SET s.name = $name, s.category = $category, s.updated_at = datetime()", **ref)
                    session.run(
                        """
                        MATCH (en:Enterprise {enterprise_id: $enterprise_id})
                        MATCH (s:Skill {skill_id: $skill_id})
                        MERGE (en)-[r:REQUIRES_SKILL]->(s)
                        SET r.need = $need, r.proficiency_level = $proficiency_level
                        """,
                        enterprise_id=enterprise_id,
                        skill_id=ref["skill_id"],
                        need=need.get("need"),
                        proficiency_level=skill.get("proficiency_level") if isinstance(skill, dict) else None,
                    )

            for worked in (ent.get("relations") or {}).get("worked_experts") or []:
                if isinstance(worked, dict) and worked.get("expert_id"):
                    session.run(
                        """
                        MATCH (e:Expert {expert_id: $expert_id})
                        MATCH (en:Enterprise {enterprise_id: $enterprise_id})
                        MERGE (e)-[:WORK_FOR]->(en)
                        """,
                        expert_id=worked["expert_id"],
                        enterprise_id=enterprise_id,
                    )
            stats.record_success("Enterprise")
        except Exception as ex_err:
            stats.record_failure("Enterprise", enterprise_id, ex_err)


def sync_funders(session):
    logger.info("Syncing Funders...")
    funders = list(mdb.funders.find({}))
    for fu in funders:
        funder_id = fu.get("funder_id")
        if not funder_id:
            stats.record_skip("Funder", "Missing funder_id")
            continue
        try:
            basic = fu.get("basic_info") or {}
            location = basic.get("location") or {}
            location_id = merge_location(session, location)
            session.run(
                """
                MERGE (f:Funder {funder_id: $funder_id})
                SET f.name = $name, f.type = $type, f.location_id = $location_id,
                    f.location_country_code = $location_country_code, f.location_region = $location_region,
                    f.location_city = $location_city, f.budget_capacity = $budget_capacity, f.updated_at = datetime()
                """,
                **clean_params(
                    funder_id=funder_id,
                    name=basic.get("name"),
                    type=basic.get("type"),
                    location_id=location_id,
                    location_country_code=location.get("country_code"),
                    location_region=location.get("region"),
                    location_city=location.get("city"),
                    budget_capacity=basic.get("budget_capacity"),
                ),
            )
            if location_id:
                session.run(
                    """
                    MATCH (f:Funder {funder_id: $funder_id})
                    MATCH (l:Location {location_id: $location_id})
                    MERGE (f)-[:LOCATED_IN]->(l)
                    """,
                    funder_id=funder_id,
                    location_id=location_id,
                )

            strategy = fu.get("funding_strategy") or {}
            for dname in strategy.get("funding_directions") or []:
                dref = direction_ref(dname)
                if not dref:
                    continue
                session.run("MERGE (d:ResearchDirection {direction_id: $direction_id}) SET d.name = $name, d.updated_at = datetime()", **dref)
                session.run(
                    """
                    MATCH (f:Funder {funder_id: $funder_id})
                    MATCH (d:ResearchDirection {direction_id: $direction_id})
                    MERGE (f)-[:SUPPORTS]->(d)
                    """,
                    funder_id=funder_id,
                    direction_id=dref["direction_id"],
                )
            for topic in strategy.get("funding_topics") or []:
                tref = topic_ref(topic if isinstance(topic, dict) else {})
                if not tref:
                    continue
                session.run("MERGE (t:ResearchTopic {topic_id: $topic_id}) SET t.name = $name, t.updated_at = datetime()", topic_id=tref["topic_id"], name=tref["name"])
                session.run(
                    """
                    MATCH (f:Funder {funder_id: $funder_id})
                    MATCH (t:ResearchTopic {topic_id: $topic_id})
                    MERGE (f)-[:SUPPORTS_TOPIC]->(t)
                    """,
                    funder_id=funder_id,
                    topic_id=tref["topic_id"],
                )
            for sector in strategy.get("focus_sectors") or []:
                iref = industry_ref(sector if isinstance(sector, dict) else {})
                if not iref:
                    continue
                session.run("MERGE (i:Industry {industry_id: $industry_id}) SET i.code = $code, i.name = $name, i.updated_at = datetime()", **iref)
                session.run(
                    """
                    MATCH (f:Funder {funder_id: $funder_id})
                    MATCH (i:Industry {industry_id: $industry_id})
                    MERGE (f)-[:FOCUSES_ON_SECTORS]->(i)
                    """,
                    funder_id=funder_id,
                    industry_id=iref["industry_id"],
                )

            for fp in ((fu.get("funding_history") or {}).get("funded_projects") or []):
                if isinstance(fp, dict) and fp.get("project_id"):
                    session.run(
                        """
                        MATCH (f:Funder {funder_id: $funder_id})
                        MATCH (p:Project {project_id: $project_id})
                        MERGE (f)-[r:FUNDS]->(p)
                        SET r.grant_amount = $grant_amount, r.year = $year, r.status = $status
                        """,
                        funder_id=funder_id,
                        project_id=fp.get("project_id"),
                        grant_amount=fp.get("grant_amount"),
                        year=fp.get("year"),
                        status=fp.get("status"),
                    )
            stats.record_success("Funder")
        except Exception as ex_err:
            stats.record_failure("Funder", funder_id, ex_err)


def sync_projects(session):
    logger.info("Syncing Projects...")
    projects = list(mdb.projects.find({}))
    for pr in projects:
        project_id = pr.get("project_id")
        if not project_id:
            stats.record_skip("Project", "Missing project_id")
            continue
        try:
            basic = pr.get("basic_info") or {}
            req = pr.get("requirements_and_timeline") or {}
            rel = pr.get("relations") or {}
            rd_profile = pr.get("rd_profile") or {}
            location = basic.get("location") or {}
            location_id = merge_location(session, location)
            session.run(
                """
                MERGE (p:Project {project_id: $project_id})
                SET p.title = $title, p.description = $description, p.status = $status,
                    p.location_id = $location_id, p.location_country_code = $location_country_code,
                    p.location_region = $location_region, p.location_city = $location_city,
                    p.keywords = $keywords, p.technology_readiness_level = $technology_readiness_level,
                    p.budget = $budget, p.updated_at = datetime()
                """,
                **clean_params(
                    project_id=project_id,
                    title=basic.get("title"),
                    description=basic.get("description"),
                    status=basic.get("status"),
                    location_id=location_id,
                    location_country_code=location.get("country_code"),
                    location_region=location.get("region"),
                    location_city=location.get("city"),
                    keywords=basic.get("keywords"),
                    technology_readiness_level=req.get("technology_readiness_level"),
                    budget=(req.get("budget") or {}).get("amount") if isinstance(req.get("budget"), dict) else req.get("budget"),
                ),
            )
            if location_id:
                session.run(
                    """
                    MATCH (p:Project {project_id: $project_id})
                    MATCH (l:Location {location_id: $location_id})
                    MERGE (p)-[:LOCATED_IN]->(l)
                    """,
                    project_id=project_id,
                    location_id=location_id,
                )

            for dname in basic.get("research_directions") or []:
                dref = direction_ref(dname)
                if not dref:
                    continue
                session.run("MERGE (d:ResearchDirection {direction_id: $direction_id}) SET d.name = $name, d.updated_at = datetime()", **dref)
                session.run(
                    """
                    MATCH (p:Project {project_id: $project_id})
                    MATCH (d:ResearchDirection {direction_id: $direction_id})
                    MERGE (p)-[:FOCUSES_ON]->(d)
                    """,
                    project_id=project_id,
                    direction_id=dref["direction_id"],
                )
            for topic in basic.get("research_topics") or []:
                tref = topic_ref(topic if isinstance(topic, dict) else {})
                if not tref:
                    continue
                session.run("MERGE (t:ResearchTopic {topic_id: $topic_id}) SET t.name = $name, t.updated_at = datetime()", topic_id=tref["topic_id"], name=tref["name"])
                session.run(
                    """
                    MATCH (p:Project {project_id: $project_id})
                    MATCH (t:ResearchTopic {topic_id: $topic_id})
                    MERGE (p)-[:FOCUSES_ON_TOPIC]->(t)
                    """,
                    project_id=project_id,
                    topic_id=tref["topic_id"],
                )
            for skill in req.get("required_skills") or []:
                ref = skill_ref(skill if isinstance(skill, dict) else {})
                if not ref:
                    continue
                session.run("MERGE (s:Skill {skill_id: $skill_id}) SET s.name = $name, s.category = $category, s.updated_at = datetime()", **ref)
                session.run(
                    """
                    MATCH (p:Project {project_id: $project_id})
                    MATCH (s:Skill {skill_id: $skill_id})
                    MERGE (p)-[r:REQUIRES_SKILL]->(s)
                    SET r.proficiency_level = $proficiency_level
                    """,
                    project_id=project_id,
                    skill_id=ref["skill_id"],
                    proficiency_level=skill.get("proficiency_level") if isinstance(skill, dict) else None,
                )
            for target in rel.get("target_industries") or []:
                iref = industry_ref(target if isinstance(target, dict) else {})
                if not iref:
                    continue
                session.run("MERGE (i:Industry {industry_id: $industry_id}) SET i.code = $code, i.name = $name, i.updated_at = datetime()", **iref)
                session.run(
                    """
                    MATCH (p:Project {project_id: $project_id})
                    MATCH (i:Industry {industry_id: $industry_id})
                    MERGE (p)-[:TARGETS]->(i)
                    """,
                    project_id=project_id,
                    industry_id=iref["industry_id"],
                )
            for ds_id in rd_profile.get("required_dataset_ids") or []:
                session.run(
                    """
                    MATCH (p:Project {project_id: $project_id})
                    MATCH (d:Dataset {dataset_id: $dataset_id})
                    MERGE (p)-[:REQUIRES_DATA]->(d)
                    """,
                    project_id=project_id,
                    dataset_id=ds_id,
                )
            for part in rel.get("participants") or []:
                if isinstance(part, dict) and part.get("expert_id"):
                    session.run(
                        """
                        MATCH (e:Expert {expert_id: $expert_id})
                        MATCH (p:Project {project_id: $project_id})
                        MERGE (e)-[r:PARTICIPATES_IN]->(p)
                        SET r.role = $role, r.period = $period
                        """,
                        expert_id=part.get("expert_id"),
                        project_id=project_id,
                        role=part.get("role"),
                        period=part.get("period"),
                    )
            for ep in rel.get("enterprise_partners") or []:
                if isinstance(ep, dict) and ep.get("enterprise_id"):
                    session.run(
                        """
                        MATCH (en:Enterprise {enterprise_id: $enterprise_id})
                        MATCH (p:Project {project_id: $project_id})
                        MERGE (en)-[r:PARTNERS_WITH]->(p)
                        SET r.type = $type
                        """,
                        enterprise_id=ep.get("enterprise_id"),
                        project_id=project_id,
                        type=ep.get("type"),
                    )
            for fund in rel.get("funders") or []:
                if isinstance(fund, dict) and fund.get("funder_id"):
                    session.run(
                        """
                        MATCH (f:Funder {funder_id: $funder_id})
                        MATCH (p:Project {project_id: $project_id})
                        MERGE (f)-[r:FUNDS]->(p)
                        SET r.grant_period = $grant_period, r.grant_amount = $grant_amount
                        """,
                        funder_id=fund.get("funder_id"),
                        project_id=project_id,
                        grant_period=fund.get("grant_period"),
                        grant_amount=fund.get("grant_amount"),
                    )
            stats.record_success("Project")
        except Exception as ex_err:
            stats.record_failure("Project", project_id, ex_err)


def sync_cross_entity_product_edges(session):
    logger.info("Syncing Product edges...")
    for pr in mdb.products.find({}):
        product_id = pr.get("product_id")
        if not product_id:
            continue
        linked_project_id = pr.get("linked_project_id")
        if linked_project_id:
            session.run(
                """
                MATCH (p:Project {project_id: $project_id})
                MATCH (o:Product {product_id: $product_id})
                MERGE (p)-[:CREATES]->(o)
                """,
                project_id=linked_project_id,
                product_id=product_id,
            )
        for eid in (pr.get("developer_ids") or pr.get("developed_by") or []):
            if not eid:
                continue
            session.run(
                """
                MATCH (e:Expert {expert_id: $expert_id})
                MATCH (o:Product {product_id: $product_id})
                MERGE (e)-[:DEVELOPS]->(o)
                """,
                expert_id=eid,
                product_id=product_id,
            )


def verify_sync(session):
    logger.info("\n" + "=" * 60)
    logger.info("VERIFICATION")
    logger.info("=" * 60)
    for record in session.run("MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count ORDER BY count DESC"):
        logger.info("  Node %-20s %s", record["label"], record["count"])
    for record in session.run("MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS count ORDER BY count DESC"):
        logger.info("  Rel  %-20s %s", record["type"], record["count"])
    logger.info("=" * 60)


def main(clear_graph: bool = False, skip_verify: bool = False, skip_indexes: bool = False):
    start_time = datetime.now()
    logger.info("=" * 60)
    logger.info("STARTING MONGODB -> NEO4J SYNC")
    logger.info("MongoDB: %s / %s", MONGO_URI, MONGO_DB_NAME)
    logger.info("Neo4j: %s", NEO4J_URI)
    logger.info("=" * 60)
    try:
        with driver.session() as session:
            if clear_graph:
                logger.warning("Clearing existing Neo4j graph...")
                session.run("MATCH (n) DETACH DELETE n")
            if not skip_indexes:
                create_neo4j_constraints_and_indexes(session)
            logger.info("PHASE 1: Assets")
            sync_datasets(session)
            sync_products(session)
            logger.info("PHASE 2: Main entities")
            sync_experts(session)
            sync_enterprises(session)
            sync_funders(session)
            sync_projects(session)
            logger.info("PHASE 3: Cross-entity edges")
            sync_cross_entity_product_edges(session)
            if not skip_verify:
                verify_sync(session)
    except Exception as ex:
        logger.error("Critical sync error: %s", ex, exc_info=True)
        raise
    finally:
        stats.print_summary()
        mongo_client.close()
        logger.info("SYNC COMPLETED in %s", datetime.now() - start_time)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Sync data from MongoDB to Neo4j (production pipeline).")
    parser.add_argument("--clear", action="store_true", help="Clear all Neo4j nodes/relationships before sync.")
    parser.add_argument("--skip-verify", action="store_true", help="Skip final verification summary.")
    parser.add_argument("--no-indexes", action="store_true", help="Do not create constraints/indexes.")
    args = parser.parse_args()
    main(clear_graph=args.clear, skip_verify=args.skip_verify, skip_indexes=args.no_indexes)

from neo4j import GraphDatabase
from pymongo import MongoClient
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from collections import defaultdict

load_dotenv()

# Neo4j sync bám mongodb_schema_full_v2.html (collection + field + gợi ý KG).
# Taxonomy: skills, locations, industries, research_directions, research_topics, products, datasets.
# Quan hệ lấy theo comment trong HTML (FOCUSES_ON, SUPPORTS, PARTICIPATES_IN, …).

# Thư mục chứa script (để lưu log)
SCRIPT_DIR = Path(__file__).resolve().parent
LOGS_DIR = SCRIPT_DIR / "logs"

# ==========================================
# LOGGING CONFIGURATION
# ==========================================
def setup_logging():
    """Configure logging: file in logs/ folder + console."""
    LOGS_DIR.mkdir(exist_ok=True)
    log_file = LOGS_DIR / f"sync_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )
    return logging.getLogger(__name__)

logger = setup_logging()

# ==========================================
# DATABASE CONNECTIONS
# ==========================================
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "rd_recommendation_system")
mongo_client = MongoClient(MONGO_URI)
mdb = mongo_client[MONGO_DB_NAME]

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

# ==========================================
# STATISTICS TRACKER
# ==========================================
class SyncStats:
    def __init__(self):
        self.stats = defaultdict(lambda: {"success": 0, "failed": 0, "skipped": 0})
        self.errors = defaultdict(list)
    
    def record_success(self, entity_type: str):
        self.stats[entity_type]["success"] += 1
    
    def record_failure(self, entity_type: str, entity_id: str, error: str):
        self.stats[entity_type]["failed"] += 1
        self.errors[entity_type].append({"id": entity_id, "error": str(error)})
    
    def record_skip(self, entity_type: str, reason: str):
        self.stats[entity_type]["skipped"] += 1
    
    def print_summary(self):
        logger.info("\n" + "="*60)
        logger.info("SYNC SUMMARY")
        logger.info("="*60)
        for entity_type, counts in self.stats.items():
            total = counts["success"] + counts["failed"] + counts["skipped"]
            logger.info(f"\n{entity_type}:")
            logger.info(f"  Total: {total}")
            logger.info(f"  [OK] Success: {counts['success']}")
            logger.info(f"  [FAIL] Failed: {counts['failed']}")
            logger.info(f"  [SKIP] Skipped: {counts['skipped']}")
            
            if self.errors[entity_type]:
                logger.info(f"  Errors ({len(self.errors[entity_type])}):")
                for err in self.errors[entity_type][:5]:  # Show first 5 errors
                    logger.info(f"    - {err['id']}: {err['error']}")
                if len(self.errors[entity_type]) > 5:
                    logger.info(f"    ... and {len(self.errors[entity_type]) - 5} more")
        logger.info("="*60)

stats = SyncStats()

# ==========================================
# HELPER FUNCTIONS
# ==========================================
def safe_get(data: Dict, *keys, default=None):
    """Safely get nested dictionary values"""
    for key in keys:
        if isinstance(data, dict):
            data = data.get(key, {})
        else:
            return default
    return data if data != {} else default

def clean_params(**params) -> Dict[str, Any]:
    """
    Keep all parameter keys for Cypher queries.

    Neo4j requires every referenced parameter to exist in the parameter map.
    We only normalize empty lists to None to avoid noisy [] writes.
    """
    cleaned = {}
    for key, value in params.items():
        cleaned[key] = None if isinstance(value, list) and len(value) == 0 else value
    return cleaned


def make_location_id(location: Dict[str, Any]) -> Optional[str]:
    """Build deterministic location_id from embedded location object."""
    if not isinstance(location, dict):
        return None
    cc = (location.get("country_code") or "").strip()
    region = (location.get("region") or location.get("city") or "").strip()
    if not cc and not region:
        return None
    if region:
        return f"{cc}-{region}" if cc else region
    return cc

def build_dynamic_set_clause(base_params: Dict[str, Any], optional_params: Dict[str, Any]) -> tuple:
    """
    Build dynamic SET clause for Cypher queries to avoid parameter missing errors
    
    Args:
        base_params: Always required parameters
        optional_params: Parameters that may be None
    
    Returns:
        (query_params, set_clauses) tuple
    """
    query_params = base_params.copy()
    set_clauses = []
    
    for key, value in optional_params.items():
        if value is not None:
            query_params[key] = value
            set_clauses.append(f"o.{key} = ${key}")
    
    return query_params, set_clauses

# ==========================================
# NEO4J CONSTRAINTS AND INDEXES
# ==========================================
def create_neo4j_constraints_and_indexes(session):
    """Create constraints and indexes in Neo4j for better performance and data integrity"""
    logger.info("Creating Neo4j constraints and indexes...")
    
    constraints = [
        "CREATE CONSTRAINT expert_id_unique IF NOT EXISTS FOR (e:Expert) REQUIRE e.expert_id IS UNIQUE",
        "CREATE CONSTRAINT project_id_unique IF NOT EXISTS FOR (p:Project) REQUIRE p.project_id IS UNIQUE",
        "CREATE CONSTRAINT enterprise_id_unique IF NOT EXISTS FOR (e:Enterprise) REQUIRE e.enterprise_id IS UNIQUE",
        "CREATE CONSTRAINT funder_id_unique IF NOT EXISTS FOR (f:Funder) REQUIRE f.funder_id IS UNIQUE",
        "CREATE CONSTRAINT location_id_unique IF NOT EXISTS FOR (l:Location) REQUIRE l.location_id IS UNIQUE",
        "CREATE CONSTRAINT industry_code_unique IF NOT EXISTS FOR (i:Industry) REQUIRE i.code IS UNIQUE",
        "CREATE CONSTRAINT skill_name_unique IF NOT EXISTS FOR (s:Skill) REQUIRE s.name IS UNIQUE",
        "CREATE CONSTRAINT direction_name_unique IF NOT EXISTS FOR (d:ResearchDirection) REQUIRE d.name IS UNIQUE",
        "CREATE CONSTRAINT topic_name_unique IF NOT EXISTS FOR (t:ResearchTopic) REQUIRE t.name IS UNIQUE",
        "CREATE CONSTRAINT product_id_unique IF NOT EXISTS FOR (p:Product) REQUIRE p.product_id IS UNIQUE",
        "CREATE CONSTRAINT dataset_id_unique IF NOT EXISTS FOR (d:Dataset) REQUIRE d.dataset_id IS UNIQUE",
    ]
    
    indexes = [
        "CREATE INDEX expert_name IF NOT EXISTS FOR (e:Expert) ON (e.name)",
        "CREATE INDEX project_title IF NOT EXISTS FOR (p:Project) ON (p.title)",
        "CREATE INDEX project_status IF NOT EXISTS FOR (p:Project) ON (p.status)",
        "CREATE INDEX enterprise_name IF NOT EXISTS FOR (e:Enterprise) ON (e.name)",
        "CREATE INDEX funder_name IF NOT EXISTS FOR (f:Funder) ON (f.name)",
        "CREATE INDEX skill_name IF NOT EXISTS FOR (s:Skill) ON (s.name)",
        "CREATE INDEX direction_name IF NOT EXISTS FOR (d:ResearchDirection) ON (d.name)",
        "CREATE INDEX topic_name IF NOT EXISTS FOR (t:ResearchTopic) ON (t.name)",
        "CREATE INDEX product_name IF NOT EXISTS FOR (p:Product) ON (p.name)",
        "CREATE INDEX dataset_name IF NOT EXISTS FOR (d:Dataset) ON (d.name)",
        "CREATE INDEX location_city IF NOT EXISTS FOR (l:Location) ON (l.city)",
        "CREATE INDEX industry_name IF NOT EXISTS FOR (i:Industry) ON (i.name)",
    ]
    
    for constraint in constraints:
        try:
            session.run(constraint)
            logger.info(f"[OK] Created constraint: {constraint.split('FOR')[1].split('REQUIRE')[0].strip()}")
        except Exception as e:
            if "already exists" in str(e).lower() or "equivalent" in str(e).lower():
                logger.debug(f"Constraint already exists: {constraint[:50]}...")
            else:
                logger.warning(f"Error creating constraint: {e}")
    
    for index in indexes:
        try:
            session.run(index)
            logger.info(f"[OK] Created index: {index.split('FOR')[1].split('ON')[0].strip()}")
        except Exception as e:
            if "already exists" in str(e).lower() or "equivalent" in str(e).lower():
                logger.debug(f"Index already exists: {index[:50]}...")
            else:
                logger.warning(f"Error creating index: {e}")


# ==========================================
# SYNC: ONTOLOGY (NEW SCHEMA)
# ==========================================
def sync_skills(session):
    """Create Skill nodes"""
    logger.info("Syncing Skills...")
    skills = list(mdb.skills.find({}))
    total = len(skills)
    logger.info(f"Found {total} skills to sync")

    for idx, sk in enumerate(skills, 1):
        skill_id = sk.get("skill_id")
        if not skill_id:
            stats.record_skip("Skill", "Missing skill_id")
            continue

        try:
            session.run(
                """
                MERGE (s:Skill {skill_id: $skill_id})
                SET s.name = $name,
                    s.category = $category,
                    s.aliases = $aliases,
                    s.parent_skill_id = $parent_skill_id,
                    s.ontology_ref = $ontology_ref,
                    s.updated_at = datetime()
                """,
                **{
                    "skill_id": skill_id,
                    "name": sk.get("name"),
                    "category": sk.get("category"),
                    "aliases": sk.get("aliases"),
                    # Must pass even when None; Neo4j expects parameter keys in the Cypher.
                    "parent_skill_id": sk.get("parent_skill_id"),
                    "ontology_ref": sk.get("ontology_ref"),
                },
            )

            # Optional parent relationship (only if parent exists in DB)
            parent_skill_id = sk.get("parent_skill_id")
            if parent_skill_id:
                session.run(
                    """
                    MATCH (c:Skill {skill_id: $child_id})
                    MATCH (p:Skill {skill_id: $parent_id})
                    MERGE (c)-[:SUB_SKILL_OF]->(p)
                    """,
                    child_id=skill_id,
                    parent_id=parent_skill_id
                )

            stats.record_success("Skill")
            if idx % 10 == 0 or idx == total:
                logger.info(f"Progress: {idx}/{total} ({idx/total*100:.1f}%)")
        except Exception as e:
            stats.record_failure("Skill", skill_id, e)
            logger.error(f"Error syncing Skill {skill_id}: {e}")


def sync_locations(session):
    """Create Location nodes"""
    logger.info("Syncing Locations...")
    locations = list(mdb.locations.find({}))
    total = len(locations)
    logger.info(f"Found {total} locations to sync")

    for idx, loc in enumerate(locations, 1):
        location_id = loc.get("location_id")
        if not location_id:
            stats.record_skip("Location", "Missing location_id")
            continue

        try:
            session.run(
                """
                MERGE (l:Location {location_id: $location_id})
                SET l.country_code = $country_code,
                    l.country_name = $country_name,
                    l.region = $region,
                    l.city = $city,
                    l.updated_at = datetime()
                """,
                **{
                    "location_id": location_id,
                    "country_code": loc.get("country_code"),
                    "country_name": loc.get("country_name"),
                    "region": loc.get("region"),
                    "city": loc.get("city"),
                }
            )
            stats.record_success("Location")
            if idx % 10 == 0 or idx == total:
                logger.info(f"Progress: {idx}/{total} ({idx/total*100:.1f}%)")
        except Exception as e:
            stats.record_failure("Location", location_id, e)
            logger.error(f"Error syncing Location {location_id}: {e}")


def sync_industries_new(session):
    """Create Industry nodes (match current Mongo schema fields)"""
    logger.info("Syncing Industries...")
    industries = list(mdb.industries.find({}))
    total = len(industries)
    logger.info(f"Found {total} industries to sync")

    for idx, ind in enumerate(industries, 1):
        industry_id = ind.get("industry_id")
        if not industry_id:
            stats.record_skip("Industry", "Missing industry_id")
            continue

        try:
            session.run(
                """
                MERGE (i:Industry {industry_id: $industry_id})
                SET i.name = $name,
                    i.code = $code,
                    i.standard = $standard,
                    i.parent_industry_id = $parent_industry_id,
                    i.updated_at = datetime()
                """,
                **{
                    "industry_id": industry_id,
                    "name": ind.get("name") or ind.get("industry_name"),
                    "code": ind.get("code"),
                    "standard": ind.get("standard"),
                    # Must pass even when None; Cypher references it.
                    "parent_industry_id": ind.get("parent_industry_id"),
                }
            )
            stats.record_success("Industry")
            if idx % 10 == 0 or idx == total:
                logger.info(f"Progress: {idx}/{total} ({idx/total*100:.1f}%)")
        except Exception as e:
            stats.record_failure("Industry", industry_id, e)
            logger.error(f"Error syncing Industry {industry_id}: {e}")


def sync_research_directions(session):
    """Create ResearchDirection nodes"""
    logger.info("Syncing ResearchDirections...")
    directions = list(mdb.research_directions.find({}))
    total = len(directions)
    logger.info(f"Found {total} research directions to sync")

    for idx, rd in enumerate(directions, 1):
        direction_id = rd.get("direction_id")
        if not direction_id:
            stats.record_skip("ResearchDirection", "Missing direction_id")
            continue

        try:
            session.run(
                """
                MERGE (d:ResearchDirection {direction_id: $direction_id})
                SET d.name = $name,
                    d.description = $description,
                    d.ontology_ref = $ontology_ref,
                    d.keywords = $keywords,
                    d.updated_at = datetime()
                """,
                **clean_params(
                    direction_id=direction_id,
                    name=rd.get("name"),
                    description=rd.get("description"),
                    ontology_ref=rd.get("ontology_ref"),
                    keywords=rd.get("keywords"),
                )
            )
            stats.record_success("ResearchDirection")
            if idx % 10 == 0 or idx == total:
                logger.info(f"Progress: {idx}/{total} ({idx/total*100:.1f}%)")
        except Exception as e:
            stats.record_failure("ResearchDirection", direction_id, e)
            logger.error(f"Error syncing ResearchDirection {direction_id}: {e}")


def sync_research_topics(session):
    """Create ResearchTopic nodes"""
    logger.info("Syncing ResearchTopics...")
    topics = list(mdb.research_topics.find({}))
    total = len(topics)
    logger.info(f"Found {total} research topics to sync")

    for idx, tp in enumerate(topics, 1):
        topic_id = tp.get("topic_id")
        if not topic_id:
            stats.record_skip("ResearchTopic", "Missing topic_id")
            continue

        try:
            session.run(
                """
                MERGE (t:ResearchTopic {topic_id: $topic_id})
                SET t.name = $name,
                    t.parent_direction_id = $parent_direction_id,
                    t.ontology_ref = $ontology_ref,
                    t.keywords = $keywords,
                    t.updated_at = datetime()
                """,
                **clean_params(
                    topic_id=topic_id,
                    name=tp.get("name"),
                    parent_direction_id=tp.get("parent_direction_id"),
                    ontology_ref=tp.get("ontology_ref"),
                    keywords=tp.get("keywords"),
                )
            )
            stats.record_success("ResearchTopic")
            if idx % 10 == 0 or idx == total:
                logger.info(f"Progress: {idx}/{total} ({idx/total*100:.1f}%)")
        except Exception as e:
            stats.record_failure("ResearchTopic", topic_id, e)
            logger.error(f"Error syncing ResearchTopic {topic_id}: {e}")


def sync_research_topic_belongs_to(session):
    """ResearchTopic -[:BELONGS_TO]-> ResearchDirection (mongodb_schema_full_v2)."""
    logger.info("Syncing ResearchTopic BELONGS_TO relationships...")
    topics = list(mdb.research_topics.find({}))
    total = len(topics)
    created = 0

    for idx, tp in enumerate(topics, 1):
        topic_id = tp.get("topic_id")
        parent_direction_id = tp.get("parent_direction_id")
        if not topic_id or not parent_direction_id:
            continue

        try:
            result = session.run(
                """
                MATCH (t:ResearchTopic {topic_id: $topic_id})
                MATCH (d:ResearchDirection {direction_id: $direction_id})
                MERGE (t)-[:BELONGS_TO]->(d)
                RETURN 1
                """,
                topic_id=topic_id,
                direction_id=parent_direction_id,
            )
            if result.single():
                created += 1
        except Exception as e:
            logger.error(f"Error creating BELONGS_TO for topic {topic_id}: {e}")

        if idx % 10 == 0 or idx == total:
            logger.info(f"Progress: {idx}/{total} ({idx/total*100:.1f}%)")

    logger.info(f"Created/ensured {created} BELONGS_TO relationships")


def sync_products(session):
    """Create Product nodes"""
    logger.info("Syncing Products...")
    products = list(mdb.products.find({}))
    total = len(products)
    logger.info(f"Found {total} products to sync")

    for idx, pr in enumerate(products, 1):
        product_id = pr.get("product_id")
        if not product_id:
            stats.record_skip("Product", "Missing product_id")
            continue

        try:
            developer_ids = pr.get("developer_ids")
            if not developer_ids:
                # Backward compatibility with old schema.
                developer_ids = pr.get("developed_by")

            session.run(
                """
                MERGE (o:Product {product_id: $product_id})
                SET o.name = $name,
                    o.type = $type,
                    o.trl = $trl,
                    o.year = $year,
                    o.linked_project_id = $linked_project_id,
                    o.license = $license,
                    o.access_url = $access_url,
                    o.developed_by = $developed_by,
                    o.updated_at = datetime()
                """,
                **{
                    "product_id": product_id,
                    "name": pr.get("name"),
                    "type": pr.get("type"),
                    "trl": pr.get("trl"),
                    "year": pr.get("year"),
                    "linked_project_id": pr.get("linked_project_id"),
                    # Must pass even when None; Cypher references it.
                    "license": pr.get("license"),
                    "access_url": pr.get("access_url"),
                    "developed_by": developer_ids,
                },
            )
            stats.record_success("Product")
            if idx % 10 == 0 or idx == total:
                logger.info(f"Progress: {idx}/{total} ({idx/total*100:.1f}%)")
        except Exception as e:
            stats.record_failure("Product", product_id, e)
            logger.error(f"Error syncing Product {product_id}: {e}")


def sync_datasets(session):
    """Tạo nút :Dataset từ MongoDB collection `datasets`."""
    logger.info("Syncing Datasets...")
    datasets = list(mdb.datasets.find({}))
    total = len(datasets)
    logger.info(f"Found {total} datasets to sync")

    for idx, ds in enumerate(datasets, 1):
        dataset_id = ds.get("dataset_id")
        if not dataset_id:
            stats.record_skip("Dataset", "Missing dataset_id")
            continue

        try:
            owner_ids = ds.get("owner_ids")
            if not owner_ids:
                # Backward compatibility with old schema.
                legacy_owner = ds.get("owner_expert_id")
                owner_ids = [legacy_owner] if legacy_owner else None

            session.run(
                """
                MERGE (d:Dataset {dataset_id: $dataset_id})
                SET d.name = $name,
                    d.description = $description,
                    d.type = $type,
                    d.trl = $trl,
                    d.year = $year,
                    d.linked_project_id = $linked_project_id,
                    d.license = $license,
                    d.access_url = $access_url,
                    d.owner_ids = $owner_ids,
                    d.size_mb = $size_mb,
                    d.domain_tags = $domain_tags,
                    d.updated_at = datetime()
                """,
                **{
                    "dataset_id": dataset_id,
                    "name": ds.get("name"),
                    "description": ds.get("description"),
                    "type": ds.get("type") or ds.get("format"),
                    "trl": ds.get("trl"),
                    "year": ds.get("year"),
                    "linked_project_id": ds.get("linked_project_id"),
                    "license": ds.get("license"),
                    "access_url": ds.get("access_url"),
                    "owner_ids": owner_ids,
                    "size_mb": ds.get("size_mb"),
                    "domain_tags": ds.get("domain_tags"),
                },
            )
            stats.record_success("Dataset")
            if idx % 10 == 0 or idx == total:
                logger.info(f"Progress: {idx}/{total} ({idx/total*100:.1f}%)")
        except Exception as e:
            stats.record_failure("Dataset", dataset_id, e)
            logger.error(f"Error syncing Dataset {dataset_id}: {e}")


# ==========================================
# SYNC: MAIN ENTITIES (NEW SCHEMA)
# ==========================================
def sync_experts_new(session, direction_ids: set, topic_ids: set):
    """Create Expert nodes + relationships"""
    logger.info("Syncing Experts...")
    experts = list(mdb.experts.find({}))
    total = len(experts)
    logger.info(f"Found {total} experts to sync")

    for idx, ex in enumerate(experts, 1):
        expert_id = ex.get("expert_id")
        if not expert_id:
            stats.record_skip("Expert", "Missing expert_id")
            continue

        try:
            basic = ex.get("basic_info") or {}
            location = basic.get("location") or {}
            location_id = make_location_id(location)
            metrics = safe_get(ex, "research_capacity", "academic_metrics") or {}

            session.run(
                """
                MERGE (e:Expert {expert_id: $expert_id})
                SET e.name = $name,
                    e.birth_year = $birth_year,
                    e.gender = $gender,
                    e.location_id = $location_id,
                    e.location_country_code = $location_country_code,
                    e.location_region = $location_region,
                    e.location_city = $location_city,
                    e.nationality = $nationality,
                    e.preferred_language = $preferred_language,
                    e.publication_count = $pub_cnt,
                    e.h_index = $h_index,
                    e.citation_count = $cit_cnt,
                    e.i10_index = $i10_index,
                    e.altmetrics = $altmetrics,
                    e.updated_at = datetime()
                """,
                **clean_params(
                    expert_id=expert_id,
                    name=basic.get("name"),
                    birth_year=basic.get("birth_year"),
                    gender=basic.get("gender"),
                    location_id=location_id,
                    location_country_code=location.get("country_code"),
                    location_region=location.get("region"),
                    location_city=location.get("city"),
                    nationality=basic.get("nationality"),
                    preferred_language=basic.get("preferred_language"),
                    pub_cnt=metrics.get("publication_count"),
                    h_index=metrics.get("h_index"),
                    cit_cnt=metrics.get("citation_count"),
                    i10_index=metrics.get("i10_index"),
                    altmetrics=metrics.get("altmetrics"),
                )
            )

            # basic_info.location_id → LOCATED_IN (schema v2)
            if location_id:
                session.run(
                    """
                    MERGE (l:Location {location_id: $location_id})
                    SET l.country_code = $country_code,
                        l.country_name = $country_name,
                        l.region = $region,
                        l.city = $city,
                        l.updated_at = datetime()
                    """,
                    location_id=location_id,
                    country_code=location.get("country_code"),
                    country_name=location.get("country_name"),
                    region=location.get("region"),
                    city=location.get("city"),
                )
                session.run(
                    """
                    MATCH (e:Expert {expert_id: $expert_id})
                    MATCH (l:Location {location_id: $location_id})
                    MERGE (e)-[:LOCATED_IN]->(l)
                    """,
                    expert_id=expert_id,
                    location_id=location_id,
                )

            skills_methods = safe_get(ex, "research_capacity", "skills_methods") or []
            for sm in skills_methods:
                skill_name = sm.get("name")
                if not skill_name:
                    continue
                # Tạo node Skill dựa trên name
                session.run(
                    """
                    MERGE (s:Skill {name: $name})
                    SET s.category = $category, s.updated_at = datetime()
                    """,
                    name=skill_name, category=sm.get("category")
                )
                # Nối Expert với Skill
                session.run(
                    """
                    MATCH (e:Expert {expert_id: $expert_id})
                    MATCH (s:Skill {name: $name})
                    MERGE (e)-[r:HAS_SKILL]->(s)
                    SET r.proficiency_level = $level
                    """,
                    expert_id=expert_id, name=skill_name, level=sm.get("proficiency_level")
                )

            rc = ex.get("research_capacity") or {}

            # applied_industries (merged schema) → APPLIES
            for ind in rc.get("applied_industries") or []:
                if not isinstance(ind, dict):
                    continue
                
                # SỬA: Lấy 'code' thay vì 'id'
                ind_code = ind.get("code")
                if not ind_code:
                    continue
                
                session.run(
                    """
                    MERGE (i:Industry {code: $code})  // SỬA: MERGE bằng code
                    SET i.name = $name,
                        i.updated_at = datetime()
                    """,
                    code=ind_code,
                    name=ind.get("name"),
                )
                session.run(
                    """
                    MATCH (e:Expert {expert_id: $expert_id})
                    MATCH (i:Industry {code: $code})
                    MERGE (e)-[:HAS_APPLICATION_EXPERIENCE_IN]->(i)
                    """,
                    expert_id=expert_id,
                    code=ind_code,
                )

            # merged schema: research_directions là list tên
            for direction_name in rc.get("research_directions") or []:
                if not direction_name:
                    continue
                session.run(
                    """
                    MERGE (d:ResearchDirection {name: $name})
                    SET d.updated_at = datetime()
                    """,
                    name=direction_name,
                )
                session.run(
                    """
                    MATCH (e:Expert {expert_id: $expert_id})
                    MATCH (d:ResearchDirection {name: $name})
                    MERGE (e)-[:RESEARCHES]->(d)
                    """,
                    expert_id=expert_id,
                    name=direction_name,
                )

            research_topics = safe_get(ex, "research_capacity", "research_topics") or []
            for topic in research_topics:
                topic_name = topic.get("name")
                if not topic_name: continue
                
                session.run(
                    "MERGE (t:ResearchTopic {name: $name}) SET t.updated_at = datetime()",
                    name=topic_name
                )
                session.run(
                    """
                    MATCH (e:Expert {expert_id: $expert_id})
                    MATCH (t:ResearchTopic {name: $name})
                    MERGE (e)-[:HAS_EXPERIENCE_IN]->(t)
                    """,
                    expert_id=expert_id, name=topic_name
                )

            # Dataset — theo mongodb_schema_full_v2: activities_and_outputs.owned/accessible_dataset_ids
            for ds_id in safe_get(ex, "activities_and_outputs", "owned_dataset_ids") or []:
                if not ds_id:
                    continue
                session.run(
                    """
                    MATCH (e:Expert {expert_id: $expert_id})
                    MATCH (d:Dataset {dataset_id: $dataset_id})
                    MERGE (e)-[:OWNS_DATA]->(d)
                    """,
                    expert_id=expert_id,
                    dataset_id=ds_id,
                )

            for ds_id in safe_get(ex, "activities_and_outputs", "accessible_dataset_ids") or []:
                if not ds_id:
                    continue
                session.run(
                    """
                    MATCH (e:Expert {expert_id: $expert_id})
                    MATCH (d:Dataset {dataset_id: $dataset_id})
                    MERGE (e)-[:HAS_ACCESS_TO]->(d)
                    """,
                    expert_id=expert_id,
                    dataset_id=ds_id,
                )

            for out in safe_get(ex, "activities_and_outputs", "list_outputs") or []:
                if not isinstance(out, dict):
                    continue
                pid = out.get("product_id")
                if pid:
                    session.run(
                        """
                        MATCH (e:Expert {expert_id: $expert_id})
                        MATCH (o:Product {product_id: $product_id})
                        MERGE (e)-[:DEVELOPS]->(o)
                        """,
                        expert_id=expert_id,
                        product_id=pid,
                    )
            # Expert -> Project (PARTICIPATES_IN)
            projects_participation = safe_get(ex, "activities_and_outputs", "projects_participation") or []
            for p_part in projects_participation:
                if not isinstance(p_part, dict):
                    continue
                prj_id = p_part.get("project_id")
                if not prj_id:
                    continue
                session.run(
                    """
                    MATCH (e:Expert {expert_id: $expert_id})
                    MERGE (p:Project {project_id: $project_id})
                    MERGE (e)-[r:PARTICIPATES_IN]->(p)
                    SET r.role = $role, r.status = $status
                    """,
                    expert_id=expert_id,
                    project_id=prj_id,
                    role=p_part.get("role"),
                    status=p_part.get("status")
                )
            # Expert -> Expert collaborations
            # CODE CHUẨN
            collaborators = safe_get(ex, "activities_and_outputs", "collaborators") or []
            for collab in collaborators:
                if not isinstance(collab, dict):
                    continue
                other_id = collab.get("expert_id")
                if not other_id or other_id == expert_id:
                    continue
                session.run(
                    """
                    MATCH (e:Expert {expert_id: $expert_id})
                    MATCH (o:Expert {expert_id: $other_id})
                    MERGE (e)-[r:COLLABORATES_WITH]->(o)
                    SET r.relation_type = $relation_type,
                        r.duration = $duration
                    """,
                    expert_id=expert_id,
                    other_id=other_id,
                    relation_type=collab.get("relation_type"),
                    duration=collab.get("duration"),
                )

            stats.record_success("Expert")
            if idx % 10 == 0 or idx == total:
                logger.info(f"Progress: {idx}/{total} ({idx/total*100:.1f}%)")

        except Exception as e:
            stats.record_failure("Expert", expert_id, e)
            logger.error(f"Error syncing Expert {expert_id}: {e}")


def sync_enterprises_new(session, direction_ids: set, topic_ids: set):
    """Enterprise + quan hệ theo ER bài báo (LOCATED_IN, HAS_SKILL, OPERATES_IN, RESEARCHES, …)."""
    logger.info("Syncing Enterprises...")
    enterprises = list(mdb.enterprises.find({}))
    total = len(enterprises)
    logger.info(f"Found {total} enterprises to sync")

    for idx, ent in enumerate(enterprises, 1):
        enterprise_id = ent.get("enterprise_id")
        if not enterprise_id:
            stats.record_skip("Enterprise", "Missing enterprise_id")
            continue

        try:
            basic = ent.get("basic_info") or {}
            location = basic.get("location") or {}
            location_id = make_location_id(location)
            org_metrics = basic.get("organization_metrics") or {}
            rd_profile = ent.get("rd_profile") or {}

            session.run(
                """
                MERGE (en:Enterprise {enterprise_id: $enterprise_id})
                SET en.name = $name,
                    en.tax_code = $tax_code,
                    en.founded_year = $founded_year,
                    en.location_id = $location_id,
                    en.location_country_code = $location_country_code,
                    en.location_region = $location_region,
                    en.location_city = $location_city,
                    en.size = $size,
                    en.income = $income,
                    en.employees = $employees,
                    en.updated_at = datetime()
                """,
                **clean_params(
                    enterprise_id=enterprise_id,
                    name=basic.get("name"),
                    tax_code=basic.get("tax_code"),
                    founded_year=basic.get("founded_year"),
                    location_id=location_id,
                    location_country_code=location.get("country_code"),
                    location_region=location.get("region"),
                    location_city=location.get("city"),
                    size=org_metrics.get("size"),
                    income=org_metrics.get("income"),
                    employees=org_metrics.get("employees"),
                )
            )

            # Located in
            if location_id:
                session.run(
                    """
                    MERGE (l:Location {location_id: $location_id})
                    SET l.country_code = $country_code,
                        l.country_name = $country_name,
                        l.region = $region,
                        l.city = $city,
                        l.updated_at = datetime()
                    """,
                    location_id=location_id,
                    country_code=location.get("country_code"),
                    country_name=location.get("country_name"),
                    region=location.get("region"),
                    city=location.get("city"),
                )
                session.run(
                    """
                    MATCH (en:Enterprise {enterprise_id: $enterprise_id})
                    MATCH (l:Location {location_id: $location_id})
                    MERGE (en)-[:LOCATED_IN]->(l)
                    """,
                    enterprise_id=enterprise_id,
                    location_id=location_id,
                )

            # Operates in (MERGE by code)
            industries = basic.get("industries") or []
            for ind in industries:
                if not isinstance(ind, dict): continue
                ind_code = ind.get("code")
                if not ind_code: continue
                
                session.run(
                    """
                    MERGE (i:Industry {code: $code})
                    SET i.name = $name, i.updated_at = datetime()
                    """,
                    code=ind_code, name=ind.get("name")
                )
                session.run(
                    """
                    MATCH (en:Enterprise {enterprise_id: $enterprise_id})
                    MATCH (i:Industry {code: $code})
                    MERGE (en)-[:OPERATES_IN]->(i)
                    """,
                    enterprise_id=enterprise_id, code=ind_code
                )

            # technology_needs.required_skills (MERGE by name)
            tech_needs = rd_profile.get("technology_needs") or []
            for need in tech_needs:
                if not isinstance(need, dict): continue
                for skill in need.get("required_skills") or []:
                    skill_name = skill.get("name")
                    if not skill_name: continue
                    
                    session.run(
                        """
                        MERGE (s:Skill {name: $name})
                        SET s.updated_at = datetime()
                        """,
                        name=skill_name
                    )
                    session.run(
                        """
                        MATCH (en:Enterprise {enterprise_id: $enterprise_id})
                        MATCH (s:Skill {name: $name})
                        MERGE (en)-[r:REQUIRES_SKILL]->(s)
                        SET r.proficiency_level = $level, r.need = $need_desc
                        """,
                        enterprise_id=enterprise_id, 
                        name=skill_name, 
                        level=skill.get("proficiency_level"),
                        need_desc=need.get("need")
                    )

            # rd_focus_directions (MERGE by name)
            for direction_name in rd_profile.get("rd_focus_directions") or []:
                if not direction_name: continue
                session.run(
                    "MERGE (d:ResearchDirection {name: $name}) SET d.updated_at = datetime()",
                    name=direction_name
                )
                session.run(
                    """
                    MATCH (en:Enterprise {enterprise_id: $enterprise_id})
                    MATCH (d:ResearchDirection {name: $name})
                    MERGE (en)-[:FOCUSES_ON]->(d)
                    """,
                    enterprise_id=enterprise_id, name=direction_name
                )
                
            # rd_focus_topics (MERGE by name)
            for topic in rd_profile.get("rd_focus_topics") or []:
                topic_name = topic.get("name")
                if not topic_name: continue
                session.run(
                    "MERGE (t:ResearchTopic {name: $name}) SET t.updated_at = datetime()",
                    name=topic_name
                )
                session.run(
                    """
                    MATCH (en:Enterprise {enterprise_id: $enterprise_id})
                    MATCH (t:ResearchTopic {name: $name})
                    MERGE (en)-[:FOCUSES_ON_TOPIC]->(t)
                    """,
                    enterprise_id=enterprise_id, name=topic_name
                )

            # WORK_FOR: relations.worked_experts
            ent_rel = ent.get("relations") or {}
            for worked in ent_rel.get("worked_experts") or []:
                if not isinstance(worked, dict): continue
                expert_id = worked.get("expert_id")
                if not expert_id: continue
                session.run(
                    """
                    MATCH (e:Expert {expert_id: $expert_id})
                    MATCH (en:Enterprise {enterprise_id: $enterprise_id})
                    MERGE (e)-[:WORK_FOR]->(en)
                    """,
                    expert_id=expert_id, enterprise_id=enterprise_id
                )

            stats.record_success("Enterprise")
            if idx % 10 == 0 or idx == total:
                logger.info(f"Progress: {idx}/{total} ({idx/total*100:.1f}%)")
        except Exception as e:
            stats.record_failure("Enterprise", enterprise_id, e)
            logger.error(f"Error syncing Enterprise {enterprise_id}: {e}")

def sync_funders_new(session, direction_ids: set, topic_ids: set):
    """Create Funder nodes + relationships (location, focuses, supports)"""
    logger.info("Syncing Funders...")
    funders = list(mdb.funders.find({}))
    total = len(funders)
    logger.info(f"Found {total} funders to sync")

    for idx, fu in enumerate(funders, 1):
        funder_id = fu.get("funder_id")
        if not funder_id:
            stats.record_skip("Funder", "Missing funder_id")
            continue

        try:
            basic = fu.get("basic_info") or {}
            location = basic.get("location") or {}
            location_id = make_location_id(location)
            strategy = fu.get("funding_strategy") or {}

            session.run(
                """
                MERGE (f:Funder {funder_id: $funder_id})
                SET f.name = $name,
                    f.type = $type,
                    f.location_id = $location_id,
                    f.location_country_code = $location_country_code,
                    f.location_region = $location_region,
                    f.location_city = $location_city,
                    f.budget_capacity = $budget_capacity,
                    f.updated_at = datetime()
                """,
                **clean_params(
                    funder_id=funder_id,
                    name=basic.get("name"),
                    type=basic.get("type"),
                    location_id=location_id,
                    location_country_code=location.get("country_code"),
                    location_region=location.get("region"),
                    location_city=location.get("city"),
                    budget_capacity=basic.get("budget_capacity"),
                )
            )

            if location_id:
                session.run(
                    """
                    MERGE (l:Location {location_id: $location_id})
                    SET l.country_code = $country_code,
                        l.country_name = $country_name,
                        l.region = $region,
                        l.city = $city,
                        l.updated_at = datetime()
                    """,
                    location_id=location_id,
                    country_code=location.get("country_code"),
                    country_name=location.get("country_name"),
                    region=location.get("region"),
                    city=location.get("city"),
                )
                session.run(
                    """
                    MATCH (f:Funder {funder_id: $funder_id})
                    MATCH (l:Location {location_id: $location_id})
                    MERGE (f)-[:LOCATED_IN]->(l)
                    """,
                    funder_id=funder_id,
                    location_id=location_id,
                )

            # focus_regions
            for region_name in strategy.get("focus_regions") or []:
                if not region_name: continue
                region_loc_id = f"{(location.get('country_code') or 'UNK')}-{region_name}"
                session.run(
                    """
                    MERGE (l:Location {location_id: $location_id})
                    SET l.region = $region, l.country_code = $country_code, l.updated_at = datetime()
                    """,
                    location_id=region_loc_id, region=region_name, country_code=location.get("country_code")
                )
                session.run(
                    """
                    MATCH (f:Funder {funder_id: $funder_id})
                    MATCH (l:Location {location_id: $location_id})
                    MERGE (f)-[:FOCUSES_ON_REGION]->(l)
                    """,
                    funder_id=funder_id, location_id=region_loc_id
                )

            # focus_sectors (MERGE by code)
            for sector in strategy.get("focus_sectors") or []:
                if not isinstance(sector, dict): continue
                ind_code = sector.get("code")
                if not ind_code: continue
                session.run(
                    """
                    MERGE (i:Industry {code: $code})
                    SET i.name = $name, i.updated_at = datetime()
                    """,
                    code=ind_code, name=sector.get("name")
                )
                session.run(
                    """
                    MATCH (f:Funder {funder_id: $funder_id})
                    MATCH (i:Industry {code: $code})
                    MERGE (f)-[:FOCUSES_ON_SECTORS]->(i)
                    """,
                    funder_id=funder_id, code=ind_code
                )

            # funding_directions (MERGE by name)
            for direction_name in strategy.get("funding_directions") or []:
                if not direction_name: continue
                session.run(
                    "MERGE (d:ResearchDirection {name: $name}) SET d.updated_at = datetime()",
                    name=direction_name
                )
                session.run(
                    """
                    MATCH (f:Funder {funder_id: $funder_id})
                    MATCH (d:ResearchDirection {name: $name})
                    MERGE (f)-[:SUPPORTS]->(d)
                    """,
                    funder_id=funder_id, name=direction_name
                )
                
            # funding_topics (MERGE by name)
            for topic in strategy.get("funding_topics") or []:
                topic_name = topic.get("name")
                if not topic_name: continue
                session.run(
                    "MERGE (t:ResearchTopic {name: $name}) SET t.updated_at = datetime()",
                    name=topic_name
                )
                session.run(
                    """
                    MATCH (f:Funder {funder_id: $funder_id})
                    MATCH (t:ResearchTopic {name: $name})
                    MERGE (f)-[:SUPPORTS_TOPIC]->(t)
                    """,
                    funder_id=funder_id, name=topic_name
                )

            # FUNDING HISTORY (Funder -> FUNDS -> Project)
            funding_history = fu.get("funding_history") or {}
            for fp in funding_history.get("funded_projects") or []:
                pid = fp.get("project_id")
                if not pid: continue
                session.run(
                    """
                    MATCH (f:Funder {funder_id: $funder_id})
                    MERGE (p:Project {project_id: $project_id})
                    MERGE (f)-[r:FUNDS]->(p)
                    SET r.grant_amount = $amount, r.year = $year, r.status = $status
                    """,
                    funder_id=funder_id, project_id=pid,
                    amount=fp.get("grant_amount"), year=fp.get("year"), status=fp.get("status")
                )

            stats.record_success("Funder")
            if idx % 10 == 0 or idx == total:
                logger.info(f"Progress: {idx}/{total} ({idx/total*100:.1f}%)")
        except Exception as e:
            stats.record_failure("Funder", funder_id, e)
            logger.error(f"Error syncing Funder {funder_id}: {e}")


def sync_projects_new(session, direction_ids: set, topic_ids: set):
    """Create Project nodes + relationships"""
    logger.info("Syncing Projects...")
    projects = list(mdb.projects.find({}))
    total = len(projects)
    logger.info(f"Found {total} projects to sync")

    for idx, pr in enumerate(projects, 1):
        project_id = pr.get("project_id")
        if not project_id:
            stats.record_skip("Project", "Missing project_id")
            continue

        try:
            basic = pr.get("basic_info") or {}
            location = basic.get("location") or {}
            location_id = make_location_id(location)
            req = pr.get("requirements_and_timeline") or {}
            rd_prof = pr.get("rd_profile") or {}
            rel = pr.get("relations") or {}

            # Node
            session.run(
                """
                MERGE (p:Project {project_id: $project_id})
                SET p.title = $title,
                    p.description = $description,
                    p.status = $status,
                    p.location_id = $location_id,
                    p.location_country_code = $location_country_code,
                    p.location_region = $location_region,
                    p.location_city = $location_city,
                    p.keywords = $keywords,
                    p.technology_readiness_level = $trl,
                    p.updated_at = datetime()
                """,
                **clean_params(
                    project_id=project_id,
                    title=basic.get("title"),
                    description=basic.get("description"),
                    status=basic.get("status"),
                    location_id=location_id,
                    location_country_code=location.get("country_code"),
                    location_region=location.get("region"),
                    location_city=location.get("city"),
                    keywords=basic.get("keywords"),
                    trl=req.get("technology_readiness_level"),
                )
            )

            # Location
            if location_id:
                session.run(
                    """
                    MERGE (l:Location {location_id: $location_id})
                    SET l.country_code = $country_code,
                        l.country_name = $country_name,
                        l.region = $region,
                        l.city = $city,
                        l.updated_at = datetime()
                    """,
                    location_id=location_id,
                    country_code=location.get("country_code"),
                    country_name=location.get("country_name"),
                    region=location.get("region"),
                    city=location.get("city"),
                )
                session.run(
                    """
                    MATCH (p:Project {project_id: $project_id})
                    MATCH (l:Location {location_id: $location_id})
                    MERGE (p)-[:LOCATED_IN]->(l)
                    """,
                    project_id=project_id, location_id=location_id,
                )

            # research_directions (MERGE by name)
            for direction_name in basic.get("research_directions") or []:
                if not direction_name: continue
                session.run(
                    "MERGE (d:ResearchDirection {name: $name}) SET d.updated_at = datetime()",
                    name=direction_name
                )
                session.run(
                    """
                    MATCH (p:Project {project_id: $project_id})
                    MATCH (d:ResearchDirection {name: $name})
                    MERGE (p)-[:FOCUSES_ON]->(d)
                    """,
                    project_id=project_id, name=direction_name
                )
                
            # research_topics (MERGE by name)
            for topic in basic.get("research_topics") or []:
                topic_name = topic.get("name")
                if not topic_name: continue
                session.run(
                    "MERGE (t:ResearchTopic {name: $name}) SET t.updated_at = datetime()",
                    name=topic_name
                )
                session.run(
                    """
                    MATCH (p:Project {project_id: $project_id})
                    MATCH (t:ResearchTopic {name: $name})
                    MERGE (p)-[:FOCUSES_ON_TOPIC]->(t)
                    """,
                    project_id=project_id, name=topic_name
                )

            # required_skills (MERGE by name)
            for skill in req.get("required_skills") or []:
                if not isinstance(skill, dict): continue
                skill_name = skill.get("name")
                if not skill_name: continue
                session.run(
                    "MERGE (s:Skill {name: $name}) SET s.updated_at = datetime()",
                    name=skill_name
                )
                session.run(
                    """
                    MATCH (p:Project {project_id: $project_id})
                    MATCH (s:Skill {name: $name})
                    MERGE (p)-[r:REQUIRES_SKILL]->(s)
                    SET r.proficiency_level = $level
                    """,
                    project_id=project_id, name=skill_name, level=skill.get("proficiency_level")
                )

            # target_industries (MERGE by code)
            for target in rel.get("target_industries") or []:
                if not isinstance(target, dict): continue
                ind_code = target.get("code")
                if not ind_code: continue
                session.run(
                    """
                    MERGE (i:Industry {code: $code})
                    SET i.name = $name, i.updated_at = datetime()
                    """,
                    code=ind_code, name=target.get("name")
                )
                session.run(
                    """
                    MATCH (p:Project {project_id: $project_id})
                    MATCH (i:Industry {code: $code})
                    MERGE (p)-[:TARGETS]->(i)
                    """,
                    project_id=project_id, code=ind_code
                )

            # Required Datasets
            for ds_id in rd_prof.get("required_dataset_ids") or []:
                if not ds_id: continue
                session.run(
                    """
                    MATCH (p:Project {project_id: $project_id})
                    MATCH (d:Dataset {dataset_id: $dataset_id})
                    MERGE (p)-[:REQUIRES_DATA]->(d)
                    """,
                    project_id=project_id, dataset_id=ds_id
                )

            # Enterprise partners -> PARTNERS_WITH -> Project
            enterprise_partners = rel.get("enterprise_partners") or []
            for ep in enterprise_partners:
                if not isinstance(ep, dict): continue
                ep_id = ep.get("enterprise_id")
                if not ep_id: continue
                session.run(
                    """
                    MATCH (en:Enterprise {enterprise_id: $enterprise_id})
                    MATCH (p:Project {project_id: $project_id})
                    MERGE (en)-[r:PARTNERS_WITH]->(p)
                    SET r.type = $type
                    """,
                    enterprise_id=ep_id, project_id=project_id, type=ep.get("type")
                )

            # Quan hệ FUNDS từ phía Project (nếu có, để đảm bảo liên kết 2 chiều an toàn)
            project_funders = rel.get("funders") or []
            for fu in project_funders:
                if not isinstance(fu, dict): continue
                fu_id = fu.get("funder_id")
                if not fu_id: continue
                session.run(
                    """
                    MATCH (f:Funder {funder_id: $funder_id})
                    MATCH (p:Project {project_id: $project_id})
                    MERGE (f)-[r:FUNDS]->(p)
                    SET r.grant_period = $grant_period, r.grant_amount = $grant_amount
                    """,
                    funder_id=fu_id, project_id=project_id, 
                    grant_period=fu.get("grant_period"), grant_amount=fu.get("grant_amount")
                )

            stats.record_success("Project")
            if idx % 10 == 0 or idx == total:
                logger.info(f"Progress: {idx}/{total} ({idx/total*100:.1f}%)")

        except Exception as e:
            stats.record_failure("Project", project_id, e)
            logger.error(f"Error syncing Project {project_id}: {e}")

def sync_expert_developed_products(session):
    """Expert -[:DEVELOPS]-> Product (products.developed_by; schema v2)."""
    logger.info("Syncing Expert DEVELOPS -> Product...")
    count = 0
    for pr in mdb.products.find({}):
        product_id = pr.get("product_id")
        if not product_id:
            continue
        developer_ids = pr.get("developer_ids")
        if not developer_ids:
            # Backward compatibility with old schema.
            developer_ids = pr.get("developed_by")

        for eid in developer_ids or []:
            if not eid:
                continue
            try:
                session.run(
                    """
                    MATCH (e:Expert {expert_id: $expert_id})
                    MERGE (o:Product {product_id: $product_id})
                    MERGE (e)-[:DEVELOPS]->(o)
                    """,
                    expert_id=eid,
                    product_id=product_id,
                )
                count += 1
            except Exception as ex:
                logger.warning("DEVELOPS edge %s -> %s: %s", eid, product_id, ex)
    logger.info(f"Ensured {count} DEVELOPS relationship operations")


def sync_products_creates(session):
    """Create Product CREATES relationship with Project nodes"""
    logger.info("Syncing Product CREATES relationships...")
    products = list(mdb.products.find({}))
    total = len(products)
    created = 0

    for idx, pr in enumerate(products, 1):
        product_id = pr.get("product_id")
        linked_project_id = pr.get("linked_project_id")
        if not product_id or not linked_project_id:
            continue

        try:
            session.run(
                """
                MATCH (p:Project {project_id: $project_id})
                MATCH (o:Product {product_id: $product_id})
                MERGE (p)-[:CREATES]->(o)
                """,
                project_id=linked_project_id,
                product_id=product_id,
            )
            created += 1
        except Exception as e:
            logger.error(f"Error syncing CREATES for product {product_id}: {e}")

        if idx % 10 == 0 or idx == total:
            logger.info(f"Progress: {idx}/{total} ({idx/total*100:.1f}%)")

    logger.info(f"Ensured/created {created} CREATES relationships")


# ==========================================
# SYNC: RESEARCH FIELDS
# ==========================================
def sync_research_fields_nodes(session):
    """Phase 1: Create/update all ResearchField nodes (without relationships)"""
    logger.info("Syncing ResearchField nodes...")
    
    fields = list(mdb.research_fields.find({}))
    total = len(fields)
    logger.info(f"Found {total} research fields to sync")
    
    for idx, rf in enumerate(fields, 1):
        field_id = rf.get("field_id")
        
        if not field_id:
            stats.record_skip("ResearchField", "Missing field_id")
            logger.warning(f"Skipping ResearchField without field_id: {rf}")
            continue
        
        try:
            session.run(
                """
                MERGE (f:ResearchField {field_id: $field_id})
                SET f.label = $label,
                    f.description = $description,
                    f.level = $level,
                    f.standard = $standard,
                    f.standard_code = $standard_code,
                    f.updated_at = datetime()
                """,
                **clean_params(
                    field_id=field_id,
                    label=rf.get("label"),
                    description=rf.get("description"),
                    level=safe_get(rf, "hierarchy", "level"),
                    standard=safe_get(rf, "mapping", "standard"),
                    standard_code=safe_get(rf, "mapping", "standard_code")
                )
            )
            stats.record_success("ResearchField")
            
            if idx % 10 == 0 or idx == total:
                logger.info(f"Progress: {idx}/{total} ({idx/total*100:.1f}%)")
                
        except Exception as e:
            stats.record_failure("ResearchField", field_id, e)
            logger.error(f"Error syncing ResearchField {field_id}: {e}")

def sync_research_field_hierarchy(session):
    """Phase 2: Create SUB_FIELD_OF relationships after all nodes exist"""
    logger.info("Syncing ResearchField hierarchy...")
    
    fields = list(mdb.research_fields.find({}))
    relationships_created = 0
    
    for rf in fields:
        field_id = rf.get("field_id")
        parent_id = safe_get(rf, "hierarchy", "parent_id")
        
        if not field_id or not parent_id:
            continue
        
        try:
            result = session.run(
                """
                MATCH (child:ResearchField {field_id: $child_id})
                MATCH (parent:ResearchField {field_id: $parent_id})
                MERGE (child)-[r:SUB_FIELD_OF]->(parent)
                RETURN r
                """,
                child_id=field_id,
                parent_id=parent_id
            )
            
            if result.single():
                relationships_created += 1
                
        except Exception as e:
            logger.error(f"Error creating hierarchy for {field_id} -> {parent_id}: {e}")
    
    logger.info(f"Created {relationships_created} SUB_FIELD_OF relationships")

# ==========================================
# SYNC: INDUSTRIES
# ==========================================
def sync_industries(session):
    """Create Industry nodes"""
    logger.info("Syncing Industries...")
    
    industries = list(mdb.industries.find({}))
    total = len(industries)
    logger.info(f"Found {total} industries to sync")
    
    for idx, ind in enumerate(industries, 1):
        industry_id = ind.get("industry_id")
        
        if not industry_id:
            stats.record_skip("Industry", "Missing industry_id")
            continue
        
        try:
            session.run(
                """
                MERGE (i:Industry {industry_id: $industry_id})
                SET i.industry_name = $industry_name,
                    i.standard_type = $standard_type,
                    i.standard_code = $standard_code,
                    i.updated_at = datetime()
                """,
                **clean_params(
                    industry_id=industry_id,
                    industry_name=ind.get("industry_name"),
                    standard_type=safe_get(ind, "standard_mapping", "type"),
                    standard_code=safe_get(ind, "standard_mapping", "code")
                )
            )
            stats.record_success("Industry")
            
            if idx % 10 == 0 or idx == total:
                logger.info(f"Progress: {idx}/{total} ({idx/total*100:.1f}%)")
                
        except Exception as e:
            stats.record_failure("Industry", industry_id, e)
            logger.error(f"Error syncing Industry {industry_id}: {e}")

# ==========================================
# SYNC: METHOD TECHNIQUES
# ==========================================
def sync_method_techniques(session):
    """Create MethodTechnique nodes and relationships to ResearchField"""
    logger.info("Syncing MethodTechniques...")
    
    techniques = list(mdb.method_techniques.find({}))
    total = len(techniques)
    logger.info(f"Found {total} method techniques to sync")
    
    for idx, mt in enumerate(techniques, 1):
        name = mt.get("name")
        
        if not name:
            stats.record_skip("MethodTechnique", "Missing name")
            continue
        
        try:
            # Create node
            session.run(
                """
                MERGE (m:MethodTechnique {name: $name})
                SET m.tech_id = $tech_id,
                    m.standard_ref = $standard_ref,
                    m.category = $category,
                    m.updated_at = datetime()
                """,
                **clean_params(
                    name=name,
                    tech_id=mt.get("tech_id"),
                    standard_ref=mt.get("standard_ref"),
                    category=mt.get("category")
                )
            )
            
            # Create relationships to ResearchFields (batch)
            related_fields = mt.get("related_fields", []) or []
            if related_fields:
                session.run(
                    """
                    MATCH (m:MethodTechnique {name: $name})
                    UNWIND $field_ids AS field_id
                    MATCH (f:ResearchField {field_id: field_id})
                    MERGE (m)-[:UNDER_FIELD]->(f)
                    """,
                    name=name,
                    field_ids=related_fields
                )
            
            stats.record_success("MethodTechnique")
            
            if idx % 10 == 0 or idx == total:
                logger.info(f"Progress: {idx}/{total} ({idx/total*100:.1f}%)")
                
        except Exception as e:
            stats.record_failure("MethodTechnique", name, e)
            logger.error(f"Error syncing MethodTechnique {name}: {e}")

# ==========================================
# SYNC: EXPERTS
# ==========================================
def sync_experts(session):
    """Create Expert nodes and relationships"""
    logger.info("Syncing Experts...")
    
    experts = list(mdb.experts.find({}))
    total = len(experts)
    logger.info(f"Found {total} experts to sync")
    
    for idx, ex in enumerate(experts, 1):
        expert_id = ex.get("expert_id")
        
        if not expert_id:
            stats.record_skip("Expert", "Missing expert_id")
            continue
        
        try:
            basic = ex.get("basic_info", {})
            metrics = safe_get(ex, "research_capacity", "academic_metrics") or {}
            
            # Create Expert node
            session.run(
                """
                MERGE (e:Expert {expert_id: $expert_id})
                SET e.name = $name,
                    e.birth_year = $birth_year,
                    e.gender = $gender,
                    e.location = $location,
                    e.nationality = $nationality,
                    e.preferred_language = $preferred_language,
                    e.publication_count = $pub_cnt,
                    e.h_index = $h_index,
                    e.citation_count = $cit_cnt,
                    e.i10_index = $i10,
                    e.altmetrics = $altmetrics,
                    e.updated_at = datetime()
                """,
                **clean_params(
                    expert_id=expert_id,
                    name=basic.get("name"),
                    birth_year=basic.get("birth_year"),
                    gender=basic.get("gender"),
                    location=basic.get("location"),
                    nationality=basic.get("nationality"),
                    preferred_language=basic.get("preferred_language"),
                    pub_cnt=metrics.get("publication_count"),
                    h_index=metrics.get("h_index"),
                    cit_cnt=metrics.get("citation_count"),
                    i10=metrics.get("i10_index"),
                    altmetrics=metrics.get("altmetrics")
                )
            )
            
            # Expert -> ResearchField (HAS_EXPERTISE_IN) - Batch
            research_fields = safe_get(ex, "research_capacity", "research_fields") or []
            if research_fields:
                session.run(
                    """
                    MATCH (e:Expert {expert_id: $expert_id})
                    UNWIND $field_ids AS field_id
                    MATCH (f:ResearchField {field_id: field_id})
                    MERGE (e)-[:HAS_EXPERTISE_IN]->(f)
                    """,
                    expert_id=expert_id,
                    field_ids=research_fields
                )
            
            # Expert -> Industry (HAS_APPLICATION_EXPERIENCE_IN) - Batch
            applied_industries = safe_get(ex, "research_capacity", "applied_industries") or []
            if applied_industries:
                session.run(
                    """
                    MATCH (e:Expert {expert_id: $expert_id})
                    UNWIND $industry_ids AS industry_id
                    MATCH (i:Industry {industry_id: industry_id})
                    MERGE (e)-[:HAS_APPLICATION_EXPERIENCE_IN]->(i)
                    """,
                    expert_id=expert_id,
                    industry_ids=applied_industries
                )
            
            # Expert -> MethodTechnique (HAS_SKILL) with proficiency level
            skills_methods = safe_get(ex, "research_capacity", "skills_methods") or []
            for sm in skills_methods:
                skill_name = sm.get("name")
                if not skill_name:
                    continue
                
                session.run(
                    """
                    MATCH (e:Expert {expert_id: $expert_id})
                    MERGE (m:MethodTechnique {name: $name})
                    MERGE (e)-[r:HAS_SKILL]->(m)
                    SET r.proficiency_level = $level
                    """,
                    expert_id=expert_id,
                    name=skill_name,
                    level=sm.get("proficiency_level")
                )
            
            # Expert -> Expert (COLLABORATES_WITH) khi collaborator có expert_id
            collaborators = safe_get(ex, "activities_and_outputs", "collaborators") or []
            for collab in collaborators:
                collab_expert_id = collab.get("expert_id")
                if not collab_expert_id or collab_expert_id == expert_id:
                    continue
                try:
                    session.run(
                        """
                        MATCH (e:Expert {expert_id: $expert_id})
                        MATCH (other:Expert {expert_id: $other_id})
                        MERGE (e)-[r:COLLABORATES_WITH]->(other)
                        SET r.relation_type = $relation_type,
                            r.duration = $duration
                        """,
                        expert_id=expert_id,
                        other_id=collab_expert_id,
                        relation_type=collab.get("relation_type"),
                        duration=collab.get("duration"),
                    )
                except Exception as collab_err:
                    logger.debug(f"Collaborator link {expert_id} -> {collab_expert_id}: {collab_err}")
            
            stats.record_success("Expert")
            
            if idx % 10 == 0 or idx == total:
                logger.info(f"Progress: {idx}/{total} ({idx/total*100:.1f}%)")
                
        except Exception as e:
            stats.record_failure("Expert", expert_id, e)
            logger.error(f"Error syncing Expert {expert_id}: {e}")

# ==========================================
# SYNC: ENTERPRISES
# ==========================================
def sync_enterprises(session):
    """Create Enterprise nodes and relationships"""
    logger.info("Syncing Enterprises...")
    
    enterprises = list(mdb.enterprises.find({}))
    total = len(enterprises)
    logger.info(f"Found {total} enterprises to sync")
    
    for idx, ent in enumerate(enterprises, 1):
        enterprise_id = ent.get("enterprise_id")
        
        if not enterprise_id:
            stats.record_skip("Enterprise", "Missing enterprise_id")
            continue
        
        try:
            basic = ent.get("basic_info", {})
            metrics = basic.get("organization_metrics", {})
            
            # Create Enterprise node (incl. rd_focus_fields for recommendation engine)
            rd_profile = ent.get("rd_profile") or {}
            rd_focus_fields = rd_profile.get("rd_focus_fields") or []
            session.run(
                """
                MERGE (en:Enterprise {enterprise_id: $enterprise_id})
                SET en.name = $name,
                    en.tax_code = $tax_code,
                    en.founded_year = $founded_year,
                    en.location = $location,
                    en.size = $size,
                    en.income = $income,
                    en.employees = $employees,
                    en.rd_focus_fields = $rd_focus_fields,
                    en.updated_at = datetime()
                """,
                **clean_params(
                    enterprise_id=enterprise_id,
                    name=basic.get("name"),
                    tax_code=basic.get("tax_code"),
                    founded_year=basic.get("founded_year"),
                    location=basic.get("location"),
                    size=metrics.get("size"),
                    income=metrics.get("income"),
                    employees=metrics.get("employees"),
                    rd_focus_fields=rd_focus_fields
                )
            )
            
            # Enterprise -> Industry (OPERATES_IN) - Batch
            # Note: Using standard_code to match with Industry nodes
            industry_codes = basic.get("industry_codes", []) or []
            if industry_codes:
                session.run(
                    """
                    MATCH (en:Enterprise {enterprise_id: $enterprise_id})
                    UNWIND $codes AS code
                    MATCH (i:Industry {standard_code: code})
                    MERGE (en)-[:OPERATES_IN]->(i)
                    """,
                    enterprise_id=enterprise_id,
                    codes=industry_codes
                )
            
            stats.record_success("Enterprise")
            
            if idx % 10 == 0 or idx == total:
                logger.info(f"Progress: {idx}/{total} ({idx/total*100:.1f}%)")
                
        except Exception as e:
            stats.record_failure("Enterprise", enterprise_id, e)
            logger.error(f"Error syncing Enterprise {enterprise_id}: {e}")

# ==========================================
# SYNC: FUNDERS
# ==========================================
def sync_funders(session):
    """Create Funder nodes and relationships"""
    logger.info("Syncing Funders...")
    
    funders = list(mdb.funders.find({}))
    total = len(funders)
    logger.info(f"Found {total} funders to sync")
    
    for idx, fu in enumerate(funders, 1):
        funder_id = fu.get("funder_id")
        
        if not funder_id:
            stats.record_skip("Funder", "Missing funder_id")
            continue
        
        try:
            basic = fu.get("basic_info", {})
            
            # Create Funder node (incl. trl_range_focus for recommendation engine)
            strategy = fu.get("funding_strategy") or {}
            session.run(
                """
                MERGE (f:Funder {funder_id: $funder_id})
                SET f.name = $name,
                    f.type = $type,
                    f.location = $location,
                    f.budget_capacity = $budget_capacity,
                    f.trl_range_focus = $trl_range_focus,
                    f.updated_at = datetime()
                """,
                **clean_params(
                    funder_id=funder_id,
                    name=basic.get("name"),
                    type=basic.get("type"),
                    location=basic.get("location"),
                    budget_capacity=basic.get("budget_capacity"),
                    trl_range_focus=strategy.get("trl_range_focus")
                )
            )
            
            # Funder -> ResearchField (SUPPORTS) - Batch
            funding_domains = safe_get(fu, "funding_strategy", "funding_domains") or []
            if funding_domains:
                session.run(
                    """
                    MATCH (fu:Funder {funder_id: $funder_id})
                    UNWIND $field_ids AS field_id
                    MATCH (rf:ResearchField {field_id: field_id})
                    MERGE (fu)-[:SUPPORTS]->(rf)
                    """,
                    funder_id=funder_id,
                    field_ids=funding_domains
                )
            
            stats.record_success("Funder")
            
            if idx % 10 == 0 or idx == total:
                logger.info(f"Progress: {idx}/{total} ({idx/total*100:.1f}%)")
                
        except Exception as e:
            stats.record_failure("Funder", funder_id, e)
            logger.error(f"Error syncing Funder {funder_id}: {e}")

# ==========================================
# SYNC: PROJECTS
# ==========================================
def sync_projects(session):
    """Create Project nodes and all related relationships"""
    logger.info("Syncing Projects...")
    
    projects = list(mdb.projects.find({}))
    total = len(projects)
    logger.info(f"Found {total} projects to sync")
    
    for idx, pr in enumerate(projects, 1):
        project_id = pr.get("project_id")
        
        if not project_id:
            stats.record_skip("Project", "Missing project_id")
            continue
        
        try:
            basic = pr.get("basic_info", {})
            req = pr.get("requirements_and_timeline", {})
            
            # Create Project node (incl. required_skills for recommendation engine)
            required_skills = req.get("required_skills") or []
            session.run(
                """
                MERGE (p:Project {project_id: $project_id})
                SET p.title = $title,
                    p.description = $description,
                    p.status = $status,
                    p.location = $location,
                    p.research_domain = $research_domain,
                    p.trl = $trl,
                    p.budget = $budget,
                    p.required_skills = $required_skills,
                    p.updated_at = datetime()
                """,
                **clean_params(
                    project_id=project_id,
                    title=basic.get("title"),
                    description=basic.get("description"),
                    status=basic.get("status"),
                    location=basic.get("location"),
                    research_domain=basic.get("research_domain"),
                    trl=req.get("technology_readiness_level"),
                    budget=req.get("budget"),
                    required_skills=required_skills
                )
            )
            
            # Project -> ResearchField (BELONGS_TO)
            research_domain = basic.get("research_domain")
            if research_domain:
                session.run(
                    """
                    MATCH (p:Project {project_id: $project_id})
                    MATCH (f:ResearchField {field_id: $field_id})
                    MERGE (p)-[:BELONGS_TO]->(f)
                    """,
                    project_id=project_id,
                    field_id=research_domain
                )
            
            # Expert -> Project (PARTICIPATES_IN)
            participants = safe_get(pr, "relations", "participants") or []
            for part in participants:
                part_expert_id = part.get("expert_id")
                if not part_expert_id:
                    continue
                
                session.run(
                    """
                    MATCH (e:Expert {expert_id: $expert_id})
                    MATCH (p:Project {project_id: $project_id})
                    MERGE (e)-[r:PARTICIPATES_IN]->(p)
                    SET r.role = $role,
                        r.period = $period
                    """,
                    expert_id=part_expert_id,
                    project_id=project_id,
                    role=part.get("role"),
                    period=part.get("period")
                )
            
            # Enterprise -> Project (PARTNERS_WITH)
            enterprise_partners = safe_get(pr, "relations", "enterprise_partners") or []
            for ep in enterprise_partners:
                ep_id = ep.get("enterprise_id")
                if not ep_id:
                    continue
                
                session.run(
                    """
                    MATCH (en:Enterprise {enterprise_id: $enterprise_id})
                    MATCH (p:Project {project_id: $project_id})
                    MERGE (en)-[r:PARTNERS_WITH]->(p)
                    SET r.type = $type
                    """,
                    enterprise_id=ep_id,
                    project_id=project_id,
                    type=ep.get("type")
                )
            
            # Funder -> Project (FUNDS)
            project_funders = safe_get(pr, "relations", "funders") or []
            for fu in project_funders:
                fu_id = fu.get("funder_id")
                if not fu_id:
                    continue
                
                session.run(
                    """
                    MATCH (f:Funder {funder_id: $funder_id})
                    MATCH (p:Project {project_id: $project_id})
                    MERGE (f)-[r:FUNDS]->(p)
                    SET r.grant_period = $grant_period,
                        r.grant_amount = $grant_amount
                    """,
                    funder_id=fu_id,
                    project_id=project_id,
                    grant_period=fu.get("grant_period"),
                    grant_amount=fu.get("grant_amount")
                )
            
            stats.record_success("Project")
            
            if idx % 10 == 0 or idx == total:
                logger.info(f"Progress: {idx}/{total} ({idx/total*100:.1f}%)")
                
        except Exception as e:
            stats.record_failure("Project", project_id, e)
            logger.error(f"Error syncing Project {project_id}: {e}")

# ==========================================
# SYNC: OUTPUT ASSETS (FIXED)
# ==========================================
def sync_output_assets(session):
    """Create OutputAsset nodes and relationships"""
    logger.info("Syncing OutputAssets...")
    
    assets = list(mdb.output_assets.find({}))
    total = len(assets)
    logger.info(f"Found {total} output assets to sync")
    
    for idx, oa in enumerate(assets, 1):
        asset_id = oa.get("asset_id")
        
        if not asset_id:
            stats.record_skip("OutputAsset", "Missing asset_id")
            continue
        
        try:
            meta = oa.get("metadata", {})
            links = oa.get("links", {})
            
            # Create OutputAsset node with dynamic SET clause
            # Base params (always present)
            base_params = {
                "asset_id": asset_id,
            }
            
            # Optional params
            optional_params = {
                "title": oa.get("title"),
                "type": oa.get("type"),
                "publisher": meta.get("publisher"),
                "year": meta.get("year"),
                "status": meta.get("status"),
            }
            
            # Build SET clauses
            set_clauses = ["o.updated_at = datetime()"]
            query_params = base_params.copy()
            
            for key, value in optional_params.items():
                if value is not None:
                    query_params[key] = value
                    set_clauses.append(f"o.{key} = ${key}")
            
            # Execute query with dynamic SET
            query = f"""
                MERGE (o:OutputAsset {{asset_id: $asset_id}})
                SET {', '.join(set_clauses)}
            """
            
            session.run(query, **query_params)
            
            # Project -> OutputAsset (PRODUCES)
            produced_by = links.get("produced_by_project")
            if produced_by:
                session.run(
                    """
                    MATCH (p:Project {project_id: $project_id})
                    MATCH (o:OutputAsset {asset_id: $asset_id})
                    MERGE (p)-[:PRODUCES]->(o)
                    """,
                    project_id=produced_by,
                    asset_id=asset_id
                )
            
            # Enterprise -> OutputAsset (COMMERCIALIZES)
            commercialized_by = links.get("commercialized_by")
            if commercialized_by:
                session.run(
                    """
                    MATCH (e:Enterprise {enterprise_id: $ent_id})
                    MATCH (o:OutputAsset {asset_id: $asset_id})
                    MERGE (e)-[:COMMERCIALIZES]->(o)
                    """,
                    ent_id=commercialized_by,
                    asset_id=asset_id
                )
            
            stats.record_success("OutputAsset")
            
            if idx % 10 == 0 or idx == total:
                logger.info(f"Progress: {idx}/{total} ({idx/total*100:.1f}%)")
                
        except Exception as e:
            stats.record_failure("OutputAsset", asset_id, e)
            logger.error(f"Error syncing OutputAsset {asset_id}: {e}")

# ==========================================
# VERIFICATION FUNCTIONS
# ==========================================
def verify_sync(session):
    """Verify the sync by counting nodes and relationships"""
    logger.info("\n" + "="*60)
    logger.info("VERIFICATION")
    logger.info("="*60)
    
    # Count nodes
    node_counts = session.run("""
        MATCH (n)
        RETURN labels(n)[0] as label, count(n) as count
        ORDER BY count DESC
    """)
    
    logger.info("\nNode counts:")
    for record in node_counts:
        logger.info(f"  {record['label']}: {record['count']}")
    
    # Count relationships
    rel_counts = session.run("""
        MATCH ()-[r]->()
        RETURN type(r) as type, count(r) as count
        ORDER BY count DESC
    """)
    
    logger.info("\nRelationship counts:")
    for record in rel_counts:
        logger.info(f"  {record['type']}: {record['count']}")
    
    logger.info("="*60)

# ==========================================
# MAIN FUNCTION
# ==========================================
def main(clear_graph: bool = False, skip_verify: bool = False, skip_indexes: bool = False):
    """
    Đồng bộ dữ liệu từ MongoDB sang Neo4j.
    :param clear_graph: Xóa toàn bộ graph trong Neo4j trước khi sync (dùng sau khi seed_data.py --force).
    :param skip_verify: Bỏ qua bước kiểm tra số node/relationship cuối.
    :param skip_indexes: Không tạo constraints/indexes (chạy nhanh hơn khi re-sync).
    """
    start_time = datetime.now()
    logger.info("="*60)
    logger.info("STARTING MONGODB -> NEO4J SYNC")
    logger.info(f"Start time: {start_time}")
    logger.info(f"MongoDB: {MONGO_URI} / {MONGO_DB_NAME}")
    logger.info(f"Neo4j: {NEO4J_URI}")
    logger.info("="*60)

    try:
        with driver.session() as session:
            if clear_graph:
                logger.warning("CLEARING EXISTING NEO4J GRAPH...")
                session.run("MATCH (n) DETACH DELETE n")
                logger.info("Graph cleared.")

            if not skip_indexes:
                create_neo4j_constraints_and_indexes(session)
            else:
                logger.info("Skipping constraints/indexes (--no-indexes).")

            # Sync ontology entities first (order matters!)
            logger.info("\n" + "="*60)
            logger.info("PHASE 1: SYNCING ONTOLOGY ENTITIES")
            logger.info("="*60)

            # Schema merged: direction/topic/skill/location nodes sẽ upsert trực tiếp từ main entities
            direction_ids = set()
            topic_ids = set()

            sync_datasets(session)
            sync_products(session)

            logger.info("\n" + "="*60)
            logger.info("PHASE 2: SYNCING MAIN ENTITIES")
            logger.info("="*60)

            sync_experts_new(session, direction_ids=direction_ids, topic_ids=topic_ids)
            sync_enterprises_new(session, direction_ids=direction_ids, topic_ids=topic_ids)
            sync_funders_new(session, direction_ids=direction_ids, topic_ids=topic_ids)
            sync_projects_new(session, direction_ids=direction_ids, topic_ids=topic_ids)
            sync_expert_developed_products(session)

            logger.info("\n" + "="*60)
            logger.info("PHASE 3: SYNCING OUTPUT ASSETS")
            logger.info("="*60)

            sync_products_creates(session)

            if not skip_verify:
                verify_sync(session)
            else:
                logger.info("Verification skipped (--skip-verify).")

    except Exception as e:
        logger.error(f"CRITICAL ERROR during sync: {e}", exc_info=True)
        raise

    finally:
        stats.print_summary()
        mongo_client.close()
        end_time = datetime.now()
        duration = end_time - start_time
        logger.info("\n" + "="*60)
        logger.info("SYNC COMPLETED")
        logger.info(f"End time: {end_time}")
        logger.info(f"Duration: {duration}")
        logger.info("="*60)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Đồng bộ dữ liệu từ MongoDB sang Neo4j (sau khi chạy seed_data.py)."
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Xóa toàn bộ graph Neo4j trước khi sync (khuyến nghị sau khi seed_data.py --force).",
    )
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="Bỏ qua bước kiểm tra số node/relationship cuối.",
    )
    parser.add_argument(
        "--no-indexes",
        action="store_true",
        help="Không tạo constraints/indexes (re-sync nhanh hơn).",
    )
    args = parser.parse_args()
    main(
        clear_graph=args.clear,
        skip_verify=args.skip_verify,
        skip_indexes=args.no_indexes,
    )