# PGPR (Policy-Guided Path Reasoning) – Hướng dẫn sử dụng

Thuật toán PGPR (Xian et al., SIGIR 2019) dùng **reinforcement learning** để học **policy** đi từng bước trên đồ thị tri thức, tìm đường đi giải thích được từ source (ví dụ Project) tới target (ví dụ Expert).

## Cấu trúc module

| File | Mô tả |
|------|--------|
| `pgpr_kg.py` | Export triples từ Neo4j, build entity/relation vocab, train TransE (embedding). |
| `pgpr_env.py` | Môi trường RL: state = path hiện tại, action = (relation, next_entity) từ Neo4j. |
| `pgpr_policy.py` | Policy network (PyTorch): encode path, score action, sample/argmax. |
| `pgpr_train.py` | Thu thập cặp (project, expert) positive/negative, train REINFORCE. |
| `pgpr_recommendation.py` | Inference: nếu có `pgpr_data/policy.pt` thì dùng policy-guided path; không thì fallback heuristic. |

---

## Cách chạy (từng bước)

**Yêu cầu:** Neo4j đã chạy và đã đồng bộ dữ liệu (chạy `python mongo_to_neo4j.py --clear` nếu cần). Cài đặt:

```bash
pip install -r requirements.txt
```

### Bước 0: Đảm bảo Neo4j có dữ liệu

```bash
python mongo_to_neo4j.py --clear
```

(Sau khi đã có MongoDB seed: `python seed_data.py --force`.)

---

### Bước 1: Chuẩn bị KG và embedding (chạy 1 lần)

Export đồ thị từ Neo4j → lưu `vocab.json`, `triples.txt`, train TransE → lưu `entity_emb.npy`, `relation_emb.npy`.

**Cách 1 – Gọi từ Python (trong thư mục project):**

```bash
cd "d:\Documents\Đồ án"
python -c "from pgpr_kg import build_kg_from_neo4j; build_kg_from_neo4j(data_dir='pgpr_data', train_emb=True, emb_dim=64)"
```

**Cách 2 – Chạy script có sẵn (nếu dùng `run_pgpr.py`):**

```bash
python run_pgpr.py --step 1
```

Sau bước 1, trong thư mục `pgpr_data/` sẽ có: `vocab.json`, `triples.txt`, `entity_emb.npy`, `relation_emb.npy`.

---

### Bước 2: Train policy (REINFORCE)

Cần có ít nhất vài cặp (project, expert) trong Neo4j (Expert PARTICIPATES_IN Project). Script tự lấy positive/negative rồi train policy.

```bash
python pgpr_train.py --data_dir pgpr_data --n_epoch 50 --save_path pgpr_data/policy.pt
```

Tùy chọn thường dùng:

- `--n_positive 200` `--n_negative 200` – số cặp train
- `--max_path_length 5` – độ dài tối đa đường đi
- `--embedding_dim 64` – khớp với `emb_dim` ở Bước 1
- `--lr 0.001` – learning rate

Hoặc:

```bash
python run_pgpr.py --step 2
```

Sau bước 2 sẽ có file `pgpr_data/policy.pt`.

---

### Bước 3: Gợi ý chuyên gia (recommendation)

Khi đã có `pgpr_data/policy.pt` và `pgpr_data/vocab.json`, engine sẽ dùng **policy-guided path**. Chạy trong Python:

```bash
python -c "
from pgpr_recommendation import PGPRRecommender, print_pgpr_recommendations
engine = PGPRRecommender(max_path_length=5, data_dir='pgpr_data')
recs = engine.recommend_experts_for_project_pgpr('PRJ_0001', limit=5, use_policy=True)
print_pgpr_recommendations(recs, 'PGPR Expert Recommendations')
engine.close()
"
```

Hoặc chạy script demo:

```bash
python run_pgpr.py --step 3 --project_id PRJ_0001
```

- **use_policy=True** (mặc định): đi từng bước theo policy (đúng thuật toán PGPR).
- **use_policy=False** hoặc chưa có policy: dùng heuristic (path + trọng số cố định).

---

## Chạy nhanh toàn bộ (Bước 1 → 2 → 3)

```bash
python run_pgpr.py --all
```

Rồi gọi recommendation thủ công (Bước 3 ở trên) hoặc:

```bash
python run_pgpr.py --all && python run_pgpr.py --step 3 --project_id PRJ_0001
```

---

## Tóm tắt luồng PGPR

1. **Chuẩn bị:** Neo4j có graph → export KG + TransE → `pgpr_data/`.
2. **Training:** (project, expert) positive/negative → REINFORCE → `policy.pt`.
3. **Inference:** Từ project, policy chọn từng bước (relation, next_entity) đến Expert → rank + explanation path.

Tham chiếu: *Reinforcement Knowledge Graph Reasoning for Explainable Recommendation* (SIGIR 2019).
