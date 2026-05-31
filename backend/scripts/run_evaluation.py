"""Run Phase 8 offline evaluation for recommendation quality assurance.

Usage (from backend/):

    python scripts/run_evaluation.py
    python scripts/run_evaluation.py --methods hybrid,random,pgpr_only
    set EVALUATION_ALLOW_SEED=true
    python scripts/run_evaluation.py --seed-hybrid
    python scripts/run_evaluation.py --baseline scripts/evaluation_baseline_report.json
"""
from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.runner import EvaluationRunner, export_report  # noqa: E402
from evaluation.seed_guard import require_evaluation_seed_allowed  # noqa: E402


DEFAULT_CASES = Path("scripts") / "evaluation_cases.json"
DEFAULT_CONFIG = Path("scripts") / "evaluation_config.json"
DEFAULT_JSON = Path("scripts") / "evaluation_report.json"
DEFAULT_CSV = Path("scripts") / "evaluation_report.csv"
DEFAULT_MD = Path("scripts") / "evaluation_report.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run offline recommendation evaluation (Phase 8)")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--baseline", type=Path, default=None, help="Previous evaluation_report.json for regression gate")
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_MD)
    parser.add_argument("--methods", type=str, default="", help="Comma-separated methods; default=all")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--k", type=str, default="5,10", help="Comma-separated K values")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--seed-hybrid",
        action="store_true",
        help="Run seed_evaluation_hybrid_fixtures.py before evaluation (requires EVALUATION_ALLOW_SEED=true)",
    )
    return parser.parse_args()


async def _main() -> int:
    args = parse_args()
    if args.seed_hybrid:
        require_evaluation_seed_allowed(invoked_by="run_evaluation.py --seed-hybrid")
        seed_script = ROOT / "scripts" / "seed_evaluation_hybrid_fixtures.py"
        env = {**os.environ, "EVALUATION_ALLOW_SEED": "true"}
        proc = subprocess.run([sys.executable, str(seed_script)], cwd=str(ROOT), env=env, check=False)
        if proc.returncode != 0:
            print("Warning: hybrid seed missing some entities; hybrid_ready cases may skip.")

    methods = [m.strip() for m in args.methods.split(",") if m.strip()] or None
    k_values = [int(x.strip()) for x in args.k.split(",") if x.strip()]

    runner = EvaluationRunner(
        args.cases,
        config_path=args.config,
        baseline_path=args.baseline,
        methods=methods,
        k_values=k_values,
        limit=args.limit,
        seed=args.seed,
    )
    report = await runner.run()
    export_report(report, args.output_json, csv_path=args.output_csv, md_path=args.output_md)

    gate = report.get("regression_gate") or {}
    print(f"Evaluation rows: {report.get('rows', 0)}")
    print(f"Report JSON: {args.output_json}")
    print(f"Report CSV: {args.output_csv}")
    print(f"Report MD: {args.output_md}")
    print(f"Regression gate: {'PASS' if gate.get('passed') else 'FAIL'} ({gate.get('message')})")

    if report.get("status") == "empty":
        return 2
    if not gate.get("passed", True):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
