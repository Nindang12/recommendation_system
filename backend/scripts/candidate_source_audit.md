# Candidate Source Audit

- Generated: 2026-06-06T08:29:53.711119+00:00
- Queries: 22
- Top-K: 5
- Returned candidates: 109

## Scoring Method Counts

| Method | Count |
| --- | ---: |
| hybrid_embedding | 18 |
| hybrid_embedding_path | 55 |
| pgpr_policy | 36 |

## Path Layer Breakdown

| Path/source layer | Count |
| --- | ---: |
| pgpr_policy | 36 |
| path_reranked_by_embedding_topic | 55 |
| cypher_fallback | 0 |
| embedding_only | 18 |

## Evidence Level Counts

| Evidence level | Count |
| --- | ---: |
| embedding_only | 18 |
| path_supported | 91 |

## Candidate Source Counts

| Source | Count |
| --- | ---: |
| embedding | 109 |
| pgpr | 91 |

## Query Method Presence

| Method | Queries with at least one candidate |
| --- | ---: |
| hybrid_embedding | 15 |
| hybrid_embedding_path | 21 |
| pgpr_policy | 18 |

## Interpretation

- `pgpr_policy`: path-supported result primarily scored by classic PGPR policy/path evidence.
- `hybrid_embedding_path`: PGPR/path-supported result reranked with embedding/topic signals.
- `hybrid_embedding`: embedding-only result without a strong PGPR reasoning path.
- `cypher_fallback`: fallback graph/path heuristic when policy is missing or insufficient; it is counted separately when present.
- `candidate_sources=pgpr`: broad path-layer marker, not always a pure policy-rollout marker.
