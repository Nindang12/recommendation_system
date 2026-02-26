# Hướng dẫn chạy hệ thống từ đầu

Hướng dẫn từ bước cài đặt môi trường đến khi chạy được đầy đủ pipeline PGPR và đề xuất kèm XAI.

---

## 1. Yêu cầu hệ thống

- **Python** 3.9 trở lên  
- **Neo4j** (khuyến nghị 4.x hoặc 5.x) đã cài và chạy  
- Đồ thị tri thức đã có trong Neo4j với các node: `Project`, `Expert`, `Funder`, `Enterprise`, `ResearchField`, `Industry` và các quan hệ tương ứng (ví dụ: `BELONGS_TO`, `PARTICIPATES_IN`, `FUNDS`, `SUPPORTS`, `PARTNERS_WITH`, `OPERATES_IN`, `HAS_EXPERTISE_IN`, …)

Nếu chưa có dữ liệu trong Neo4j, cần chạy script seed/import của dự án (ví dụ từ MongoDB hoặc file seed) trước khi làm các bước dưới.

---

## 2. Chuẩn bị môi trường

### 2.1. Mở terminal tại thư mục dự án

```bash
cd "d:\Documents\Đồ án\pgpr_method"
```

(Điều chỉnh đường dẫn đúng với máy bạn.)

### 2.2. Tạo môi trường ảo và kích hoạt

**Windows (PowerShell):**

```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

**Windows (CMD):**

```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

**Linux / macOS:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2.3. Cài đặt thư viện

```bash
pip install -r requirements.txt
```

(Cần có file `requirements.txt` trong thư mục; thường gồm `neo4j`, `python-dotenv`, `numpy`, và nếu dùng policy thì `torch`.)

### 2.4. Cấu hình Neo4j (.env)

Tạo hoặc chỉnh file `.env` **trong cùng thư mục** với code (ví dụ trong `pgpr_method`):

```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
```

Thay `your_password` bằng mật khẩu Neo4j của bạn. Đảm bảo Neo4j đang chạy và có thể kết nối tới `NEO4J_URI`.

---

## 3. Đảm bảo Neo4j có dữ liệu

- Nếu dự án có script đồng bộ từ MongoDB sang Neo4j (ví dụ `mongo_to_neo4j.py`), chạy theo tài liệu của script đó.
- Nếu có script seed (ví dụ `seed_data.py`), chạy để tạo dữ liệu mẫu trước.
- Kiểm tra trong Neo4j Browser hoặc Cypher: có node `Project`, `Expert`, `Funder`, `Enterprise` và quan hệ giữa chúng.

Ví dụ kiểm tra nhanh:

```cypher
MATCH (n) RETURN labels(n), count(n) LIMIT 20
```

---

## 4. Chạy pipeline PGPR (build KG + train policy)

Pipeline gồm 3 bước, dùng script `run_pgpr.py`.

### Bước 1: Xuất đồ thị từ Neo4j và train embedding (TransE)

```bash
python run_pgpr.py --step 1
```

Tùy chọn:

- `--data_dir pgpr_data` (mặc định)
- `--emb_dim 64`

Kết quả: trong `pgpr_data/` có `vocab.json`, `triples.txt`, `entity_emb.npy`, `relation_emb.npy`.

### Bước 2: Train policy (REINFORCE)

```bash
python run_pgpr.py --step 2 --n_epoch 50
```

Tùy chọn: `--n_positive 200`, `--n_negative 200`, `--data_dir pgpr_data`.

Kết quả: file `pgpr_data/policy.pt` (nếu train thành công). Nếu không có policy, engine vẫn chạy được ở chế độ heuristic.

### Chạy liền Bước 1 + 2

```bash
python run_pgpr.py --all
```

Sau đó chạy riêng Bước 3 khi cần.

### Bước 3: Demo gợi ý chuyên gia cho một dự án

```bash
python run_pgpr.py --step 3 --project_id PRJ_0001 --limit 5
```

- Thay `PRJ_0001` bằng `project_id` có trong Neo4j.
- Kết quả in ra console: danh sách expert được gợi ý, điểm, đường dẫn lý giải.

---

## 5. Chạy đề xuất kèm XAI (giải thích chi tiết)

Sau khi Neo4j và (tùy chọn) PGPR policy đã sẵn sàng, có thể dùng module tích hợp để lấy gợi ý kèm giải thích tự nhiên và chi tiết từ Neo4j.

### 5.1. Chạy ví dụ mặc định trong integration

File `pgpr_xai_integration.py` có block `if __name__ == "__main__":` mặc định gọi gợi ý **funder** cho một project, in ra console và lưu HTML + JSON:

```bash
python pgpr_xai_integration.py
```

Kết quả:

- In ra console: báo cáo tổng quan, từng gợi ý kèm natural language, visualization, confidence.
- File `funder_recommendations_explained.html` (mở bằng trình duyệt).
- File `recommendations_with_explanations.json`.

### 5.2. XAI với Ollama LLM (giải thích bằng mô hình ngôn ngữ)

Để dùng LLM (Ollama) thay cho template sẵn để tạo giải thích tự nhiên:

1. Cài [Ollama](https://ollama.com) và chạy `ollama serve`
2. Tải model: `ollama pull llama3` (hoặc mistral, phi, …)
3. Chạy integration với cờ `--llm`:

```bash
python pgpr_xai_integration.py PRJ_0001 --llm
python pgpr_xai_integration.py PRJ_0001 --llm --model mistral
```

Hoặc từ code:

```python
result = generate_project_multi_recommendations(
    project_id="PRJ_0001",
    use_llm=True,
    ollama_model="llama3",
)
```

Nếu Ollama không chạy hoặc gọi API lỗi, hệ thống tự động quay về giải thích theo template.

### 5.3. Gọi từ code Python (tùy biến)

Có thể import và gọi các hàm tích hợp trong script hoặc notebook của bạn.

**Đề xuất cho một Project (funders + experts):**

```python
from pgpr_xai_integration import generate_project_multi_recommendations

result = generate_project_multi_recommendations(
    project_id="PRJ_0004",
    limit_funders=5,
    limit_experts=5,
    language="vi",
)
# result["funders"]  # list { recommendation, explanation }
# result["experts"]
```

**Đề xuất cho một Expert (enterprises + funders + projects):**

```python
from pgpr_xai_integration import generate_expert_multi_recommendations

result = generate_expert_multi_recommendations(
    expert_id="EXP_0001",
    limit_enterprises=5,
    limit_funders=5,
    limit_projects=5,
    language="vi",
)
# result["enterprises"], result["funders"], result["projects"]
```

**Đề xuất cho một Enterprise (experts + projects):**

```python
from pgpr_xai_integration import generate_enterprise_multi_recommendations

result = generate_enterprise_multi_recommendations(
    enterprise_id="ENT_0001",
    limit_experts=5,
    limit_projects=5,
    language="vi",
)
# result["experts"], result["projects"]
```

**Đề xuất cho một Funder (experts + projects):**

```python
from pgpr_xai_integration import generate_funder_multi_recommendations

result = generate_funder_multi_recommendations(
    funder_id="FUN_0001",
    limit_experts=5,
    limit_projects=5,
    language="vi",
)
# result["experts"], result["projects"]
```

**Lưu HTML và JSON:**

```python
from pgpr_xai_integration import (
    generate_project_multi_recommendations,
    save_explained_recommendations_html,
)
import json

result = generate_project_multi_recommendations(
    project_id="PRJ_0004",
    limit_funders=5,
    limit_experts=5,
    language="vi",
)

# Lưu HTML (cấu trúc HTML dùng cho dạng result có "recommendations" + "summary";
# với multi-recommendations có thể cần build result tương thích hoặc dùng hàm tương ứng nếu có)
# save_explained_recommendations_html(result, "output.html")

with open("recommendations_with_explanations.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
```

(Lưu ý: `save_explained_recommendations_html` được thiết kế cho dạng kết quả có `result["recommendations"]` và `result["summary"]` (như từ `generate_explained_recommendations`). Với `generate_project_multi_recommendations` bạn nhận `result["funders"]` và `result["experts"]`; nếu cần xuất HTML cho dạng này có thể tự build từ các key đó hoặc gộp về format có `recommendations` rồi gọi hàm save.)

---

## 6. Thứ tự chạy tóm tắt (từ đầu)

1. Cài Python 3.9+, Neo4j; tạo venv, `pip install -r requirements.txt`.
2. Tạo file `.env` với `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`.
3. Đảm bảo Neo4j đã có dữ liệu (seed/import).
4. **Bước 1:** `python run_pgpr.py --step 1`
5. **Bước 2 (tùy chọn):** `python run_pgpr.py --step 2 --n_epoch 50`
6. **Bước 3 (demo PGPR):** `python run_pgpr.py --step 3 --project_id PRJ_0001`
7. **XAI:** `python pgpr_xai_integration.py` hoặc gọi các hàm `generate_*` từ code như trên.

---

## 7. Một số lỗi thường gặp

| Triệu chứng | Gợi ý xử lý |
|-------------|-------------|
| Lỗi kết nối Neo4j | Kiểm tra Neo4j đang chạy, `NEO4J_URI`/user/password trong `.env` đúng. |
| Không tìm thấy đường dẫn / gợi ý rỗng | Kiểm tra đồ thị có đủ node và quan hệ; thử `project_id`/`expert_id`/… có trong DB. |
| Thiếu `policy.pt` | Bước 2 có thể bị lỗi (thiếu cặp positive/negative, lỗi PyTorch,…). Hệ thống vẫn chạy ở chế độ heuristic. |
| XAI không có “Chi tiết từ đồ thị tri thức” | Kiểm tra `source_context` đã truyền đúng khi gọi `explain_recommendation`; Neo4j kết nối được và có dữ liệu tương ứng. |

---

## 8. Tài liệu liên quan

- **TONG_HOP_HE_THONG.md** – Tổng hợp chi tiết chức năng, luồng đề xuất, XAI, cấu trúc file.
- **PGPR_README.md** – Mô tả PGPR, cấu trúc module, tham chiếu bài báo.
