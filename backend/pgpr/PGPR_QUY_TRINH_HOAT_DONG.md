# PGPR (Policy-Guided Path Reasoning) — Quy trình hoạt động & Cách tạo gợi ý

Tài liệu này giải thích **PGPR đang được triển khai trong repo của bạn** hoạt động như thế nào và luồng dữ liệu đi qua các module nào để tạo ra **recommendation + reasoning paths (giải thích được)**.

## 1. PGPR là gì (trong hệ thống này)

PGPR xem việc “tìm gợi ý” là bài toán **đi đường trên Knowledge Graph (Neo4j)**:
- **Source**: thực thể đầu vào (thường là `Project`, cũng có thể là `Expert`, `Enterprise`, `Funder`)
- **Target type**: loại thực thể cần gợi ý (ví dụ `Expert`, `Funder`, `Enterprise`, `Project`)
- Mỗi gợi ý đi kèm **một hoặc nhiều đường dẫn (reasoning paths)** từ source đến target, giúp giải thích “vì sao gợi ý này hợp lý”.

Repo của bạn có 2 chế độ suy luận:
- **Policy-guided (đúng “PGPR-RL”)**: dùng policy RL đã train (`pgpr_data/policy.pt`) để “đi” trên graph.
- **Heuristic fallback**: không cần policy; dùng Cypher tìm đường đi + chấm điểm đường đi để xếp hạng.

## 2. Tổng quan pipeline (Neo4j → PGPR → XAI)

Luồng chính đang chạy trong repo:

1) **Dữ liệu trong Neo4j**
- Neo4j có node/relationship (KG) cho các thực thể chính + taxonomy (kỹ năng, địa điểm, ngành, hướng/chủ đề nghiên cứu…).

2) **Build KG cho PGPR (vocab + triples + embedding)**
- Export toàn bộ cạnh từ Neo4j → tạo:
  - `pgpr_data/vocab.json` (entity2id, relation2id)
  - `pgpr_data/triples.txt`
  - (tuỳ chọn) `entity_emb.npy`, `relation_emb.npy` (TransE)

3) **Train policy (REINFORCE)**
- Lấy cặp positive/negative từ Neo4j (mặc định: `Project`–`Expert` theo `PARTICIPATES_IN`)
- Train `PolicyNetwork` để tối đa hoá reward (đến đúng target) → lưu `pgpr_data/policy.pt`

4) **Recommendation (gợi ý)**
- Lấy candidates (batch query) → với mỗi candidate:
  - tìm reasoning paths bằng Cypher (`find_reasoning_paths`)
  - chấm điểm path (`_score_path`)
  - tổng hợp điểm candidate (`_calculate_*_score`)
- Hoặc nếu có policy: rollout theo policy (`policy_guided_paths`) → gom kết quả → rank.

5) **XAI (giải thích)**
- XAI đọc chính `reasoning_paths` từ recommender để:
  - tạo giải thích template hoặc gọi LLM (Ollama)
  - xuất HTML/JSON cho người dùng xem.

## 3. Các file chính và vai trò

- `pgpr_kg.py`
  - Build KG từ Neo4j (export triples), train TransE, lưu `vocab.json` + embeddings.
- `pgpr_env.py`
  - Môi trường RL `KGEnv`: state=đỉnh hiện tại + path; action=(relation, next_entity) lấy từ Neo4j (cả chiều đi và chiều ngược).
- `pgpr_policy.py`
  - `PolicyNetwork`: encode path + score valid actions; `select_action()` (sample hoặc argmax).
- `pgpr_train.py`
  - Thu thập positive/negative pairs + vòng lặp REINFORCE, lưu `policy.pt`.
- `pgpr_recommendation.py`
  - `PGPRRecommender`: recommend đa thực thể, heuristic scoring + policy-guided inference.
- `pgpr_xai_explainer.py`
  - `PGPRExplainer`: chuyển reasoning paths → giải thích tiếng Việt/Anh + visualization + confidence.
- `pgpr_xai_integration.py`
  - Script chạy “multi-entity” (Project/Expert/Enterprise/Funder) và xuất HTML/JSON.

## 4. Chi tiết: heuristic mode (không cần policy)

### 4.1 Tìm reasoning paths bằng Cypher

Trong `PGPRRecommender.find_reasoning_paths()`:
- Query dạng (rút gọn):
  - `MATCH path = (source:SourceType {source_id_prop: $source_id})-[*1..L]-(target:TargetType {target_id_prop: $target_id})`
- Trả về:
  - `relation_types`: danh sách `type(r)` trên path
  - `node_types`: danh sách `labels(n)[0]`
  - `entity_names`: ưu tiên `name/title/label` hoặc các id (`project_id/expert_id/...`) để path đọc được
  - `path_length`
- Sau đó:
  - Chấm điểm path bằng `_score_path()`
  - Dedup path theo **pattern quan hệ** (tuple(relation_types))
  - Giữ top `top_k_paths`

### 4.2 Chấm điểm một path (`_score_path`)

Path score = tích các thành phần:
- **relation_score**: \(\prod_i weight(rel_i)\) với `relation_weights`
- **discount**: \(\gamma^{length}\) (mặc định \(\gamma = 0.99\))
- **length_penalty**: \(max(0.1, 1 - path\_penalty \times length)\)

Tạo `explanation` (string) theo dạng:
`"<rel_desc> <entity_name> -> <rel_desc> <entity_name> -> ..."`

### 4.3 Tổng hợp điểm candidate (ví dụ Expert)

Trong `_calculate_expert_score()`:
- `max_path_score`: điểm lớn nhất trong các path
- `avg_path_score`: trung bình điểm các path
- `min_path_length`: độ dài ngắn nhất
- `path_diversity`: số pattern quan hệ khác nhau
- `quality_score`: từ `h_index` + `citations` (chuẩn hoá)

Công thức (trọng số hiện tại trong code):
- `0.4 * max_path_score`
- `+ 0.2 * avg_path_score`
- `+ 0.1 * (1/min_path_length)`
- `+ 0.1 * diversity_score`
- `+ 0.2 * quality_score`

Các target type khác (Project/Funder/Enterprise) dùng hàm `_calculate_project_score`/`_calculate_funder_score` (logic tương tự: path score + diversity là chính).

## 5. Chi tiết: policy-guided mode (PGPR-RL)

### 5.1 MDP (mô hình hoá bài toán đi đường)

Trong `pgpr_env.py`:
- **State**: `(current_entity_id, path)` với `path=[(h,r,t), ...]`
- **Valid actions**: các hàng xóm lấy từ Neo4j:
  - outgoing: `(a)-[r]->(b)`
  - incoming: `(a)<-[r]-(b)` (để policy đi “ngược” khi cần)
- **Reward**
  - +1.0 nếu đến node có type = `target_type` (trong inference)
  - trong training: reward phụ thuộc “đúng target_key hay không” + positive/negative pair

### 5.2 Policy network (cách chọn action)

Trong `pgpr_policy.py`:
- Encode state:
  - `path_emb = entity_emb[current] + Σ(relation_emb[r] + entity_emb[t])`
- Encode action:
  - `action_emb = relation_emb[r] + entity_emb[t]`
- Score:
  - `MLP([path_emb; action_emb]) -> logit`
- Chọn action:
  - deterministic: `argmax(logits)`
  - stochastic: sample theo `softmax(logits)`

### 5.3 Inference theo policy (`policy_guided_paths`)

Trong `pgpr_recommendation.py`:
- Rollout `n_rollouts` lần từ source:
  - cộng `path_log_prob = Σ log π(a_t|s_t)`
  - nếu đến đúng `target_type`:
    - score_rollout = `exp(path_log_prob) * reward`
- Gom theo target entity, lấy:
  - `score = mean(score_rollout)`
  - `path_relations`/`path_entities` của best rollout để làm explanation

Nếu policy không ra kết quả, code tự động fallback sang heuristic.

## 6. XAI giải thích “vì sao gợi ý”

Trong `pgpr_xai_explainer.py`:
- Input: recommendation dict gồm `score`, `reasoning_paths`, `path_diversity`, (tuỳ loại có `metrics`)
- Output:
  - `natural_language`: giải thích tiếng Việt/Anh (template hoặc LLM)
  - `visualization`: ASCII path
  - `confidence`: phân tích độ tin cậy

Trong `pgpr_xai_integration.py`:
- Có các chế độ multi-entity:
  - Project → Experts/Funders/Enterprises/Similar Projects
  - Expert → Enterprises/Funders/Projects
  - Enterprise → Experts/Projects
  - Funder → Experts/Projects
- Xuất `*.html` + `*.json` để xem.

## 7. Cách chạy (gợi ý theo đúng pipeline)

### 7.1 Chuẩn bị Neo4j có dữ liệu
- Nếu đồng bộ từ MongoDB: chạy `add_data/mongo_to_neo4j.py --clear`

### 7.2 Build KG + embedding (tuỳ chọn nhưng khuyến nghị)

```bash
python run_pgpr.py --step 1
```

Kết quả: `pgpr_data/vocab.json`, `pgpr_data/triples.txt`, `pgpr_data/entity_emb.npy`, `pgpr_data/relation_emb.npy`

### 7.3 Train policy (tuỳ chọn)

```bash
python pgpr_train.py --data_dir pgpr_data --n_epoch 50 --save_path pgpr_data/policy.pt
```

### 7.4 Demo gợi ý multi-entity + XAI (khuyến nghị để xem “gợi ý + giải thích” ngay)

```bash
python pgpr_xai_integration.py PRJ_0001
```

Tuỳ chọn LLM:

```bash
python pgpr_xai_integration.py PRJ_0001 --llm --model llama3
```

## 8. Những thứ cần bổ sung nếu bạn muốn gợi ý “mạnh” hơn

PGPR mạnh lên khi KG có nhiều “cầu nối” và dữ liệu đủ dày. Nếu bạn muốn tăng chất lượng gợi ý (và đường dẫn giải thích đa dạng), nên bổ sung:
- **`required_skill_ids`** cho `Project.requirements_and_timeline` và `Enterprise.rd_profile.technology_needs` để edge `REQUIRES_SKILL` rõ ràng.
- **dataset** (`datasets` collection) + liên kết `REQUIRES_DATA`, `OWNS_DATA`, `HAS_ACCESS_TO` nếu bạn muốn gợi ý dựa trên dữ liệu.
- **focus_sector_ids / focus_region_ids** cho funder strategy để tạo edge `FOCUSES_ON_SECTORS/FOCUSES_ON_REGION`.
- Mở rộng positive pairs cho training (không chỉ Project–Expert) nếu bạn muốn policy RL học nhiều loại đề xuất hơn.

