# Demo cases — R&D Recommendation API

ID mẫu (Mongo/Neo4j seed hiện tại):

| Entity | ID | Ghi chú |
|--------|-----|---------|
| Project | `prj_001` | Case chính dashboard |
| Expert | `exp_001`, `exp_002` | Gợi ý Project → Expert |
| Funder | `fnd_001` | Project → Funder |
| Enterprise | `ent_001` | Project → Enterprise |

## Case 1: Project → Expert

- **Endpoint:** `POST /api/v1/recommendations/policy`
- **Body:**

```json
{
  "source_id": "prj_001",
  "source_type": "project",
  "target_type": "expert",
  "limit": 5,
  "language": "vi"
}
```

- **Kỳ vọng:** HTTP 200, `count` ≥ 1; mỗi item có `id`, `name`, `score`, `explanation`; nhiều item có `reasoning_paths`.
- **Paths (Cypher):** `GET /api/v1/graph/paths?source_type=project&source_id=prj_001&target_type=expert&target_id=exp_002`

## Case 2: Project → Funder

```json
{
  "source_id": "prj_001",
  "source_type": "project",
  "target_type": "funder",
  "limit": 3,
  "language": "vi"
}
```

## Case 3: Project overview

- **Endpoint:** `POST /api/v1/recommendations/projects/prj_001/overview?limit=3`
- **Kỳ vọng:** `data.experts`, `data.funders`, `data.enterprises`, `data.similar_projects` mỗi nhóm có phần tử.

## Case 4: Explanation (rule)

- **Endpoint:** `POST /api/v1/explanations`
- **Body:** lấy một item từ Case 1, thêm `mode: "rule"`.

## Ghi chú demo

- Policy PGPR là luồng chính; `reasoning_paths` có thể rỗng với một số cặp entity (vẫn HTTP 200).
- Graph paths API dùng Cypher (`find_reasoning_paths_cypher`), không phụ thuộc `POLICY_ONLY_MODE` của heuristic path finder.
