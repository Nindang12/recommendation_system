"""Compare Inductive PGPR shadow beam-search with current hybrid candidates.

This script is diagnostic only. It does not promote or enable Inductive PGPR in
runtime recommendation APIs.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.rankers import EvaluationRankers  # noqa: E402
from pgpr.inductive_shadow import InductivePGPRShadowRunner  # noqa: E402


DEFAULT_SNAPSHOT = ROOT / "artifacts" / "graph_snapshots" / "snapshot_20260605T150221_309299Z0000_inductive_feasibility.json"
DEFAULT_OUTPUT = ROOT / "scripts" / "inductive_pgpr_shadow_compare_report.json"
SOURCE_SAMPLES = (
    ("project", "prj_001"),
    ("expert", "exp_001"),
    ("enterprise", "ent_001"),
    ("funder", "fnd_001"),
)
TARGET_TYPES = ("expert", "project", "funder", "enterprise")


async def _run_case(
    *,
    rankers: EvaluationRankers,
    shadow: InductivePGPRShadowRunner,
    source_type: str,
    source_id: str,
    target_type: str,
    beam_width: int,
    max_hops: int,
    limit: int,
    mode: str,
) -> dict[str, Any]:
    source_key = f"{source_type.capitalize()}::{source_id}"
    target_label = target_type.capitalize()

    hybrid_candidates: list[dict[str, Any]] = []
    hybrid_error: str | None = None
    hybrid_latency_ms = 0.0
    try:
        hybrid_candidates, hybrid_latency_ms = await rankers.rank(
            "hybrid",
            source_type=source_type,
            source_id=source_id,
            target_type=target_type,
            limit=limit,
            mode=mode,
        )
    except Exception as exc:  # pragma: no cover - diagnostic script resilience
        hybrid_error = f"{exc.__class__.__name__}: {exc}"

    shadow_report = shadow.recommend_beam_shadow(
        source_key=source_key,
        target_type=target_label,
        beam_width=beam_width,
        max_hops=max_hops,
        limit=limit,
    )
    inductive_candidates = shadow_report.get("candidates") or []
    hybrid_ids = [_candidate_id(item) for item in hybrid_candidates[:limit]]
    inductive_ids = [_entity_key_to_id(item.get("entity_key")) for item in inductive_candidates[:limit]]
    hybrid_set = {cid for cid in hybrid_ids if cid}
    inductive_set = {cid for cid in inductive_ids if cid}
    overlap = sorted(hybrid_set & inductive_set)
    new_candidates = [cid for cid in inductive_ids if cid and cid not in hybrid_set]

    invalid_paths = [
        item
        for item in inductive_candidates
        if not ((item.get("path_validity") or {}).get("valid"))
    ]
    terminal_mismatches = [
        item.get("entity_key")
        for item in inductive_candidates
        if not str(item.get("entity_key") or "").startswith(f"{target_label}::")
    ]

    return {
        "case_id": f"{source_type}_{source_id}_to_{target_type}",
        "source_type": source_type,
        "source_id": source_id,
        "source_key": source_key,
        "target_type": target_type,
        "hybrid_error": hybrid_error,
        "hybrid_candidates": [_slim_hybrid_candidate(item) for item in hybrid_candidates[:limit]],
        "inductive_shadow_candidates": [_slim_inductive_candidate(item) for item in inductive_candidates[:limit]],
        "overlap_at_5": len(overlap),
        "overlap_candidate_ids": overlap,
        "new_candidates_at_5": len(new_candidates),
        "new_candidate_ids": new_candidates,
        "path_count": sum(1 for item in inductive_candidates if item.get("reasoning_path")),
        "invalid_path_count": len(invalid_paths),
        "terminal_target_type_mismatch_count": len(terminal_mismatches),
        "terminal_target_type_mismatches": terminal_mismatches,
        "blocked_action_count": int(shadow_report.get("blocked_action_count") or 0),
        "blocked_action_counts": shadow_report.get("blocked_action_counts") or {},
        "blocked_node_counts": shadow_report.get("blocked_node_counts") or {},
        "latency_ms": {
            "hybrid": round(float(hybrid_latency_ms or 0.0), 3),
            "inductive_shadow": float(shadow_report.get("latency_ms") or 0.0),
        },
    }


def _default_cases() -> list[tuple[str, str, str]]:
    return [
        (source_type, source_id, target_type)
        for source_type, source_id in SOURCE_SAMPLES
        for target_type in TARGET_TYPES
        if target_type != source_type
    ]


def _candidate_id(item: dict[str, Any]) -> str:
    for key in ("id", "expert_id", "project_id", "funder_id", "enterprise_id", "entity_id"):
        value = item.get(key)
        if value not in (None, "", [], {}):
            return str(value)
    return ""


def _entity_key_to_id(entity_key: Any) -> str:
    text = str(entity_key or "")
    if "::" not in text:
        return text
    return text.split("::", 1)[1]


def _slim_hybrid_candidate(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _candidate_id(item),
        "name": item.get("name") or item.get("title"),
        "score": item.get("score"),
        "scoring_method": item.get("scoring_method"),
        "evidence_level": item.get("evidence_level"),
    }


def _slim_inductive_candidate(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "entity_key": item.get("entity_key"),
        "id": _entity_key_to_id(item.get("entity_key")),
        "path_score_prototype": item.get("path_score_prototype"),
        "hops": item.get("hops"),
        "reasoning_path": item.get("reasoning_path"),
        "path_valid": (item.get("path_validity") or {}).get("valid"),
    }


def _latency_summary(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"p50": None, "p95": None, "avg": None}
    ordered = sorted(values)
    p95_idx = min(len(ordered) - 1, int(round((len(ordered) - 1) * 0.95)))
    return {
        "p50": round(float(median(ordered)), 3),
        "p95": round(float(ordered[p95_idx]), 3),
        "avg": round(sum(ordered) / len(ordered), 3),
    }


async def main_async() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="Compare Inductive PGPR shadow against current hybrid candidates.")
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--beam-width", type=int, default=5)
    parser.add_argument("--max-hops", type=int, default=3)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--mode", default="public")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    rankers = EvaluationRankers()
    shadow = InductivePGPRShadowRunner.from_snapshot_path(args.snapshot, enabled=False)
    cases = _default_cases()
    rows: list[dict[str, Any]] = []
    for source_type, source_id, target_type in cases:
        rows.append(
            await _run_case(
                rankers=rankers,
                shadow=shadow,
                source_type=source_type,
                source_id=source_id,
                target_type=target_type,
                beam_width=args.beam_width,
                max_hops=args.max_hops,
                limit=args.limit,
                mode=args.mode,
            )
        )

    shadow_latencies = [float(row["latency_ms"]["inductive_shadow"]) for row in rows]
    hybrid_latencies = [float(row["latency_ms"]["hybrid"]) for row in rows if not row.get("hybrid_error")]
    report = {
        "status": "complete",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "runtime_unchanged": True,
        "shadow_runtime_enabled": False,
        "snapshot_path": str(args.snapshot),
        "beam_width": args.beam_width,
        "max_hops": args.max_hops,
        "limit": args.limit,
        "mode": args.mode,
        "case_count": len(rows),
        "summary": {
            "total_overlap_at_5": sum(int(row["overlap_at_5"]) for row in rows),
            "total_new_candidates_at_5": sum(int(row["new_candidates_at_5"]) for row in rows),
            "total_path_count": sum(int(row["path_count"]) for row in rows),
            "total_invalid_path_count": sum(int(row["invalid_path_count"]) for row in rows),
            "total_terminal_target_type_mismatch_count": sum(
                int(row["terminal_target_type_mismatch_count"]) for row in rows
            ),
            "total_blocked_action_count": sum(int(row["blocked_action_count"]) for row in rows),
            "latency_ms": {
                "hybrid": _latency_summary(hybrid_latencies),
                "inductive_shadow": _latency_summary(shadow_latencies),
            },
            "quality_claim": "not_claimed",
        },
        "rows": rows,
        "checklist": {
            "path_validity_checked": True,
            "terminal_target_type_checked": True,
            "blocked_action_reasons_logged": True,
            "owner_only_or_rejected_mask_checked_by_env": True,
            "candidate_quality_claimed": False,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "complete",
                "output": str(args.output),
                "case_count": len(rows),
                "invalid_path_count": report["summary"]["total_invalid_path_count"],
                "shadow_latency_p95_ms": report["summary"]["latency_ms"]["inductive_shadow"]["p95"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
