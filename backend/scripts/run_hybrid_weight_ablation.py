"""Hybrid weight sensitivity check on a stratified data1 smoke subset.

Sampling is stratified across all 8 recommendation directions (5 query/direction,
40 total) instead of taking the first N cases from the case file. The previous
version took the first 20 cases of the (now-removed) 160-query file, which are
all `project -> expert` -- a direction where even the `random` baseline scores
~0.91 NDCG@5 on the full 160/240-query runs (near-ceiling candidate pool), so
NDCG@5/MRR were pinned at 1.0000 for every weight profile regardless of the
weights actually used. Stratifying across directions -- including the harder
`expert-expert` / `project-project` pairs noted elsewhere in the evaluation --
gives the ranking metrics room to move so the ablation can show real weight
sensitivity.
"""
from __future__ import annotations

import asyncio
import json
import sys
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import services.hybrid_recommendation_service as hybrid_mod  # noqa: E402
from evaluation.runner import EvaluationRunner  # noqa: E402

CASES = Path("scripts/evaluation_cases_data1_leave_one_edge_out_smoke_stratified.json")
SOURCE_CASES = Path("scripts/evaluation_cases_data1_leave_one_edge_out_240.json")
OUT = Path("scripts/evaluation_hybrid_weight_ablation_smoke40_stratified.json")
PER_DIRECTION_COUNT = 5

PROFILES = {
    "default_0.62_0.18_0.12_0.08": (0.62, 0.18, 0.12, 0.08),
    "pgpr_heavy_0.70_0.15_0.10_0.05": (0.70, 0.15, 0.10, 0.05),
    "balanced_0.50_0.20_0.20_0.10": (0.50, 0.20, 0.20, 0.10),
    "embedding_boost_0.50_0.15_0.25_0.10": (0.50, 0.15, 0.25, 0.10),
}


def write_smoke_cases() -> None:
    payload = json.loads(SOURCE_CASES.read_text(encoding="utf-8-sig"))
    all_cases = list(payload.get("cases") or [])

    by_direction: "OrderedDict[tuple[str, str], list]" = OrderedDict()
    for case in all_cases:
        key = (case.get("source_type"), case.get("target_type"))
        by_direction.setdefault(key, []).append(case)

    stratified = []
    for key, direction_cases in by_direction.items():
        stratified.extend(direction_cases[:PER_DIRECTION_COUNT])

    smoke = {
        "version": payload.get("version"),
        "description": (
            f"Stratified ablation smoke subset ({PER_DIRECTION_COUNT} case/direction x "
            f"{len(by_direction)} directions = {len(stratified)}) from {SOURCE_CASES.name}"
        ),
        "label_version": payload.get("label_version"),
        "label_created_at": payload.get("label_created_at"),
        "label_policy": payload.get("label_policy"),
        "cases": stratified,
    }
    CASES.write_text(json.dumps(smoke, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(stratified)} stratified cases across {len(by_direction)} directions to {CASES}")


async def run_profile(name: str, weights: tuple[float, float, float, float]) -> dict:
    hybrid_mod.WEIGHT_PGPR, hybrid_mod.WEIGHT_PATH, hybrid_mod.WEIGHT_EMBEDDING, hybrid_mod.WEIGHT_TOPIC = weights
    runner = EvaluationRunner(CASES, methods=("hybrid",), limit=10, k_values=(5,))
    report = await runner.run()
    summary = report["summary"]["hybrid"]
    return {
        "profile": name,
        "weights": {
            "pgpr": weights[0],
            "path": weights[1],
            "embedding": weights[2],
            "topic": weights[3],
        },
        "queries": summary.get("queries"),
        "ndcg_at_5": summary.get("ndcg_at_5"),
        "mrr": summary.get("mrr"),
        "precision_at_5": summary.get("precision_at_5"),
        "recall_at_5": summary.get("recall_at_5"),
    }


async def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    write_smoke_cases()
    results = []
    for name, weights in PROFILES.items():
        results.append(await run_profile(name, weights))
    payload = {
        "cases_path": str(CASES),
        "per_direction_count": PER_DIRECTION_COUNT,
        "case_count": PER_DIRECTION_COUNT * 8,
        "note": (
            "Leave-one-edge-out smoke subset stratified across all 8 recommendation "
            "directions (5 query/direction), including expert-expert and "
            "project-project which are harder than project-expert on the full "
            "240-query benchmark."
        ),
        "profiles": results,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
