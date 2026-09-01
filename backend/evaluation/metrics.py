"""Ranking metrics for offline evaluation."""
from __future__ import annotations

import math
from statistics import median
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


def _relevance_map(relevant_ids: Sequence[str], graded: Optional[Mapping[str, float]] = None) -> Dict[str, float]:
    graded = graded or {}
    out: Dict[str, float] = {}
    for rid in relevant_ids:
        rid = str(rid)
        out[rid] = float(graded.get(rid, 1.0))
    for rid, score in graded.items():
        if str(rid) not in out:
            out[str(rid)] = float(score)
    return out


def precision_at_k(ranked_ids: Sequence[str], relevant_ids: Sequence[str], k: int) -> float:
    if k <= 0:
        return 0.0
    top = [str(x) for x in ranked_ids[:k]]
    rel = {str(x) for x in relevant_ids}
    if not top:
        return 0.0
    hits = sum(1 for item in top if item in rel)
    return hits / len(top)


def recall_at_k(ranked_ids: Sequence[str], relevant_ids: Sequence[str], k: int) -> float:
    rel = {str(x) for x in relevant_ids}
    if not rel:
        return 0.0
    top = [str(x) for x in ranked_ids[:k]]
    hits = sum(1 for item in top if item in rel)
    return hits / len(rel)


def hit_rate_at_k(ranked_ids: Sequence[str], relevant_ids: Sequence[str], k: int) -> float:
    rel = {str(x) for x in relevant_ids}
    if not rel:
        return 0.0
    top = {str(x) for x in ranked_ids[:k]}
    return 1.0 if top & rel else 0.0


def dcg_at_k(ranked_ids: Sequence[str], relevance: Mapping[str, float], k: int) -> float:
    total = 0.0
    for index, item_id in enumerate(ranked_ids[:k], start=1):
        rel = float(relevance.get(str(item_id), 0.0))
        if rel <= 0:
            continue
        total += rel / math.log2(index + 1)
    return total


def ndcg_at_k(
    ranked_ids: Sequence[str],
    relevant_ids: Sequence[str],
    k: int,
    *,
    graded_relevance: Optional[Mapping[str, float]] = None,
) -> float:
    relevance = _relevance_map(relevant_ids, graded_relevance)
    if not relevance:
        return 0.0
    dcg = dcg_at_k(ranked_ids, relevance, k)
    ideal_ids = sorted(relevance.keys(), key=lambda key: relevance[key], reverse=True)
    idcg = dcg_at_k(ideal_ids, relevance, k)
    if idcg <= 0:
        return 0.0
    return dcg / idcg


def mrr(ranked_ids: Sequence[str], relevant_ids: Sequence[str]) -> float:
    rel = {str(x) for x in relevant_ids}
    if not rel:
        return 0.0
    for index, item_id in enumerate(ranked_ids, start=1):
        if str(item_id) in rel:
            return 1.0 / index
    return 0.0


def coverage(all_recommended: Iterable[str], catalog_ids: Sequence[str]) -> float:
    catalog = {str(x) for x in catalog_ids}
    if not catalog:
        return 0.0
    seen = {str(x) for x in all_recommended}
    return len(seen & catalog) / len(catalog)


def explanation_coverage(items: Sequence[Mapping[str, Any]]) -> float:
    if not items:
        return 0.0
    covered = 0
    for item in items:
        paths = item.get("reasoning_paths") or []
        explanation = str(item.get("explanation") or item.get("xai_explanation") or "").strip()
        if paths or explanation:
            covered += 1
    return covered / len(items)


def percentile(values: Sequence[float], pct: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (pct / 100.0)
    low = int(math.floor(rank))
    high = int(math.ceil(rank))
    if low == high:
        return ordered[low]
    weight = rank - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def aggregate_metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Average per-query metrics grouped by method."""
    by_method: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        by_method.setdefault(str(row["method"]), []).append(row)

    summary: Dict[str, Any] = {}
    for method, group in by_method.items():
        latencies = [float(g.get("latency_ms", 0.0) or 0.0) for g in group]
        summary[method] = {
            "queries": len(group),
            "precision_at_5": _mean([g.get("precision_at_5") for g in group]),
            "recall_at_5": _mean([g.get("recall_at_5") for g in group]),
            "ndcg_at_5": _mean([g.get("ndcg_at_5") for g in group]),
            "mrr": _mean([g.get("mrr") for g in group]),
            "hit_rate_at_5": _mean([g.get("hit_rate_at_5") for g in group]),
            "precision_at_10": _mean([g.get("precision_at_10") for g in group]),
            "recall_at_10": _mean([g.get("recall_at_10") for g in group]),
            "ndcg_at_10": _mean([g.get("ndcg_at_10") for g in group]),
            "hit_rate_at_10": _mean([g.get("hit_rate_at_10") for g in group]),
            "coverage": _mean([g.get("coverage") for g in group]),
            "cold_start_success_rate": _mean([g.get("cold_start_success") for g in group]),
            "explanation_coverage": _mean([g.get("explanation_coverage") for g in group]),
            "latency_ms_avg": _mean(latencies),
            "latency_ms_p50": percentile(latencies, 50),
            "latency_ms_p95": percentile(latencies, 95),
            "time_to_first_usable_ms_avg": _mean([g.get("time_to_first_usable_ms") for g in group]),
        }
    return summary


def _mean(values: Sequence[Any]) -> Optional[float]:
    nums = [float(v) for v in values if v is not None]
    if not nums:
        return None
    return sum(nums) / len(nums)
