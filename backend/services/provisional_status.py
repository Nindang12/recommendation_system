from __future__ import annotations

ACCOUNT_EMAIL_UNVERIFIED = "email_unverified"
ACCOUNT_EMAIL_VERIFIED = "email_verified"

ENTITY_UNVERIFIED = "unverified"
ENTITY_PENDING_REVIEW = "pending_review"
ENTITY_VERIFIED = "verified"
ENTITY_REJECTED = "rejected"

KG_NOT_SYNCED = "not_synced"
KG_SYNCING = "syncing"
KG_SYNCED_UNVERIFIED = "synced_unverified"
KG_SYNCED_VERIFIED = "synced_verified"
KG_MERGE_REQUIRED = "merge_required"
KG_SYNC_FAILED = "sync_failed"
KG_SYNC_PARTIAL = "sync_partial"
KG_DISABLED = "disabled"
KG_REJECTED = "rejected"

VISIBILITY_PUBLIC = "public"
VISIBILITY_LIMITED = "limited"
VISIBILITY_PRIVATE = "private"
VISIBILITY_HIDDEN = "hidden"
VISIBILITY_DISABLED = "disabled"

SCOPE_PUBLIC = "public"
SCOPE_OWNER_ONLY = "owner_only"
SCOPE_ADMIN_ONLY = "admin_only"
SCOPE_DISABLED = "disabled"

KG_SCHEMA_VERSION = 1
PROVISIONAL_SYNC_VERSION = 1


def default_unverified_state(trust_weight: float = 0.5) -> dict:
    return {
        "entity_verification_status": ENTITY_UNVERIFIED,
        "kg_sync_status": KG_NOT_SYNCED,
        "visibility": VISIBILITY_LIMITED,
        "participation_scope": SCOPE_OWNER_ONLY,
        "allow_as_source": True,
        "recommendable_as_target": False,
        "allow_as_intermediate_node": False,
        "trust_weight": trust_weight,
        "kg_schema_version": KG_SCHEMA_VERSION,
        "provisional_sync_version": PROVISIONAL_SYNC_VERSION,
    }


def verified_state() -> dict:
    return {
        "entity_verification_status": ENTITY_VERIFIED,
        "kg_sync_status": KG_SYNCED_VERIFIED,
        "visibility": VISIBILITY_PUBLIC,
        "participation_scope": SCOPE_PUBLIC,
        "allow_as_source": True,
        "recommendable_as_target": True,
        "allow_as_intermediate_node": True,
        "trust_weight": 1.0,
        "kg_schema_version": KG_SCHEMA_VERSION,
        "provisional_sync_version": PROVISIONAL_SYNC_VERSION,
    }
