from __future__ import annotations

import json
from pathlib import Path
from statistics import median
from typing import Any

from evaluation.rankers import EvaluationRankers
from pgpr.inductive_shadow import InductivePGPRShadowRunner


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT = ROOT / "artifacts" / "graph_snapshots" / "snapshot_20260605T150221_309299Z0000_inductive_feasibility.json"


class InductivePGPRShadowService:
    """Admin-only diagnostic service for Inductive PGPR shadow inspection."""

    def __init__(
        self,
        *,
        snapshot_path: Path | None = None,
        rankers: EvaluationRankers | None = None,
    ) -> None:
        self.snapshot_path = snapshot_path or DEFAULT_SNAPSHOT
        self.rankers = rankers or EvaluationRankers()

    async def inspect(
        self,
        *,
        source_type: str,
        source_id: str,
        target_type: str,
        beam_width: int = 5,
        max_hops: int = 3,
        limit: int = 5,
        mode: str = "admin_debug",
        current_user_id: str | None = None,
    ) -> dict[str, Any]:
        source_type = source_type.lower()
        target_type = target_type.lower()
        mode = mode if mode in {"public", "personal", "admin_debug"} else "admin_debug"
        limit = min(max(int(limit), 1), 20)
        beam_width = min(max(int(beam_width), 1), 20)
        max_hops = min(max(int(max_hops), 1), 6)

        source_key = f"{source_type.capitalize()}::{source_id}"
        target_label = target_type.capitalize()
        shadow_runner = InductivePGPRShadowRunner.from_snapshot_path(
            self.snapshot_path,
            enabled=False,
            env_kwargs={
                "mode": mode,
                "current_user_id": current_user_id,
            },
        )
        shadow = shadow_runner.recommend_beam_shadow(
            source_key=source_key,
            target_type=target_label,
            beam_width=beam_width,
            max_hops=max_hops,
            limit=limit,
        )

        hybrid_candidates: list[dict[str, Any]] = []
        hybrid_error: str | None = None
        hybrid_latency_ms = 0.0
        try:
            hybrid_candidates, hybrid_latency_ms = await self.rankers.rank(
                "hybrid",
                source_type=source_type,
                source_id=source_id,
                target_type=target_type,
                limit=limit,
                mode=mode,
                current_user_id=current_user_id,
            )
        except Exception as exc:  # pragma: no cover - endpoint must stay diagnostic
            hybrid_error = f"{exc.__class__.__name__}: {exc}"

        inductive_candidates = shadow.get("candidates") or []
        hybrid_ids = [_candidate_id(item) for item in hybrid_candidates[:limit]]
        inductive_ids = [_entity_key_to_id(item.get("entity_key")) for item in inductive_candidates[:limit]]
        hybrid_set = {item for item in hybrid_ids if item}
        inductive_set = {item for item in inductive_ids if item}
        overlap = sorted(hybrid_set & inductive_set)
        new_candidates = [item for item in inductive_ids if item and item not in hybrid_set]
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
            "status": "success",
            "prototype_only": True,
            "runtime_enabled": False,
            "warning": "Inductive PGPR is shadow/debug only. This response is not used by production recommendation routes and is not cached.",
            "source": {
                "source_type": source_type,
                "source_id": source_id,
                "source_key": source_key,
            },
            "target_type": target_type,
            "params": {
                "beam_width": beam_width,
                "max_hops": max_hops,
                "limit": limit,
                "mode": mode,
            },
            "hybrid": {
                "error": hybrid_error,
                "latency_ms": round(float(hybrid_latency_ms or 0.0), 3),
                "candidates": [_slim_hybrid_candidate(item) for item in hybrid_candidates[:limit]],
            },
            "inductive_shadow": {
                "latency_ms": float(shadow.get("latency_ms") or 0.0),
                "candidate_count": len(inductive_candidates[:limit]),
                "candidates": [_slim_inductive_candidate(item) for item in inductive_candidates[:limit]],
                "blocked_action_count": int(shadow.get("blocked_action_count") or 0),
                "blocked_action_counts": shadow.get("blocked_action_counts") or {},
                "blocked_node_counts": shadow.get("blocked_node_counts") or {},
                "expansion_trace": shadow.get("expansion_trace") or [],
            },
            "comparison": {
                "overlap_at_5": len(overlap),
                "overlap_candidate_ids": overlap,
                "new_candidates_at_5": len(new_candidates),
                "new_candidate_ids": new_candidates,
                "path_count": sum(1 for item in inductive_candidates if item.get("reasoning_path")),
                "invalid_path_count": len(invalid_paths),
                "terminal_target_type_mismatch_count": len(terminal_mismatches),
                "terminal_target_type_mismatches": terminal_mismatches,
                "latency_ms": {
                    "hybrid": round(float(hybrid_latency_ms or 0.0), 3),
                    "inductive_shadow": float(shadow.get("latency_ms") or 0.0),
                },
            },
            "snapshot": {
                "path": str(self.snapshot_path),
                "exists": self.snapshot_path.exists(),
            },
        }


def summarize_shadow_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    shadow_latencies = [float((row.get("comparison") or {}).get("latency_ms", {}).get("inductive_shadow") or 0.0) for row in rows]
    return {
        "case_count": len(rows),
        "total_invalid_path_count": sum(int((row.get("comparison") or {}).get("invalid_path_count") or 0) for row in rows),
        "total_terminal_target_type_mismatch_count": sum(
            int((row.get("comparison") or {}).get("terminal_target_type_mismatch_count") or 0) for row in rows
        ),
        "shadow_latency_ms": _latency_summary(shadow_latencies),
    }


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
        "path_validity": item.get("path_validity"),
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


def write_debug_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
