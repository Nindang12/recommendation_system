"""Phase 8 evaluation pipeline tests."""
from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.metrics import (  # noqa: E402
    aggregate_metrics,
    mrr,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)
from evaluation.regression_gate import evaluate_regression_gate  # noqa: E402
from evaluation.runner import EvaluationRunner, export_report  # noqa: E402
from repositories.auth_repo import AuthRepository  # noqa: E402
from services import provisional_status as st  # noqa: E402

OUT = Path("scripts") / "phase8_evaluation_report.json"


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def unit_vector(first: float, second: float = 0.0, dimension: int = 128) -> List[float]:
    values = [0.0] * dimension
    values[0] = first
    values[1] = second
    norm = sum(v * v for v in values) ** 0.5
    return [v / norm for v in values] if norm else values


def embedding_doc(vector: List[float]) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "status": st.EMBEDDING_READY,
        "model": "graphsage_lite_v1",
        "version": 1,
        "dimension": 128,
        "source_hash": "phase8_eval",
        "vector": vector,
        "normalized": True,
        "signal": st.EMBEDDING_SIGNAL_OK,
        "updated_at": now,
    }


def test_metric_functions() -> None:
    ranked = ["b", "d", "a", "c"]
    relevant = ["b", "d"]
    assert_true(abs(precision_at_k(ranked, relevant, 3) - 2 / 3) < 1e-9, "precision@3")
    assert_true(abs(recall_at_k(ranked, relevant, 3) - 1.0) < 1e-9, "recall@3")
    assert_true(abs(mrr(ranked, relevant) - 1.0) < 1e-9, "mrr")
    ndcg = ndcg_at_k(ranked, relevant, 5, graded_relevance={"b": 3, "d": 1})
    assert_true(ndcg > 0.0, "ndcg")


def test_regression_gate() -> None:
    summary = {
        "hybrid": {"ndcg_at_5": 0.39, "mrr": 0.5, "precision_at_5": 0.4},
        "random": {"ndcg_at_5": 0.1, "mrr": 0.1, "precision_at_5": 0.05},
    }
    baseline = {"hybrid": {"ndcg_at_5": 0.45, "mrr": 0.52, "precision_at_5": 0.41}}
    gate = evaluate_regression_gate(summary, baseline_summary=baseline)
    assert_true(gate["passed"] is False, gate)
    gate_ok = evaluate_regression_gate(
        {"hybrid": {"ndcg_at_5": 0.44, "mrr": 0.51, "precision_at_5": 0.4}},
        baseline_summary=baseline,
    )
    assert_true(gate_ok["passed"] is True, gate_ok)
    assert_true(gate.get("primary_metrics") == ["ndcg_at_5", "mrr"], gate)
    # precision@5 regression alone must not block promote when primary metrics are stable
    gate_precision_only = evaluate_regression_gate(
        {"hybrid": {"ndcg_at_5": 0.45, "mrr": 0.52, "precision_at_5": 0.1}},
        baseline_summary=baseline,
    )
    assert_true(gate_precision_only["passed"] is True, gate_precision_only)


def seed_phase8_fixtures(repo: AuthRepository, suffix: str) -> Dict[str, str]:
    project_id = f"prj_phase8_{suffix}"
    expert_good = f"exp_phase8_good_{suffix}"
    expert_noise = f"exp_phase8_noise_{suffix}"

    project = {
        "project_id": project_id,
        "title": f"Phase8 AI Project {suffix}",
        **st.verified_state(),
        "kg_sync_status": st.KG_SYNCED_VERIFIED,
        "research_topics": ["machine learning", "computer vision"],
        "requirements_and_timeline": {"required_skills": ["python", "deep learning"]},
        "embedding": embedding_doc(unit_vector(1.0, 0.2)),
        "embedding_status": st.EMBEDDING_READY,
    }
    expert_a = {
        "expert_id": expert_good,
        "name": "Phase8 Expert Good",
        **st.verified_state(),
        "kg_sync_status": st.KG_SYNCED_VERIFIED,
        "research_topics": ["machine learning", "computer vision", "nlp"],
        "skills": ["python", "deep learning"],
        "embedding": embedding_doc(unit_vector(0.95, 0.25)),
        "embedding_status": st.EMBEDDING_READY,
    }
    expert_b = {
        "expert_id": expert_noise,
        "name": "Phase8 Expert Noise",
        **st.verified_state(),
        "kg_sync_status": st.KG_SYNCED_VERIFIED,
        "research_topics": ["finance"],
        "skills": ["excel"],
        "embedding": embedding_doc(unit_vector(-0.9, 0.1)),
        "embedding_status": st.EMBEDDING_READY,
    }

    for entity_type, doc in (
        ("project", project),
        ("expert", expert_a),
        ("expert", expert_b),
    ):
        collection = repo.get_entity_collection(entity_type)
        id_field = repo.entity_id_field(entity_type)
        collection.delete_many({id_field: doc[id_field]})
        collection.insert_one(doc)

    return {"project_id": project_id, "expert_good": expert_good, "expert_noise": expert_noise}


async def test_runner_smoke(repo: AuthRepository, suffix: str) -> Dict[str, Any]:
    ids = seed_phase8_fixtures(repo, suffix)
    cases_path = Path("scripts") / f"phase8_eval_cases_{suffix}.json"
    cases_path.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "phase8_project_expert",
                        "source_type": "project",
                        "source_id": ids["project_id"],
                        "target_type": "expert",
                        "relevant_ids": [ids["expert_good"]],
                        "graded_relevance": {ids["expert_good"]: 3},
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    runner = EvaluationRunner(
        cases_path,
        methods=("random", "topic_overlap", "embedding_only", "hybrid"),
        k_values=(5,),
        limit=5,
        seed=7,
    )
    report = await runner.run()
    assert_true(report.get("rows", 0) >= 4, report)
    summary = report.get("summary") or {}
    assert_true("hybrid" in summary and "random" in summary, summary)
    hybrid_ndcg = float(summary["hybrid"].get("ndcg_at_5") or 0.0)
    random_ndcg = float(summary["random"].get("ndcg_at_5") or 0.0)
    assert_true(hybrid_ndcg >= random_ndcg, (hybrid_ndcg, random_ndcg, summary))
    assert_true("regression_gate" in report, report)
    cases_path.unlink(missing_ok=True)
    return report


async def main() -> int:
    suffix = str(int(time.time() * 1000))
    repo = AuthRepository()

    test_metric_functions()
    test_regression_gate()
    smoke = await test_runner_smoke(repo, suffix)

    # Optional smoke on canonical data1 leave-one-edge-out set when present.
    full_cases = Path("scripts") / "evaluation_cases_data1_leave_one_edge_out_160.json"
    full_report: Dict[str, Any] | None = None
    if full_cases.exists():
        runner = EvaluationRunner(full_cases, methods=("hybrid",), limit=5, k_values=(5, 10))
        full_report = await runner.run()
        if full_report.get("rows", 0) > 0:
            export_report(
                full_report,
                Path("scripts") / "evaluation_report_phase8_data1_smoke.json",
                csv_path=Path("scripts") / "evaluation_report_phase8_data1_smoke.csv",
                md_path=Path("scripts") / "evaluation_report_phase8_data1_smoke.md",
            )

    report = {
        "status": "passed",
        "suffix": suffix,
        "smoke_summary": smoke.get("summary"),
        "smoke_regression_gate": smoke.get("regression_gate"),
        "full_rows": (full_report or {}).get("rows"),
        "full_summary": (full_report or {}).get("summary"),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"PASS written {OUT}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except Exception as exc:  # noqa: BLE001
        OUT.write_text(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"FAIL {exc}")
        sys.exit(1)
