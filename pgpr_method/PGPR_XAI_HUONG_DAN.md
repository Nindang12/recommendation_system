## Hướng dẫn chạy hệ thống PGPR + XAI

### 1. Chuẩn bị môi trường

- **Yêu cầu**
  - Python 3.9+
  - Neo4j đang chạy (có graph: `Project`, `Expert`, `Funder`, `ResearchField`, …)

- **Tạo môi trường ảo & cài thư viện**

```bash
cd "d:\Documents\Đồ án\pgpr_method"
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

- **Cấu hình Neo4j trong `.env` (cùng thư mục)**

```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
```

### 2. Pipeline PGPR (không XAI)

File chính: `run_pgpr.py`

- **Bước 1 – Build KG + embedding từ Neo4j**

```bash
python run_pgpr.py --step 1
```

- **Bước 2 – Train policy PGPR**

```bash
python run_pgpr.py --step 2 --n_epoch 50
```

- **Chạy liền bước 1 + 2**

```bash
python run_pgpr.py --all
```

- **Bước 3 – Test gợi ý chuyên gia cho 1 dự án**

```bash
python run_pgpr.py --step 3 --project_id PRJ_0004 --limit 5
```

### 3. Chạy Recommendation + XAI giải thích chi tiết

File chính: `pgpr_xai_integration.py` (tích hợp `PGPRRecommender` + `PGPRExplainer`).

Chạy ví dụ mặc định (gợi ý funder cho `PRJ_0004`, tiếng Việt):

```bash
python pgpr_xai_integration.py
```

Script sẽ:

- Gọi `generate_explained_recommendations(...)` để sinh:
  - Danh sách gợi ý (funder / expert / project).
  - Giải thích tự nhiên (tiếng Việt), phân tích đường dẫn, độ tin cậy.
  - Giải thích chi tiết từ Neo4j (lĩnh vực trùng khớp, dự án liên quan, quỹ tài trợ chung, …).
- In kết quả ra console bằng `print_explained_recommendations(...)`.
- Lưu:
  - `funder_recommendations_explained.html`: giao diện đẹp xem trên trình duyệt.
  - `recommendations_with_explanations.json`: dữ liệu thô, có đầy đủ `recommendation` + `explanation` + `neo4j_details`.

### 4. Tùy chỉnh type gợi ý (funder / expert / project)

Trong `pgpr_xai_integration.py`, đoạn ví dụ cuối file:

```python
result = generate_explained_recommendations(
    project_id="PRJ_0004",
    rec_type="funder",   # "funder" | "expert" | "project"
    limit=5,
    language="vi",
)
```

- **Gợi ý funder cho 1 dự án**: `rec_type="funder"`, `project_id` là ID project (`PRJ_0004`, …).
- **Gợi ý chuyên gia cho 1 dự án**: `rec_type="expert"`, `project_id` là ID project.
- **Gợi ý dự án cho 1 chuyên gia**: `rec_type="project"`, khi đó `project_id` thực chất là ID expert (ví dụ `EXP_0001`).

Sau khi sửa tham số, chỉ cần chạy lại:

```bash
python pgpr_xai_integration.py
```

### 5. Mẫu script start riêng (tuỳ biến)

Nếu muốn tự tạo file start riêng, có thể dùng mẫu sau trong `start_system.py`:

```python
from pgpr_xai_integration import (
    generate_explained_recommendations,
    print_explained_recommendations,
    save_explained_recommendations_html,
)
import json

if __name__ == "__main__":
    result = generate_explained_recommendations(
        project_id="PRJ_0004",
        rec_type="expert",   # "funder" | "expert" | "project"
        limit=5,
        language="vi",
    )

    print_explained_recommendations(result)
    save_explained_recommendations_html(result, "recommendations_explained.html")

    with open("recommendations_with_explanations.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
```

Chạy:

```bash
python start_system.py
```

