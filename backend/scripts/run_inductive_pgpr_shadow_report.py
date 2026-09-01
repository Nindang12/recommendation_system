"""Run a snapshot-only shadow report for the Inductive PGPR candidate."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pgpr.inductive_shadow import InductivePGPRShadowRunner  # noqa: E402


DEFAULT_SNAPSHOT = ROOT / "artifacts" / "graph_snapshots" / "snapshot_20260605T150221_309299Z0000_inductive_feasibility.json"
DEFAULT_BASELINE = ROOT / "scripts" / "evaluation_inductive_pgpr_baseline.json"


def _load_hybrid_baseline(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"status": "missing", "path": str(path)}
    payload = json.loads(path.read_text(encoding="utf-8"))
    hybrid = (payload.get("summary") or {}).get("hybrid")
    rows = [
        row
        for row in payload.get("per_query") or []
        if row.get("method") == "hybrid"
    ]
    return {
        "status": "loaded",
        "path": str(path),
        "summary": hybrid,
        "query_count": len(rows),
        "note": "This is the current hybrid evaluation baseline; Inductive PGPR shadow is not promoted and is not compared as a quality metric yet.",
    }


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="Run Inductive PGPR beam-search shadow report.")
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--source", default="Project::prj_001")
    parser.add_argument("--target-type", default="Expert")
    parser.add_argument("--beam-width", type=int, default=5)
    parser.add_argument("--max-hops", type=int, default=3)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--hybrid-baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--output", type=Path, default=ROOT / "scripts" / "inductive_pgpr_shadow_report.json")
    args = parser.parse_args()

    runner = InductivePGPRShadowRunner.from_snapshot_path(args.snapshot, enabled=False)
    beam = runner.recommend_beam_shadow(
        source_key=args.source,
        target_type=args.target_type,
        beam_width=args.beam_width,
        max_hops=args.max_hops,
        limit=args.limit,
    )
    report = {
        "status": "complete",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "runtime_unchanged": True,
        "shadow_runtime_enabled": False,
        "snapshot_path": str(args.snapshot),
        "source": args.source,
        "target_type": args.target_type,
        "inductive_pgpr_shadow": beam,
        "hybrid_reference": _load_hybrid_baseline(args.hybrid_baseline),
        "conclusion": {
            "architecture_ready_for_shadow": bool(beam.get("candidate_count", 0) > 0),
            "quality_claim": "not_claimed",
            "next_step": "Use this report to validate path generation before RL training; train only after data/dependency readiness.",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "complete", "output": str(args.output), "candidate_count": beam.get("candidate_count")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
