"""Phase 8.1 evaluation hardening tests (data1 leave-one-edge-out cases)."""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.regression_gate import build_baseline_comparison  # noqa: E402
from evaluation.runner import EvaluationRunner, export_report  # noqa: E402

DATA1_CASES = Path("scripts") / "evaluation_cases_data1_leave_one_edge_out_160.json"
DATA1_SMOKE_LIMIT = 5
OUT = Path("scripts") / "phase8_1_hardening_report.json"
SMOKE_REPORT_JSON = Path("scripts") / "evaluation_report_phase8_1_data1_smoke.json"
SMOKE_REPORT_CSV = Path("scripts") / "evaluation_report_phase8_1_data1_smoke.csv"
SMOKE_REPORT_MD = Path("scripts") / "evaluation_report_phase8_1_data1_smoke.md"
SMOKE_CASES = Path("scripts") / "evaluation_cases_data1_leave_one_edge_out_smoke.json"


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_data1_smoke_cases(case_count: int) -> Path:
    """Slice the canonical data1 case file for fast smoke tests."""
    payload = json.loads(DATA1_CASES.read_text(encoding="utf-8-sig"))
    cases = list(payload.get("cases") or [])[:case_count]
    smoke = {
        "version": payload.get("version"),
        "description": f"Smoke subset ({case_count} cases) from {DATA1_CASES.name}",
        "label_version": payload.get("label_version"),
        "label_created_at": payload.get("label_created_at"),
        "label_policy": payload.get("label_policy"),
        "cases": cases,
    }
    SMOKE_CASES.write_text(json.dumps(smoke, ensure_ascii=False, indent=2), encoding="utf-8")
    return SMOKE_CASES


def test_baseline_comparison_table() -> None:
    current = {"hybrid": {"ndcg_at_5": 0.40, "mrr": 0.5}, "random": {"ndcg_at_5": 0.1}}
    baseline = {"hybrid": {"ndcg_at_5": 0.35, "mrr": 0.52}, "random": {"ndcg_at_5": 0.12}}
    rows = build_baseline_comparison(current, baseline)
    assert_true(len(rows) >= 3, rows)
    hybrid_ndcg = next(r for r in rows if r["method"] == "hybrid" and r["metric"] == "ndcg_at_5")
    assert_true(hybrid_ndcg["status"] == "improved", hybrid_ndcg)
    assert_true(abs(float(hybrid_ndcg["delta"]) - 0.05) < 1e-9, hybrid_ndcg)


async def test_data1_dataset_metadata() -> None:
    assert_true(DATA1_CASES.exists(), f"missing {DATA1_CASES}")
    runner = EvaluationRunner(DATA1_CASES, limit=DATA1_SMOKE_LIMIT, k_values=(5,))
    cases = runner.load_cases()
    meta = runner.load_dataset_metadata()
    leave_one = [
        c
        for c in cases
        if c.get("evaluation_protocol") == "leave_one_edge_out"
        or "leave_one_edge_out" in (c.get("tags") or [])
    ]
    graph_labels = [c for c in cases if c.get("label_source") == "graph_leave_one_edge_out_data1"]
    assert_true(len(cases) == 160, len(cases))
    assert_true(len(leave_one) == 160, len(leave_one))
    assert_true(len(graph_labels) == 160, len(graph_labels))
    assert_true(meta.get("label_policy") == "graph_leave_one_edge_out_data1", meta)
    assert_true(str(meta.get("label_version") or "").startswith("data1_leave_one_edge_out"), meta)


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


async def test_data1_hybrid_smoke() -> None:
    smoke_path = write_data1_smoke_cases(DATA1_SMOKE_LIMIT)
    runner = EvaluationRunner(
        smoke_path,
        methods=("hybrid", "embedding_only"),
        limit=5,
        k_values=(5,),
    )
    report = await runner.run()
    hybrid_rows = [r for r in report.get("per_query", []) if r.get("method") == "hybrid"]
    assert_true(len(hybrid_rows) >= DATA1_SMOKE_LIMIT, report.get("skipped"))
    assert_true(not report.get("skipped"), report.get("skipped"))
    assert_true("hybrid" in (report.get("summary") or {}), report.keys())
    assert_true("regression_gate" in report, report.keys())


async def test_pgpr_latency_on_data1() -> None:
    smoke_path = write_data1_smoke_cases(3)
    runner = EvaluationRunner(
        smoke_path,
        methods=("pgpr_only",),
        limit=5,
        k_values=(5,),
    )
    report = await runner.run()
    latencies = [
        float(r.get("latency_ms") or 0.0)
        for r in report.get("per_query", [])
        if r.get("method") == "pgpr_only"
    ]
    assert_true(len(latencies) >= 3, latencies)
    assert_true(max(latencies) < 120000, latencies)


async def main() -> int:
    assert_true(DATA1_CASES.exists(), f"missing {DATA1_CASES}")

    test_baseline_comparison_table()
    test_seed_guard_blocks_without_flag()
    await test_data1_dataset_metadata()
    await test_data1_hybrid_smoke()
    await test_pgpr_latency_on_data1()

    smoke_path = write_data1_smoke_cases(DATA1_SMOKE_LIMIT)
    runner = EvaluationRunner(smoke_path, methods=("hybrid",), limit=5)
    report = await runner.run()
    export_report(
        report,
        SMOKE_REPORT_JSON,
        csv_path=SMOKE_REPORT_CSV,
        md_path=SMOKE_REPORT_MD,
    )
    SMOKE_CASES.unlink(missing_ok=True)

    result = {
        "status": "passed",
        "cases_path": str(DATA1_CASES),
        "leave_one_edge_out_case_count": 160,
        "queries_run": report.get("queries_run"),
        "rows": report.get("rows"),
        "skipped_count": len(report.get("skipped") or []),
        "baseline_comparison_rows": len(report.get("baseline_comparison") or []),
        "smoke_report": str(SMOKE_REPORT_JSON),
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
