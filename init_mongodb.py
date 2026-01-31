from pymongo import MongoClient, ASCENDING, TEXT
from pymongo.errors import CollectionInvalid, OperationFailure
import os
from dotenv import load_dotenv

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
# 2. Danh sách collection
# =========================
# Thực thể chính
MAIN_COLLECTIONS = [
    "experts",           # Chuyên gia / Nhà nghiên cứu
    "enterprises",       # Doanh nghiệp / Tổ chức R&D
    "projects",          # Dự án R&D
    "funders",           # Quỹ tài trợ / Nhà đầu tư
]

# Thực thể bổ trợ (ontology & assets)
AUXILIARY_COLLECTIONS = [
    "research_fields",   # Lĩnh vực nghiên cứu (ResearchField)
    "industries",        # Ngành công nghiệp (Industry)
    "method_techniques", # Phương pháp & Kỹ thuật (MethodTechnique)
    "output_assets",     # Kết quả & Tài sản R&D (OutputAsset)
]

ALL_COLLECTIONS = MAIN_COLLECTIONS + AUXILIARY_COLLECTIONS

for col in ALL_COLLECTIONS:
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
    except OperationFailure as e:
        if "already exists" in str(e):
            print(f"    Index already exists: {kwargs.get('name', keys)}")
        else:
            raise e

# ---- EXPERTS ----
print("\n[Experts]")
create_index_safe(db.experts, [("expert_id", ASCENDING)], unique=True, name="idx_expert_id_unique")
create_index_safe(db.experts, [("basic_info.name", ASCENDING)], name="idx_expert_name")
create_index_safe(db.experts, [("basic_info.location", ASCENDING)], name="idx_expert_location")
create_index_safe(db.experts, [("identifiers.ORCID", ASCENDING)], sparse=True, name="idx_expert_orcid")
create_index_safe(db.experts, [("research_capacity.research_fields", ASCENDING)], name="idx_expert_research_fields")
create_index_safe(db.experts, [("research_capacity.applied_industries", ASCENDING)], name="idx_expert_industries")
create_index_safe(db.experts, [("governance.privacy.privacy_level", ASCENDING)], name="idx_expert_privacy")
# Text index cho tìm kiếm
create_index_safe(db.experts, [
    ("basic_info.name", TEXT),
    ("research_capacity.research_interests", TEXT)
], name="idx_expert_text_search", default_language="none")

# ---- ENTERPRISES ----
print("\n[Enterprises]")
create_index_safe(db.enterprises, [("enterprise_id", ASCENDING)], unique=True, name="idx_enterprise_id_unique")
create_index_safe(db.enterprises, [("basic_info.name", ASCENDING)], name="idx_enterprise_name")
create_index_safe(db.enterprises, [("basic_info.tax_code", ASCENDING)], sparse=True, name="idx_enterprise_tax_code")
create_index_safe(db.enterprises, [("basic_info.industry_codes", ASCENDING)], name="idx_enterprise_industry_codes")
create_index_safe(db.enterprises, [("basic_info.location", ASCENDING)], name="idx_enterprise_location")
create_index_safe(db.enterprises, [("rd_profile.rd_focus_fields", ASCENDING)], name="idx_enterprise_rd_fields")
create_index_safe(db.enterprises, [("governance.privacy.privacy_level", ASCENDING)], name="idx_enterprise_privacy")
# Text index
create_index_safe(db.enterprises, [
    ("basic_info.name", TEXT),
    ("rd_profile.technology_needs.need", TEXT)
], name="idx_enterprise_text_search", default_language="none")

# ---- PROJECTS ----
print("\n[Projects]")
create_index_safe(db.projects, [("project_id", ASCENDING)], unique=True, name="idx_project_id_unique")
create_index_safe(db.projects, [("basic_info.title", ASCENDING)], name="idx_project_title")
create_index_safe(db.projects, [("basic_info.research_domain", ASCENDING)], name="idx_project_domain")
create_index_safe(db.projects, [("basic_info.status", ASCENDING)], name="idx_project_status")
create_index_safe(db.projects, [("basic_info.location", ASCENDING)], name="idx_project_location")
create_index_safe(db.projects, [("requirements_and_timeline.technology_readiness_level", ASCENDING)], name="idx_project_trl")
create_index_safe(db.projects, [("requirements_and_timeline.required_skills", ASCENDING)], name="idx_project_skills")
create_index_safe(db.projects, [("relations.participants.expert_id", ASCENDING)], name="idx_project_participants")
create_index_safe(db.projects, [("relations.enterprise_partners.enterprise_id", ASCENDING)], name="idx_project_enterprises")
create_index_safe(db.projects, [("relations.funders.funder_id", ASCENDING)], name="idx_project_funders")
create_index_safe(db.projects, [("governance.privacy.privacy_level", ASCENDING)], name="idx_project_privacy")
# Compound index cho query phổ biến
create_index_safe(db.projects, [
    ("basic_info.status", ASCENDING),
    ("basic_info.research_domain", ASCENDING)
], name="idx_project_status_domain")
# Text index
create_index_safe(db.projects, [
    ("basic_info.title", TEXT),
    ("basic_info.description", TEXT),
    ("basic_info.keywords", TEXT)
], name="idx_project_text_search", default_language="none")

# ---- FUNDERS ----
print("\n[Funders]")
create_index_safe(db.funders, [("funder_id", ASCENDING)], unique=True, name="idx_funder_id_unique")
create_index_safe(db.funders, [("basic_info.name", ASCENDING)], name="idx_funder_name")
create_index_safe(db.funders, [("basic_info.type", ASCENDING)], name="idx_funder_type")
create_index_safe(db.funders, [("basic_info.location", ASCENDING)], name="idx_funder_location")
create_index_safe(db.funders, [("funding_strategy.funding_domains", ASCENDING)], name="idx_funder_domains")
create_index_safe(db.funders, [("funding_strategy.trl_range_focus", ASCENDING)], name="idx_funder_trl")
create_index_safe(db.funders, [("governance.privacy.privacy_level", ASCENDING)], name="idx_funder_privacy")
# Text index
create_index_safe(db.funders, [
    ("basic_info.name", TEXT),
    ("funding_strategy.eligibility_criteria", TEXT)
], name="idx_funder_text_search", default_language="none")

# ---- RESEARCH FIELDS ----
print("\n[Research Fields]")
create_index_safe(db.research_fields, [("field_id", ASCENDING)], unique=True, name="idx_field_id_unique")
create_index_safe(db.research_fields, [("label", ASCENDING)], name="idx_field_label")
create_index_safe(db.research_fields, [("hierarchy.parent_id", ASCENDING)], sparse=True, name="idx_field_parent")
create_index_safe(db.research_fields, [("hierarchy.level", ASCENDING)], name="idx_field_level")
create_index_safe(db.research_fields, [("mapping.standard_code", ASCENDING)], sparse=True, name="idx_field_standard_code")

# ---- INDUSTRIES ----
print("\n[Industries]")
create_index_safe(db.industries, [("industry_id", ASCENDING)], unique=True, name="idx_industry_id_unique")
create_index_safe(db.industries, [("industry_name", ASCENDING)], name="idx_industry_name")
create_index_safe(db.industries, [("standard_mapping.code", ASCENDING)], sparse=True, name="idx_industry_code")
create_index_safe(db.industries, [("standard_mapping.type", ASCENDING)], name="idx_industry_standard_type")

# ---- METHOD TECHNIQUES ----
print("\n[Method Techniques]")
create_index_safe(db.method_techniques, [("tech_id", ASCENDING)], unique=True, name="idx_tech_id_unique")
create_index_safe(db.method_techniques, [("name", ASCENDING)], name="idx_tech_name")
create_index_safe(db.method_techniques, [("category", ASCENDING)], name="idx_tech_category")
create_index_safe(db.method_techniques, [("related_fields", ASCENDING)], name="idx_tech_related_fields")

# ---- OUTPUT ASSETS ----
print("\n[Output Assets]")
create_index_safe(db.output_assets, [("asset_id", ASCENDING)], unique=True, name="idx_asset_id_unique")
create_index_safe(db.output_assets, [("title", ASCENDING)], name="idx_asset_title")
create_index_safe(db.output_assets, [("type", ASCENDING)], name="idx_asset_type")
create_index_safe(db.output_assets, [("metadata.year", ASCENDING)], name="idx_asset_year")
create_index_safe(db.output_assets, [("links.produced_by_project", ASCENDING)], sparse=True, name="idx_asset_project")
create_index_safe(db.output_assets, [("links.commercialized_by", ASCENDING)], sparse=True, name="idx_asset_commercialized")
# Text index
create_index_safe(db.output_assets, [("title", TEXT)], name="idx_asset_text_search", default_language="none")

# =========================
# 4. Kiểm tra kết quả
# =========================
print("\n" + "="*50)
print("INITIALIZATION COMPLETE")
print("="*50)
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
