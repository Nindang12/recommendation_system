from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from models.canonical_taxonomy import (
    CANONICAL_INDUSTRIES,
    CANONICAL_SKILLS,
    CANONICAL_TOPICS,
    normalize_text,
)
from repositories.auth_repo import AuthRepository
from repositories.pgpr_graph_repo import PGPRGraphRepository


class GovernanceActionService:
    """Small, audited governance mutations. No destructive deletes by default."""

    VALID_TAXONOMY_TYPES = {"topic", "skill", "industry"}

    def __init__(
        self,
        repo: Optional[AuthRepository] = None,
        graph_repo: Optional[PGPRGraphRepository] = None,
    ) -> None:
        self.repo = repo or AuthRepository()
        self.graph_repo = graph_repo or PGPRGraphRepository()

    def map_taxonomy_alias(
        self,
        *,
        taxonomy_type: str,
        raw_value: str,
        canonical_id: str,
        reason: str,
        admin_user_id: str,
    ) -> Dict[str, Any]:
        taxonomy_type = str(taxonomy_type or "").strip().lower()
        raw_value = str(raw_value or "").strip()
        canonical_id = str(canonical_id or "").strip()
        reason = str(reason or "").strip()
        if taxonomy_type not in self.VALID_TAXONOMY_TYPES:
            raise ValueError(f"Invalid taxonomy_type: {taxonomy_type}")
        if not raw_value:
            raise ValueError("raw_value is required")
        if not canonical_id:
            raise ValueError("canonical_id is required")
        if not reason:
            raise ValueError("reason is required")
        self._validate_canonical_id(taxonomy_type, canonical_id)

        now = datetime.now(timezone.utc)
        normalized_raw_value = normalize_text(raw_value)
        query = {"taxonomy_type": taxonomy_type, "normalized_raw_value": normalized_raw_value}
        before = self.repo.db.taxonomy_aliases.find_one(query) or {}
        payload = {
            "taxonomy_type": taxonomy_type,
            "raw_value": raw_value,
            "normalized_raw_value": normalized_raw_value,
            "canonical_id": canonical_id,
            "reason": reason,
            "active": True,
            "updated_by": admin_user_id,
            "updated_at": now,
        }
        if not before:
            payload["created_by"] = admin_user_id
            payload["created_at"] = now
        self.repo.db.taxonomy_aliases.update_one(query, {"$set": payload}, upsert=True)
        after = self.repo.db.taxonomy_aliases.find_one(query) or payload
        return {"before": before, "after": after}

    def mark_orphan_cleanup_candidate(
        self,
        *,
        entity_type: str,
        entity_id: str,
        reason: str,
        admin_user_id: str,
    ) -> Dict[str, Any]:
        entity_type = str(entity_type or "").strip().lower()
        entity_id = str(entity_id or "").strip()
        reason = str(reason or "").strip()
        if entity_type not in {"project", "expert", "enterprise", "funder"}:
            raise ValueError(f"Invalid entity_type: {entity_type}")
        if not entity_id:
            raise ValueError("entity_id is required")
        if not reason:
            raise ValueError("reason is required")

        now = datetime.now(timezone.utc)
        repo_before = self.repo.find_entity_by_id(entity_type, entity_id) or {}
        collection = self.repo.get_entity_collection(entity_type)
        id_field = self.repo.entity_id_field(entity_type)
        marker = {
            "cleanup_candidate": True,
            "cleanup_candidate_reason": reason,
            "cleanup_candidate_marked_by": admin_user_id,
            "cleanup_candidate_marked_at": now,
            "updated_at": now,
        }
        if collection is not None and repo_before:
            collection.update_one({id_field: entity_id}, {"$set": marker})

        self.graph_repo.update_entity_verification_status(entity_type, entity_id, marker)
        repo_after = self.repo.find_entity_by_id(entity_type, entity_id) or {**repo_before, **marker}
        return {"before": repo_before, "after": repo_after}

    def disable_orphan_from_recommendation(
        self,
        *,
        entity_type: str,
        entity_id: str,
        reason: str,
        admin_user_id: str,
    ) -> Dict[str, Any]:
        entity_type = str(entity_type or "").strip().lower()
        entity_id = str(entity_id or "").strip()
        reason = str(reason or "").strip()
        if entity_type not in {"project", "expert", "enterprise", "funder"}:
            raise ValueError(f"Invalid entity_type: {entity_type}")
        if not entity_id:
            raise ValueError("entity_id is required")
        if not reason:
            raise ValueError("reason is required")

        now = datetime.now(timezone.utc)
        before = self.repo.find_entity_by_id(entity_type, entity_id) or {}
        collection = self.repo.get_entity_collection(entity_type)
        id_field = self.repo.entity_id_field(entity_type)
        payload = {
            "visibility": "hidden",
            "participation_scope": "disabled",
            "recommendable_as_target": False,
            "allow_as_intermediate_node": False,
            "cleanup_candidate": True,
            "disabled_from_recommendation": True,
            "disabled_from_recommendation_reason": reason,
            "disabled_from_recommendation_by": admin_user_id,
            "disabled_from_recommendation_at": now,
            "updated_at": now,
        }
        if collection is not None and before:
            collection.update_one({id_field: entity_id}, {"$set": payload})
        self.graph_repo.update_entity_verification_status(entity_type, entity_id, payload)
        after = self.repo.find_entity_by_id(entity_type, entity_id) or {**before, **payload}
        return {"before": before, "after": after}

    def request_more_information(
        self,
        *,
        entity_type: str,
        entity_id: str,
        requested_fields: List[str],
        admin_note: str,
        reason: str,
        admin_user_id: str,
    ) -> Dict[str, Any]:
        entity_type = str(entity_type or "").strip().lower()
        entity_id = str(entity_id or "").strip()
        requested_fields = [str(item).strip() for item in requested_fields if str(item).strip()]
        admin_note = str(admin_note or "").strip()
        reason = str(reason or "").strip()
        if entity_type not in {"project", "expert", "enterprise", "funder"}:
            raise ValueError(f"Invalid entity_type: {entity_type}")
        if not entity_id:
            raise ValueError("entity_id is required")
        if not requested_fields:
            raise ValueError("requested_fields is required")
        if not reason:
            raise ValueError("reason is required")

        now = datetime.now(timezone.utc)
        before = self.repo.find_entity_by_id(entity_type, entity_id) or {}
        if not before:
            raise ValueError(f"Entity not found: {entity_type}/{entity_id}")
        request_doc = {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "requested_fields": requested_fields,
            "admin_note": admin_note,
            "reason": reason,
            "status": "open",
            "created_by": admin_user_id,
            "created_at": now,
            "resolved_at": None,
        }
        result = self.repo.db.data_quality_requests.insert_one(request_doc)
        request_doc["_id"] = result.inserted_id

        collection = self.repo.get_entity_collection(entity_type)
        id_field = self.repo.entity_id_field(entity_type)
        marker = {
            "latest_data_quality_request": {
                "request_id": str(result.inserted_id),
                "status": "open",
                "requested_fields": requested_fields,
                "admin_note": admin_note,
                "created_at": now,
            },
            "updated_at": now,
        }
        if collection is not None:
            collection.update_one({id_field: entity_id}, {"$set": marker})
        after = self.repo.find_entity_by_id(entity_type, entity_id) or {**before, **marker}
        return {"before": before, "after": after, "request": request_doc}

    @staticmethod
    def _validate_canonical_id(taxonomy_type: str, canonical_id: str) -> None:
        catalog = {
            "topic": CANONICAL_TOPICS,
            "skill": CANONICAL_SKILLS,
            "industry": CANONICAL_INDUSTRIES,
        }[taxonomy_type]
        if canonical_id not in catalog:
            raise ValueError(f"Unknown canonical_id for {taxonomy_type}: {canonical_id}")
