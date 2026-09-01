"""Graph path queries for API (via PGPRGraphRepository / PGPRRecommender)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from pgpr.pgpr_recommendation import PGPRRecommender

logger = logging.getLogger(__name__)

ENTITY_LABEL_MAP = {
    "project": "Project",
    "expert": "Expert",
    "funder": "Funder",
    "enterprise": "Enterprise",
}


class GraphService:
    def __init__(self, recommender: Optional[PGPRRecommender] = None) -> None:
        self.recommender = recommender

    async def get_reasoning_paths(
        self,
        source_type: str,
        source_id: str,
        target_type: str,
        target_id: str,
        max_length: Optional[int] = None,
        limit: int = 10,
        mode: str = "public",
        current_user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if self.recommender is None:
            raise RuntimeError("PGPRRecommender is not configured")

        source_label = ENTITY_LABEL_MAP.get(source_type.lower())
        target_label = ENTITY_LABEL_MAP.get(target_type.lower())
        if not source_label or not target_label:
            raise ValueError(f"Unsupported entity type: {source_type} or {target_type}")

        def _run() -> List[Dict[str, Any]]:
            return self.recommender.find_reasoning_paths_cypher(
                source_id=source_id,
                source_type=source_label,
                target_id=target_id,
                target_type=target_label,
                max_length=max_length,
                limit=limit,
                mode=mode,
                current_user_id=current_user_id,
            )

        raw_paths = await asyncio.to_thread(_run)
        return [self._to_api_path_item(p) for p in raw_paths]

    async def get_entity_neighbors(
        self,
        entity_type: str,
        entity_id: str,
        depth: int = 1,
        limit: int = 80,
        mode: str = "public",
        current_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if self.recommender is None:
            raise RuntimeError("PGPRRecommender is not configured")

        entity_label = ENTITY_LABEL_MAP.get(entity_type.lower())
        if not entity_label:
            raise ValueError(f"Unsupported entity type: {entity_type}")

        def _run() -> Dict[str, Any]:
            return self.recommender.graph_repo.find_entity_neighbors(
                entity_type=entity_label,
                entity_id=entity_id,
                depth=depth,
                limit=limit,
                mode=mode,
                current_user_id=current_user_id,
            )

        graph = await asyncio.to_thread(_run)
        nodes = graph.get("nodes") or []
        edges = graph.get("edges") or []
        return {
            "nodes": [self._to_api_node(node) for node in nodes],
            "edges": [self._to_api_edge(edge) for edge in edges],
        }

    @staticmethod
    def _to_api_path_item(path: Dict[str, Any]) -> Dict[str, Any]:
        relations = path.get("relations") or []
        entities = path.get("entity_names") or path.get("nodes") or []
        explanation = path.get("explanation") or " -> ".join(relations)
        return {
            "path": explanation if isinstance(explanation, str) else " -> ".join(relations),
            "score": round(float(path.get("score", 0.0)), 4),
            "relations": list(relations),
            "entities": list(entities),
            "path_length": int(path.get("length", len(relations))),
            "explanation": path.get("explanation"),
        }

    @staticmethod
    def _to_api_node(node: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": str(node.get("id") or ""),
            "label": str(node.get("label") or node.get("id") or ""),
            "type": str(node.get("type") or "Unknown"),
            "properties": GraphService._json_safe(node.get("properties") or {}),
        }

    @staticmethod
    def _to_api_edge(edge: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": str(edge.get("id") or f"{edge.get('source')}->{edge.get('target')}:{edge.get('type')}"),
            "source": str(edge.get("source") or ""),
            "target": str(edge.get("target") or ""),
            "type": str(edge.get("type") or "RELATED_TO"),
        }

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, list):
            return [GraphService._json_safe(item) for item in value]
        if isinstance(value, tuple):
            return [GraphService._json_safe(item) for item in value]
        if isinstance(value, dict):
            return {str(key): GraphService._json_safe(item) for key, item in value.items()}
        return str(value)
