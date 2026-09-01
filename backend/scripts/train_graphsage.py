"""Create a Phase 10 GraphSAGE-real candidate artifact.

The script is intentionally conservative:
- GraphSAGE-lite remains the active runtime model.
- Candidate artifacts are written to their own directory.
- If data is insufficient or PyTorch Geometric is unavailable, a warning report
  is created and the candidate is not promoted.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml.graphsage.constants import (  # noqa: E402
    DEFAULT_BASELINE_NAME,
    DEFAULT_CANDIDATE_NAME,
    DEFAULT_DIMENSION,
    DEFAULT_MIN_POSITIVE_EDGES,
    DEFAULT_RANDOM_SEED,
)
from ml.graphsage.trainer import GraphSAGECandidateTrainer  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train/scaffold GraphSAGE real candidate artifact")
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--model-name", type=str, default=DEFAULT_CANDIDATE_NAME)
    parser.add_argument("--dimension", type=int, default=DEFAULT_DIMENSION)
    parser.add_argument("--min-positive-edges", type=int, default=DEFAULT_MIN_POSITIVE_EDGES)
    parser.add_argument("--random-seed", type=int, default=DEFAULT_RANDOM_SEED)
    parser.add_argument("--evaluation-baseline", type=str, default=DEFAULT_BASELINE_NAME)
    return parser.parse_args()


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    args = parse_args()
    if not args.snapshot.exists():
        print(f"Snapshot not found: {args.snapshot}", file=sys.stderr)
        return 2
    trainer = GraphSAGECandidateTrainer(
        model_name=args.model_name,
        dimension=args.dimension,
        min_positive_edges=args.min_positive_edges,
        random_seed=args.random_seed,
        evaluation_baseline=args.evaluation_baseline,
    )
    report = trainer.train_from_snapshot(args.snapshot)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
