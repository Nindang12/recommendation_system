from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

from repositories.pgpr_graph_repo import PGPRGraphRepository

from .constants import SENSITIVE_PROPERTY_NAMES, TRAINING_FEATURE_KEYS, VECTOR_PROPERTY_NAMES


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def snapshot_id_from_time(created_at: str | None = None) -> str:
    created_at = created_at or utc_now_iso()
    return "snapshot_" + created_at.replace(":", "").replace("-", "").replace(".", "_").replace("+", "Z")


def sanitize_properties(properties: Dict[str, Any] | None) -> Dict[str, Any]:
    """Keep only model-relevant, non-sensitive scalar/list/dict properties."""

    sanitized: Dict[str, Any] = {}
    for raw_key, raw_value in (properties or {}).items():
        key = str(raw_key)
        key_lower = key.lower()
        if key_lower in SENSITIVE_PROPERTY_NAMES or key_lower in VECTOR_PROPERTY_NAMES:
            continue
        if key not in TRAINING_FEATURE_KEYS and key_lower not in TRAINING_FEATURE_KEYS:
            continue
        value = _sanitize_value(raw_value)
        if value not in (None, "", [], {}):
            sanitized[key] = value
    return sanitized


def _sanitize_value(value: Any, *, depth: int = 0) -> Any:
    if value in (None, "", [], {}):
        return None
    if depth > 2:
        return str(value)
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if isinstance(value, list):
        out = [_sanitize_value(item, depth=depth + 1) for item in value[:50]]
        return [item for item in out if item not in (None, "", [], {})]
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for raw_key, raw_item in value.items():
            key = str(raw_key)
            key_lower = key.lower()
            if key_lower in SENSITIVE_PROPERTY_NAMES or key_lower in VECTOR_PROPERTY_NAMES:
                continue
            item = _sanitize_value(raw_item, depth=depth + 1)
            if item not in (None, "", [], {}):
                out[key] = item
        return out
    return str(value)


class GraphSnapshotExporter:
    """Read-only Neo4j exporter for Phase 10 model lifecycle."""

    def __init__(self, graph_repo: PGPRGraphRepository | None = None) -> None:
        self.graph_repo = graph_repo or PGPRGraphRepository()

    def export(self, *, node_limit: int = 10000, edge_limit: int = 50000) -> Dict[str, Any]:
        created_at = utc_now_iso()
        snapshot_id = snapshot_id_from_time(created_at)
        nodes = self._load_nodes(node_limit)
        edges = self._load_edges(edge_limit)
        node_ids = {node["element_id"] for node in nodes}
        edges = [edge for edge in edges if edge["source"] in node_ids and edge["target"] in node_ids]
        label_counts = Counter(label for node in nodes for label in node.get("labels", []))
        relationship_counts = Counter(edge["type"] for edge in edges)
        return {
            "schema_version": 1,
            "snapshot_id": snapshot_id,
            "created_at": created_at,
            "source": "neo4j",
            "privacy": {
                "sanitized": True,
                "excluded": sorted(SENSITIVE_PROPERTY_NAMES | VECTOR_PROPERTY_NAMES),
                "note": "Snapshot keeps model features only and does not export secrets/contact data/vectors.",
            },
            "metadata": {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "label_counts": dict(sorted(label_counts.items())),
                "relationship_counts": dict(sorted(relationship_counts.items())),
                "node_limit": node_limit,
                "edge_limit": edge_limit,
            },
            "nodes": nodes,
            "edges": edges,
        }

    def export_to_file(self, output_path: Path, *, node_limit: int = 10000, edge_limit: int = 50000) -> Dict[str, Any]:
        payload = self.export(node_limit=node_limit, edge_limit=edge_limit)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    def _load_nodes(self, limit: int) -> List[Dict[str, Any]]:
        rows = self.graph_repo.run_read(
            """
            MATCH (n)
            RETURN elementId(n) AS element_id,
                   labels(n) AS labels,
                   properties(n) AS properties
            LIMIT $limit
            """,
            limit=max(1, int(limit)),
            timeout=30,
        )
        nodes: List[Dict[str, Any]] = []
        for row in rows:
            properties = sanitize_properties(row.get("properties") or {})
            labels = [str(label) for label in row.get("labels") or []]
            stable_id = _first_non_empty(
                properties.get("id"),
                properties.get("expert_id"),
                properties.get("project_id"),
                properties.get("enterprise_id"),
                properties.get("funder_id"),
                properties.get("topic_id"),
                properties.get("skill_id"),
                properties.get("industry_id"),
                properties.get("location_id"),
                row.get("element_id"),
            )
            nodes.append(
                {
                    "element_id": str(row.get("element_id")),
                    "id": str(stable_id),
                    "labels": labels,
                    "primary_label": labels[0] if labels else "Node",
                    "properties": properties,
                }
            )
        return nodes

    def _load_edges(self, limit: int) -> List[Dict[str, Any]]:
        rows = self.graph_repo.run_read(
            """
            MATCH (a)-[r]->(b)
            RETURN elementId(r) AS element_id,
                   elementId(a) AS source,
                   elementId(b) AS target,
                   type(r) AS type,
                   properties(r) AS properties
            LIMIT $limit
            """,
            limit=max(1, int(limit)),
            timeout=30,
        )
        edges: List[Dict[str, Any]] = []
        for row in rows:
            edges.append(
                {
                    "element_id": str(row.get("element_id")),
                    "source": str(row.get("source")),
                    "target": str(row.get("target")),
                    "type": str(row.get("type")),
                    "properties": sanitize_properties(row.get("properties") or {}),
                }
            )
        return edges


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def load_snapshot(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_node_text_features(node: Dict[str, Any]) -> Iterable[str]:
    yield from (str(label) for label in node.get("labels") or [])
    props = node.get("properties") or {}
    for key in ("name", "title", "label", "status", "entity_verification_status", "kg_sync_status"):
        value = props.get(key)
        if value not in (None, "", [], {}):
            yield str(value)

