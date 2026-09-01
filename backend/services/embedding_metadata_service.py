from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from services import provisional_status as st


class EmbeddingMetadataService:
    """Build and maintain cold-start embedding metadata without running a model."""

    HASH_FIELDS = {
        "entity_type",
        "entity_id",
        "research_topics",
        "skills",
        "industry",
        "location",
        "relevant_relationship_ids",
        "embedding_version",
    }

    @classmethod
    def default_embedding(
        cls,
        entity_type: str,
        entity: Optional[Dict[str, Any]] = None,
        *,
        status: str = st.EMBEDDING_PENDING,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        now = now or datetime.now(timezone.utc)
        source_hash = cls.compute_source_hash(entity_type, entity or {})
        return {
            "status": status,
            "job_id": None,
            "last_event_id": None,
            "retry_count": 0,
            "max_retry": st.EMBEDDING_MAX_RETRY,
            "model": st.EMBEDDING_MODEL_NONE,
            "version": st.EMBEDDING_VERSION,
            "dimension": st.EMBEDDING_DIMENSION,
            "source_hash": source_hash,
            "last_queued_at": None,
            "last_processed_at": None,
            "updated_at": now,
            "error": None,
            "error_type": None,
            "vector": None,
            "normalized": False,
            "signal": st.EMBEDDING_SIGNAL_NONE,
            "locked_by": None,
            "locked_at": None,
        }

    @classmethod
    def refresh_after_source_change(
        cls,
        entity_type: str,
        entity: Dict[str, Any],
        *,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Return a new embedding object if source data changed, else existing/default."""
        now = now or datetime.now(timezone.utc)
        existing = dict(entity.get("embedding") or {})
        current_hash = cls.compute_source_hash(entity_type, entity)
        if not existing:
            return cls.default_embedding(entity_type, entity, now=now)

        previous_hash = existing.get("source_hash")
        if previous_hash == current_hash:
            return existing

        updated = {
            **cls.default_embedding(entity_type, entity, status=st.EMBEDDING_STALE, now=now),
            "job_id": existing.get("job_id"),
            "last_event_id": existing.get("last_event_id"),
            "retry_count": int(existing.get("retry_count") or 0),
            "model": existing.get("model"),
            "version": existing.get("version", st.EMBEDDING_VERSION),
            "dimension": existing.get("dimension", st.EMBEDDING_DIMENSION),
            "last_queued_at": existing.get("last_queued_at"),
            "last_processed_at": existing.get("last_processed_at"),
            "vector": existing.get("vector"),
            "normalized": bool(existing.get("normalized", False)),
            "signal": existing.get("signal", st.EMBEDDING_SIGNAL_NONE),
        }
        updated["source_hash"] = current_hash
        updated["updated_at"] = now
        updated["error"] = None
        updated["error_type"] = None
        return updated

    @classmethod
    def compute_source_hash(cls, entity_type: str, entity: Dict[str, Any]) -> str:
        payload = cls.source_payload(entity_type, entity)
        normalized = cls._normalize(payload)
        raw = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @classmethod
    def source_payload(cls, entity_type: str, entity: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "entity_type": str(entity_type or "").strip().lower(),
            "entity_id": cls._entity_id(entity_type, entity),
            "research_topics": cls._research_topics(entity_type, entity),
            "skills": cls._skills(entity),
            "industry": cls._industry(entity),
            "location": cls._location(entity),
            "relevant_relationship_ids": cls._relationship_ids(entity),
            "embedding_version": st.EMBEDDING_VERSION,
        }

    @classmethod
    def _entity_id(cls, entity_type: str, entity: Dict[str, Any]) -> str:
        fields = {
            "project": ["project_id", "proj_id", "id"],
            "expert": ["expert_id", "id"],
            "enterprise": ["enterprise_id", "id"],
            "funder": ["funder_id", "id"],
        }.get(str(entity_type or "").lower(), ["id"])
        for field in fields:
            value = entity.get(field)
            if value not in (None, "", [], {}):
                return str(value)
        if entity.get("_id") is not None:
            return str(entity["_id"])
        return ""

    @classmethod
    def _research_topics(cls, entity_type: str, entity: Dict[str, Any]) -> List[Any]:
        if str(entity_type).lower() == "expert":
            values = [
                entity.get("research_topics"),
                entity.get("research_interests"),
                cls._get_path(entity, "research_capacity.research_topics"),
                cls._get_path(entity, "research_capacity.research_interests"),
            ]
        elif str(entity_type).lower() == "enterprise":
            values = [
                entity.get("research_topics"),
                cls._get_path(entity, "rd_profile.rd_focus_topics"),
            ]
        elif str(entity_type).lower() == "funder":
            values = [
                entity.get("research_topics"),
                cls._get_path(entity, "funding_strategy.funding_topics"),
            ]
        else:
            values = [
                entity.get("research_topics"),
                cls._get_path(entity, "basic_info.research_topics"),
                cls._get_path(entity, "basic_info.keywords"),
            ]
        return cls._names_from_many(values)

    @classmethod
    def _skills(cls, entity: Dict[str, Any]) -> List[Any]:
        return cls._names_from_many(
            [
                entity.get("skills"),
                entity.get("custom_skills"),
                cls._get_path(entity, "research_capacity.technology"),
                cls._get_path(entity, "research_capacity.skills_methods"),
                cls._get_path(entity, "requirements_and_timeline.required_skills"),
                cls._get_path(entity, "rd_profile.technology_needs"),
            ]
        )

    @classmethod
    def _industry(cls, entity: Dict[str, Any]) -> List[Any]:
        return cls._names_from_many(
            [
                entity.get("industry"),
                entity.get("industries"),
                cls._get_path(entity, "basic_info.industries"),
                cls._get_path(entity, "applied_industries"),
                cls._get_path(entity, "funding_strategy.focus_sectors"),
            ]
        )

    @classmethod
    def _location(cls, entity: Dict[str, Any]) -> Dict[str, Any]:
        location = entity.get("location") or cls._get_path(entity, "basic_info.location") or {}
        if not isinstance(location, dict):
            return {"raw": str(location)}
        return {
            "country": location.get("country") or location.get("country_code") or entity.get("country"),
            "province": location.get("province") or location.get("region") or entity.get("province"),
            "district": location.get("district") or location.get("city") or entity.get("district"),
        }

    @classmethod
    def _relationship_ids(cls, entity: Dict[str, Any]) -> List[Any]:
        values: List[Any] = []
        for key in (
            "owner_entity_id",
            "matched_existing_entity_id",
            "merged_into",
        ):
            if entity.get(key):
                values.append(entity[key])
        for path in (
            "relations.participants",
            "relations.enterprise_partners",
            "relations.funders",
            "relations.rd_projects",
            "activities_and_outputs.projects_participation",
            "funding_history.funded_projects",
        ):
            values.extend(cls._names_from_many([cls._get_path(entity, path)]))
        return values

    @classmethod
    def _names_from_many(cls, values: Iterable[Any]) -> List[Any]:
        out: List[Any] = []
        for value in values:
            if value in (None, "", [], {}):
                continue
            if isinstance(value, list):
                for item in value:
                    name = cls._name_from_item(item)
                    if name not in (None, "", [], {}) and name not in out:
                        out.append(name)
            else:
                name = cls._name_from_item(value)
                if name not in (None, "", [], {}) and name not in out:
                    out.append(name)
        return out

    @staticmethod
    def _name_from_item(item: Any) -> Any:
        if isinstance(item, dict):
            for key in ("id", "topic_id", "skill_id", "industry_id", "project_id", "expert_id", "name", "title", "label"):
                if item.get(key):
                    return item[key]
            return item
        return item

    @staticmethod
    def _get_path(data: Dict[str, Any], path: str) -> Any:
        current: Any = data
        for part in path.split("."):
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        return current

    @classmethod
    def _normalize(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(k).strip().lower(): cls._normalize(v) for k, v in sorted(value.items()) if v not in (None, "", [], {})}
        if isinstance(value, list):
            normalized = [cls._normalize(item) for item in value if item not in (None, "", [], {})]
            return sorted(normalized, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))
        if isinstance(value, str):
            return " ".join(value.strip().lower().split())
        return value
