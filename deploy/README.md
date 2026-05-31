# Production deployment (Phase 9)

Xem tổng quan hệ thống: [SYSTEM_INVENTORY.md](SYSTEM_INVENTORY.md).

## Mô hình deploy hiện tại (khuyến nghị)

| Thành phần | Chạy ở đâu |
|------------|-------------|
| MongoDB, Neo4j, Redis, RabbitMQ, Ollama | Container/process **sẵn có trên máy** |
| backend, embedding_worker, outbox_publisher, frontend | `docker-compose.production.yml` |

### Chạy app

```powershell
cd "D:\Documents\Đồ án"
# Cấu hình: file .env ở thư mục gốc (localhost cho dev; Docker tự map host.docker.internal)
docker compose -f docker-compose.production.yml up -d --build
```

- Frontend Docker: http://localhost:3000  
- API: http://localhost:8000 — health: `/api/v1/health`  
- Frontend dev (không Docker): port **9002** — giữ trong `CORS_ORIGINS`

### Biến quan trọng trong `.env`

| Biến | Vai trò |
|------|---------|
| `MONGO_USERNAME` / `MONGO_PASSWORD` / `MONGO_DB_NAME` | Mongo (`rd_knowledge_graph`) |
| `NEO4J_USER` / `NEO4J_PASSWORD` | Neo4j |
| `RABBITMQ_URL` hoặc `RABBITMQ_USER` / `RABBITMQ_PASSWORD` | Queue embedding |
| `EMBEDDING_*`, `WORKER_HEARTBEAT_STALE_SECONDS` | Pipeline embedding |
| `APP_AUTH_SECRET`, `ROOT_ADMIN_*` | Auth / RBAC |

Docker **ghi đè** host kết nối qua `host.docker.internal` (hoặc `INFRA_HOST` trong `.env` nếu Linux).

## Kiểm tra inventory

```powershell
cd backend
python scripts/system_inventory_check.py
python scripts/test_phase9_production_deploy.py
```

## Backup

**Infra ngoài** (container bạn đang dùng):

```powershell
.\deploy\backup\backup_external.ps1 -MongoContainer <ten-mongo> -Neo4jContainer <ten-neo4j> `
  -MongoUser admin -MongoPassword password
```

**Infra trong Compose** (`docker-compose.infra.yml`):

```powershell
.\deploy\backup\backup_all.ps1
```

Restore mẫu: `restore_mongo_sample.ps1`, `restore_neo4j_sample.ps1` (staging only).

## Gói DB trong Compose (tuỳ chọn)

```powershell
docker compose -f docker-compose.infra.yml -f docker-compose.production.yml up -d --build
```

Đặt trong `.env` hostname service: `mongodb`, `neo4j`, `redis`, `rabbitmq` (xem comment trong `.env.production.example`).

## RBAC / secrets

Đổi `APP_AUTH_SECRET`, `ROOT_ADMIN_PASSWORD` trước go-live. Không set `EVALUATION_ALLOW_SEED` trên production.
