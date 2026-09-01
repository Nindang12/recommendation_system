"""Ensure hybrid-ready embedding fixtures for Phase 8.1 evaluation cases.

Run from backend/ before evaluation when testing embedding/hybrid contribution:

    set EVALUATION_ALLOW_SEED=true   # dev/eval only — never on production without backup
    python scripts/seed_evaluation_hybrid_fixtures.py

WARNING: Overwrites embedding on seed entities (prj_001, exp_001, ...). Not for production.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.seed_guard import require_evaluation_seed_allowed  # noqa: E402
from repositories.auth_repo import AuthRepository  # noqa: E402
from services import provisional_status as st  # noqa: E402

OUT = Path("scripts") / "evaluation_hybrid_seed_report.json"

HYBRID_SOURCE_IDS = {
    "project": ["prj_001", "prj_005"],
    "expert": ["exp_001", "exp_006"],
    "enterprise": ["ent_001"],
    "funder": ["fnd_001", "fnd_002"],
}


def unit_vector(first: float, second: float = 0.0, dimension: int = 128) -> List[float]:
    values = [0.0] * dimension
    values[0] = first
    values[1] = second
    norm = sum(v * v for v in values) ** 0.5
    return [v / norm for v in values] if norm else values


def embedding_doc(vector: List[float], *, source_hash: str) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "status": st.EMBEDDING_READY,
        "model": "graphsage_lite_v1",
        "version": 1,
        "dimension": 128,
        "source_hash": source_hash,
        "vector": vector,
        "normalized": True,
        "signal": st.EMBEDDING_SIGNAL_OK,
        "updated_at": now,
    }


def seed_entity(repo: AuthRepository, entity_type: str, entity_id: str, vector: List[float]) -> bool:
    collection = repo.get_entity_collection(entity_type)
    if collection is None:
        return False
    id_field = repo.entity_id_field(entity_type)
    doc = repo.find_entity_by_id(entity_type, entity_id)
    if not doc:
        return False
    embedding = embedding_doc(vector, source_hash=f"eval_hybrid_{entity_id}")
    collection.update_one(
        {id_field: entity_id},
        {
            "$set": {
                "embedding": embedding,
                "embedding_status": st.EMBEDDING_READY,
                "kg_sync_status": doc.get("kg_sync_status") or st.KG_SYNCED_VERIFIED,
            }
        },
    )
    return True


def main() -> int:
    require_evaluation_seed_allowed()
    if str(os.getenv("APP_ENV", "development")).lower() in {"production", "prod"}:
        print(
            "WARNING: APP_ENV=production — hybrid seed should only run against dev/staging copies.",
            file=sys.stderr,
        )
    repo = AuthRepository()
    vectors = {
        "prj_001": unit_vector(1.0, 0.1),
        "prj_005": unit_vector(0.9, 0.2),
        "exp_001": unit_vector(0.85, 0.15),
        "exp_006": unit_vector(0.8, 0.25),
        "ent_001": unit_vector(0.7, 0.3),
        "fnd_001": unit_vector(0.75, 0.2),
        "fnd_002": unit_vector(0.65, 0.35),
    }
    report: Dict[str, Any] = {"seeded": [], "missing": []}
    for entity_type, ids in HYBRID_SOURCE_IDS.items():
        for entity_id in ids:
            vector = vectors.get(entity_id) or unit_vector(0.5, 0.1)
            if seed_entity(repo, entity_type, entity_id, vector):
                report["seeded"].append({"entity_type": entity_type, "entity_id": entity_id})
            else:
                report["missing"].append({"entity_type": entity_type, "entity_id": entity_id})

    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Hybrid seed report: {OUT} seeded={len(report['seeded'])} missing={len(report['missing'])}")
    return 0 if report["seeded"] else 1


if __name__ == "__main__":
    sys.exit(main())
