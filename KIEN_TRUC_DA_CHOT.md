# Kien truc da chot cho he thong R&D Recommendation

> **Cap nhat:** 2026-05-23 — Refactor `PGPRGraphRepository` da trien khai va test API 15/15 PASS. Chi tiet: `NHAT_KY_REFACTOR_PGPR.md`.

## 1. Nguyen tac kien truc

He thong duoc chia thanh cac lop ro rang:

- Frontend: giao dien web cho nguoi dung thao tac.
- FastAPI Router: nhan HTTP request, validate input co ban, tra HTTP response.
- Service Layer: xu ly business workflow va dieu phoi cac thanh phan ben duoi.
- Repository Layer: truy cap du lieu nghiep vu tu MongoDB/Neo4j.
- Recommendation Engine Layer: chua PGPR va XAI, dung cho recommendation va giai thich.
- Database Layer: MongoDB va Neo4j Knowledge Graph.

Quyet dinh quan trong:

```text
Khong phai API nao cung di qua PGPR.
PGPR chi duoc dung cho recommendation/path reasoning.
API lay danh sach data/detail/search entity se di qua Repository, khong di qua PGPR.
```

## 2. So do kien truc tong quan da chot

```text
Frontend
   |
   v
FastAPI Router
   |
   v
Service Layer
   |-----------------------------|
   |                             |
   v                             v
MongoRepository         PGPRRecommender / XAI
   |                             |
   v                             v
MongoDB                 PGPRGraphRepository
                                 |
                                 v
                               Neo4j
```

Quyet dinh chot:

```text
PGPRRecommender / XAI la Recommendation Engine Layer.
PGPRRecommender khong nen truy cap Neo4j driver truc tiep.
Neu PGPR can du lieu graph thi goi PGPRGraphRepository.
MongoRepository phuc vu entity data tu MongoDB.
PGPRGraphRepository phuc vu graph/path/candidate data tu Neo4j cho PGPR.
```

## 3. Vai tro tung lop

### 3.1 Frontend

Frontend dung de:

- Hien thi dashboard.
- Hien thi danh sach project/expert/funder/enterprise.
- Cho nguoi dung chon source entity.
- Goi API recommendation.
- Hien thi score, reasoning paths va explanation.

Frontend khong xu ly recommendation logic.

### 3.2 FastAPI Router

Router chi nen lam cac viec nhe:

- Nhan request tu frontend.
- Validate input o muc HTTP.
- Goi service tuong ung.
- Chuyen loi business thanh HTTP error.
- Tra response ve frontend.

Router khong nen:

- Viet query MongoDB/Neo4j truc tiep.
- Tu chay logic recommendation.
- Tu dieu phoi nhieu workflow phuc tap.

### 3.3 Service Layer

Service Layer la noi xu ly business workflow.

Vi du:

- `EntityService`: lay danh sach entity, lay detail entity.
- `RecommendationService`: goi PGPR, enrich explanation, cache ket qua.
- `HealthService`: kiem tra trang thai MongoDB, Neo4j, Redis, PGPR assets.

Service co the goi:

- MongoRepository de lay entity/profile data.
- PGPRRecommender de thuc hien recommendation.
- PGPRExplainer/XAI de sinh giai thich.
- Cache.

### 3.4 Repository Layer

Repository Layer co nhiem vu boc truy cap database.

Repository dung cho:

- Lay danh sach projects/experts/funders/enterprises.
- Search entity.
- Lay detail entity.
- Health check database.
- Cac query graph/path/candidate cho PGPR thong qua `PGPRGraphRepository`.

Repository khong phai la noi tinh recommendation score.

Vi du luong entity:

```text
GET /api/v1/entities/projects
   -> Entity Router
   -> EntityService
   -> MongoDBRepository
   -> MongoDB
```

### 3.5 Recommendation Engine Layer

Recommendation Engine Layer la lop rieng cho thuat toan.

Trong he thong hien tai, lop nay gom:

- `PGPRRecommender`
- `PGPRExplainer`
- cac thanh phan PGPR nhu environment, policy, KG, training/inference
- `PGPRGraphRepository` duoc goi boi PGPR khi can truy cap Neo4j

PGPR dung de:

- Tim reasoning paths tren Knowledge Graph.
- Chay policy-guided inference.
- Rank candidates.
- Tinh score recommendation.
- Tra ve path co the giai thich.

XAI dung de:

- Doc reasoning paths.
- Sinh giai thich rule-based.
- Goi LLM/Ollama neu can.

PGPR khong dung de lay danh sach data thong thuong.

PGPR cung khong nen tu quan ly Neo4j driver truc tiep trong kien truc da chot. Thay vao do:

```text
PGPRRecommender
   -> PGPRGraphRepository
   -> Neo4j
```

## 4. Luong API da chot

### 4.1 Lay danh sach entity

Khong qua PGPR.

```text
Frontend
   -> FastAPI Router
   -> EntityService
   -> MongoDBRepository
   -> MongoDB
```

API:

```http
GET /api/v1/entities/projects
GET /api/v1/entities/experts
GET /api/v1/entities/funders
GET /api/v1/entities/enterprises
```

### 4.2 Lay chi tiet entity

Khong qua PGPR.

```text
Frontend
   -> FastAPI Router
   -> EntityService
   -> MongoDBRepository
   -> MongoDB
```

API:

```http
GET /api/v1/entities/{entity_type}/{entity_id}
```

### 4.3 Goi y recommendation

Co qua PGPR.

```text
Frontend
   -> FastAPI Router
   -> RecommendationService
   -> PGPRRecommender
   -> PGPRGraphRepository
   -> Neo4j Knowledge Graph
```

API:

```http
POST /api/v1/recommendations/policy
```

### 4.4 Project overview

Co qua PGPR vi day la workflow recommendation.

```text
Frontend
   -> FastAPI Router
   -> RecommendationService
   -> PGPRRecommender
   -> PGPRGraphRepository
   -> Neo4j Knowledge Graph
```

API:

```http
POST /api/v1/recommendations/projects/{project_id}/overview
```

### 4.5 Explanation

Dung XAI Explainer.

```text
Frontend
   -> FastAPI Router
   -> RecommendationService
   -> PGPRExplainer
```

Neu explanation can reasoning paths thi dung output tu PGPR hoac PGPRGraphRepository/Graph API.

API:

```http
POST /api/v1/explanations          # mode: rule | llm | auto
POST /api/v1/recommendations/explain  # legacy, mode mac dinh auto
GET  /api/v1/graph/paths             # Cypher paths giua 2 entity
```

## 5. Vi tri cua PGPR trong he thong

PGPR khong phai Repository.

PGPR la:

```text
Recommendation Engine Layer
```

hoac:

```text
Algorithm Layer
```

Ly do:

- PGPR khong chi lay du lieu.
- PGPR thuc hien suy luan tren graph.
- PGPR tim path, chon action, tinh score, rank candidates.
- PGPR tra ve ket qua recommendation co kha nang giai thich.

## 6. Vi tri cua Repository trong he thong

Repository van can thiet vi:

- Tach code query database ra khoi service.
- Giu service sach hon.
- De test/mock hon.
- De doi schema/database sau nay de hon.
- Phu hop mo hinh phan lop khi bao ve do an.

Trong kien truc da chot:

- `MongoRepository` duoc dung cho entity data va profile/detail.
- `PGPRGraphRepository` duoc dung cho du lieu graph, candidate va reasoning paths.
- PGPRRecommender se goi `PGPRGraphRepository` khi can truy cap Neo4j.

Refactor **da hoan thanh** (xem `NHAT_KY_REFACTOR_PGPR.md`):

```text
PGPRRecommender
   -> PGPRGraphRepository (singleton qua api/deps.py)
   -> Neo4j
```

`PGPRRecommender` **khong** con `GraphDatabase` / `driver.session` / `session.run` trong `pgpr_recommendation.py`.

### 6.1 Phan biet hai repository Neo4j

| Class | File | Vai tro |
|-------|------|---------|
| `MongoRepository` | `backend/repositories/mongodb_repo.py` | Entity list/detail tu MongoDB |
| `PGPRGraphRepository` | `backend/repositories/pgpr_graph_repo.py` | **Duy nhat** cho Cypher phuc vu PGPR inference (paths, candidates, entity info tren graph) |
| `Neo4jRepository` | `backend/repositories/neo4j_repo.py` | Health check va query Neo4j chung (chua dung trong luong recommendation chinh) |

**Luu y:** `pgpr_kg.py`, `pgpr_train.py` van truy cap Neo4j truc tiep khi **train/build KG** — ngoai pham vi inference API.

### 6.2 Dependency Injection (FastAPI)

File `backend/api/deps.py`:

```python
get_pgpr_graph_repo()   # singleton PGPRGraphRepository
get_pgpr_recommender()  # inject graph_repo=...
get_recommendation_service()
get_entity_service()
get_health_service()
```

Mot ung dung chi tao **mot** Neo4j driver cho PGPR (qua graph repo), tranh mo driver moi moi request.

### 6.3 Cac file backend chinh

```text
backend/
  main.py
  api/deps.py
  api/v1/endpoints/
    health.py
    entities.py
    recommendations.py
  services/
    entity_service.py
    recommendation_service.py
    health_service.py
  repositories/
    mongodb_repo.py
    neo4j_repo.py
    pgpr_graph_repo.py      # Neo4j cho PGPR
  pgpr/
    pgpr_recommendation.py  # Engine, khong query Neo4j truc tiep
    pgpr_env.py, pgpr_kg.py, pgpr_policy.py, ...
```

## 7. Ket luan da chot

Kien truc he thong duoc chot nhu sau:

```text
API lay du lieu:
Router -> EntityService -> Repository -> MongoDB

API recommendation:
Router -> RecommendationService -> PGPRRecommender -> PGPRGraphRepository -> Neo4j KG

API explanation:
Router -> RecommendationService -> PGPRExplainer

API health:
Router -> HealthService -> Repository/cache/file checks
```

Thong diep khi trinh bay bao cao:

```text
He thong tach rieng data access layer va recommendation engine layer.
MongoRepository phu trach truy cap du lieu entity/profile trong MongoDB.
PGPRGraphRepository phu trach truy cap Knowledge Graph trong Neo4j cho PGPR.
PGPR la engine thuat toan phu trach suy luan va xep hang recommendation tren Knowledge Graph, nhung khong truy cap database truc tiep.
```

## 8. Huong dan test sau refactor

### 8.1 Khoi dong backend

```powershell
cd backend
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

### 8.2 Smoke test nhanh

```powershell
# Health
curl http://127.0.0.1:8000/api/v1/health

# Policy (Project -> Expert)
curl -X POST http://127.0.0.1:8000/api/v1/recommendations/policy ^
  -H "Content-Type: application/json" ^
  -d "{\"source_id\":\"prj_001\",\"source_type\":\"project\",\"target_type\":\"expert\",\"limit\":3,\"language\":\"vi\"}"
```

### 8.3 Test day du 15 cap entity

```powershell
cd backend
python scripts/test_recommendation_api.py
```

Ket qua mong doi: `policy total: 15 pass, 0 fail`. Chi tiet JSON: `backend/scripts/api_test_results.json`.

### 8.4 Response shape recommendation item

Moi item nen co (khi policy tim duoc duong):

- `id`, `name`, `score`
- `reasoning_paths` (mang `{path, score, length}`)
- `path_diversity` (neu co)
- `explanation` / `xai_explanation`
- `metrics` (tuy entity type)

Mot so cap entity co the tra ve item khong co `reasoning_paths` nhung van HTTP 200 — do policy rollout, khong phai loi refactor repository.
