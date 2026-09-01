"""Paired statistical significance tests for the 240-query multi-method run.

Reads the per-query rows already produced by the offline evaluation runner
(``evaluation_report_data1_leave_one_edge_out_240_all.json``) and computes, for
each pair of methods sharing the same 240 leave-one-edge-out queries:

- Wilcoxon signed-rank test (normal approximation with tie correction; no
  scipy dependency, matching this project's requirements.txt) on the paired
  per-query metric values.
- A 10,000-resample bootstrap 95% confidence interval on the mean paired
  difference.
- Matched-pairs rank-biserial correlation as an effect-size estimate.

This is a read-only, offline analysis script: it does not call the live
recommendation pipeline or touch Neo4j/MongoDB, it only re-analyzes an
existing evaluation artifact.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "scripts" / "evaluation_report_data1_leave_one_edge_out_240_all.json"
DEFAULT_OUTPUT_JSON = ROOT / "scripts" / "significance_tests_240_all.json"
DEFAULT_OUTPUT_MD = ROOT / "scripts" / "significance_tests_240_all.md"

METRICS = ["ndcg_at_5", "mrr", "precision_at_5", "recall_at_5", "explanation_coverage", "cold_start_success"]
METHODS = ["hybrid", "pgpr_only", "graph_heuristic", "random"]
PAIRS = [
    ("hybrid", "pgpr_only"),
    ("hybrid", "graph_heuristic"),
    ("hybrid", "random"),
    ("pgpr_only", "graph_heuristic"),
]
ALPHA = 0.05
BOOTSTRAP_RESAMPLES = 10_000
RANDOM_SEED = 42


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _rankdata_avg(a: np.ndarray) -> np.ndarray:
    """Average ranks with tie handling (1-indexed), no scipy dependency."""
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(len(a), dtype=float)
    sorted_a = a[order]
    i = 0
    while i < len(a):
        j = i
        while j < len(a) - 1 and sorted_a[j + 1] == sorted_a[i]:
            j += 1
        ranks[order[i : j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return ranks


def wilcoxon_signed_rank(x: list[float], y: list[float]) -> dict[str, Any]:
    """Two-sided Wilcoxon signed-rank test, normal approximation with tie correction."""
    diff = np.asarray(x, dtype=float) - np.asarray(y, dtype=float)
    nz = diff[diff != 0]
    n = len(nz)
    if n == 0:
        return dict(n=0, n_zero=len(diff), w_plus=0.0, w_minus=0.0, z=0.0, p_value=1.0, effect_r=0.0)
    abs_d = np.abs(nz)
    ranks = _rankdata_avg(abs_d)
    signed_ranks = ranks * np.sign(nz)
    w_plus = float(signed_ranks[signed_ranks > 0].sum())
    w_minus = float(-signed_ranks[signed_ranks < 0].sum())
    w_stat = min(w_plus, w_minus)
    mean_w = n * (n + 1) / 4.0
    _vals, counts = np.unique(abs_d, return_counts=True)
    tie_term = float(np.sum(counts**3 - counts))
    var_w = n * (n + 1) * (2 * n + 1) / 24.0 - tie_term / 48.0
    z = (w_stat - mean_w) / math.sqrt(var_w) if var_w > 0 else 0.0
    p_value = 2 * (1 - _norm_cdf(abs(z)))
    total_rank_sum = n * (n + 1) / 2.0
    effect_r = (w_plus - w_minus) / total_rank_sum if total_rank_sum > 0 else 0.0
    return dict(
        n=n, n_zero=len(diff) - n, w_plus=w_plus, w_minus=w_minus,
        z=z, p_value=p_value, effect_r=effect_r,
    )


def bootstrap_ci_mean_diff(
    x: list[float], y: list[float], rng: np.random.Generator, resamples: int = BOOTSTRAP_RESAMPLES,
    alpha: float = ALPHA,
) -> dict[str, float]:
    diff = np.asarray(x, dtype=float) - np.asarray(y, dtype=float)
    n = len(diff)
    boot_means = np.empty(resamples)
    for b in range(resamples):
        sample_idx = rng.integers(0, n, n)
        boot_means[b] = diff[sample_idx].mean()
    lo = float(np.percentile(boot_means, 100 * alpha / 2))
    hi = float(np.percentile(boot_means, 100 * (1 - alpha / 2)))
    return dict(mean_diff=float(diff.mean()), ci_lo=lo, ci_hi=hi)


def _load_per_query_index(path: Path) -> dict[str, dict[str, dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    per_query = payload["per_query"]
    idx: dict[str, dict[str, dict[str, Any]]] = {m: {} for m in METHODS}
    for row in per_query:
        method = row.get("method")
        if method in idx:
            idx[method][row["case_id"]] = row
    return idx


def run(input_path: Path) -> dict[str, Any]:
    idx = _load_per_query_index(input_path)
    case_ids = sorted(idx["hybrid"].keys())
    for m in METHODS:
        if set(idx[m].keys()) != set(case_ids):
            raise ValueError(f"Method '{m}' does not share the same case_id set as 'hybrid'")

    rng = np.random.default_rng(RANDOM_SEED)
    rows: list[dict[str, Any]] = []
    for metric in METRICS:
        for a, b in PAIRS:
            xa = [idx[a][c][metric] for c in case_ids]
            xb = [idx[b][c][metric] for c in case_ids]
            wr = wilcoxon_signed_rank(xa, xb)
            boot = bootstrap_ci_mean_diff(xa, xb, rng)
            row = dict(
                metric=metric, method_a=a, method_b=b,
                mean_a=float(np.mean(xa)), mean_b=float(np.mean(xb)),
                significant=bool(wr["p_value"] < ALPHA),
                **wr, **boot,
            )
            rows.append(row)

    return dict(
        input_artifact=str(input_path.relative_to(ROOT)),
        n_queries=len(case_ids),
        alpha=ALPHA,
        bootstrap_resamples=BOOTSTRAP_RESAMPLES,
        random_seed=RANDOM_SEED,
        test="wilcoxon_signed_rank_normal_approx_tie_corrected",
        rows=rows,
    )


def _fmt(v: float) -> str:
    return f"{v:.4f}"


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Paired significance tests (240-query leave-one-edge-out, multi-method run)",
        "",
        f"Input artifact: `{result['input_artifact']}`  ",
        f"n_queries={result['n_queries']}, alpha={result['alpha']}, "
        f"bootstrap_resamples={result['bootstrap_resamples']}, test={result['test']}",
        "",
        "| Metric | A vs B | mean(A) | mean(B) | mean diff | 95% CI | z | p-value | effect r | Significant? |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in result["rows"]:
        ci = f"[{_fmt(row['ci_lo'])}, {_fmt(row['ci_hi'])}]"
        sig = "Yes" if row["significant"] else "No"
        lines.append(
            f"| {row['metric']} | {row['method_a']} vs {row['method_b']} | "
            f"{_fmt(row['mean_a'])} | {_fmt(row['mean_b'])} | {_fmt(row['mean_diff'])} | {ci} | "
            f"{row['z']:.3f} | {row['p_value']:.4g} | {row['effect_r']:.3f} | {sig} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    args = parser.parse_args()

    result = run(args.input)
    args.output_json.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    args.output_md.write_text(render_markdown(result), encoding="utf-8")
    print(f"Wrote {args.output_json}")
    print(f"Wrote {args.output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
