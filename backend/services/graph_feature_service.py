from __future__ import annotations

from typing import Any, Dict, List, Optional

from repositories.auth_repo import AuthRepository
from repositories.pgpr_graph_repo import PGPRGraphRepository
from services import provisional_status as st
from services.embedding_metadata_service import EmbeddingMetadataService


class GraphFeatureService:
    """Extract normalized features for GraphSAGE-lite embedding inference."""

    def __init__(
        self,
        repo: Optional[AuthRepository] = None,
        graph_repo: Optional[PGPRGraphRepository] = None,
    ) -> None:
        self.repo = repo or AuthRepository()
        self.graph_repo = graph_repo or PGPRGraphRepository()

    def extract(self, entity_type: str, entity_id: str) -> Dict[str, Any]:
        entity_type = str(entity_type).lower()
        entity = self.repo.find_entity_by_id(entity_type, entity_id)
        if not entity:
            raise ValueError(f"Entity not found: {entity_type}/{entity_id}")
        self._validate_entity(entity_type, entity_id, entity)

        source_payload = EmbeddingMetadataService.source_payload(entity_type, entity)
        graph_neighbors = self._graph_neighbors(entity_type, entity_id)
        return {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "source_hash": EmbeddingMetadataService.compute_source_hash(entity_type, entity),
            "topics": source_payload.get("research_topics") or [],
            "skills": source_payload.get("skills") or [],
            "industries": source_payload.get("industry") or [],
            "location": self._location_tokens(source_payload.get("location") or {}),
            "graph_relations": graph_neighbors.get("relations") or [],
            "graph_neighbor_labels": graph_neighbors.get("labels") or [],
            "trust_weight": float(entity.get("trust_weight", 1.0) or 1.0),
            "entity_verification_status": entity.get("entity_verification_status"),
            "kg_sync_status": entity.get("kg_sync_status"),
        }

    def _validate_entity(self, entity_type: str, entity_id: str, entity: Dict[str, Any]) -> None:
        if entity.get("entity_verification_status") == st.ENTITY_REJECTED:
            raise ValueError(f"Entity rejected: {entity_type}/{entity_id}")
        if entity.get("kg_sync_status") in {st.KG_DISABLED, st.KG_REJECTED}:
            raise ValueError(f"Entity disabled/rejected in KG: {entity_type}/{entity_id}")
        if entity.get("visibility") in {st.VISIBILITY_HIDDEN, st.VISIBILITY_DISABLED}:
            raise ValueError(f"Entity hidden/disabled: {entity_type}/{entity_id}")

    @staticmethod
    def _location_tokens(location: Dict[str, Any]) -> List[str]:
        tokens: List[str] = []
        for key in ("country", "province", "district", "raw"):
            value = location.get(key)
            if value not in (None, "", [], {}) and str(value) not in tokens:
                tokens.append(str(value))
        return tokens

    def _graph_neighbors(self, entity_type: str, entity_id: str) -> Dict[str, List[str]]:
        label = PGPRGraphRepository._safe_label(entity_type)
        id_prop = PGPRGraphRepository._id_prop(label)
        try:
            rows = self.graph_repo.run_read(
                f"""
                MATCH (n:{label} {{{id_prop}: $entity_id}})
                OPTIONAL MATCH (n)-[r]-(m)
                WITH r, m, CASE WHEN m IS NULL THEN {{}} ELSE properties(m) END AS props
                WHERE m IS NULL OR (
                  NOT coalesce(props.visibility, "public") IN ["hidden", "disabled"]
                  AND coalesce(props.participation_scope, "public") <> "disabled"
                  AND coalesce(props.entity_verification_status, "verified") <> "rejected"
                  AND coalesce(props.kg_sync_status, "synced_verified") <> "merge_required"
                )
                RETURN collect(DISTINCT type(r)) AS relations,
                       collect(DISTINCT coalesce(
                         props.name, props.title, props.label,
                         props.topic_id, props.skill_id, props.industry_id, props.location_id,
                         props.project_id, props.expert_id, props.enterprise_id, props.funder_id
                       )) AS labels
                """,
                entity_id=entity_id,
                timeout=5,
            )
        except Exception:
            return {"relations": [], "labels": []}
        if not rows:
            return {"relations": [], "labels": []}
        row = rows[0]
        return {
            "relations": [str(item) for item in row.get("relations") or [] if item],
            "labels": [str(item) for item in row.get("labels") or [] if item],
        }
