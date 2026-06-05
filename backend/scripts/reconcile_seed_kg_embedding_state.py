"""Reconcile legacy seed entities that exist in Neo4j but miss Mongo KG/embedding state.

Dry-run by default:

    python scripts/reconcile_seed_kg_embedding_state.py

Apply:

    python scripts/reconcile_seed_kg_embedding_state.py --apply

This is intended for old/seed data imported before the cold-start pipeline added
kg_sync_status, participation_scope, and embedding metadata fields.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from repositories.auth_repo import AuthRepository  # noqa: E402
from repositories.pgpr_graph_repo import PGPRGraphRepository  # noqa: E402
from services import provisional_status as st  # noqa: E402
from services.embedding_metadata_service import EmbeddingMetadataService  # noqa: E402


ENTITY_TYPES = ("expert", "project", "funder", "enterprise")


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value) if value.__class__.__name__ == "ObjectId" else value


def _entity_types(raw: str) -> List[str]:
    values = [item.strip().lower() for item in str(raw or "").split(",") if item.strip()]
    if not values or values == ["all"]:
        return list(ENTITY_TYPES)
    unknown = sorted(set(values) - set(ENTITY_TYPES))
    if unknown:
        raise ValueError(f"Unsupported entity type(s): {', '.join(unknown)}")
    return values


def _iter_entities(repo: AuthRepository, entity_types: Iterable[str], limit: int) -> Iterable[tuple[str, Dict[str, Any]]]:
    remaining = max(1, int(limit))
    for entity_type in entity_types:
        collection = repo.get_entity_collection(entity_type)
        if collection is None:
            continue
        for doc in collection.find({}).sort("updated_at", -1).limit(remaining):
            yield entity_type, doc


def _needs_reconcile(doc: Dict[str, Any], *, refresh_stale: bool) -> tuple[bool, List[str]]:
    reasons: List[str] = []
    embedding = doc.get("embedding") or {}
    if not doc.get("kg_sync_status"):
        reasons.append("missing_kg_sync_status")
    if not doc.get("entity_verification_status"):
        reasons.append("missing_entity_verification_status")
    if not doc.get("participation_scope"):
        reasons.append("missing_participation_scope")
    if not doc.get("visibility"):
        reasons.append("missing_visibility")
    if not embedding:
        reasons.append("missing_embedding_metadata")
    elif refresh_stale:
        reasons.append("refresh_embedding_metadata")
    return bool(reasons), reasons


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile seed Mongo state with existing Neo4j nodes.")
    parser.add_argument("--apply", action="store_true", help="Apply Mongo updates. Default is dry-run.")
    parser.add_argument("--types", default="all", help="Comma-separated entity types.")
    parser.add_argument("--limit", type=int, default=1000, help="Maximum documents to scan per run.")
    parser.add_argument("--refresh-stale", action="store_true", help="Refresh embedding source_hash metadata.")
    parser.add_argument(
        "--output",
        default=str(Path("scripts") / "seed_kg_embedding_reconcile_report.json"),
        help="Where to write the JSON report.",
    )
    args = parser.parse_args()

    repo = AuthRepository()
    graph = PGPRGraphRepository()
    entity_types = _entity_types(args.types)
    now = datetime.now(timezone.utc)
    report: Dict[str, Any] = {
        "started_at": now.isoformat(),
        "apply": bool(args.apply),
        "entity_types": entity_types,
        "scanned": 0,
        "found_in_neo4j": 0,
        "eligible": 0,
        "updated": 0,
        "skipped": {},
        "results": [],
    }

    try:
        for entity_type, doc in _iter_entities(repo, entity_types, args.limit):
            report["scanned"] += 1
            id_field = repo.entity_id_field(entity_type)
            entity_id = str(doc.get(id_field) or doc.get("_id"))
            graph_status = graph.get_entity_status(entity_type, entity_id)
            if not graph_status:
                reason = "missing_in_neo4j"
                report["skipped"][reason] = int(report["skipped"].get(reason, 0)) + 1
                continue

            report["found_in_neo4j"] += 1
            needs_update, reasons = _needs_reconcile(doc, refresh_stale=bool(args.refresh_stale))
            if not needs_update:
                reason = "already_has_runtime_state"
                report["skipped"][reason] = int(report["skipped"].get(reason, 0)) + 1
                continue

            report["eligible"] += 1
            merged_doc = {
                **doc,
                "kg_sync_status": graph_status.get("kg_sync_status") or st.KG_SYNCED_VERIFIED,
                "entity_verification_status": graph_status.get("entity_verification_status") or st.ENTITY_VERIFIED,
                "visibility": graph_status.get("visibility") or st.VISIBILITY_PUBLIC,
                "participation_scope": graph_status.get("participation_scope") or st.SCOPE_PUBLIC,
                "allow_as_source": graph_status.get("allow_as_source")
                if graph_status.get("allow_as_source") is not None
                else True,
                "recommendable_as_target": graph_status.get("recommendable_as_target")
                if graph_status.get("recommendable_as_target") is not None
                else True,
                "allow_as_intermediate_node": graph_status.get("allow_as_intermediate_node")
                if graph_status.get("allow_as_intermediate_node") is not None
                else True,
                "trust_weight": float(graph_status.get("trust_weight") or 1.0),
            }
            embedding = EmbeddingMetadataService.default_embedding(entity_type, merged_doc, now=now)
            payload = {
                "kg_sync_status": merged_doc["kg_sync_status"],
                "entity_verification_status": merged_doc["entity_verification_status"],
                "visibility": merged_doc["visibility"],
                "participation_scope": merged_doc["participation_scope"],
                "allow_as_source": merged_doc["allow_as_source"],
                "recommendable_as_target": merged_doc["recommendable_as_target"],
                "allow_as_intermediate_node": merged_doc["allow_as_intermediate_node"],
                "trust_weight": merged_doc["trust_weight"],
                "embedding": embedding,
                "embedding_status": embedding.get("status"),
            }
            row = {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "reasons": reasons,
                "payload": payload,
            }
            if args.apply:
                repo.update_entity_status(entity_type, entity_id, payload)
                report["updated"] += 1
            report["results"].append(row)
    finally:
        graph.close()

    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(_json_safe(report), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"written {output_path}")
    print(
        "apply={apply} scanned={scanned} found_in_neo4j={found} eligible={eligible} updated={updated}".format(
            apply=report["apply"],
            scanned=report["scanned"],
            found=report["found_in_neo4j"],
            eligible=report["eligible"],
            updated=report["updated"],
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
