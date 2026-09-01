"""Guardrails for evaluation-only MongoDB mutations (hybrid seed fixtures)."""
from __future__ import annotations

import os
import sys


def evaluation_seed_allowed() -> bool:
    return str(os.getenv("EVALUATION_ALLOW_SEED", "")).strip().lower() in {"1", "true", "yes"}


def require_evaluation_seed_allowed(*, invoked_by: str = "seed_evaluation_hybrid_fixtures") -> None:
    if evaluation_seed_allowed():
        return
    message = (
        f"{invoked_by} refused: set EVALUATION_ALLOW_SEED=true in a dev/eval environment only.\n"
        "This script overwrites embedding fields on seed entities (prj_001, exp_001, ...).\n"
        "Do NOT run on production data without a verified backup."
    )
    print(message, file=sys.stderr)
    raise SystemExit(2)
