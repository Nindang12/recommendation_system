"""Run offline evaluation across baselines and production rankers."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from evaluation.metrics import (
    aggregate_metrics,
    coverage,
    explanation_coverage,
    hit_rate_at_k,
    mrr,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)
from evaluation.rankers import METHODS, EvaluationRankers
from evaluation.pgpr_session import close_evaluation_recommender
from evaluation.regression_gate import (
    build_baseline_comparison,
    evaluate_regression_gate,
    load_baseline_summary,
    load_thresholds,
)
from repositories.auth_repo import AuthRepository
from services.hybrid_recommendation_service import HybridRecommendationService


class EvaluationRunner:
    def __init__(
        self,
        cases_path: Path,
        *,
        config_path: Optional[Path] = None,
        baseline_path: Optional[Path] = None,
        methods: Optional[Sequence[str]] = None,
        k_values: Optional[Sequence[int]] = None,
        limit: int = 10,
        seed: int = 42,
    ) -> None:
        self.cases_path = cases_path
        self.config_path = config_path
        self.baseline_path = baseline_path
        self.methods = tuple(methods or METHODS)
        self.k_values = tuple(k_values or (5, 10))
        self.limit = max(1, min(limit, 50))
        self.repo = AuthRepository()
        self.hybrid = HybridRecommendationService(self.repo)
        self.rankers = EvaluationRankers(auth_repo=self.repo, hybrid=self.hybrid, seed=seed)
        self.thresholds = load_thresholds(config_path)

    def load_cases(self) -> List[Dict[str, Any]]:
        payload = json.loads(self.cases_path.read_text(encoding="utf-8"))
        cases = payload.get("cases") or []
        if not isinstance(cases, list):
            raise ValueError("evaluation cases must be a list")
        return cases

    def load_dataset_metadata(self) -> Dict[str, Any]:
        payload = json.loads(self.cases_path.read_text(encoding="utf-8"))
        return {
            "label_version": payload.get("label_version"),
            "label_created_at": payload.get("label_created_at"),
            "label_policy": payload.get("label_policy"),
            "cases_file_version": payload.get("version"),
        }

    async def run(self) -> Dict[str, Any]:
        cases = self.load_cases()
        per_query: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        catalog_by_target: Dict[str, List[str]] = {}

        try:
            return await self._run_cases(cases, per_query, skipped, catalog_by_target)
        finally:
            close_evaluation_recommender()

    async def _run_cases(
        self,
        cases: List[Dict[str, Any]],
        per_query: List[Dict[str, Any]],
        skipped: List[Dict[str, Any]],
        catalog_by_target: Dict[str, List[str]],
    ) -> Dict[str, Any]:
        for case in cases:
            prepared = self._prepare_case(case)
            if prepared is None:
                skipped.append({"case_id": case.get("case_id"), "reason": "missing_source_or_empty_ground_truth"})
                continue

            case_id = prepared["case_id"]
            target_type = prepared["target_type"]
            catalog_ids = self._catalog_ids(target_type)
            catalog_by_target[target_type] = catalog_ids
            src_ctx = self.hybrid.source_recommendation_context(prepared["source_type"], prepared["source_id"])
            cold_start = bool(src_ctx.get("cold_start"))

            for method in self.methods:
                try:
                    items, latency_ms = await self.rankers.rank(
                        method,
                        source_type=prepared["source_type"],
                        source_id=prepared["source_id"],
                        target_type=target_type,
                        limit=self.limit,
                        mode=prepared.get("mode") or "public",
                        current_user_id=prepared.get("current_user_id"),
                    )
                except Exception as exc:  # noqa: BLE001
                    skipped.append({"case_id": case_id, "method": method, "reason": str(exc)})
                    continue

                ranked_ids = [str(item.get("id") or "") for item in items if item.get("id")]
                relevant = prepared["relevant_ids"]
                graded = prepared.get("graded_relevance") or {}

                row: Dict[str, Any] = {
                    "case_id": case_id,
                    "method": method,
                    "source_type": prepared["source_type"],
                    "source_id": prepared["source_id"],
                    "target_type": target_type,
                    "label_source": prepared.get("label_source"),
                    "tags": prepared.get("tags") or [],
                    "hybrid_ready_expected": prepared.get("hybrid_ready_expected", False),
                    "cold_start": cold_start,
                    "latency_ms": round(latency_ms, 2),
                    "time_to_first_usable_ms": round(latency_ms, 2) if ranked_ids else None,
                    "result_count": len(ranked_ids),
                    "coverage": coverage(ranked_ids, catalog_ids),
                    "explanation_coverage": explanation_coverage(items),
                    "cold_start_success": 1.0 if (not cold_start or hit_rate_at_k(ranked_ids, relevant, max(self.k_values))) else 0.0,
                    "mrr": mrr(ranked_ids, relevant),
                }
                for k in self.k_values:
                    row[f"precision_at_{k}"] = precision_at_k(ranked_ids, relevant, k)
                    row[f"recall_at_{k}"] = recall_at_k(ranked_ids, relevant, k)
                    row[f"ndcg_at_{k}"] = ndcg_at_k(ranked_ids, relevant, k, graded_relevance=graded)
                    row[f"hit_rate_at_{k}"] = hit_rate_at_k(ranked_ids, relevant, k)
                per_query.append(row)

        summary = aggregate_metrics(per_query)
        baseline_summary = load_baseline_summary(self.baseline_path)
        regression = evaluate_regression_gate(summary, baseline_summary=baseline_summary, thresholds=self.thresholds)
        baseline_comparison = build_baseline_comparison(summary, baseline_summary)

        explicit_cases = sum(1 for case in cases if case.get("label_source") == "admin_review" and case.get("relevant_ids"))
        hybrid_cases = sum(1 for case in cases if "hybrid_ready" in (case.get("tags") or []))

        return {
            "status": "success" if per_query else "empty",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "cases_path": str(self.cases_path),
            "label_metadata": self.load_dataset_metadata(),
            "methods": list(self.methods),
            "k_values": list(self.k_values),
            "limit": self.limit,
            "queries_run": len({row["case_id"] for row in per_query}),
            "explicit_case_count": explicit_cases,
            "hybrid_ready_case_count": hybrid_cases,
            "rows": len(per_query),
            "skipped": skipped,
            "per_query": per_query,
            "summary": summary,
            "baseline_comparison": baseline_comparison,
            "regression_gate": regression,
        }

    def _prepare_case(self, case: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        source_type = str(case.get("source_type") or "").lower()
        source_id = str(case.get("source_id") or "")
        target_type = str(case.get("target_type") or "").lower()
        if not source_type or not source_id or not target_type:
            return None

        source = self.repo.find_entity_by_id(source_type, source_id)
        if not source:
            return None

        relevant_ids = [str(x) for x in (case.get("relevant_ids") or [])]
        graded = case.get("graded_relevance") or {}
        auto_mode = str(case.get("auto_ground_truth") or "").strip()

        if not relevant_ids and auto_mode:
            relevant_ids, graded = self._auto_ground_truth(
                source_type,
                source_id,
                target_type,
                mode=auto_mode,
                top_n=int(case.get("auto_top_n") or 3),
            )

        if not relevant_ids:
            return None

        return {
            "case_id": str(case.get("case_id") or f"{source_id}->{target_type}"),
            "source_type": source_type,
            "source_id": source_id,
            "target_type": target_type,
            "mode": case.get("mode") or "public",
            "current_user_id": case.get("current_user_id"),
            "relevant_ids": relevant_ids,
            "graded_relevance": graded,
            "label_source": case.get("label_source") or ("auto_ground_truth" if auto_mode else "unspecified"),
            "tags": case.get("tags") or [],
            "hybrid_ready_expected": bool(case.get("hybrid_ready_expected") or "hybrid_ready" in (case.get("tags") or [])),
            "notes": case.get("notes"),
        }

    def _auto_ground_truth(
        self,
        source_type: str,
        source_id: str,
        target_type: str,
        *,
        mode: str,
        top_n: int,
    ) -> tuple[List[str], Dict[str, float]]:
        source = self.repo.find_entity_by_id(source_type, source_id) or {}
        if mode == "topic_overlap_top":
            hits = self.rankers._topic_overlap_hits(
                source,
                target_type,
                exclude_ids=set(),
                limit=max(top_n, 3),
                require_embedding_ready=False,
            )
            hits.sort(key=lambda row: float(row.get("topic_overlap", 0.0) or 0.0), reverse=True)
            ids = [str(h.get("id")) for h in hits[:top_n] if h.get("id")]
            graded = {rid: float(top_n - idx) for idx, rid in enumerate(ids)}
            return ids, graded
        return [], {}

    def _catalog_ids(self, target_type: str) -> List[str]:
        collection = self.repo.get_entity_collection(target_type)
        if collection is None:
            return []
        id_field = self.repo.entity_id_field(target_type)
        cursor = collection.find({}, {id_field: 1}).limit(500)
        return [str(doc.get(id_field)) for doc in cursor if doc.get(id_field)]


def export_report(report: Dict[str, Any], output_json: Path, *, csv_path: Optional[Path] = None, md_path: Optional[Path] = None) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    if csv_path:
        _write_csv(report.get("per_query") or [], csv_path)
    if md_path:
        _write_markdown(report, md_path)


def _write_csv(rows: List[Dict[str, Any]], path: Path) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: List[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_markdown(report: Dict[str, Any], path: Path) -> None:
    summary = report.get("summary") or {}
    gate = report.get("regression_gate") or {}
    lines = [
        "# Evaluation Report",
        "",
        f"- Generated: {report.get('generated_at')}",
        f"- Cases: {report.get('queries_run')} queries, {report.get('rows')} rows",
        f"- Regression gate: **{'PASS' if gate.get('passed') else 'FAIL'}** ({gate.get('message')})",
        "",
        "## Summary by method",
        "",
        "| Method | NDCG@5 | MRR | P@5 | R@5 | Latency p50 (ms) | Explanation cov. |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for method, metrics in sorted(summary.items()):
        lines.append(
            "| {method} | {ndcg:.4f} | {mrr:.4f} | {p5:.4f} | {r5:.4f} | {lat} | {xcov:.4f} |".format(
                method=method,
                ndcg=float(metrics.get("ndcg_at_5") or 0.0),
                mrr=float(metrics.get("mrr") or 0.0),
                p5=float(metrics.get("precision_at_5") or 0.0),
                r5=float(metrics.get("recall_at_5") or 0.0),
                lat=metrics.get("latency_ms_p50"),
                xcov=float(metrics.get("explanation_coverage") or 0.0),
            )
        )
    if gate.get("checks"):
        primary = gate.get("primary_metrics") or []
        lines.extend(
            [
                "",
                "## Regression checks",
                "",
                f"Primary metrics (gate): `{', '.join(primary)}`",
                "",
            ]
        )
        for check in gate["checks"]:
            status = "PASS" if check.get("passed") else "FAIL"
            primary_tag = "primary" if check.get("is_primary") else "informational"
            lines.append(
                f"- [{status}] `{check.get('method')}.{check.get('metric')}` ({primary_tag}) "
                f"current={check.get('current')} baseline={check.get('baseline')} ({check.get('reason')})"
            )

    comparison = report.get("baseline_comparison") or []
    if comparison:
        lines.extend(
            [
                "",
                "## Delta vs baseline",
                "",
                "| Method | Metric | Current | Baseline | Delta | Status |",
                "|---|---|---:|---:|---:|---|",
            ]
        )
        for row in comparison:
            lines.append(
                "| {method} | {metric} | {current} | {baseline} | {delta} | {status} |".format(
                    method=row.get("method"),
                    metric=row.get("metric"),
                    current=row.get("current"),
                    baseline=row.get("baseline"),
                    delta=row.get("delta"),
                    status=row.get("status"),
                )
            )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
