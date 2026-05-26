# Hệ thống khuyến nghị R&D dựa trên đồ thị kiến thức

Hệ thống khuyến nghị sử dụng Knowledge Graph (Neo4j), dữ liệu nghiệp vụ (MongoDB), thuật toán **PGPR** (Policy-Guided Path Reasoning) và **XAI** để gợi ý và giải thích kết nối giữa dự án, chuyên gia, quỹ tài trợ và doanh nghiệp.

## Kiến trúc (đã chốt)

```text
Frontend
   → FastAPI Router
   → Service Layer
        ├─ EntityService → MongoRepository → MongoDB
        └─ RecommendationService → PGPRRecommender / XAI
                                      → PGPRGraphRepository → Neo4j
```

- **API entity** (danh sách, chi tiết): không qua PGPR.
- **API recommendation**: qua PGPR; mọi Cypher inference nằm trong `PGPRGraphRepository`.

Tài liệu chi tiết:

| File | Nội dung |
|------|----------|
| [KIEN_TRUC_DA_CHOT.md](KIEN_TRUC_DA_CHOT.md) | Kiến trúc lớp, luồng API, DI, hướng dẫn test |
| [KE_HOACH_HOAN_THIEN_HE_THONG.md](KE_HOACH_HOAN_THIEN_HE_THONG.md) | Lộ trình hoàn thiện hệ thống |
| [NHAT_KY_REFACTOR_PGPR.md](NHAT_KY_REFACTOR_PGPR.md) | Nhật ký refactor PGPR + kết quả test API |
| [CHECKLIST_REFACTOR_KIEN_TRUC_PGPR.md](CHECKLIST_REFACTOR_KIEN_TRUC_PGPR.md) | Checklist refactor từng phase |

## Yêu cầu

- Python 3.10+
- MongoDB 4.4+
- Neo4j 5.0+
- Redis (tùy chọn, cache)
- PyTorch (PGPR policy)
- Ollama (tùy chọn, giải thích LLM)

## Cấu hình

Tạo file `.env` tại thư mục gốc dự án (hoặc `backend/`):

```env
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=rd_recommendation_system

NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password

# Tùy chọn
OLLAMA_MODEL=llama3
```

## Chuẩn bị dữ liệu

```bash
cd add_data
pip install -r requirements.txt
python init_mongodb.py
python seed_data.py --force
python mongo_to_neo4j.py --clear
```

## Chạy Backend API

```powershell
cd backend
pip install neo4j python-dotenv pymongo numpy torch fastapi uvicorn redis httpx

python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

- Swagger: http://127.0.0.1:8000/docs  
- Health: http://127.0.0.1:8000/api/v1/health  

### API chính

| Method | Endpoint | Mô tả |
|--------|----------|--------|
| GET | `/api/v1/health` | Trạng thái MongoDB, Neo4j, Redis, PGPR |
| GET | `/api/v1/entities/projects` | Danh sách dự án (MongoDB) |
| GET | `/api/v1/entities/experts` | Danh sách chuyên gia |
| GET | `/api/v1/entities/{type}/{id}` | Chi tiết entity |
| POST | `/api/v1/recommendations/policy` | Gợi ý theo policy PGPR (mọi cặp entity) |
| POST | `/api/v1/recommendations/experts` | Gợi ý chuyên gia cho dự án (legacy) |
| POST | `/api/v1/recommendations/projects/{id}/overview` | Overview 4 nhóm gợi ý |
| POST | `/api/v1/explanations` | Giải thích (mode: rule / llm / auto) |
| GET | `/api/v1/graph/paths` | Reasoning paths Cypher giữa 2 entity |

Ví dụ request policy:

```json
{
  "source_id": "prj_001",
  "source_type": "project",
  "target_type": "expert",
  "limit": 5,
  "language": "vi"
}
```

## Test API recommendation

Server phải đang chạy (`uvicorn` như trên):

```powershell
cd backend
python scripts/test_recommendation_api.py
```

Kết quả mong đợi: `policy total: 15 pass, 0 fail`. Chi tiết: `backend/scripts/api_test_results.json`.

## Train PGPR (tùy chọn)

Pipeline train vẫn chạy từ `backend/pgpr/` (truy cập Neo4j trực tiếp khi build KG — không qua API):

```bash
cd backend/pgpr
python run_pgpr.py --step 1
python run_pgpr.py --step 2
python run_pgpr.py --step 3 --project_id prj_001
```

Xem thêm: [backend/pgpr/PGPR_README.md](backend/pgpr/PGPR_README.md).

## Cấu trúc thư mục

```text
Đồ án/
├── add_data/                 # MongoDB init, seed, sync → Neo4j
├── backend/
│   ├── main.py               # FastAPI app
│   ├── api/
│   │   ├── deps.py           # Singleton PGPRGraphRepository, PGPRRecommender
│   │   └── v1/endpoints/     # health, entities, recommendations
│   ├── services/             # Entity, Recommendation, Health
│   ├── repositories/
│   │   ├── mongodb_repo.py
│   │   ├── neo4j_repo.py     # Health / query chung
│   │   └── pgpr_graph_repo.py # Neo4j cho PGPR inference
│   ├── pgpr/                 # PGPR engine, policy, XAI, pgpr_data/
│   └── scripts/
│       └── test_recommendation_api.py
├── KIEN_TRUC_DA_CHOT.md
├── KE_HOACH_HOAN_THIEN_HE_THONG.md
├── NHAT_KY_REFACTOR_PGPR.md
└── README.md
```

## Tài liệu khác

- [Thiết kế đồ thị kiến thức](Thiet_ke_do_thi_kien_thuc_RS_nghien_cuu_sua.md)
- [PGPR quy trình](backend/pgpr/PGPR_QUY_TRINH_HOAT_DONG.md)

---

Dự án nghiên cứu — hệ thống gợi ý có giải thích trên Knowledge Graph cho hệ sinh thái R&D.
