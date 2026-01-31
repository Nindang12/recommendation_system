from neo4j import GraphDatabase
from pymongo import MongoClient
import os
from dotenv import load_dotenv
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from collections import defaultdict

load_dotenv()

# ==========================================
# LOGGING CONFIGURATION
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'sync_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

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
    """Remove None values and convert empty lists to None"""
    cleaned = {}
    for key, value in params.items():
        if value is not None:
            if isinstance(value, list) and len(value) == 0:
                cleaned[key] = None
            else:
                cleaned[key] = value
    return cleaned

def batch_execute(session, query: str, items: List[Dict], batch_size: int = 100):
    """Execute query in batches for better performance"""
    total = len(items)
    for i in range(0, total, batch_size):
        batch = items[i:i + batch_size]
        try:
            session.run(query, batch=batch)
            logger.debug(f"Processed batch {i//batch_size + 1}/{(total + batch_size - 1)//batch_size}")
        except Exception as e:
            logger.error(f"Error in batch {i//batch_size + 1}: {e}")
            raise

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
        "CREATE CONSTRAINT field_id_unique IF NOT EXISTS FOR (f:ResearchField) REQUIRE f.field_id IS UNIQUE",
        "CREATE CONSTRAINT industry_id_unique IF NOT EXISTS FOR (i:Industry) REQUIRE i.industry_id IS UNIQUE",
        "CREATE CONSTRAINT asset_id_unique IF NOT EXISTS FOR (o:OutputAsset) REQUIRE o.asset_id IS UNIQUE",
        "CREATE CONSTRAINT method_name_unique IF NOT EXISTS FOR (m:MethodTechnique) REQUIRE m.name IS UNIQUE",
    ]
    
    indexes = [
        "CREATE INDEX expert_name IF NOT EXISTS FOR (e:Expert) ON (e.name)",
        "CREATE INDEX expert_location IF NOT EXISTS FOR (e:Expert) ON (e.location)",
        "CREATE INDEX project_status IF NOT EXISTS FOR (p:Project) ON (p.status)",
        "CREATE INDEX project_trl IF NOT EXISTS FOR (p:Project) ON (p.trl)",
        "CREATE INDEX project_domain IF NOT EXISTS FOR (p:Project) ON (p.research_domain)",
        "CREATE INDEX enterprise_name IF NOT EXISTS FOR (e:Enterprise) ON (e.name)",
        "CREATE INDEX funder_type IF NOT EXISTS FOR (f:Funder) ON (f.type)",
        "CREATE INDEX field_label IF NOT EXISTS FOR (f:ResearchField) ON (f.label)",
        "CREATE INDEX field_level IF NOT EXISTS FOR (f:ResearchField) ON (f.level)",
        "CREATE INDEX industry_name IF NOT EXISTS FOR (i:Industry) ON (i.industry_name)",
        "CREATE INDEX asset_type IF NOT EXISTS FOR (o:OutputAsset) ON (o.type)",
        "CREATE INDEX asset_year IF NOT EXISTS FOR (o:OutputAsset) ON (o.year)",
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
            
            # Create Enterprise node
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
                    employees=metrics.get("employees")
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
            
            # Create Funder node
            session.run(
                """
                MERGE (f:Funder {funder_id: $funder_id})
                SET f.name = $name,
                    f.type = $type,
                    f.location = $location,
                    f.budget_capacity = $budget_capacity,
                    f.updated_at = datetime()
                """,
                **clean_params(
                    funder_id=funder_id,
                    name=basic.get("name"),
                    type=basic.get("type"),
                    location=basic.get("location"),
                    budget_capacity=basic.get("budget_capacity")
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
            
            # Create Project node
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
                    budget=req.get("budget")
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
# SYNC: OUTPUT ASSETS
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
            
            # Create OutputAsset node
            session.run(
                """
                MERGE (o:OutputAsset {asset_id: $asset_id})
                SET o.title = $title,
                    o.type = $type,
                    o.publisher = $publisher,
                    o.year = $year,
                    o.status = $status,
                    o.updated_at = datetime()
                """,
                **clean_params(
                    asset_id=asset_id,
                    title=oa.get("title"),
                    type=oa.get("type"),
                    publisher=meta.get("publisher"),
                    year=meta.get("year"),
                    status=meta.get("status")
                )
            )
            
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
def main():
    """Main sync function with proper error handling and rollback"""
    start_time = datetime.now()
    logger.info("="*60)
    logger.info("STARTING MONGODB -> NEO4J SYNC")
    logger.info(f"Start time: {start_time}")
    logger.info("="*60)
    
    try:
        with driver.session() as session:
            # Optional: Clear existing graph (uncomment if needed)
            # logger.warning("CLEARING EXISTING GRAPH...")
            # session.run("MATCH (n) DETACH DELETE n")
            # logger.info("Graph cleared")
            
            # Create constraints and indexes
            create_neo4j_constraints_and_indexes(session)
            
            # Sync ontology entities first (order matters!)
            logger.info("\n" + "="*60)
            logger.info("PHASE 1: SYNCING ONTOLOGY ENTITIES")
            logger.info("="*60)
            
            # Phase 1: Create ResearchField nodes
            sync_research_fields_nodes(session)
            # Phase 2: Create ResearchField hierarchy
            sync_research_field_hierarchy(session)
            
            sync_industries(session)
            sync_method_techniques(session)
            
            # Sync main entities
            logger.info("\n" + "="*60)
            logger.info("PHASE 2: SYNCING MAIN ENTITIES")
            logger.info("="*60)
            
            sync_experts(session)
            sync_enterprises(session)
            sync_funders(session)
            sync_projects(session)
            
            # Sync output assets last (depends on Projects)
            logger.info("\n" + "="*60)
            logger.info("PHASE 3: SYNCING OUTPUT ASSETS")
            logger.info("="*60)
            
            sync_output_assets(session)
            
            # Verify sync
            verify_sync(session)
            
    except Exception as e:
        logger.error(f"CRITICAL ERROR during sync: {e}", exc_info=True)
        raise
    
    finally:
        # Print statistics
        stats.print_summary()
        
        # Close connections
        driver.close()
        mongo_client.close()
        
        end_time = datetime.now()
        duration = end_time - start_time
        
        logger.info("\n" + "="*60)
        logger.info("SYNC COMPLETED")
        logger.info(f"End time: {end_time}")
        logger.info(f"Duration: {duration}")
        logger.info("="*60)

if __name__ == "__main__":
    main()