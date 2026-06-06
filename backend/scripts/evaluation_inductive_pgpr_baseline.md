# Evaluation Report

- Generated: 2026-06-05T15:07:00.578110+00:00
- Cases: 22 queries, 88 rows
- Regression gate: **PASS** (promote_allowed)

## Summary by method

| Method | NDCG@5 | MRR | P@5 | R@5 | Latency p50 (ms) | Explanation cov. |
|---|---:|---:|---:|---:|---:|---:|
| embedding_only | 0.5402 | 0.6152 | 0.2364 | 0.6136 | 33.615 | 0.0000 |
| hybrid | 0.5355 | 0.5871 | 0.2636 | 0.6515 | 2005.545 | 0.8000 |
| random | 0.3840 | 0.4788 | 0.2182 | 0.5076 | 1887.3600000000001 | 0.6182 |
| topic_overlap | 0.4085 | 0.5455 | 0.3864 | 0.3409 | 8.805 | 0.0000 |

## Regression checks

Primary metrics (gate): `ndcg_at_5, mrr`

- [PASS] `hybrid.ndcg_at_5` (primary) current=0.5355031656326352 baseline=None (ok)
- [PASS] `hybrid.mrr` (primary) current=0.587121212121212 baseline=None (ok)
- [PASS] `hybrid.precision_at_5` (informational) current=0.26363636363636367 baseline=None (ok)
