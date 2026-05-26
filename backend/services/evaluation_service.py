from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


class EvaluationService:
    """MVP evaluation summary for demo UI.

    This is not the final offline evaluation pipeline. It summarizes available
    smoke-test artifacts and provides placeholder baseline rows until
    `backend/evaluation/` is implemented.
    """

    def get_summary(self) -> Dict[str, Any]:
        artifact = Path(__file__).resolve().parents[1] / "scripts" / "api_test_results.json"
        policy_passed = None
        total_cases = None

        if artifact.exists():
            try:
                payload = json.loads(artifact.read_text(encoding="utf-8"))
                policy_cases = payload.get("policy_tests") or payload.get("tests") or []
                if isinstance(policy_cases, list):
                    total_cases = len(policy_cases)
                    policy_passed = sum(1 for item in policy_cases if self._is_pass(item))
            except Exception:
                policy_passed = None
                total_cases = None

        rows: List[Dict[str, Any]] = [
            {
                "method": "Random",
                "precision_at_5": None,
                "recall_at_5": None,
                "ndcg_at_5": None,
                "hit_rate_at_5": None,
                "status": "pending",
            },
            {
                "method": "Content-based",
                "precision_at_5": None,
                "recall_at_5": None,
                "ndcg_at_5": None,
                "hit_rate_at_5": None,
                "status": "pending",
            },
            {
                "method": "Graph heuristic",
                "precision_at_5": None,
                "recall_at_5": None,
                "ndcg_at_5": None,
                "hit_rate_at_5": None,
                "status": "pending",
            },
            {
                "method": "PGPR proposed",
                "precision_at_5": None,
                "recall_at_5": None,
                "ndcg_at_5": None,
                "hit_rate_at_5": None,
                "status": "smoke_pass" if policy_passed and total_cases and policy_passed == total_cases else "pending",
            },
        ]

        return {
            "status": "success",
            "data": {
                "note": "MVP summary only. Final baseline metrics still require backend/evaluation pipeline.",
                "smoke_tests": {
                    "passed": policy_passed,
                    "total": total_cases,
                    "artifact": str(artifact),
                },
                "metrics": rows,
            },
        }

    @staticmethod
    def _is_pass(item: Dict[str, Any]) -> bool:
        if item.get("ok") is True or item.get("passed") is True:
            return True
        status = str(item.get("status") or "").lower()
        return status in {"pass", "passed", "success"}
