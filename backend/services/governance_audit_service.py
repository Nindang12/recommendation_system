from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo.errors import PyMongoError

from repositories.auth_repo import AuthRepository
from repositories.pgpr_graph_repo import PGPRGraphRepository
from services import provisional_status as st
from services.data_quality_service import DataQualityService
from models.canonical_taxonomy import normalize_text


class GovernanceAuditService:
    """Read-only data governance audit for Phase 11."""

    ENTITY_TYPES = ("expert", "enterprise", "funder", "project")

    def __init__(
        self,
        repo: Optional[AuthRepository] = None,
        graph_repo: Optional[PGPRGraphRepository] = None,
        data_quality: Optional[DataQualityService] = None,
    ) -> None:
        self.repo = repo or AuthRepository()
        self.graph_repo = graph_repo or PGPRGraphRepository()
        self.data_quality = data_quality or DataQualityService(self._load_taxonomy_aliases())

    def audit_entities(self, limit: int = 100) -> Dict[str, Any]:
        rows: List[Dict[str, Any]] = []
        summary = {
            "total": 0,
            "by_quality_level": {},
            "by_review_status": {},
            "unmapped_taxonomy_warnings": 0,
            "duplicate_or_merge_required": 0,
            "available": True,
        }
        per_type_limit = max(1, int(limit))
        for entity_type in self.ENTITY_TYPES:
            collection = self.repo.get_entity_collection(entity_type)
            if collection is None:
                continue
            id_field = self.repo.entity_id_field(entity_type)
            try:
                cursor = collection.find({}).sort("updated_at", -1).limit(per_type_limit)
                docs = list(cursor)
            except PyMongoError as exc:
                summary["available"] = False
                summary["error"] = str(exc)
                break
            for doc in docs:
                entity_id = str(doc.get(id_field) or doc.get("_id"))
                quality = self.data_quality.evaluate(entity_type, doc)
                review_status = self.data_quality.review_status(entity_type, doc, quality)
                row = {
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "name": self._display_name(doc),
                    "kg_sync_status": doc.get("kg_sync_status"),
                    "entity_verification_status": doc.get("entity_verification_status"),
                    "participation_scope": doc.get("participation_scope"),
                    "trust_weight": doc.get("trust_weight"),
                    "review_status": review_status,
                    "data_quality": quality,
                    "duplicate_candidates_count": len(doc.get("duplicate_candidates") or []),
                    "matched_existing_entity_id": doc.get("matched_existing_entity_id"),
                    "updated_at": self._json_safe(doc.get("updated_at")),
                }
                rows.append(row)
                summary["total"] += 1
                self._inc(summary["by_quality_level"], str(quality.get("level")))
                self._inc(summary["by_review_status"], review_status)
                if any(str(w).startswith("unmapped_") for w in quality.get("warnings") or []):
                    summary["unmapped_taxonomy_warnings"] += 1
                if review_status == "merge_required":
                    summary["duplicate_or_merge_required"] += 1
        rows.sort(key=lambda item: (item["data_quality"]["score"], item["updated_at"] or ""), reverse=False)
        return {"summary": summary, "items": rows[:limit]}

    def review_queue(
        self,
        *,
        review_status: Optional[str] = None,
        level: Optional[str] = None,
        has_unmapped_taxonomy: Optional[bool] = None,
        has_duplicate_candidates: Optional[bool] = None,
        entity_type: Optional[str] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Return admin-facing governance queue rows without mutating data."""
        audit = self.audit_entities(limit=max(limit, 100))
        rows: List[Dict[str, Any]] = []
        for item in audit.get("items") or []:
            quality = item.get("data_quality") or {}
            warnings = quality.get("warnings") or []
            unmapped_values = [warning for warning in warnings if str(warning).startswith("unmapped_")]
            duplicate_count = int(item.get("duplicate_candidates_count") or 0)
            if entity_type and item.get("entity_type") != entity_type:
                continue
            if review_status and item.get("review_status") != review_status:
                continue
            if level and quality.get("level") != level:
                continue
            if has_unmapped_taxonomy is not None and bool(unmapped_values) != has_unmapped_taxonomy:
                continue
            if has_duplicate_candidates is not None and bool(duplicate_count) != has_duplicate_candidates:
                continue
            rows.append(
                {
                    "entity_id": item.get("entity_id"),
                    "entity_type": item.get("entity_type"),
                    "name": item.get("name"),
                    "data_quality": {
                        "score": quality.get("score"),
                        "level": quality.get("level"),
                        "missing_fields": quality.get("missing_fields") or [],
                        "warnings": warnings,
                    },
                    "review_status": item.get("review_status"),
                    "unmapped_taxonomy_values": unmapped_values,
                    "duplicate_candidates_count": duplicate_count,
                    "matched_existing_entity_id": item.get("matched_existing_entity_id"),
                    "recommended_action": self._recommended_action(item),
                    "kg_sync_status": item.get("kg_sync_status"),
                    "entity_verification_status": item.get("entity_verification_status"),
                    "participation_scope": item.get("participation_scope"),
                    "trust_weight": item.get("trust_weight"),
                    "updated_at": item.get("updated_at"),
                }
            )
        return {
            "available": bool((audit.get("summary") or {}).get("available", True)),
            "source_summary": audit.get("summary") or {},
            "items": rows[:limit],
            "count": len(rows[:limit]),
        }

    def audit_orphans(self, limit: int = 100) -> Dict[str, Any]:
        query = """
        MATCH (n)
        WHERE NOT (n)--()
        WITH n, labels(n) AS labels
        RETURN labels,
               coalesce(
                 n.project_id, n.expert_id, n.enterprise_id, n.funder_id,
                 n.topic_id, n.skill_id, n.industry_id, n.location_id, n.id
               ) AS entity_id,
               coalesce(n.name, n.title, n.label, n.topic_id, n.skill_id, n.industry_id, n.location_id, n.id) AS name,
               n.entity_verification_status AS entity_verification_status,
               n.kg_sync_status AS kg_sync_status,
               n.visibility AS visibility,
               n.participation_scope AS participation_scope
        LIMIT $limit
        """
        try:
            rows = self.graph_repo.run_read(query, limit=int(limit), timeout=8)
        except Exception as exc:
            return {"available": False, "error": str(exc), "items": [], "summary": {"orphan_nodes": 0}}
        items = [self._json_safe(row) for row in rows]
        by_label: Dict[str, int] = {}
        for row in items:
            labels = row.get("labels") or ["unknown"]
            label = str(labels[0] if labels else "unknown")
            self._inc(by_label, label)
        return {
            "available": True,
            "summary": {"orphan_nodes": len(items), "by_label": by_label},
            "items": items,
        }

    def audit_provisional_lifecycle(self, max_age_days: int = 30, limit: int = 100) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        items: List[Dict[str, Any]] = []
        summary = {"total_provisional": 0, "stale_provisional": 0, "by_status": {}}
        for entity_type in self.ENTITY_TYPES:
            collection = self.repo.get_entity_collection(entity_type)
            if collection is None:
                continue
            id_field = self.repo.entity_id_field(entity_type)
            query = {
                "$or": [
                    {"entity_verification_status": {"$ne": st.ENTITY_VERIFIED}},
                    {"participation_scope": st.SCOPE_OWNER_ONLY},
                    {"kg_sync_status": {"$in": [st.KG_SYNCED_UNVERIFIED, st.KG_MERGE_REQUIRED, st.KG_SYNC_FAILED]}},
                ]
            }
            try:
                docs = list(collection.find(query).sort("updated_at", -1).limit(limit))
            except PyMongoError as exc:
                return {
                    "summary": {**summary, "available": False, "error": str(exc)},
                    "items": items,
                    "max_age_days": max_age_days,
                }
            for doc in docs:
                created_at = doc.get("created_at") or doc.get("updated_at")
                age_days = self._age_days(now, created_at)
                is_stale = age_days is not None and age_days >= max_age_days
                kg_status = str(doc.get("kg_sync_status") or "")
                summary["total_provisional"] += 1
                self._inc(summary["by_status"], kg_status or "unknown")
                if is_stale:
                    summary["stale_provisional"] += 1
                items.append(
                    {
                        "entity_type": entity_type,
                        "entity_id": str(doc.get(id_field) or doc.get("_id")),
                        "name": self._display_name(doc),
                        "age_days": age_days,
                        "is_stale": is_stale,
                        "kg_sync_status": doc.get("kg_sync_status"),
                        "entity_verification_status": doc.get("entity_verification_status"),
                        "participation_scope": doc.get("participation_scope"),
                    }
                )
        items.sort(key=lambda item: item.get("age_days") or -1, reverse=True)
        return {"summary": summary, "items": items[:limit], "max_age_days": max_age_days}

    def retention_summary(self) -> Dict[str, Any]:
        collections = {
            "embedding_event_outbox": "published events older than 30-90 days can be archived/deleted",
            "admin_audit_logs": "keep at least 365 days for governance traceability",
            "embedding_failed_jobs": "keep failed/DLQ samples 30-90 days after resolution",
        }
        summary: Dict[str, Any] = {}
        for name, policy in collections.items():
            try:
                count = int(self.repo.db[name].count_documents({}))
            except Exception:
                count = None
            summary[name] = {"count": count, "policy": policy}
        return summary

    def _load_taxonomy_aliases(self) -> Dict[str, set[str]]:
        aliases: Dict[str, set[str]] = {"topic": set(), "skill": set(), "industry": set()}
        try:
            for row in self.repo.db.taxonomy_aliases.find({"active": {"$ne": False}}):
                taxonomy_type = str(row.get("taxonomy_type") or "").lower()
                raw_value = row.get("raw_value")
                if taxonomy_type in aliases and raw_value:
                    aliases[taxonomy_type].add(normalize_text(raw_value))
        except Exception:
            pass
        return aliases

    def full_audit(self, limit: int = 100, max_age_days: int = 30) -> Dict[str, Any]:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "read_only": True,
            "entities": self.audit_entities(limit=limit),
            "orphans": self.audit_orphans(limit=limit),
            "provisional_lifecycle": self.audit_provisional_lifecycle(
                max_age_days=max_age_days,
                limit=limit,
            ),
            "retention": self.retention_summary(),
        }

    def _display_name(self, doc: Dict[str, Any]) -> str:
        for path in ("name", "title", "basic_info.name", "basic_info.title"):
            value = self._get_path(doc, path)
            if value not in (None, "", [], {}):
                return str(value)
        return ""

    @staticmethod
    def _recommended_action(item: Dict[str, Any]) -> str:
        review_status = item.get("review_status")
        quality = item.get("data_quality") or {}
        warnings = quality.get("warnings") or []
        if review_status == "merge_required":
            return "review_duplicate_or_merge"
        if any(str(w).startswith("unmapped_") for w in warnings):
            return "map_taxonomy_alias"
        if review_status == "needs_more_info":
            return "request_more_information"
        if item.get("kg_sync_status") in {st.KG_SYNC_FAILED, st.KG_SYNC_PARTIAL, st.KG_NOT_SYNCED}:
            return "retry_or_review_kg_sync"
        if review_status == "pending_review":
            return "admin_verify_or_reject"
        if review_status == "rejected":
            return "keep_hidden_or_archive"
        return "no_action_required"

    @staticmethod
    def _get_path(data: Dict[str, Any], path: str) -> Any:
        current: Any = data
        for part in path.split("."):
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        return current

    @staticmethod
    def _inc(bucket: Dict[str, int], key: str) -> None:
        bucket[key] = int(bucket.get(key, 0)) + 1

    @staticmethod
    def _age_days(now: datetime, value: Any) -> Optional[int]:
        if not isinstance(value, datetime):
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return max(0, (now - value).days)

    def _json_safe(self, value: Any) -> Any:
        if isinstance(value, ObjectId):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, list):
            return [self._json_safe(item) for item in value]
        if isinstance(value, dict):
            return {str(key): self._json_safe(item) for key, item in value.items()}
        return value
