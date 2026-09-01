from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class EvaluationService:
    """Evaluation summary for admin/demo UI backed by Phase 8 offline reports."""

    REPORT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "evaluation_report.json"
    ARTIFACT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "api_test_results.json"

    def get_summary(self) -> Dict[str, Any]:
        report = self._load_report()
        if report and report.get("summary"):
            return {
                "status": "success",
                "data": {
                    "note": "Phase 8 offline evaluation report.",
                    "generated_at": report.get("generated_at"),
                    "queries_run": report.get("queries_run"),
                    "regression_gate": report.get("regression_gate"),
                    "baseline_comparison": report.get("baseline_comparison") or [],
                    "metrics": self._summary_rows(report.get("summary") or {}),
                    "report_path": str(self.REPORT_PATH),
                },
            }

        return self._legacy_smoke_summary()

    def _load_report(self) -> Optional[Dict[str, Any]]:
        if not self.REPORT_PATH.exists():
            return None
        try:
            return json.loads(self.REPORT_PATH.read_text(encoding="utf-8"))
        except Exception:
            return None

    @staticmethod
    def _summary_rows(summary: Dict[str, Any]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for method, metrics in sorted(summary.items()):
            if not isinstance(metrics, dict):
                continue
            rows.append(
                {
                    "method": method,
                    "precision_at_5": metrics.get("precision_at_5"),
                    "recall_at_5": metrics.get("recall_at_5"),
                    "ndcg_at_5": metrics.get("ndcg_at_5"),
                    "mrr": metrics.get("mrr"),
                    "hit_rate_at_5": metrics.get("hit_rate_at_5"),
                    "coverage": metrics.get("coverage"),
                    "cold_start_success_rate": metrics.get("cold_start_success_rate"),
                    "explanation_coverage": metrics.get("explanation_coverage"),
                    "latency_ms_p50": metrics.get("latency_ms_p50"),
                    "latency_ms_p95": metrics.get("latency_ms_p95"),
                    "status": "measured",
                }
            )
        return rows

    def _legacy_smoke_summary(self) -> Dict[str, Any]:
        artifact = self.ARTIFACT_PATH
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
                "method": method,
                "precision_at_5": None,
                "recall_at_5": None,
                "ndcg_at_5": None,
                "hit_rate_at_5": None,
                "status": "pending",
            }
            for method in ("random", "topic_overlap", "graph_heuristic", "pgpr_only", "embedding_only", "hybrid")
        ]
        rows.append(
            {
                "method": "PGPR policy smoke",
                "precision_at_5": None,
                "recall_at_5": None,
                "ndcg_at_5": None,
                "hit_rate_at_5": None,
                "status": "smoke_pass"
                if policy_passed and total_cases and policy_passed == total_cases
                else "pending",
            }
        )

        return {
            "status": "success",
            "data": {
                "note": "Chua co evaluation_report.json. Chay: python scripts/run_evaluation.py",
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
