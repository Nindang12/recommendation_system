# Candidate Source Audit

- Generated: 2026-06-20T14:26:36.486238+00:00
- Queries: 240
- Top-K: 5
- Returned candidates: 587

## Scoring Method Counts

| Method | Count |
| --- | ---: |
| cypher_fallback | 45 |
| pgpr_policy | 542 |

## Path Layer Breakdown

| Path/source layer | Count |
| --- | ---: |
| pgpr_policy | 542 |
| path_reranked_by_embedding_topic | 0 |
| cypher_fallback | 45 |
| embedding_only | 0 |

## Evidence Level Counts

| Evidence level | Count |
| --- | ---: |
| fallback_only | 45 |
| path_supported | 542 |

## Candidate Source Counts

| Source | Count |
| --- | ---: |
| pgpr | 587 |

## Query Method Presence

| Method | Queries with at least one candidate |
| --- | ---: |
| cypher_fallback | 21 |
| pgpr_policy | 209 |

## Interpretation

- `pgpr_policy`: path-supported result primarily scored by classic PGPR policy/path evidence.
- `hybrid_embedding_path`: PGPR/path-supported result reranked with embedding/topic signals.
- `hybrid_embedding`: embedding-only result without a strong PGPR reasoning path.
- `cypher_fallback`: fallback graph/path heuristic when policy is missing or insufficient; it is counted separately when present.
- `candidate_sources=pgpr`: broad path-layer marker, not always a pure policy-rollout marker.
