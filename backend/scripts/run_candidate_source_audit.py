"""Audit candidate contribution sources for the thesis report.

This diagnostic script runs the current hybrid ranker on evaluation cases and
counts how many returned candidates come from PGPR paths, embedding similarity,
topic/skill overlap, or fallback-only evidence. It does not mutate runtime data.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.rankers import EvaluationRankers  # noqa: E402


DEFAULT_CASES = ROOT / "scripts" / "evaluation_cases.json"
DEFAULT_OUTPUT_JSON = ROOT / "scripts" / "candidate_source_audit.json"
DEFAULT_OUTPUT_MD = ROOT / "scripts" / "candidate_source_audit.md"


def _load_cases(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = list(payload.get("cases") or [])
    return cases[:limit] if limit else cases


def _heldout_relevant_ids(case: dict[str, Any]) -> list[str]:
    """Match EvaluationRunner LOO hook: allow held-out targets in candidate pool."""
    if str(case.get("evaluation_protocol") or "") != "leave_one_edge_out":
        return []
    return [str(x) for x in (case.get("relevant_ids") or []) if x]


def _path_layer_counts(method_counts: Counter[str]) -> dict[str, int]:
    return {
        "pgpr_policy": int(method_counts.get("pgpr_policy", 0)),
        "path_reranked_by_embedding_topic": int(method_counts.get("hybrid_embedding_path", 0)),
        "cypher_fallback": int(method_counts.get("cypher_fallback", 0)),
        "embedding_only": int(method_counts.get("hybrid_embedding", 0)),
    }


async def _main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="Audit contribution sources in hybrid recommendations.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--limit-cases", type=int, default=0)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    args = parser.parse_args()

    cases = _load_cases(args.cases, limit=args.limit_cases or None)
    rankers = EvaluationRankers()
    method_counts: Counter[str] = Counter()
    evidence_counts: Counter[str] = Counter()
    candidate_source_counts: Counter[str] = Counter()
    query_method_presence: dict[str, int] = defaultdict(int)
    rows: list[dict[str, Any]] = []

    for case in cases:
        source_type = str(case["source_type"])
        source_id = str(case["source_id"])
        target_type = str(case["target_type"])
        mode = str(case.get("mode") or "public")
        heldout_relevant_ids = _heldout_relevant_ids(case)
        items, latency_ms = await rankers.rank(
            "hybrid",
            source_type=source_type,
            source_id=source_id,
            target_type=target_type,
            limit=args.top_k,
            mode=mode,
            heldout_relevant_ids=heldout_relevant_ids,
        )
        case_methods: set[str] = set()
        for item in items:
            method = str(item.get("scoring_method") or "unknown")
            evidence = str(item.get("evidence_level") or "unknown")
            method_counts[method] += 1
            evidence_counts[evidence] += 1
            case_methods.add(method)
            sources = item.get("candidate_sources") or []
            if not sources:
                candidate_source_counts["unspecified"] += 1
            for source in sources:
                candidate_source_counts[str(source)] += 1
        for method in case_methods:
            query_method_presence[method] += 1
        rows.append(
            {
                "case_id": case.get("case_id"),
                "source_type": source_type,
                "source_id": source_id,
                "target_type": target_type,
                "mode": mode,
                "evaluation_protocol": case.get("evaluation_protocol"),
                "heldout_relevant_ids": heldout_relevant_ids or None,
                "latency_ms": round(float(latency_ms), 3),
                "result_count": len(items),
                "methods": dict(Counter(str(item.get("scoring_method") or "unknown") for item in items)),
                "evidence_levels": dict(Counter(str(item.get("evidence_level") or "unknown") for item in items)),
                "candidate_sources": dict(
                    Counter(
                        str(source)
                        for item in items
                        for source in (item.get("candidate_sources") or ["unspecified"])
                    )
                ),
            }
        )

    total_candidates = sum(method_counts.values())
    report = {
        "status": "complete",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cases_path": str(args.cases),
        "query_count": len(cases),
        "loo_heldout_hook": True,
        "top_k": args.top_k,
        "total_returned_candidates": total_candidates,
        "method_counts": dict(method_counts),
        "path_layer_counts": _path_layer_counts(method_counts),
        "evidence_counts": dict(evidence_counts),
        "candidate_source_counts": dict(candidate_source_counts),
        "query_method_presence": dict(query_method_presence),
        "rows": rows,
        "interpretation": {
            "pgpr_path_supported_methods": ["pgpr_policy", "hybrid_embedding_path"],
            "embedding_only_method": "hybrid_embedding",
            "fallback_method": "cypher_fallback",
            "note": (
                "candidate source `pgpr` means the candidate has PGPR/path-layer evidence. "
                "`pgpr_policy` is policy/path evidence, `hybrid_embedding_path` is path-supported reranking, "
                "and `cypher_fallback` is counted separately when it appears."
            ),
        },
    }
    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.output_md.write_text(_to_markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "complete",
                "output_json": str(args.output_json),
                "output_md": str(args.output_md),
                "query_count": len(cases),
                "total_returned_candidates": total_candidates,
                "method_counts": dict(method_counts),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _to_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Candidate Source Audit",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Queries: {report['query_count']}",
        f"- Top-K: {report['top_k']}",
        f"- Returned candidates: {report['total_returned_candidates']}",
        "",
        "## Scoring Method Counts",
        "",
        "| Method | Count |",
        "| --- | ---: |",
    ]
    for key, value in sorted((report.get("method_counts") or {}).items()):
        lines.append(f"| {key} | {value} |")
    lines.extend(["", "## Path Layer Breakdown", "", "| Path/source layer | Count |", "| --- | ---: |"])
    for key, value in (report.get("path_layer_counts") or {}).items():
        lines.append(f"| {key} | {value} |")
    lines.extend(["", "## Evidence Level Counts", "", "| Evidence level | Count |", "| --- | ---: |"])
    for key, value in sorted((report.get("evidence_counts") or {}).items()):
        lines.append(f"| {key} | {value} |")
    lines.extend(["", "## Candidate Source Counts", "", "| Source | Count |", "| --- | ---: |"])
    for key, value in sorted((report.get("candidate_source_counts") or {}).items()):
        lines.append(f"| {key} | {value} |")
    lines.extend(["", "## Query Method Presence", "", "| Method | Queries with at least one candidate |", "| --- | ---: |"])
    for key, value in sorted((report.get("query_method_presence") or {}).items()):
        lines.append(f"| {key} | {value} |")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `pgpr_policy`: path-supported result primarily scored by classic PGPR policy/path evidence.",
            "- `hybrid_embedding_path`: PGPR/path-supported result reranked with embedding/topic signals.",
            "- `hybrid_embedding`: embedding-only result without a strong PGPR reasoning path.",
            "- `cypher_fallback`: fallback graph/path heuristic when policy is missing or insufficient; it is counted separately when present.",
            "- `candidate_sources=pgpr`: broad path-layer marker, not always a pure policy-rollout marker.",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
