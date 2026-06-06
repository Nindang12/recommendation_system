"""Feasibility check for the Inductive PGPR candidate roadmap.

This script is read-only against MongoDB/Neo4j. It does not train or promote a
model. It answers whether the current graph/data is large and labeled enough to
move beyond prototype/lifecycle work.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from importlib.util import find_spec
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml.graphsage.snapshot import GraphSnapshotExporter, load_snapshot, snapshot_id_from_time, utc_now_iso  # noqa: E402
from pgpr.inductive_action_schema import ALLOWED_ACTION_RELATIONS, POSITIVE_LABEL_RELATIONS  # noqa: E402
from repositories.auth_repo import AuthRepository  # noqa: E402


ENTITY_TYPES = ("expert", "project", "funder", "enterprise")
MIN_NODE_COUNT = 1_000
MIN_EDGE_COUNT = 10_000
MIN_POSITIVE_LABELS = 500
MIN_COLD_START_CASES = 20
MIN_ALLOWED_ACTION_COVERAGE = 0.65


def _safe_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _safe_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_safe_json(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value) if value.__class__.__name__ == "ObjectId" else value


def _load_or_export_snapshot(snapshot_path: Path | None, *, node_limit: int, edge_limit: int) -> tuple[Dict[str, Any], Path]:
    if snapshot_path and snapshot_path.exists():
        return load_snapshot(snapshot_path), snapshot_path

    now = utc_now_iso()
    output = ROOT / "artifacts" / "graph_snapshots" / f"{snapshot_id_from_time(now)}_inductive_feasibility.json"
    exporter = GraphSnapshotExporter()
    try:
        snapshot = exporter.export_to_file(output, node_limit=node_limit, edge_limit=edge_limit)
    finally:
        exporter.graph_repo.close()
    return snapshot, output


def _load_pgpr_vocab(data_dir: Path) -> Set[str]:
    vocab_path = data_dir / "vocab.json"
    if not vocab_path.exists():
        return set()
    payload = json.loads(vocab_path.read_text(encoding="utf-8"))
    entity2id = payload.get("entity2id") or {}
    if isinstance(entity2id, dict):
        return {str(key) for key in entity2id.keys()}
    return set()


def _cold_start_stats(repo: AuthRepository, pgpr_vocab: Set[str]) -> Dict[str, Any]:
    by_type: Dict[str, Dict[str, int]] = {}
    total = 0
    missing = 0
    ready_missing = 0
    for entity_type in ENTITY_TYPES:
        collection = repo.get_entity_collection(entity_type)
        if collection is None:
            continue
        id_field = repo.entity_id_field(entity_type)
        type_total = 0
        type_missing = 0
        type_ready_missing = 0
        for doc in collection.find({}):
            entity_id = str(doc.get(id_field) or doc.get("_id"))
            key = f"{entity_type.capitalize()}::{entity_id}"
            type_total += 1
            if key not in pgpr_vocab:
                type_missing += 1
                emb = doc.get("embedding") or {}
                if emb.get("status") == "ready" and emb.get("signal") != "no_signal":
                    type_ready_missing += 1
        by_type[entity_type] = {
            "total": type_total,
            "missing_pgpr_vocab": type_missing,
            "ready_embedding_missing_pgpr_vocab": type_ready_missing,
        }
        total += type_total
        missing += type_missing
        ready_missing += type_ready_missing
    return {
        "total_entities": total,
        "missing_pgpr_vocab": missing,
        "ready_embedding_missing_pgpr_vocab": ready_missing,
        "by_type": by_type,
    }


def _relation_stats(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    relationships = Counter(str(edge.get("type") or "") for edge in snapshot.get("edges") or [])
    total_edges = sum(relationships.values())
    allowed_edges = sum(count for rel, count in relationships.items() if rel in ALLOWED_ACTION_RELATIONS)
    positive_labels = sum(count for rel, count in relationships.items() if rel in POSITIVE_LABEL_RELATIONS)
    blocked_relations = {
        rel: count
        for rel, count in sorted(relationships.items())
        if rel and rel not in ALLOWED_ACTION_RELATIONS
    }
    return {
        "relationship_counts": dict(sorted(relationships.items())),
        "allowed_action_relations": sorted(ALLOWED_ACTION_RELATIONS),
        "allowed_action_edges": allowed_edges,
        "allowed_action_coverage": round(allowed_edges / max(1, total_edges), 6),
        "blocked_or_unclassified_relations": blocked_relations,
        "positive_label_relations": sorted(POSITIVE_LABEL_RELATIONS),
        "positive_label_edges": positive_labels,
    }


def _dependency_stats() -> Dict[str, Any]:
    return {
        "torch": find_spec("torch") is not None,
        "torch_geometric": find_spec("torch_geometric") is not None,
    }


def _decision(snapshot: Dict[str, Any], relation_stats: Dict[str, Any], cold_start: Dict[str, Any], deps: Dict[str, Any]) -> Dict[str, Any]:
    metadata = snapshot.get("metadata") or {}
    node_count = int(metadata.get("node_count") or len(snapshot.get("nodes") or []))
    edge_count = int(metadata.get("edge_count") or len(snapshot.get("edges") or []))
    positive_labels = int(relation_stats.get("positive_label_edges") or 0)
    cold_start_cases = int(cold_start.get("ready_embedding_missing_pgpr_vocab") or 0)
    coverage = float(relation_stats.get("allowed_action_coverage") or 0.0)

    checks = {
        "node_count_ready_for_deep_model": node_count >= MIN_NODE_COUNT,
        "edge_count_ready_for_deep_model": edge_count >= MIN_EDGE_COUNT,
        "positive_labels_ready": positive_labels >= MIN_POSITIVE_LABELS,
        "cold_start_eval_cases_ready": cold_start_cases >= MIN_COLD_START_CASES,
        "action_schema_coverage_ready": coverage >= MIN_ALLOWED_ACTION_COVERAGE,
        "torch_available": bool(deps.get("torch")),
        "torch_geometric_available": bool(deps.get("torch_geometric")),
    }
    blocking = [name for name, ok in checks.items() if not ok]
    promote_allowed = not blocking
    if promote_allowed:
        recommendation = "Proceed to offline Inductive PGPR prototype training; keep shadow-mode gate before runtime."
    else:
        recommendation = (
            "Do not train/promote a real Inductive PGPR model yet. Keep this as candidate lifecycle/prototype, "
            "grow labels/data, and use current hybrid as production baseline."
        )
    return {
        "promote_allowed": promote_allowed,
        "checks": checks,
        "blocking_checks": blocking,
        "thresholds": {
            "min_node_count": MIN_NODE_COUNT,
            "min_edge_count": MIN_EDGE_COUNT,
            "min_positive_labels": MIN_POSITIVE_LABELS,
            "min_cold_start_cases": MIN_COLD_START_CASES,
            "min_allowed_action_coverage": MIN_ALLOWED_ACTION_COVERAGE,
        },
        "recommendation": recommendation,
    }


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="Run Inductive PGPR candidate feasibility check.")
    parser.add_argument("--snapshot", type=Path, default=None, help="Existing sanitized snapshot JSON.")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "pgpr" / "pgpr_data")
    parser.add_argument("--node-limit", type=int, default=10000)
    parser.add_argument("--edge-limit", type=int, default=50000)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "scripts" / "inductive_pgpr_feasibility_report.json",
    )
    args = parser.parse_args()

    snapshot, snapshot_path = _load_or_export_snapshot(args.snapshot, node_limit=args.node_limit, edge_limit=args.edge_limit)
    repo = AuthRepository()
    pgpr_vocab = _load_pgpr_vocab(args.data_dir)
    relation_stats = _relation_stats(snapshot)
    cold_start = _cold_start_stats(repo, pgpr_vocab)
    deps = _dependency_stats()
    decision = _decision(snapshot, relation_stats, cold_start, deps)

    report = {
        "status": "complete",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_path": str(snapshot_path),
        "snapshot_metadata": snapshot.get("metadata") or {},
        "dependencies": deps,
        "pgpr_vocab": {
            "data_dir": str(args.data_dir),
            "entity_count": len(pgpr_vocab),
        },
        "cold_start": cold_start,
        "relations": relation_stats,
        "decision": decision,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(_safe_json(report), ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "complete", "output": str(args.output), "decision": decision}, ensure_ascii=False, indent=2))
    return 0 if decision["promote_allowed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
