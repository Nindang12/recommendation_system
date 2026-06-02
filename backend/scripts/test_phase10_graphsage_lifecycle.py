"""Phase 10 GraphSAGE lifecycle smoke tests.

The test uses an in-memory synthetic snapshot so it does not require Neo4j and
does not mutate the running recommendation system.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml.graphsage.constants import DEFAULT_CANDIDATE_NAME  # noqa: E402
from ml.graphsage.encoder import NodeFeatureEncoder  # noqa: E402
from ml.graphsage.snapshot import sanitize_properties  # noqa: E402
from ml.graphsage.trainer import GraphSAGECandidateTrainer  # noqa: E402

OUT = ROOT / "scripts" / "phase10_graphsage_lifecycle_report.json"
TMP = ROOT / "artifacts" / "phase10_test"


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def make_snapshot() -> dict:
    return {
        "schema_version": 1,
        "snapshot_id": "snapshot_phase10_unit",
        "created_at": "2026-06-01T00:00:00+00:00",
        "nodes": [
            {
                "element_id": "n1",
                "id": "exp_a",
                "labels": ["Expert"],
                "primary_label": "Expert",
                "properties": {"expert_id": "exp_a", "name": "Expert A", "trust_weight": 1.0},
            },
            {
                "element_id": "n2",
                "id": "prj_a",
                "labels": ["Project"],
                "primary_label": "Project",
                "properties": {"project_id": "prj_a", "title": "Project A", "trust_weight": 1.0},
            },
            {
                "element_id": "n3",
                "id": "topic_ai",
                "labels": ["ResearchTopic"],
                "primary_label": "ResearchTopic",
                "properties": {"topic_id": "topic_ai", "name": "Artificial Intelligence"},
            },
        ],
        "edges": [
            {"element_id": "r1", "source": "n1", "target": "n3", "type": "INTERESTED_IN", "properties": {}},
            {"element_id": "r2", "source": "n2", "target": "n3", "type": "FOCUSES_ON_TOPIC", "properties": {}},
        ],
        "metadata": {"node_count": 3, "edge_count": 2},
    }


def main() -> int:
    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir(parents=True, exist_ok=True)
    snapshot_path = TMP / "snapshot_phase10_unit.json"
    snapshot_path.write_text(json.dumps(make_snapshot(), ensure_ascii=False, indent=2), encoding="utf-8")

    sanitized = sanitize_properties(
        {
            "name": "Visible",
            "email": "hidden@example.com",
            "phone": "hidden",
            "password_hash": "hidden",
            "embedding_vector": [1, 2, 3],
            "trust_weight": 0.5,
        }
    )
    assert_true("name" in sanitized, "name should be kept")
    assert_true("trust_weight" in sanitized, "trust_weight should be kept")
    assert_true("email" not in sanitized, "email must not be exported")
    assert_true("phone" not in sanitized, "phone must not be exported")
    assert_true("password_hash" not in sanitized, "password hash must not be exported")
    assert_true("embedding_vector" not in sanitized, "vectors must not be exported")

    encoder = NodeFeatureEncoder(dimension=16)
    first = encoder.encode_snapshot(make_snapshot())
    second = encoder.encode_snapshot(make_snapshot())
    assert_true(first == second, "encoder must be deterministic")

    trainer = GraphSAGECandidateTrainer(
        model_name=DEFAULT_CANDIDATE_NAME,
        dimension=16,
        min_positive_edges=50,
        random_seed=42,
    )
    trainer.registry.root = TMP / "models"
    trainer.registry.active_pointer = trainer.registry.root / "active_embedding_model.json"
    report = trainer.train_from_snapshot(snapshot_path)
    assert_true(report["runtime_unchanged"] is True, "training must not alter runtime")
    assert_true(report["promote_allowed"] is False, "small dataset must not promote")
    assert_true("positive_edges_below_threshold" in " ".join(report["warnings"]), "expected threshold warning")
    candidate_dir = trainer.registry.root / DEFAULT_CANDIDATE_NAME
    assert_true((candidate_dir / "metadata.json").exists(), "metadata artifact")
    assert_true((candidate_dir / "evaluation_report.json").exists(), "candidate evaluation report")
    assert_true((trainer.registry.root / "active_embedding_model.json").exists(), "active pointer")

    OUT.write_text(json.dumps({"status": "pass", "report": report}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "pass", "report_path": str(OUT)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

