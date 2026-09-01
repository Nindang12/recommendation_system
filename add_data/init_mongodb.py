import os

from dotenv import load_dotenv
from pymongo import ASCENDING, TEXT, MongoClient
from pymongo.errors import OperationFailure

load_dotenv()

# =========================
# 1. Kết nối MongoDB
# =========================
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGO_DB_NAME", "rd_recommendation_system")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

print(f"Connected to MongoDB database: {DB_NAME}")

# =========================
# 2. Collection schema merged
# =========================
COLLECTIONS = ["experts", "enterprises", "projects", "funders", "products", "datasets"]

for col in COLLECTIONS:
    if col not in db.list_collection_names():
        db.create_collection(col)
        print(f"[+] Created collection: {col}")
    else:
        print(f"[=] Collection already exists: {col}")


# =========================
# 3. Tạo Index
# =========================
def create_index_safe(collection, keys, **kwargs):
    """Tạo index an toàn, bỏ qua nếu đã tồn tại."""
    try:
        collection.create_index(keys, **kwargs)
        print(f"    Index created: {kwargs.get('name', keys)}")
    except OperationFailure as exc:
        if "already exists" in str(exc):
            print(f"    Index already exists: {kwargs.get('name', keys)}")
        else:
            raise


# ---- EXPERTS ----
print("\n[Experts]")
create_index_safe(db.experts, [("expert_id", ASCENDING)], unique=True, name="idx_expert_id_unique")
create_index_safe(db.experts, [("basic_info.name", ASCENDING)], name="idx_expert_name")
create_index_safe(db.experts, [("basic_info.birth_year", ASCENDING)], sparse=True, name="idx_expert_birth_year")
create_index_safe(db.experts, [("basic_info.location.country_code", ASCENDING)], sparse=True, name="idx_expert_country_code")
create_index_safe(db.experts, [("basic_info.location.region", ASCENDING)], sparse=True, name="idx_expert_region")
create_index_safe(db.experts, [("identifiers.ORCID", ASCENDING)], sparse=True, name="idx_expert_orcid")
create_index_safe(db.experts, [("identifiers.Scopus_ID", ASCENDING)], sparse=True, name="idx_expert_scopus")
create_index_safe(db.experts, [("identifiers.ResearcherID", ASCENDING)], sparse=True, name="idx_expert_researcherid")
create_index_safe(db.experts, [("research_capacity.research_directions", ASCENDING)], sparse=True, name="idx_expert_research_directions")
create_index_safe(db.experts, [("research_capacity.research_topics.name", ASCENDING)], sparse=True, name="idx_expert_research_topic_name")
create_index_safe(
    db.experts,
    [("research_capacity.research_topics.parent_direction", ASCENDING)],
    sparse=True,
    name="idx_expert_research_topic_parent_direction",
)
create_index_safe(db.experts, [("research_capacity.skills_methods.name", ASCENDING)], sparse=True, name="idx_expert_skill_name")
create_index_safe(db.experts, [("research_capacity.applied_industries.code", ASCENDING)], sparse=True, name="idx_expert_applied_industry_code")
create_index_safe(db.experts, [("research_capacity.applied_industries.name", ASCENDING)], sparse=True, name="idx_expert_applied_industry_name")
create_index_safe(db.experts, [("activities_and_outputs.list_outputs.type", ASCENDING)], sparse=True, name="idx_expert_output_type")
create_index_safe(db.experts, [("activities_and_outputs.owned_dataset_ids", ASCENDING)], sparse=True, name="idx_expert_owned_datasets")
create_index_safe(db.experts, [("activities_and_outputs.collaborators.expert_id", ASCENDING)], sparse=True, name="idx_expert_collaborator_expert_id")
create_index_safe(db.experts, [("activities_and_outputs.projects_participation.project_id", ASCENDING)], sparse=True, name="idx_expert_project_participation_project_id")
create_index_safe(db.experts, [("activities_and_outputs.grant_history.funder_id", ASCENDING)], sparse=True, name="idx_expert_grant_funder_id")
create_index_safe(db.experts, [("governance.privacy.privacy_level", ASCENDING)], sparse=True, name="idx_expert_privacy")
create_index_safe(
    db.experts,
    [
        ("basic_info.name", TEXT),
        ("basic_info.bio", TEXT),
        ("research_capacity.research_directions", TEXT),
        ("research_capacity.research_topics.name", TEXT),
    ],
    name="idx_expert_text_search",
    default_language="none",
)

# ---- ENTERPRISES ----
print("\n[Enterprises]")
create_index_safe(db.enterprises, [("enterprise_id", ASCENDING)], unique=True, name="idx_enterprise_id_unique")
create_index_safe(db.enterprises, [("basic_info.name", ASCENDING)], name="idx_enterprise_name")
create_index_safe(db.enterprises, [("basic_info.tax_code", ASCENDING)], sparse=True, name="idx_enterprise_tax_code")
create_index_safe(db.enterprises, [("basic_info.location.country_code", ASCENDING)], sparse=True, name="idx_enterprise_country_code")
create_index_safe(db.enterprises, [("basic_info.industries.code", ASCENDING)], sparse=True, name="idx_enterprise_industry_code")
create_index_safe(db.enterprises, [("basic_info.industries.name", ASCENDING)], sparse=True, name="idx_enterprise_industry_name")
create_index_safe(db.enterprises, [("rd_profile.rd_focus_directions", ASCENDING)], sparse=True, name="idx_enterprise_rd_focus_directions")
create_index_safe(db.enterprises, [("rd_profile.rd_focus_topics.name", ASCENDING)], sparse=True, name="idx_enterprise_rd_focus_topic_name")
create_index_safe(
    db.enterprises,
    [("rd_profile.rd_focus_topics.parent_direction", ASCENDING)],
    sparse=True,
    name="idx_enterprise_rd_focus_topic_parent_direction",
)
create_index_safe(db.enterprises, [("rd_profile.technology_needs.required_skills.name", ASCENDING)], sparse=True, name="idx_enterprise_required_skill_name")
create_index_safe(db.enterprises, [("relations.rd_projects.project_id", ASCENDING)], sparse=True, name="idx_enterprise_rd_project_id")
create_index_safe(db.enterprises, [("relations.worked_experts.expert_id", ASCENDING)], sparse=True, name="idx_enterprise_worked_expert_id")
create_index_safe(db.enterprises, [("governance.privacy.privacy_level", ASCENDING)], sparse=True, name="idx_enterprise_privacy")
create_index_safe(
    db.enterprises,
    [
        ("basic_info.name", TEXT),
        ("rd_profile.rd_focus_directions", TEXT),
        ("rd_profile.rd_focus_topics.name", TEXT),
        ("rd_profile.technology_needs.need", TEXT),
        ("rd_profile.technology_needs.required_skills.name", TEXT),
    ],
    name="idx_enterprise_text_search",
    default_language="none",
)

# ---- PROJECTS ----
print("\n[Projects]")
create_index_safe(db.projects, [("project_id", ASCENDING)], unique=True, name="idx_project_id_unique")
create_index_safe(db.projects, [("basic_info.title", ASCENDING)], name="idx_project_title")
create_index_safe(db.projects, [("basic_info.status", ASCENDING)], sparse=True, name="idx_project_status")
create_index_safe(db.projects, [("basic_info.research_directions", ASCENDING)], sparse=True, name="idx_project_research_directions")
create_index_safe(db.projects, [("basic_info.research_topics.name", ASCENDING)], sparse=True, name="idx_project_research_topic_name")
create_index_safe(
    db.projects,
    [("basic_info.research_topics.parent_direction", ASCENDING)],
    sparse=True,
    name="idx_project_research_topic_parent_direction",
)
create_index_safe(db.projects, [("basic_info.location.country_code", ASCENDING)], sparse=True, name="idx_project_country_code")
create_index_safe(db.projects, [("requirements_and_timeline.technology_readiness_level", ASCENDING)], sparse=True, name="idx_project_trl")
create_index_safe(db.projects, [("requirements_and_timeline.required_skills.name", ASCENDING)], sparse=True, name="idx_project_required_skill_name")
create_index_safe(db.projects, [("rd_profile.required_dataset_ids", ASCENDING)], sparse=True, name="idx_project_required_dataset_ids")
create_index_safe(db.projects, [("relations.participants.expert_id", ASCENDING)], sparse=True, name="idx_project_participant_expert_id")
create_index_safe(db.projects, [("relations.enterprise_partners.enterprise_id", ASCENDING)], sparse=True, name="idx_project_enterprise_partner_id")
create_index_safe(db.projects, [("relations.funders.funder_id", ASCENDING)], sparse=True, name="idx_project_funder_id")
create_index_safe(db.projects, [("relations.target_industries.code", ASCENDING)], sparse=True, name="idx_project_target_industry_code")
create_index_safe(db.projects, [("governance.privacy.privacy_level", ASCENDING)], sparse=True, name="idx_project_privacy")
create_index_safe(
    db.projects,
    [("basic_info.status", ASCENDING), ("basic_info.research_directions", ASCENDING)],
    name="idx_project_status_direction",
)
create_index_safe(
    db.projects,
    [("basic_info.status", ASCENDING), ("basic_info.research_topics.name", ASCENDING)],
    name="idx_project_status_topic",
)
create_index_safe(
    db.projects,
    [
        ("basic_info.title", TEXT),
        ("basic_info.description", TEXT),
        ("basic_info.keywords", TEXT),
        ("basic_info.research_directions", TEXT),
        ("basic_info.research_topics.name", TEXT),
    ],
    name="idx_project_text_search",
    default_language="none",
)

# ---- FUNDERS ----
print("\n[Funders]")
create_index_safe(db.funders, [("funder_id", ASCENDING)], unique=True, name="idx_funder_id_unique")
create_index_safe(db.funders, [("basic_info.name", ASCENDING)], name="idx_funder_name")
create_index_safe(db.funders, [("basic_info.type", ASCENDING)], sparse=True, name="idx_funder_type")
create_index_safe(db.funders, [("basic_info.location.country_code", ASCENDING)], sparse=True, name="idx_funder_country_code")
create_index_safe(db.funders, [("funding_strategy.funding_directions", ASCENDING)], sparse=True, name="idx_funder_funding_directions")
create_index_safe(db.funders, [("funding_strategy.funding_topics.name", ASCENDING)], sparse=True, name="idx_funder_funding_topic_name")
create_index_safe(
    db.funders,
    [("funding_strategy.funding_topics.parent_direction", ASCENDING)],
    sparse=True,
    name="idx_funder_funding_topic_parent_direction",
)
create_index_safe(db.funders, [("funding_strategy.focus_regions", ASCENDING)], sparse=True, name="idx_funder_focus_regions")
create_index_safe(db.funders, [("funding_strategy.focus_sectors.code", ASCENDING)], sparse=True, name="idx_funder_focus_sector_code")
create_index_safe(db.funders, [("funding_strategy.focus_sectors.name", ASCENDING)], sparse=True, name="idx_funder_focus_sector_name")
create_index_safe(db.funders, [("funding_strategy.trl_range_focus.min", ASCENDING)], sparse=True, name="idx_funder_trl_min")
create_index_safe(db.funders, [("funding_strategy.trl_range_focus.max", ASCENDING)], sparse=True, name="idx_funder_trl_max")
create_index_safe(db.funders, [("programs.program_id", ASCENDING)], sparse=True, name="idx_funder_program_id")
create_index_safe(db.funders, [("programs.target_industries.code", ASCENDING)], sparse=True, name="idx_funder_program_target_industry_code")
create_index_safe(db.funders, [("funding_history.funded_projects.project_id", ASCENDING)], sparse=True, name="idx_funder_funded_project_id")
create_index_safe(db.funders, [("relations.invests_in_enterprise_ids", ASCENDING)], sparse=True, name="idx_funder_invest_enterprise")
create_index_safe(db.funders, [("relations.collaborates_with_funder_ids", ASCENDING)], sparse=True, name="idx_funder_collab_funder")
create_index_safe(db.funders, [("governance.privacy.privacy_level", ASCENDING)], sparse=True, name="idx_funder_privacy")
create_index_safe(
    db.funders,
    [
        ("basic_info.name", TEXT),
        ("funding_strategy.funding_directions", TEXT),
        ("funding_strategy.funding_topics.name", TEXT),
        ("funding_strategy.eligibility_criteria", TEXT),
    ],
    name="idx_funder_text_search",
    default_language="none",
)

# ---- PRODUCTS ----
print("\n[Products]")
create_index_safe(db.products, [("product_id", ASCENDING)], unique=True, name="idx_product_id_unique")
create_index_safe(db.products, [("type", ASCENDING)], sparse=True, name="idx_product_type")
create_index_safe(db.products, [("trl", ASCENDING)], sparse=True, name="idx_product_trl")
create_index_safe(db.products, [("year", ASCENDING)], sparse=True, name="idx_product_year")
create_index_safe(db.products, [("linked_project_id", ASCENDING)], sparse=True, name="idx_product_linked_project")
create_index_safe(db.products, [("developer_ids", ASCENDING)], sparse=True, name="idx_product_developed_by")
create_index_safe(db.products, [("license", ASCENDING)], sparse=True, name="idx_product_license")
create_index_safe(db.products, [("name", TEXT)], name="idx_product_text_search", default_language="none")

# ---- DATASETS ----
print("\n[Datasets]")
create_index_safe(db.datasets, [("dataset_id", ASCENDING)], unique=True, name="idx_dataset_id_unique")
create_index_safe(db.datasets, [("format", ASCENDING)], sparse=True, name="idx_dataset_format")
create_index_safe(db.datasets, [("license", ASCENDING)], sparse=True, name="idx_dataset_license")
create_index_safe(db.datasets, [("owner_ids", ASCENDING)], sparse=True, name="idx_dataset_owner_ids")
create_index_safe(db.datasets, [("domain_tags", ASCENDING)], sparse=True, name="idx_dataset_domain_tags")
create_index_safe(db.datasets, [("size_mb", ASCENDING)], sparse=True, name="idx_dataset_size_mb")
create_index_safe(db.datasets, [("name", TEXT), ("description", TEXT)], name="idx_dataset_text_search", default_language="none")

# =========================
# 4. Kiểm tra kết quả
# =========================
print("\n" + "=" * 50)
print("INITIALIZATION COMPLETE")
print("=" * 50)
print(f"\nDatabase: {DB_NAME}")
print(f"Total collections: {len(db.list_collection_names())}")
print("\nCollections:")
for name in sorted(db.list_collection_names()):
    count = db[name].count_documents({})
    indexes = len(db[name].index_information())
    print(f"  - {name}: {count} documents, {indexes} indexes")

# =========================
# 5. Đóng kết nối
# =========================
# client.close()
# print("\nMongoDB connection closed.")
