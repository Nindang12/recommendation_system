# Báo cáo triển khai PGPR – Policy-Guided Path Reasoning

**Tài liệu tham chiếu:** *Reinforcement Knowledge Graph Reasoning for Explainable Recommendation* (Xian et al., SIGIR 2019).

---

## 1. Tổng quan những gì đã làm

Hệ thống triển khai **PGPR (Policy-Guided Path Reasoning)** trên **Knowledge Graph (KG)** R&D, dùng **Reinforcement Learning (RL)** để học policy đi từng bước trên đồ thị, tìm đường đi có thể giải thích được từ nguồn (ví dụ Project) tới đích (ví dụ Expert). Các thành phần chính:

| Thành phần | Mô tả |
|------------|--------|
| **KG & Embedding** | Export triples từ Neo4j, xây vocab entity/relation, train TransE (embedding). |
| **Môi trường RL** | State = path hiện tại, action = (relation, next_entity) lấy từ Neo4j. |
| **Policy Network** | Mạng neural (PyTorch) mã hóa path, chấm điểm action, sample/argmax. |
| **Training** | Thu thập cặp (project, expert) positive/negative, train REINFORCE. |
| **Recommendation** | Inference: policy-guided path nếu có `policy.pt`, không thì heuristic. |
| **XAI** | Giải thích bằng ngôn ngữ tự nhiên, visualization đường đi, confidence, có thể dùng LLM (Ollama). |

Hệ thống hỗ trợ **đa thực thể**: Project, Expert, Funder, Enterprise với các cặp gợi ý (Project→Expert, Project→Funder, Expert→Project, …) theo framework trong `MULTI_ENTITY_PGPR_FRAMEWORK.md`.

---

## 2. Các bước thực hiện chi tiết

### Bước 0: Chuẩn bị dữ liệu

- **Neo4j** đã chạy và đã đồng bộ dữ liệu (nếu cần: `python mongo_to_neo4j.py --clear`).
- Cài đặt: `pip install -r requirements.txt`.

### Bước 1: Chuẩn bị KG và embedding

**Mục đích:** Export đồ thị từ Neo4j → vocab + triples → train TransE → lưu embedding.

**Chi tiết:**

1. **Export từ Neo4j** (`pgpr_kg.py` – `KG.export_from_neo4j`):
   - Cypher: `MATCH (a)-[r]->(b)` lấy tất cả cạnh, với `labels(a)[0]`, `type(r)`, `labels(b)[0]`.
   - Entity key: `Label::id_value` (ví dụ `Project::PRJ_0001`, `Expert::EXP_0001`).
   - Xây `entity2id`, `relation2id`, danh sách triples `(h, r, t)` dạng id.
   - Lưu `vocab.json` (entity2id, relation2id) và `triples.txt`.

2. **TransE** (`pgpr_kg.py` – `KG.train_transe`):
   - Khởi tạo `entity_emb`, `relation_emb` ngẫu nhiên (dim=64).
   - Với mỗi triple (h, r, t): score dương = `||h + r - t||`, negative sample t ngẫu nhiên → margin loss.
   - Cập nhật embedding bằng gradient (numpy). Sau 100 epoch lưu `entity_emb.npy`, `relation_emb.npy`.

**Lệnh:**

```bash
python run_pgpr.py --step 1
# hoặc
python -c "from pgpr_kg import build_kg_from_neo4j; build_kg_from_neo4j(data_dir='pgpr_data', train_emb=True, emb_dim=64)"
```

**Kết quả:** Thư mục `pgpr_data/` có `vocab.json`, `triples.txt`, `entity_emb.npy`, `relation_emb.npy`.

---

### Bước 2: Train policy (REINFORCE)

**Mục đích:** Học policy π(a|s) để từ source (Project) bước đi trên KG tới target (Expert), tối đa hóa reward.

**Chi tiết:**

1. **Thu thập dữ liệu** (`pgpr_train.py`):
   - **Positive:** `(Project, Expert)` mà Expert `PARTICIPATES_IN` Project (Cypher).
   - **Negative:** (Project, Expert) ngẫu nhiên sao cho Expert không tham gia Project đó.
   - Số lượng: `n_positive`, `n_negative` (mặc định 200/200).

2. **Môi trường RL** (`pgpr_env.py` – `KGEnv`):
   - **State:** (current_entity_id, path) với path = [(h, r, t), ...].
   - **Action:** (relation_id, next_entity_id) – chỉ các hàng xóm hợp lệ từ Neo4j (outgoing + incoming edges).
   - **Reward:** +1.0 nếu đến đúng entity đích (target_type, ví dụ Expert); -0.1 nếu hết bước mà chưa tới đích; với negative pair: -0.5 nếu tới đích, +0.1 nếu không tới.

3. **Policy network** (`pgpr_policy.py` – `PolicyNetwork`):
   - Embedding entity/relation (khởi tạo từ TransE).
   - **Encode path:** path_emb = entity_emb[current] + Σ(relation_emb[r] + entity_emb[t]) theo từng bước path.
   - **Action encoding:** action_emb = relation_emb[r] + entity_emb[t].
   - **Score:** MLP([path_emb; action_emb]) → logits; softmax → xác suất, log_softmax → log_prob.

4. **REINFORCE** (`pgpr_train.py` – `train_pgpr`):
   - Với mỗi (source, target): chạy 1 episode (policy đi từ source tới khi done).
   - Loss = -Σ log_prob(a_t) × (reward - baseline). Baseline cập nhật exponential moving average (decay 0.99).
   - Optimizer Adam, clip gradient 1.0. Mỗi 10 epoch lưu checkpoint `policy.pt`.

**Lệnh:**

```bash
python pgpr_train.py --data_dir pgpr_data --n_epoch 50 --save_path pgpr_data/policy.pt
# hoặc
python run_pgpr.py --step 2
```

**Kết quả:** File `pgpr_data/policy.pt`.

---

### Bước 3: Gợi ý (Recommendation)

**Mục đích:** Với project_id, trả về danh sách expert (hoặc funder, enterprise, project tương tự) kèm score và đường đi giải thích.

**Chi tiết:**

1. **Nếu có policy** (`pgpr_recommendation.py` – `_recommend_with_policy`):
   - Gọi `policy_guided_paths(project_id, Project, Expert, n_rollouts, deterministic=False)`.
   - Mỗi rollout: reset env tại Project, policy chọn action từng bước đến khi gặp Expert hoặc hết max_path_length.
   - Với mỗi expert đến được: score = mean(exp(sum log_prob)) × reward; lưu path (relation types).
   - Lấy top theo score, bổ sung thông tin expert từ Neo4j, trả về recommendations.

2. **Nếu không có policy (heuristic):**
   - Batch query tất cả expert có thể đến được từ project (qua BELONGS_TO → ResearchField, SUB_FIELD_OF, HAS_EXPERTISE_IN).
   - Với mỗi candidate: `find_reasoning_paths(project, Project, expert, Expert)` – Cypher tìm đường đi; `_score_path` cho từng path; `_calculate_expert_score` tổng hợp.
   - Sắp xếp theo score, trả về top-k.

**Lệnh:**

```bash
python run_pgpr.py --step 3 --project_id PRJ_0001
```

**Chạy nhanh toàn bộ (Bước 1 + 2):**

```bash
python run_pgpr.py --all
```

---

## 3. Thuật toán PGPR hoạt động như thế nào

### 3.1 Ý tưởng tổng quát

- **Bài toán:** Cho source entity (ví dụ Project) và target type (ví dụ Expert), tìm các entity đích “phù hợp” và **giải thích được** bằng đường đi trên KG.
- **Cách làm:** Coi việc đi từ source tới target là **MDP**: mỗi bước agent chọn (relation, next_entity) trong số hàng xóm hợp lệ. Policy π(a|s) được học bằng **REINFORCE** để tối đa hóa reward (đến đúng đích với cặp positive, tránh đích với cặp negative).

### 3.2 MDP (Markov Decision Process)

- **State s:** (current_entity_id, path).
  - path = [(h_1, r_1, t_1), (h_2, r_2, t_2), ...] là chuỗi (head, relation, tail) đã đi.
- **Action a:** (relation_id, next_entity_id) – chỉ những cạnh thực sự tồn tại trên Neo4j (ra vào node hiện tại).
- **Transition:** Xác định: next_entity trở thành current, path thêm (current, r, next_entity).
- **Reward:**
  - Đến entity có type = target_type (và đúng entity đích trong train): +1.0 (positive) hoặc -0.5 (negative).
  - Hết số bước mà chưa tới đích: -0.1 (positive) hoặc +0.1 (negative).

### 3.3 Policy network

- **Đầu vào:** state (current_entity_id, path), danh sách valid_actions [(r, t), ...].
- **Mã hóa state (path):**
  - path_emb = entity_emb[current] + Σ (relation_emb[r_i] + entity_emb[t_i]) với mọi (h_i, r_i, t_i) trong path.
- **Mã hóa action:** action_emb = relation_emb[r] + entity_emb[t].
- **Scoring:** Với mỗi action: input = [path_emb; action_emb] → MLP(2×dim → hidden → 1) → logit. Softmax trên các action hợp lệ → xác suất π(a|s).
- **Hành vi:** Training: sample theo π; inference: có thể deterministic (argmax) hoặc sample nhiều rollout.

### 3.4 Training (REINFORCE)

- Với mỗi (source_key, target_key, is_positive):
  - Chạy 1 episode: s_0, a_0, ..., s_T, reward R.
  - Loss = -Σ_t log π(a_t|s_t) × (R - baseline).
  - Baseline = EMA của reward (giảm phương sai). Cập nhật policy bằng gradient descent.

### 3.5 Inference

- **Policy-guided:** N lần rollout từ source, mỗi lần đi theo π đến khi gặp target_type hoặc max_step. Gom theo entity đích, score = trung bình exp(sum log_prob) × reward, path = chuỗi relation types.
- **Heuristic (fallback):** Tìm candidate bằng Cypher (meta-path), với mỗi candidate tìm đường đi bằng Cypher `MATCH path = (source)-[*1..L]-(target)`, chấm điểm từng path rồi tổng hợp (xem mục 4).

---

## 4. Cách tính score để đánh giá độ phù hợp

Có hai lớp: **điểm cho từng đường đi** và **điểm tổng hợp cho một đề xuất (một candidate)**.

### 4.1 Điểm cho một đường đi (path score) – `_score_path`

Dùng trong chế độ heuristic (tìm path bằng Cypher), trong `find_reasoning_paths`:

- **Relation score:** Tích trọng số theo từng relation trên path:
  - relation_score = ∏ weight(rel_i), với `relation_weights` (ví dụ HAS_EXPERTISE_IN=1.0, PARTICIPATES_IN=0.85, BELONGS_TO=0.8, SUB_FIELD_OF=0.7, …).
- **Discount theo độ dài:** discount = γ^path_length (γ = 0.99).
- **Length penalty:** length_penalty = max(0.1, 1.0 - path_penalty × path_length).
- **Điểm path:**
  - **path_score = relation_score × discount × length_penalty.**

Đường ngắn, quan hệ “mạnh” được ưu tiên.

### 4.2 Điểm đề xuất Expert – `_calculate_expert_score`

Gộp nhiều path từ source tới cùng expert:

- **max_path_score:** max điểm trong các path.
- **avg_path_score:** trung bình điểm các path.
- **min_path_length:** độ dài path ngắn nhất.
- **path_diversity:** số pattern relation khác nhau (số tập tuple(relations) khác nhau).
- **diversity_score:** min(path_diversity / top_k_paths, 1.0).
- **length_score:** 1.0 / min_path_length (ưu tiên đường ngắn).
- **Chất lượng expert (nếu có):** h_index, citations → chuẩn hóa → quality_score (ví dụ (h_norm + log_citation_norm)/2).
- **Tổng hợp (trọng số mặc định trong code):**
  - **final_score =**
    - **0.4 × max_path_score**
    - **+ 0.2 × avg_path_score**
    - **+ 0.1 × length_score**
    - **+ 0.1 × diversity_score**
    - **+ 0.2 × quality_score**

### 4.3 Điểm đề xuất Project / Funder (và tương tự)

- **max_path_score**, **avg_path_score**, **path_diversity** giống trên.
- **Score = 0.5 × max_path_score + 0.3 × avg_path_score + 0.2 × (path_diversity / top_k_paths).**

(Không dùng length_score hay quality_score riêng cho project/funder trong công thức hiện tại.)

### 4.4 Điểm khi dùng policy (policy-guided paths)

- Mỗi rollout đến đích: score_rollout = exp(Σ log π(a_t|s_t)) × reward (reward=1 khi đến đúng Expert).
- Với mỗi target entity: lấy danh sách scores từ các rollout tới entity đó; điểm gán cho entity = **mean(scores)** (và có thể dùng best path cho explanation).

---

## 5. Khả năng giải thích XAI – mô tả chi tiết thuật toán

Module XAI nằm ở `pgpr_xai_explainer.py` và tích hợp trong `pgpr_xai_integration.py`. Mỗi đề xuất có **reasoning_paths** (danh sách path + score + length); XAI dùng trực tiếp các path này để tạo giải thích.

### 5.1 Đầu vào cho XAI

- **recommendation:** dict gồm name/title, score, path_diversity, reasoning_paths (mỗi path: path/explanation, score, length), có thể thêm metrics (h_index, citations, …).
- **rec_type:** "expert" | "funder" | "project" | "enterprise".
- **source_context:** {source_id, source_type} (và có thể source_name) để nêu “cho dự án X” / “cho chuyên gia Y”.

### 5.2 Luồng tổng thể – `explain_recommendation`

1. **Natural language explanation**
   - Nếu `use_llm=True`: build prompt từ paths + metrics + source_context → gọi Ollama (`llm_explain_paths_ollama`) → wrap kết quả với intro/score/diversity.
   - Nếu không LLM: `_generate_natural_language` dùng template (intro, score level, diversity, path_intro + `_explain_paths`).

2. **Path analysis** – `_analyze_paths`
   - Thống kê: path_categories (field_alignment, funder_support, expertise_match, collaboration_network, funding_history) dựa trên từ khóa trong path text; avg_path_length, shortest_path, longest_path.

3. **Path visualization** – `_generate_path_visualization`
   - ASCII: với mỗi path (path text, score), in từng bước dạng cây (┌─, ├─>, └─>).

4. **Confidence** – `_calculate_confidence`
   - base_confidence = score đề xuất.
   - quality_boost = min(số path có score > 0.5 / 5, 0.2).
   - total_confidence = min(base + quality_boost, 1.0).
   - Path diversity chỉ được giữ làm thông tin giải thích, không cộng trực tiếp vào confidence.
   - Gán level (Rất cao/Cao/Trung bình/Thấp) và interpretation (câu mô tả bằng tiếng Việt hoặc tiếng Anh).

Kết quả trả về: natural_language, path_analysis, visualization, confidence, metadata.

### 5.3 Natural language không dùng LLM

- **Template:** intro (“Chúng tôi gợi ý **{name}** cho dự án của bạn vì:”), score với level (Xuất sắc/Rất tốt/Tốt/…), diversity (“Tìm thấy **{count}** cách kết nối”), path_intro (“**Lý do chính:**”).
- **Giải thích từng path** – `_explain_paths`:
  - Mỗi path → `_narrate_path(path_text, rec_type, target_name)`.
  - **Parse path** – `_parse_path_steps`: tách chuỗi "rel1 -> rel2 -> ..." thành các bước (relation_key, entity_name) bằng regex (belongs to field, is sub-field of, has expertise in, participates in, funds, supports, …).
  - **Narrative theo loại:**
    - **Expert:** `_narrate_path_expert`: dự án thuộc lĩnh vực X, nhánh của Y, … → “{expert_name} có chuyên môn đúng trong lĩnh vực này…”
    - **Funder:** “Dự án thuộc lĩnh vực X. Quỹ hỗ trợ lĩnh vực X. Vì vậy quỹ này phù hợp…”
    - **Enterprise:** “Dự án thuộc lĩnh vực X. Doanh nghiệp hoạt động/đối tác … Hệ thống đánh giá doanh nghiệp này phù hợp…”
    - **Project:** “Cả hai dự án thuộc lĩnh vực X. Cùng chuyên gia/quỹ… Dự án tương tự để tham khảo.”
  - Nếu không parse được: `_simplify_path` (pattern match) hoặc `_generic_simplification` (từ khóa: cùng lĩnh vực, được hỗ trợ, có chuyên môn, tham gia, cộng tác, tài trợ).

### 5.4 Natural language dùng LLM (Ollama)

- **Build prompt** – `build_prompt_from_paths`:
  - Đưa vào: tên đề xuất, score, (nếu expert) metrics, source_context, danh sách path (text + score + length).
  - Yêu cầu LLM: (1) Với mỗi đường dẫn, viết 1–2 câu giải thích ý nghĩa; (2) Tổng kết tại sao đề xuất phù hợp; (3) Không dùng thuật ngữ node/edge/KG; diễn giải tự nhiên.
- **Gọi API:** POST `/api/generate`, model (llama3/mistral/…), stream=false, timeout 30s.
- **Wrap:** Thêm intro, score, diversity và “**Giải thích chi tiết:**” + nội dung LLM.

### 5.5 So sánh top 2 – `explain_comparison`

- So sánh recommendation[0] và recommendation[1]: name, score, path_diversity.
- Giải thích “Tại sao (name1) xếp cao hơn?”: chênh lệch điểm, đa dạng đường đi (số cách kết nối), đường đi tốt nhất mạnh hơn, đường đi ngắn hơn.
- Trả về đoạn văn (vi/en) tổng kết.

### 5.6 Báo cáo tổng quan – `generate_summary_report`

- Thống kê: tổng số gợi ý, điểm trung bình, đa dạng trung bình.
- Top 3: tên, điểm, số đường dẫn, lý do chính (simplify path đầu tiên).
- Phân bố: Xuất sắc (≥0.6), Tốt (0.4–0.6), Trung bình (<0.4).

### 5.7 Tích hợp multi-entity

- `pgpr_xai_integration.py`: `generate_project_multi_recommendations(project_id)` gọi PGPR cho experts, funders, enterprises, similar_projects; với mỗi đề xuất gọi `explainer.explain_recommendation(rec, rec_type, source_context)`.
- Có thể xuất HTML (`save_project_multi_html`) và JSON. Tùy chọn `--llm` và `--model` để bật giải thích bằng Ollama.

---

## 6. Tóm tắt luồng dữ liệu

```
Neo4j (graph)
    → Bước 1: Export KG + TransE → pgpr_data (vocab, triples, entity_emb, relation_emb)
    → Bước 2: (Project, Expert) positive/negative → REINFORCE → policy.pt
    → Bước 3: project_id → Policy/Heuristic → paths → scoring → recommendations (score, reasoning_paths)
    → XAI: reasoning_paths + metadata → natural language, visualization, confidence, (optional) LLM
```

---

## 7. Tài liệu tham khảo trong project

- `PGPR_README.md` – Hướng dẫn chạy từng bước.
- `MULTI_ENTITY_PGPR_FRAMEWORK.md` – Meta-path và cặp (source, target) cho từng loại gợi ý.
- `HUONG_DAN_CHAY_HE_THONG.md` – Hướng dẫn chạy hệ thống tổng thể.

---

*Báo cáo được tạo từ phân tích toàn bộ code trong thư mục pgpr_method.*

---

## 8. Giải thích dễ hiểu & ví dụ minh họa

Phần này viết lại ngắn gọn, dễ hiểu hơn và có ví dụ cho từng bước, đồng thời nêu rõ **nếu thiếu phần đó thì hệ thống sẽ như thế nào**.

### 8.1 Bước 1 – KG & embedding (pgpr_kg.py)

- **Dễ hiểu:** Bạn có một bản đồ kiến thức (Neo4j). Bước 1 là **chụp lại bản đồ** này thành các số (ID + vector) để máy học có thể hiểu và tính toán.\n
- **Ví dụ cụ thể:**
  - Trong Neo4j có `Project(PRJ_0001)` thuộc `ResearchField(AI_001)` và `Expert(EXP_0001)` có `HAS_EXPERTISE_IN(AI_001)`.
  - Sau Bước 1, hệ thống biết:
    - `Project::PRJ_0001` là entity số 42, vector `[0.1, -0.05, ...]`.
    - `Expert::EXP_0001` là entity số 123, vector `[0.08, -0.02, ...]`.
    - Quan hệ `HAS_EXPERTISE_IN` có ID riêng và vector riêng.
- **Nếu thiếu Bước 1 hoặc làm không đúng:**
  - Không có `vocab.json`, `triples.txt` → **policy RL không train được** vì không biết ID của entity/relation.
  - Không có `entity_emb.npy`, `relation_emb.npy` → vẫn có thể train, nhưng policy phải khởi tạo embedding ngẫu nhiên, chất lượng thường **kém hơn**, hệ thống vẫn chạy nhưng kém “thông minh” hơn.

### 8.2 Bước 2 – Policy RL (pgpr_env.py, pgpr_policy.py, pgpr_train.py)

- **Dễ hiểu:** Hãy tưởng tượng một “con bot” đi trên bản đồ tri thức. Bước 2 là **dạy bot thói quen đi đường** sao cho:
  - Với cặp (Project, Expert đúng), bot **cố gắng tìm đường đi tới Expert đó**.
  - Với cặp (Project, Expert không liên quan), bot **tránh đi tới Expert đó**.
- **Ví dụ cụ thể:**
  - Positive pair: (PRJ_0001, EXP_0001).
    - Bot học được thói quen: từ `PRJ_0001` đi `BELONGS_TO` tới `AI_001`, sau đó đi `HAS_EXPERTISE_IN` tới `EXP_0001`.
  - Negative pair: (PRJ_0001, EXP_9999) – chuyên gia không liên quan.
    - Nếu bot “lỡ” đi tới `EXP_9999`, nó bị phạt (reward âm) → lần sau ít chọn kiểu đường đó hơn.
- **Nếu không train policy (không có Bước 2 / không có policy.pt):**
  - Hệ thống **vẫn chạy được** bằng chế độ heuristic trong `pgpr_recommendation.py`.
  - Lúc này, hệ thống **không dùng bot RL** nữa mà:
    - Dùng Cypher để tìm tất cả đường đi phù hợp (meta-path cố định).
    - Tự chấm điểm đường đi theo rule (trọng số quan hệ, độ dài, v.v.).
  - Nhược điểm: ít “học từ dữ liệu” hơn, chỉ dựa trên luật được code sẵn. Ưu điểm: dễ kiểm soát, dễ debug.

### 8.3 Bước 3 – Recommendation (pgpr_recommendation.py)

- **Dễ hiểu:** Đây là **đầu ra mà người dùng nhìn thấy** – danh sách gợi ý (chuyên gia, quỹ, doanh nghiệp, dự án tương tự) kèm lý do.\n
- **Ví dụ cụ thể (Project → Expert):**
  - Input: `project_id = "PRJ_0001"`.
  - Output: danh sách như:
    - Expert A – score 0.82 – đường đi: “thuộc lĩnh vực Thị giác máy tính → là nhánh của Trí tuệ nhân tạo → có chuyên môn của PGS.TS. A”.
    - Expert B – score 0.65 – đường đi: “có kỹ năng Deep Learning → áp dụng trong cùng lĩnh vực dự án”.
- **Nếu không có Bước 3:**
  - Các bước trước chỉ chuẩn bị dữ liệu và policy, nhưng **không có API nào** để trả về danh sách gợi ý cho UI / file HTML / JSON.
  - Thực tế: `PGPR_README.md`, `pgpr_xai_integration.py`, `run_pgpr.py` đều dựa vào các hàm trong `pgpr_recommendation.py`. Nếu thiếu file này, hệ thống **không tạo được gợi ý hoàn chỉnh** cho người dùng cuối.

### 8.4 Cách tính điểm (scoring)

- **Dễ hiểu:** Mỗi đường đi giống như **một lý do**. Hệ thống chấm điểm:\n
  - Lý do càng “thẳng, rõ ràng” (ít bước, quan hệ quan trọng) → điểm cao.\n
  - Một candidate có nhiều lý do khác nhau, chất lượng tốt → tổng điểm càng cao.\n
- **Ví dụ cụ thể (Expert):**
  - Expert A có 2 đường đi từ project:
    - Path 1: cùng lĩnh vực chính → score 0.9.\n
    - Path 2: cùng kỹ thuật Deep Learning → score 0.7.\n
  - Path diversity = 2 (2 kiểu lý do khác nhau).\n
  - Nếu A có h-index cao, nhiều trích dẫn → quality_score cao.\n
  - Công thức kết hợp cho A cho ra final_score ≈ 0.8.\n
  - Expert B chỉ có 1 path mờ nhạt, không có chỉ số học thuật → final_score ≈ 0.3.\n
- **Nếu không có phần scoring này (hoặc scoring quá đơn giản):**
  - Hệ thống **vẫn có thể liệt kê các candidate**, nhưng:\n
    - Không biết ai quan trọng hơn ai.\n
    - Khó giải thích tại sao Expert A đứng trên Expert B.\n
  - Thực tế: việc tách rõ `_score_path`, `_calculate_expert_score`, `_calculate_funder_score`, … giúp sau này **dễ chỉnh policy “mềm”** (tăng/giảm trọng số) mà không sửa phần RL.\n

### 8.5 XAI (giải thích – pgpr_xai_explainer.py, pgpr_xai_integration.py)

- **Dễ hiểu:** PGPR đã tìm đường đi (lý do) rồi. XAI là lớp **“phiên dịch”**:\n
  - Biến path dạng kỹ thuật (`belongs to field AI_001 -> has expertise in EXP_0001`) thành câu tiếng Việt dễ hiểu.\n
  - Vẽ sơ đồ chữ (ASCII) để nhìn nhanh đường đi.\n
  - Tính “độ tin cậy” dựa trên điểm, số lượng và chất lượng đường đi.\n
  - (Tuỳ chọn) Gọi LLM (Ollama) để viết đoạn giải thích dài, tự nhiên hơn.\n
- **Ví dụ cụ thể:**\n
  - Path kỹ thuật: `belongs to field Thị giác máy tính -> is sub-field of Trí tuệ nhân tạo -> has expertise in PGS.TS. Nguyễn Văn A`.\n
  - XAI diễn giải: “Dự án của bạn thuộc lĩnh vực Thị giác máy tính, đây là một nhánh của Trí tuệ nhân tạo. PGS.TS. Nguyễn Văn A có chuyên môn đúng trong lĩnh vực này, nên là ứng viên phù hợp cho dự án.”\n
  - Confidence: 0.84 → “Khuyến nghị – Có đủ bằng chứng tin cậy”.\n
- **Nếu không có XAI:**\n
  - Hệ thống **vẫn gợi ý được danh sách** (ID + score + raw reasoning_paths).\n
  - Tuy nhiên:\n
    - Người dùng phải tự đọc các chuỗi path kỹ thuật, khó hiểu hơn.\n
    - Không có đoạn giải thích tiếng Việt/tiếng Anh, không có thống kê path, không có confidence tóm tắt.\n
  - Lợi ích của XAI là biến hệ thống từ “hộp đen” sang “hộp trong suốt”: **mỗi gợi ý đều kèm lý do rõ ràng**.\n
