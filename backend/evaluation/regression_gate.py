"""Compare evaluation reports against baseline regression thresholds."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_THRESHOLDS = {
    "reference_method": "hybrid",
    "primary_metrics": ["ndcg_at_5", "mrr"],
    "metrics": {
        "ndcg_at_5": {"min_absolute": 0.0, "max_regression": 0.05},
        "mrr": {"min_absolute": 0.0, "max_regression": 0.05},
        "precision_at_5": {
            "min_absolute": 0.0,
            "max_regression": 0.05,
            "informational_only": True,
        },
    },
}


def load_thresholds(path: Optional[Path]) -> Dict[str, Any]:
    if path is None or not path.exists():
        return dict(DEFAULT_THRESHOLDS)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        merged = json.loads(json.dumps(DEFAULT_THRESHOLDS))
        for key, value in payload.items():
            if key == "metrics" and isinstance(value, dict):
                merged.setdefault("metrics", {}).update(value)
            else:
                merged[key] = value
        return merged
    except Exception:
        return dict(DEFAULT_THRESHOLDS)


def _primary_metrics_list(thresholds: Dict[str, Any]) -> List[str]:
    raw = thresholds.get("primary_metrics") or ["ndcg_at_5", "mrr"]
    return [str(m) for m in raw]


def evaluate_regression_gate(
    summary: Dict[str, Any],
    *,
    baseline_summary: Optional[Dict[str, Any]] = None,
    thresholds: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    thresholds = thresholds or DEFAULT_THRESHOLDS
    reference = str(thresholds.get("reference_method") or "hybrid")
    metric_rules = thresholds.get("metrics") or {}
    primary_metrics = _primary_metrics_list(thresholds)
    ref_metrics = (summary or {}).get(reference) or {}
    base_metrics = ((baseline_summary or {}).get(reference) or {}) if baseline_summary else {}

    checks: List[Dict[str, Any]] = []
    primary_passed = True

    for metric_name, rule in metric_rules.items():
        if not isinstance(rule, dict):
            continue
        is_primary = metric_name in primary_metrics and not rule.get("informational_only")
        current = ref_metrics.get(metric_name)
        baseline = base_metrics.get(metric_name)
        min_absolute = rule.get("min_absolute")
        max_regression = rule.get("max_regression")

        ok = True
        reason = "ok"
        if current is None:
            ok = False
            reason = "missing_metric"
        elif min_absolute is not None and float(current) < float(min_absolute):
            ok = False
            reason = f"below_min_absolute({min_absolute})"
        elif baseline is not None and max_regression is not None:
            drop = float(baseline) - float(current)
            if drop > float(max_regression):
                ok = False
                reason = f"regressed_by_{drop:.4f}_max_{max_regression}"

        if not ok and is_primary:
            primary_passed = False

        checks.append(
            {
                "method": reference,
                "metric": metric_name,
                "is_primary": is_primary,
                "current": current,
                "baseline": baseline,
                "passed": ok,
                "reason": reason,
            }
        )

    return {
        "passed": primary_passed,
        "reference_method": reference,
        "primary_metrics": primary_metrics,
        "checks": checks,
        "message": "promote_allowed" if primary_passed else "promote_blocked_regression",
    }


def load_baseline_summary(path: Optional[Path]) -> Optional[Dict[str, Any]]:
    if path is None or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload.get("summary") or payload.get("data", {}).get("summary")
    except Exception:
        return None


LOWER_IS_BETTER_METRICS = frozenset({"latency_ms_p50", "latency_ms_p95", "latency_ms_avg"})

COMPARISON_METRICS = (
    "ndcg_at_5",
    "mrr",
    "precision_at_5",
    "recall_at_5",
    "ndcg_at_10",
    "hit_rate_at_5",
    "latency_ms_p50",
    "explanation_coverage",
)


def build_baseline_comparison(
    summary: Dict[str, Any],
    baseline_summary: Optional[Dict[str, Any]],
    *,
    epsilon: float = 1e-6,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not baseline_summary:
        return rows

    for method in sorted(set(summary.keys()) | set(baseline_summary.keys())):
        current_metrics = summary.get(method) or {}
        base_metrics = baseline_summary.get(method) or {}
        for metric in COMPARISON_METRICS:
            current = current_metrics.get(metric)
            baseline = base_metrics.get(metric)
            if current is None and baseline is None:
                continue
            delta = None
            status = "no_baseline"
            if current is not None and baseline is not None:
                delta = float(current) - float(baseline)
                if abs(delta) <= epsilon:
                    status = "unchanged"
                elif metric in LOWER_IS_BETTER_METRICS:
                    status = "improved" if delta < 0 else "regressed"
                else:
                    status = "improved" if delta > 0 else "regressed"
            elif current is not None:
                status = "new_metric"
            rows.append(
                {
                    "method": method,
                    "metric": metric,
                    "current": current,
                    "baseline": baseline,
                    "delta": round(delta, 6) if delta is not None else None,
                    "status": status,
                }
            )
    return rows
