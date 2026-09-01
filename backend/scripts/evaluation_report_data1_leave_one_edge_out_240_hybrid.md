# Evaluation Report

- Generated: 2026-06-20T07:10:18.997855+00:00
- Cases: 240 queries, 240 rows
- Regression gate: **PASS** (promote_allowed)

## Summary by method

| Method | NDCG@5 | MRR | P@5 | R@5 | Latency p50 (ms) | Explanation cov. |
|---|---:|---:|---:|---:|---:|---:|
| hybrid | 0.7465 | 0.7832 | 0.6660 | 0.7438 | 3042.365 | 0.8833 |

## Regression checks

Primary metrics (gate): `ndcg_at_5, mrr`

- [PASS] `hybrid.ndcg_at_5` (primary) current=0.7464917778513025 baseline=None (ok)
- [PASS] `hybrid.mrr` (primary) current=0.7832109788359788 baseline=None (ok)
- [PASS] `hybrid.precision_at_5` (informational) current=0.6659722222222223 baseline=None (ok)
