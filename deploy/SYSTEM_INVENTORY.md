# Tổng quan hệ thống (inventory)

Cập nhật sau Phase 9 — dùng để đối chiếu checklist deploy với code thực tế.

## 1. Kiến trúc runtime

```text
Frontend (Next.js, port 9002 dev / 3000 Docker)
    → FastAPI backend (:8000)
        ├─ Auth / Entities / Admin → MongoDB (rd_knowledge_graph)
        ├─ Recommendations / Explanations
        │     ├─ HybridRecommendationService (PGPR + embedding + topic)
        │     ├─ PGPRRecommender + PGPRGraphRepository → Neo4j
        │     └─ XAI / Ollama (optional)
        ├─ Graph API → Neo4j
        └─ Health → Mongo, Neo4j, Redis (optional), RabbitMQ (optional), PGPR assets

Async embedding pipeline:
    API / sync → Mongo outbox → outbox_publisher → RabbitMQ (durable)
        → embedding_worker → Mongo embedding + Neo4j features
```

## 2. Đã có theo phase (code)

| Phase | Nội dung chính | Trạng thái |
|-------|----------------|------------|
| 0 | Baseline snapshot PGPR, compile | ✅ |
| 1 | `embedding` metadata, backfill | ✅ |
| 2 | RabbitMQ optional, events, publisher | ✅ |
| 3 | `embedding_worker`, job processing | ✅ |
| 4 | Mongo outbox, `run_outbox_publisher.py` | ✅ |
| 5 | Candidate mask, embedding safety | ✅ |
| 6 | Hybrid recommendation | ✅ |
| 7 | Admin embedding pipeline API | ✅ |
| 7.1 | Heartbeat, DLQ, retry filters, audit reason | ✅ |
| 8 | `backend/evaluation/`, metrics, regression gate | ✅ |
| 8.1 | 22 GT cases, seed guard, primary_metrics | ✅ |
| 9 | Docker app-only, healthcheck, backup scripts | ✅ App-only smoke validated; ⚠️ full destructive restore staging still recommended |
| 10–12 | GraphSAGE real, governance, security hardening | ⏳ Chưa |

## 3. API endpoints (`backend/main.py`)

| Nhóm | Prefix |
|------|--------|
| Health | `/api/v1/health` |
| Auth | `/api/v1/auth/*` |
| Entities | `/api/v1/entities/*` |
| Recommendations | `/api/v1/recommendations/*` |
| Explanations | `/api/v1/explanations/*` |
| Graph | `/api/v1/graph/*` |
| Admin | `/api/v1/admin/*` |
| Evaluation summary | `/api/v1/evaluation/*` |
| Taxonomy | `/api/v1/taxonomy/*` |

## 4. Services & workers (Python)

| Thành phần | File |
|------------|------|
| Hybrid / PGPR / embedding | `services/hybrid_recommendation_service.py`, `embedding_service.py`, … |
| Outbox publisher | `services/outbox_publisher_service.py` |
| Health | `services/health_service.py` |
| Embedding worker | `workers/embedding_worker.py` |
| Evaluation offline | `evaluation/runner.py`, `scripts/run_evaluation.py` |

## 5. Hạ tầng (môi trường của bạn)

Theo `.env` gốc dự án — **chạy sẵn ngoài Docker**:

| Dịch vụ | Cấu hình hiện tại |
|---------|-------------------|
| MongoDB | `admin` / `rd_knowledge_graph` @ localhost:27017 |
| Neo4j | `neo4j://127.0.0.1:7687` |
| Redis | localhost:6379 |
| RabbitMQ | guest @ localhost:5672, queue `embedding.jobs` |
| Ollama | localhost:11434 |

Phase 9 **không** khởi tạo lại các dịch vụ này; chỉ đóng gói app và map `host.docker.internal`.

## 6. Phase 9 — phạm vi thực tế

Trạng thái: **app-only production smoke validated**. Đã build/up production compose và chạy restore smoke opt-in. Full destructive restore từ backup archive/dump thật vẫn nên chạy trên staging riêng trước go-live.

| Hạng mục | Có | Ghi chú |
|----------|-----|---------|
| `docker-compose.production.yml` | ✅ | backend, worker, outbox, frontend |
| `docker-compose.infra.yml` | ✅ | Tuỳ chọn |
| Dockerfile backend/frontend | ✅ | |
| Dùng `.env` gốc | ✅ | Không bắt buộc `.env.production` |
| Backup bundled infra | ✅ | `backup_all.ps1` + `docker-compose.infra.yml` |
| Backup infra ngoài | ✅ | `backup_external.ps1` (tên container) |
| Restore verify | ⚠️ | Script mẫu + test opt-in; cần chạy tay trên staging |
| Docker build đã verify trên máy | ⚠️ | Cần `docker compose build` lần đầu (PyTorch nặng) |

## 7. Lệnh kiểm tra nhanh

```powershell
cd backend
python scripts/system_inventory_check.py
python scripts/test_phase9_production_deploy.py
```
