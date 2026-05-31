"""Phase 8.1 evaluation hardening tests."""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.regression_gate import build_baseline_comparison  # noqa: E402
from evaluation.runner import EvaluationRunner, export_report  # noqa: E402
OUT = Path("scripts") / "phase8_1_hardening_report.json"


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_baseline_comparison_table() -> None:
    current = {"hybrid": {"ndcg_at_5": 0.40, "mrr": 0.5}, "random": {"ndcg_at_5": 0.1}}
    baseline = {"hybrid": {"ndcg_at_5": 0.35, "mrr": 0.52}, "random": {"ndcg_at_5": 0.12}}
    rows = build_baseline_comparison(current, baseline)
    assert_true(len(rows) >= 3, rows)
    hybrid_ndcg = next(r for r in rows if r["method"] == "hybrid" and r["metric"] == "ndcg_at_5")
    assert_true(hybrid_ndcg["status"] == "improved", hybrid_ndcg)
    assert_true(abs(float(hybrid_ndcg["delta"]) - 0.05) < 1e-9, hybrid_ndcg)


async def test_explicit_case_count() -> None:
    runner = EvaluationRunner(Path("scripts") / "evaluation_cases.json", limit=5, k_values=(5,))
    cases = runner.load_cases()
    meta = runner.load_dataset_metadata()
    explicit = [c for c in cases if c.get("label_source") == "admin_review"]
    hybrid = [c for c in cases if "hybrid_ready" in (c.get("tags") or [])]
    assert_true(len(explicit) >= 10, len(explicit))
    assert_true(len(hybrid) >= 5, len(hybrid))
    assert_true(meta.get("label_version") == "v1", meta)
    assert_true(meta.get("label_policy"), meta)


def test_seed_guard_blocks_without_flag() -> None:
    env = {k: v for k, v in os.environ.items() if k != "EVALUATION_ALLOW_SEED"}
    proc = subprocess.run(
        [sys.executable, "scripts/seed_evaluation_hybrid_fixtures.py"],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    assert_true(proc.returncode == 2, proc.stderr or proc.stdout)
    assert_true("EVALUATION_ALLOW_SEED" in (proc.stderr or proc.stdout), proc.stderr)


async def test_hybrid_ready_after_seed() -> None:
    env = {**os.environ, "EVALUATION_ALLOW_SEED": "true"}
    subprocess.run(
        [sys.executable, "scripts/seed_evaluation_hybrid_fixtures.py"],
        cwd=str(ROOT),
        env=env,
        check=False,
    )
    runner = EvaluationRunner(
        Path("scripts") / "evaluation_cases.json",
        methods=("hybrid", "embedding_only"),
        limit=5,
        k_values=(5,),
    )
    report = await runner.run()
    hybrid_rows = [r for r in report.get("per_query", []) if r.get("case_id", "").startswith("hybrid_")]
    assert_true(len(hybrid_rows) > 0, report.get("skipped"))
    ready_rows = [r for r in hybrid_rows if r.get("cold_start") is False]
    assert_true(len(ready_rows) > 0, hybrid_rows[:3])
    assert_true("baseline_comparison" in report, report.keys())


async def test_pgpr_latency_within_single_run() -> None:
    runner = EvaluationRunner(
        Path("scripts") / "evaluation_cases.json",
        methods=("pgpr_only",),
        limit=3,
        k_values=(5,),
    )
    report = await runner.run()
    latencies = [float(r.get("latency_ms") or 0.0) for r in report.get("per_query", []) if r.get("method") == "pgpr_only"]
    assert_true(len(latencies) >= 3, latencies)
    assert_true(max(latencies) < 30000, latencies)


async def main() -> int:
    test_baseline_comparison_table()
    test_seed_guard_blocks_without_flag()
    await test_explicit_case_count()
    await test_hybrid_ready_after_seed()
    await test_pgpr_latency_within_single_run()

    runner = EvaluationRunner(Path("scripts") / "evaluation_cases.json", limit=5)
    report = await runner.run()
    export_report(
        report,
        Path("scripts") / "evaluation_report.json",
        csv_path=Path("scripts") / "evaluation_report.csv",
        md_path=Path("scripts") / "evaluation_report.md",
    )

    result = {
        "status": "passed",
        "explicit_case_count": report.get("explicit_case_count"),
        "hybrid_ready_case_count": report.get("hybrid_ready_case_count"),
        "queries_run": report.get("queries_run"),
        "rows": report.get("rows"),
        "baseline_comparison_rows": len(report.get("baseline_comparison") or []),
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"PASS written {OUT}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except Exception as exc:  # noqa: BLE001
        OUT.write_text(json.dumps({"status": "failed", "error": str(exc)}, indent=2), encoding="utf-8")
        print(f"FAIL {exc}")
        sys.exit(1)
