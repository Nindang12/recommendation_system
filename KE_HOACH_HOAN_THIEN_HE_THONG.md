# Ke hoach hoan thien he thong R&D Recommendation

> **Cap nhat:** 2026-05-24 - Refactor PGPR xong; test policy 15/15 PASS; Phase 2 backend da them; Frontend MVP Next.js da co dashboard/entity/recommendation/XAI detail; cache explanation da chuyen vao service layer. Xem `NHAT_KY_REFACTOR_PGPR.md`, `DEMO_CASES.md`.

## 1. Muc tieu tong the

Hoan thien he thong goi y R&D dua tren Knowledge Graph, PGPR va XAI theo huong co the demo tren web, deploy duoc ban so bo, va du kha nang bao ve do an tot nghiep.

He thong hoan chinh can co:

- Backend FastAPI on dinh.
- Frontend web de nguoi dung thao tac.
- Knowledge Graph trong Neo4j.
- Du lieu goc trong MongoDB.
- PGPR recommendation tra ve ket qua co score.
- XAI explanation giai thich vi sao goi y phu hop.
- Graph/path visualization phuc vu demo.
- Evaluation co metric va baseline.
- Tai lieu, slide, demo script ro rang.

## 2. Lo trinh uu tien

Thu tu nen lam:

0. ~~Refactor PGPR: tach Neo4j query ra `PGPRGraphRepository`~~ **(da xong 2026-05-23)**
1. Hoan thien API cot loi.
2. ~~Tao frontend MVP.~~ **(da co ban local 2026-05-24)**
3. Chuan hoa demo data va demo case.
4. ~~Hoan thien explanation va graph paths.~~ **(da co API + UI detail co ban)**
5. Deploy ban so bo.
6. Them evaluation pipeline.
7. Them auth/history/favorite neu con thoi gian.
8. Viet bao cao, slide va kich ban bao ve.

## 3. Phase 1 - Backend API MVP

Muc tieu: frontend co the goi API va demo recommendation duoc.

### 3.1 Health API

Can tao:

```http
GET /api/v1/health
```

Response mong muon:

```json
{
  "status": "ok",
  "services": {
    "mongodb": "connected",
    "neo4j": "connected",
    "redis": "optional",
    "pgpr": "ready"
  }
}
```

Trang thai hoan thanh:

- [x] Tao endpoint health.
- [x] Kiem tra MongoDB connection.
- [x] Kiem tra Neo4j connection.
- [x] Kiem tra PGPR data/policy co ton tai.
- [x] Redis chi nen de optional, khong lam fail he thong neu Redis chua chay.

### 3.2 Entity List API

Can tao:

```http
GET /api/v1/entities/projects
GET /api/v1/entities/experts
GET /api/v1/entities/funders
GET /api/v1/entities/enterprises
```

Query params:

```text
search: optional
limit: default 20
page: default 1
```

Response mau:

```json
{
  "status": "success",
  "data": [
    {
      "id": "prj_001",
      "name": "Du an AI trong y te",
      "type": "project",
      "summary": "..."
    }
  ],
  "count": 1
}
```

Trang thai hoan thanh:

- [x] Projects list.
- [x] Experts list.
- [x] Funders list.
- [x] Enterprises list.
- [x] Search theo name/title/id.
- [x] Limit ket qua de frontend load nhanh.

### 3.3 Entity Detail API

Can tao:

```http
GET /api/v1/entities/{entity_type}/{entity_id}
```

Vi du:

```http
GET /api/v1/entities/project/prj_001
GET /api/v1/entities/expert/exp_001
```

Trang thai hoan thanh:

- [x] Lay detail project.
- [x] Lay detail expert.
- [x] Lay detail funder.
- [x] Lay detail enterprise.
- [x] Chuan hoa output thanh id, name, type, summary, metadata.

### 3.4 Recommendation API

Giu va on dinh API hien co:

```http
POST /api/v1/recommendations/policy
```

Request:

```json
{
  "source_id": "prj_001",
  "source_type": "project",
  "target_type": "expert",
  "limit": 5,
  "language": "vi"
}
```

Trang thai hoan thanh:

- [x] Project -> Expert.
- [x] Project -> Funder.
- [x] Project -> Enterprise.
- [x] Project -> Similar Project.
- [x] Expert -> Project.
- [x] Expert -> Expert.
- [x] Enterprise -> Expert.
- [x] Funder -> Project.
- [x] Response luon co id, name, score, reasoning_paths, explanation.
- [x] Refactor: recommendation di qua `PGPRRecommender` -> `PGPRGraphRepository` -> Neo4j (khong query truc tiep trong recommender).
- [x] Test smoke 15 cap entity: `python backend/scripts/test_recommendation_api.py` (ket qua: 15 pass).

### 3.5 Project Overview API

Can tao de frontend dashboard dep hon:

```http
POST /api/v1/recommendations/projects/{project_id}/overview
```

Response:

```json
{
  "status": "success",
  "source": {
    "id": "prj_001",
    "type": "project",
    "name": "Du an AI trong y te"
  },
  "data": {
    "experts": [],
    "funders": [],
    "enterprises": [],
    "similar_projects": []
  }
}
```

Trang thai hoan thanh:

- [x] Overview project goi song song 4 loai recommendation.
- [x] Moi nhom chi lay limit 3 den 5 de tranh cham.
- [x] Neu mot nhom loi thi nhom khac van tra ve duoc.

## 4. Phase 2 - XAI va Graph API

Muc tieu: he thong khong chi tra goi y, ma con giai thich duoc.

### 4.1 Explanation API

Can tao hoac chuan hoa:

```http
POST /api/v1/explanations
```

Request:

```json
{
  "recommendation": {},
  "target_type": "expert",
  "source_context": {
    "source_id": "prj_001",
    "source_type": "project",
    "source_name": "Du an AI trong y te"
  },
  "language": "vi",
  "mode": "rule"
}
```

Mode:

```text
rule
llm
auto
```

Trang thai hoan thanh:

- [x] Rule-based explanation chay nhanh (`POST /api/v1/explanations`, `mode=rule`).
- [x] LLM explanation qua Ollama la optional (`mode=llm`).
- [x] Neu Ollama loi thi fallback ve rule-based (`mode=auto` hoac `/recommendations/explain`).
- [x] Giai thich dua tren `reasoning_paths` trong recommendation payload (explainer hien co).
- [x] Cache explanation nam trong `RecommendationService`, khong de frontend quyet dinh cache nghiep vu.
- [x] `force_refresh=true` cho phep tao lai explanation khi can.

### 4.2 Graph Paths API

Can tao:

```http
GET /api/v1/graph/paths
```

Query:

```text
source_type=project
source_id=prj_001
target_type=expert
target_id=exp_001
```

Response:

```json
{
  "status": "success",
  "data": [
    {
      "path": "Project -> Skill -> Expert",
      "score": 0.72,
      "relations": ["REQUIRES_SKILL", "HAS_SKILL"],
      "entities": ["Du an AI", "Machine Learning", "Nguyen Van A"]
    }
  ]
}
```

Trang thai hoan thanh:

- [x] Lay paths tu `PGPRGraphRepository` qua `GraphService` / `find_reasoning_paths_cypher` (router khong query Neo4j).
- [x] Chuan hoa path: `path`, `score`, `relations`, `entities`, `path_length`.
- [x] Query params `max_length`, `limit` tren `GET /api/v1/graph/paths`.

### 4.3 Neighbor Graph API

Co the lam sau graph paths:

```http
GET /api/v1/graph/entities/{entity_type}/{entity_id}/neighbors?depth=2
```

Trang thai hoan thanh:

- [ ] Tra ve nodes va edges.
- [ ] Dung de ve graph visualization tren frontend.

## 5. Phase 3 - Frontend MVP

Muc tieu: co web de demo toan bo luong su dung.

### 5.1 Cong nghe de xuat

- React + Vite.
- Thuc te hien tai: Next.js App Router + TypeScript + Tailwind/shadcn-style components tu Firebase Studio.
- TypeScript neu co thoi gian, JavaScript neu can nhanh.
- CSS thuan hoac Tailwind.
- Thu vien graph co the dung React Flow hoac vis-network.

### 5.2 Man hinh can co truoc

1. Dashboard chinh.
2. Entity browser.
3. Recommendation workspace.
4. Recommendation detail.
5. Explanation/path view.

### 5.3 Dashboard chinh

Can hien thi:

- Trang thai backend.
- Tong quan cac loai entity.
- Nut vao demo Project -> Expert.
- Mot vai demo case co san.

Trang thai hoan thanh:

- [x] Goi `/api/v1/health`.
- [x] Hien thi service status.
- [x] Co quick demo buttons.

### 5.4 Entity Browser

Can hien thi:

- Tabs: Projects, Experts, Funders, Enterprises.
- Search.
- Danh sach entity.
- Click de xem detail.

API dung:

```text
GET /api/v1/entities/projects
GET /api/v1/entities/experts
GET /api/v1/entities/funders
GET /api/v1/entities/enterprises
GET /api/v1/entities/{type}/{id}
```

Trang thai hoan thanh:

- [x] Tab entity.
- [x] Search.
- [x] Detail panel.

### 5.5 Recommendation Workspace

Can hien thi:

- Chon source type.
- Chon source entity.
- Chon target type.
- Chon limit.
- Bam "Recommend".
- Danh sach ket qua.

API dung:

```text
POST /api/v1/recommendations/policy
```

Trang thai hoan thanh:

- [x] Form goi y tong quat.
- [x] Loading state.
- [x] Error state.
- [x] Empty state.
- [x] Ket qua co score, explanation preview, reasoning paths count.

### 5.6 Recommendation Detail

Khi click mot recommendation:

- Hien score.
- Hien explanation.
- Hien reasoning paths.
- Co nut sinh LLM explanation neu Ollama chay.

API dung:

```text
POST /api/v1/explanations
GET /api/v1/graph/paths
```

Trang thai hoan thanh:

- [x] Detail drawer/modal.
- [x] Path list format thanh card/chip.
- [x] Explanation block goi `POST /api/v1/explanations`.
- [x] Confidence va visualization text da format de demo.

## 6. Phase 4 - Chuan hoa du lieu demo

Muc tieu: demo khong bi trong ket qua.

Can chon truoc it nhat 3 case dep:

1. Project -> Expert.
2. Project -> Funder.
3. Expert -> Project hoac Enterprise -> Expert.

Voi moi case can ghi lai:

```text
source_id:
source_name:
target_type:
expected top recommendations:
reasoning paths dep:
```

Trang thai hoan thanh:

- [x] Chon 3 den 5 source IDs demo (`DEMO_CASES.md`).
- [x] Kiem tra Neo4j co path cho case demo chinh.
- [x] Kiem tra API tra ket qua tren frontend local.
- [x] Kiem tra explanation doc duoc va format lai trong XAI dialog.
- [ ] Chup screenshot de dua vao bao cao.

## 7. Phase 5 - Deploy ban so bo

Muc tieu: frontend va backend co the truy cap qua web.

### 7.1 Huong deploy de xuat

Phuong an de lam:

- Frontend: Vercel, Netlify hoac static hosting.
- Backend: Render, Railway, VPS hoac server local expose bang tunnel cho demo.
- Database: MongoDB/Neo4j nen uu tien chay tren VPS/local neu cloud phuc tap.

### 7.2 Backend deploy checklist

- [x] Tao `backend/requirements.txt`.
- [x] Them bien moi truong mau cho MongoDB, Neo4j, Redis, Ollama trong `backend/.env.example`.
- [x] Backend doc config tu environment variables.
- [ ] CORS chi ro frontend URL khi deploy.
- [ ] Test `/api/v1/health`.
- [ ] Test `/api/v1/recommendations/policy`.

### 7.3 Frontend deploy checklist

- [ ] Tao `.env` frontend voi `NEXT_PUBLIC_API_BASE_URL`.
- [x] Build production thanh cong (`npm.cmd run build`).
- [ ] Goi API backend deploy.
- [ ] Xu ly loi network va timeout.

## 8. Phase 6 - Evaluation

Muc tieu: chung minh PGPR tot hon baseline.

### 8.1 Baseline can co

1. Random.
2. Content-based matching.
3. Graph heuristic.
4. PGPR proposed method.

### 8.2 Metrics can co

- Precision@K.
- Recall@K.
- HitRate@K.
- NDCG@K.
- MRR neu co thoi gian.

### 8.3 File nen tao

```text
backend/evaluation/baselines.py
backend/evaluation/metrics.py
backend/evaluation/evaluate.py
```

Trang thai hoan thanh:

- [ ] Tao ground truth tu relationship co san trong Neo4j.
- [ ] Chay random baseline.
- [ ] Chay content-based baseline.
- [ ] Chay graph heuristic baseline.
- [ ] Chay PGPR.
- [ ] In bang ket qua.
- [ ] Luu ket qua JSON/CSV de dua vao bao cao.

Bang bao cao mau:

| Method | Precision@5 | Recall@5 | NDCG@5 | HitRate@5 |
|---|---:|---:|---:|---:|
| Random | | | | |
| Content-based | | | | |
| Graph heuristic | | | | |
| PGPR | | | | |

## 9. Phase 7 - Auth va tinh nang nguoi dung

Day la phase phu, chi lam sau khi core on dinh.

### 9.1 Auth API toi thieu

```http
POST /api/v1/auth/register
POST /api/v1/auth/login
GET /api/v1/auth/me
POST /api/v1/auth/logout
```

Trang thai hoan thanh:

- [ ] User collection trong MongoDB.
- [ ] Hash password.
- [ ] JWT access token.
- [ ] Role don gian: researcher, expert, enterprise, funder, admin.

### 9.2 User features

Co the them:

```http
GET /api/v1/users/me/history
POST /api/v1/users/me/favorites
DELETE /api/v1/users/me/favorites/{item_id}
```

Trang thai hoan thanh:

- [ ] Luu lich su recommendation.
- [ ] Luu favorite.
- [ ] Frontend co trang history/favorites.

## 10. Phase 8 - Bao cao va bao ve

Muc tieu: bien he thong thanh cau chuyen de bao ve tot.

### 10.1 Noi dung bao cao can co

1. Ly do chon de tai.
2. Bai toan recommendation trong he sinh thai R&D.
3. Thiet ke du lieu MongoDB.
4. Thiet ke Knowledge Graph trong Neo4j.
5. Phuong phap PGPR.
6. XAI explanation.
7. Thiet ke backend API.
8. Thiet ke frontend.
9. Thuc nghiem va danh gia.
10. Ket qua, han che, huong phat trien.

### 10.2 So do can co

- Architecture diagram.
- Data pipeline diagram.
- Knowledge Graph schema.
- PGPR training/inference pipeline.
- API flow.
- Frontend screen flow.

### 10.3 Kich ban demo

1. Mo frontend.
2. Kiem tra system health.
3. Chon mot project demo.
4. Goi y experts.
5. Mo detail mot expert.
6. Xem reasoning paths.
7. Sinh explanation.
8. Chuyen sang project overview.
9. Show bang evaluation.
10. Ket luan PGPR co kha nang goi y va giai thich.

## 11. Definition of Done

Du an duoc xem la hoan thien so bo khi:

- [x] Kien truc PGPR tach repository Neo4j (`PGPRGraphRepository`) â€” tai lieu: `KIEN_TRUC_DA_CHOT.md`.
- [x] Backend chay duoc local.
- [x] Frontend chay duoc local.
- [x] Frontend goi duoc API backend.
- [x] Co it nhat 3 demo case co ket qua dep.
- [x] Recommendation co score va explanation.
- [x] Reasoning paths hien thi duoc.
- [x] Co health API.
- [x] Co entity browser API.
- [x] Co project overview API.
- [ ] Deploy duoc frontend.
- [ ] Backend co endpoint public hoac demo duoc qua local/tunnel.
- [ ] Co bang evaluation baseline vs PGPR.
- [x] Co README huong dan chay (cap nhat phan `backend/` va test API).
- [ ] Co slide va kich ban bao ve.

## 12. Uu tien ngan han

Trong 1 den 2 ngay toi:

1. Tao health API.
2. Tao entity list/detail API.
3. On dinh recommendation policy API.
4. Tao project overview API.
5. Tao frontend MVP voi entity browser va recommendation form.
6. Chon 3 demo case.

Trong 3 den 5 ngay toi:

1. Them explanation API.
2. Them graph paths API.
3. Lam dep frontend recommendation detail.
4. Deploy frontend va backend ban dau.
5. Viet README chay local/deploy.

Trong 1 den 2 tuan toi:

1. Them evaluation pipeline.
2. Them baseline.
3. Tao bang metric.
4. Hoan thien bao cao va slide.
5. Neu con thoi gian moi them auth/history/favorite.

## 13. Checklist viec can lam tiep theo

Cap nhat sau khi da hoan thanh backend MVP va refactor runtime PGPR:

- Backend runtime recommendation da di theo luong `RecommendationService -> PGPRRecommender -> PGPRGraphRepository -> Neo4j`.
- Cac script build/train nhu `pgpr_kg.py`, `pgpr_train.py` tam thoi bo qua, khong nam trong runtime API.
- Viec tiep theo nen uu tien project overview page, frontend env config, deploy, evaluation va graph neighbors API.

### 13.1 Backend API con thieu

- [x] Tao endpoint chuan `POST /api/v1/explanations`.
- [x] Ho tro explanation mode: `rule`, `llm`, `auto`.
- [x] Dam bao explanation router di qua service, khong goi explainer truc tiep.
- [x] Tao endpoint `GET /api/v1/graph/paths`.
- [x] Tao `GraphService` de lay reasoning paths.
- [x] Graph paths API dung `PGPRGraphRepository`, khong query Neo4j trong router.
- [x] Response graph paths co `path`, `score`, `relations`, `entities`, `path_length`.
- [x] Test explanation va graph paths bang `TestClient`.
- [x] Them FastAPI lifespan/shutdown de dong `PGPRGraphRepository` khi app dung.
- [x] Cache explanation trong `RecommendationService`, co `force_refresh`.

### 13.2 Frontend MVP

- [x] Tao thu muc `frontend/`.
- [x] Tao Next.js app tu Firebase Studio.
- [ ] Tao file `frontend/.env.example` voi `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`.
- [x] Tao API client dung chung.
- [x] Tao dashboard health goi `/api/v1/health`.
- [x] Tao entity browser cho projects/experts/funders/enterprises.
- [x] Tao search va detail panel cho entity.
- [x] Tao recommendation workspace goi `/api/v1/recommendations/policy`.
- [ ] Tao project overview page goi `/api/v1/recommendations/projects/{project_id}/overview`.
- [x] Tao recommendation detail drawer/modal.
- [x] Hien score, confidence, explanation va reasoning paths.
- [x] Them loading/error/empty states.
- [x] Them quick demo buttons cho cac case da chon.

### 13.3 Demo cases va bao ve

- [x] Tao file `DEMO_CASES.md`.
- [x] Chon 3 den 5 case co ket qua dep.
- [x] It nhat co Project -> Expert.
- [x] It nhat co Project -> Funder.
- [x] It nhat co Project -> Enterprise.
- [ ] Them 1 case Expert -> Project hoac Enterprise -> Expert neu dep.
- [x] Ghi source_id, source_name, target_type cho tung case.
- [x] Ghi request body/API endpoint cho tung case.
- [ ] Ghi top recommendations ky vong.
- [ ] Ghi reasoning paths dep cho tung case.
- [ ] Ghi explanation ngan gon de dua vao bao cao.
- [ ] Chup screenshot frontend cho dashboard/entity/recommendation/detail.
- [ ] Viet demo script tung buoc.

### 13.4 Deploy

- [x] Tao `backend/requirements.txt`.
- [x] Tao `backend/.env.example` khong chua password that.
- [ ] Tao `frontend/.env.example`.
- [ ] Cau hinh CORS theo frontend URL khi deploy.
- [ ] Tao production command cho backend.
- [x] Chay frontend production build thanh cong.
- [ ] Chon phuong an deploy frontend: Vercel, Netlify, static hosting.
- [ ] Chon phuong an deploy backend: Render, Railway, VPS, hoac local tunnel.
- [ ] Neu Redis khong co tren deploy, dam bao Redis optional khong lam fail.
- [ ] Test `/api/v1/health` sau deploy.
- [ ] Test `/api/v1/recommendations/policy` sau deploy.
- [ ] Ghi huong dan deploy/local run vao README.

### 13.5 Evaluation

- [ ] Tao thu muc `backend/evaluation/`.
- [ ] Viet metrics: Precision@K.
- [ ] Viet metrics: Recall@K.
- [ ] Viet metrics: HitRate@K.
- [ ] Viet metrics: NDCG@K.
- [ ] Tao random baseline.
- [ ] Tao content-based baseline.
- [ ] Tao graph heuristic baseline.
- [ ] Chay PGPR proposed method.
- [ ] Tao ground truth tu relationship co san trong Neo4j.
- [ ] Chay evaluation cho Project -> Expert truoc.
- [ ] Mo rong evaluation cho Project -> Funder hoac Expert -> Project neu con thoi gian.
- [ ] Luu ket qua JSON/CSV.
- [ ] Tao bang markdown ket qua.
- [ ] Dua bang metric vao bao cao/slide.

### 13.6 Cleanup ky thuat

- [ ] Kiem tra lai `git status`, phan biet file code va file artifact.
- [ ] Can nhac dua `scripts/api_test_results.json` vao `.gitignore` neu chi la ket qua chay local.
- [ ] Kiem tra `.env` khong bi commit.
- [ ] Kiem tra cac file `.pt`, `.npy`, `triples.txt` co nen commit hay khong.
- [ ] Sua comment/tai lieu bi mojibake neu co thoi gian.
- [ ] Bo hoac danh dau cac script patch tam thoi trong `backend/scripts/`.
- [ ] Them README section: "Architecture", "Run local", "Test API", "Known limitations".

### 13.7 Tuy chon sau MVP

- [ ] Auth register/login/logout neu con thoi gian.
- [ ] Recommendation history.
- [ ] Favorite recommendations.
- [ ] Admin page xem health/evaluation.
- [ ] Graph neighbor visualization day du.
