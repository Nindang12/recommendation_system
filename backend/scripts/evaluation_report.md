# Evaluation Report

- Generated: 2026-05-29T06:09:16.902043+00:00
- Cases: 22 queries, 132 rows
- Regression gate: **PASS** (promote_allowed)

## Summary by method

| Method | NDCG@5 | MRR | P@5 | R@5 | Latency p50 (ms) | Explanation cov. |
|---|---:|---:|---:|---:|---:|---:|
| embedding_only | 0.1762 | 0.2273 | 0.2045 | 0.1894 | 29.134999999999998 | 0.0000 |
| graph_heuristic | 0.5255 | 0.5939 | 0.2614 | 0.6288 | 1522.69 | 0.8977 |
| hybrid | 0.5386 | 0.5886 | 0.2750 | 0.6288 | 1517.315 | 0.8000 |
| pgpr_only | 0.4322 | 0.4939 | 0.2447 | 0.4848 | 1440.33 | 1.0000 |
| random | 0.3181 | 0.3030 | 0.1977 | 0.4545 | 1544.4850000000001 | 0.4591 |
| topic_overlap | 0.2109 | 0.2727 | 0.1477 | 0.2045 | 5.85 | 0.0000 |

## Regression checks

Primary metrics (gate): `ndcg_at_5, mrr`

- [PASS] `hybrid.ndcg_at_5` (primary) current=0.5385735394806932 baseline=None (ok)
- [PASS] `hybrid.mrr` (primary) current=0.5886363636363636 baseline=None (ok)
- [PASS] `hybrid.precision_at_5` (informational) current=0.275 baseline=None (ok)
