from __future__ import annotations

DEFAULT_DIMENSION = 128
DEFAULT_RANDOM_SEED = 42
DEFAULT_MIN_POSITIVE_EDGES = 50
DEFAULT_BASELINE_NAME = "v2_after_hybrid_anchor"
DEFAULT_ACTIVE_MODEL = "graphsage_lite_v1"
DEFAULT_CANDIDATE_NAME = "graphsage_real_v1_candidate"

MODEL_STATUS_CANDIDATE = "candidate"
MODEL_STATUS_ACTIVE = "active"
MODEL_STATUS_REJECTED = "rejected"
MODEL_STATUS_ARCHIVED = "archived"
MODEL_STATUS_ROLLBACK = "rollback"

MODEL_STATUSES = {
    MODEL_STATUS_CANDIDATE,
    MODEL_STATUS_ACTIVE,
    MODEL_STATUS_REJECTED,
    MODEL_STATUS_ARCHIVED,
    MODEL_STATUS_ROLLBACK,
}

SENSITIVE_PROPERTY_NAMES = {
    "password",
    "password_hash",
    "hashed_password",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "api_key",
    "email",
    "emails",
    "phone",
    "phones",
    "contact_email",
    "contact_phone",
}

VECTOR_PROPERTY_NAMES = {
    "embedding_vector",
    "embedding",
    "vector",
}

TRAINING_FEATURE_KEYS = {
    "id",
    "name",
    "title",
    "label",
    "type",
    "expert_id",
    "project_id",
    "enterprise_id",
    "funder_id",
    "topic_id",
    "skill_id",
    "industry_id",
    "location_id",
    "research_topics",
    "skills",
    "industry",
    "industries",
    "location",
    "status",
    "entity_verification_status",
    "kg_sync_status",
    "visibility",
    "participation_scope",
    "trust_weight",
    "embedding_status",
    "embedding_model",
    "embedding_version",
    "embedding_dimension",
    "embedding_signal",
}

