# Evaluation Report

- Generated: 2026-06-21T17:24:10.533800+00:00
- Cases: 240 queries, 1440 rows
- Regression gate: **PASS** (promote_allowed)

## Summary by method

| Method | NDCG@5 | MRR | P@5 | R@5 | Latency p50 (ms) | Explanation cov. |
|---|---:|---:|---:|---:|---:|---:|
| embedding_only | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 1.66 | 0.0000 |
| graph_heuristic | 0.7438 | 0.7645 | 0.6626 | 0.7465 | 1505.6599999999999 | 0.8583 |
| hybrid | 0.7438 | 0.7657 | 0.6656 | 0.7458 | 1504.4850000000001 | 0.8667 |
| pgpr_only | 0.7441 | 0.7641 | 0.6608 | 0.7472 | 1450.425 | 0.8542 |
| random | 0.7025 | 0.7249 | 0.6677 | 0.7354 | 1495.675 | 0.8708 |
| topic_overlap | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 5.984999999999999 | 0.0000 |

## Regression checks

Primary metrics (gate): `ndcg_at_5, mrr`

- [PASS] `hybrid.ndcg_at_5` (primary) current=0.7438362185521533 baseline=None (ok)
- [PASS] `hybrid.mrr` (primary) current=0.7657341269841269 baseline=None (ok)
- [PASS] `hybrid.precision_at_5` (informational) current=0.665625 baseline=None (ok)
