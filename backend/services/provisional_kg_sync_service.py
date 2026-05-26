from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from repositories.auth_repo import AuthRepository
from repositories.pgpr_graph_repo import PGPRGraphRepository
from services import provisional_status as st

logger = logging.getLogger(__name__)

RESEARCH_TOPIC_TO_KG_TOPICS = {
    "ai-healthcare": ["topic_medical_imaging", "topic_computer_vision"],
    "computer-vision": ["topic_computer_vision"],
    "machine-learning": ["topic_predictive_maintenance", "topic_graph_analytics"],
    "deep-learning": ["topic_computer_vision"],
    "natural-language-processing": ["topic_knowledge_tracing"],
    "iot": ["topic_grid_stability_prediction"],
    "data-science": ["topic_graph_analytics", "topic_time_series_analysis"],
    "knowledge-graph": ["topic_graph_analytics"],
    "robotics": ["topic_route_optimization"],
    "renewable-energy": ["topic_solar_forecasting", "topic_grid_stability_prediction"],
    "smart-manufacturing": ["topic_predictive_maintenance"],
    "cybersecurity": ["topic_fraud_detection"],
}


class ProvisionalKGSyncService:
    """Sync user-created entities into Neo4j with limited participation."""

    def __init__(
        self,
        repo: Optional[AuthRepository] = None,
        graph_repo: Optional[PGPRGraphRepository] = None,
    ) -> None:
        self.repo = repo or AuthRepository()
        self.graph_repo = graph_repo or PGPRGraphRepository()

    def sync_entity_as_unverified(self, entity_type: str, entity_id: str) -> Dict[str, Any]:
        entity = self.repo.find_entity_by_id(entity_type, entity_id)
        if not entity:
            raise ValueError(f"Entity not found: {entity_type}/{entity_id}")

        self.repo.update_entity_status(entity_type, entity_id, {"kg_sync_status": st.KG_SYNCING})
        try:
            self.graph_repo.ensure_constraints()
            props = self._neo4j_properties(entity_type, entity, verified=False)
            self.graph_repo.upsert_provisional_entity(entity_type, entity_id, props)
            self.graph_repo.upsert_topic_relationships(
                entity_type=entity_type,
                entity_id=entity_id,
                topic_ids=self._kg_topic_ids(list(entity.get("research_topics") or [])),
            )
            updated = self.repo.update_entity_status(
                entity_type,
                entity_id,
                {
                    "kg_sync_status": st.KG_SYNCED_UNVERIFIED,
                    "sync_error": None,
                },
            )
            return updated or entity
        except Exception as exc:
            logger.exception("Provisional KG sync failed for %s/%s", entity_type, entity_id)
            self.repo.update_entity_status(
                entity_type,
                entity_id,
                {
                    "kg_sync_status": st.KG_SYNC_FAILED,
                    "sync_error": str(exc),
                },
            )
            raise

    def retry_sync(self, entity_type: str, entity_id: str) -> Dict[str, Any]:
        return self.sync_entity_as_unverified(entity_type, entity_id)

    def _kg_topic_ids(self, research_topics: list[str]) -> list[str]:
        topic_ids: list[str] = []
        for topic in research_topics or []:
            mapped = RESEARCH_TOPIC_TO_KG_TOPICS.get(str(topic), [str(topic)])
            for topic_id in mapped:
                if topic_id and topic_id not in topic_ids:
                    topic_ids.append(topic_id)
        return topic_ids

    def verify_entity(self, entity_type: str, entity_id: str) -> Dict[str, Any]:
        state = st.verified_state()
        updated = self.repo.update_entity_status(entity_type, entity_id, state)
        self.graph_repo.update_entity_verification_status(entity_type, entity_id, state)
        if not updated:
            raise ValueError(f"Entity not found: {entity_type}/{entity_id}")
        return updated

    def reject_entity(self, entity_type: str, entity_id: str) -> Dict[str, Any]:
        state = {
            "entity_verification_status": st.ENTITY_REJECTED,
            "kg_sync_status": st.KG_REJECTED,
            "visibility": st.VISIBILITY_HIDDEN,
            "participation_scope": st.SCOPE_DISABLED,
            "active": False,
            "trust_weight": 0,
        }
        updated = self.repo.update_entity_status(entity_type, entity_id, state)
        self.graph_repo.update_entity_verification_status(entity_type, entity_id, state)
        if not updated:
            raise ValueError(f"Entity not found: {entity_type}/{entity_id}")
        return updated

    def disable_entity(self, entity_type: str, entity_id: str) -> Dict[str, Any]:
        state = {
            "kg_sync_status": st.KG_DISABLED,
            "visibility": st.VISIBILITY_DISABLED,
            "participation_scope": st.SCOPE_DISABLED,
            "active": False,
            "trust_weight": 0,
        }
        updated = self.repo.update_entity_status(entity_type, entity_id, state)
        self.graph_repo.disable_entity(entity_type, entity_id)
        if not updated:
            raise ValueError(f"Entity not found: {entity_type}/{entity_id}")
        return updated

    def merge_entities(self, entity_type: str, source_entity_id: str, target_entity_id: str) -> Dict[str, Any]:
        source = self.repo.find_entity_by_id(entity_type, source_entity_id)
        target = self.repo.find_entity_by_id(entity_type, target_entity_id)
        if not source:
            raise ValueError(f"Source entity not found: {entity_type}/{source_entity_id}")
        if not target:
            raise ValueError(f"Target entity not found: {entity_type}/{target_entity_id}")

        relinked_users = self.repo.relink_users_from_entity(entity_type, source_entity_id, target)
        state = {
            "kg_sync_status": st.KG_DISABLED,
            "visibility": st.VISIBILITY_DISABLED,
            "participation_scope": st.SCOPE_DISABLED,
            "active": False,
            "trust_weight": 0,
            "matched_existing_entity_id": target_entity_id,
            "merged_into": target_entity_id,
        }
        updated = self.repo.update_entity_status(entity_type, source_entity_id, state)
        self.graph_repo.disable_entity(entity_type, source_entity_id, merged_into=target_entity_id)
        if not updated:
            raise ValueError(f"Entity not found: {entity_type}/{source_entity_id}")
        updated["relinked_users"] = relinked_users
        return updated

    def _neo4j_properties(self, entity_type: str, entity: Dict[str, Any], verified: bool) -> Dict[str, Any]:
        state = st.verified_state() if verified else st.default_unverified_state(
            trust_weight=float(entity.get("trust_weight", 0.5) or 0.5)
        )
        return {
            **state,
            "name": entity.get("name") or entity.get("title") or "",
            "title": entity.get("title") or entity.get("name") or "",
            "email": entity.get("email", ""),
            "user_id": entity.get("user_id") or entity.get("owner_id") or entity.get("owner_user_id"),
            "owner_user_id": entity.get("owner_user_id") or entity.get("owner_id"),
            "owner_entity_id": entity.get("owner_entity_id"),
            "source": entity.get("source", "user_registration"),
            "summary": entity.get("summary") or entity.get("description") or "",
            "active": entity.get("active", True),
            "kg_sync_status": entity.get("kg_sync_status")
            if entity.get("kg_sync_status") == st.KG_MERGE_REQUIRED
            else (st.KG_SYNCED_VERIFIED if verified else st.KG_SYNCED_UNVERIFIED),
            "custom_research_topics": list(entity.get("custom_research_topics") or []),
            "kg_schema_version": st.KG_SCHEMA_VERSION,
            "provisional_sync_version": st.PROVISIONAL_SYNC_VERSION,
        }
