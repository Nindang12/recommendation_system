# Tong quan he thong dang build

> Cap nhat: 2026-05-26  
> Muc dich: ghi lai nhung gi da hieu ve he thong, phan da lam duoc, phan chua lam duoc va cac viec nen uu tien tiep theo.  
> Doi chieu code va `NHAT_KY_REFACTOR_PGPR.md` (den Phase 8).

## 1. He thong nay la gi

Day la he thong goi y ket noi trong linh vuc R&D, su dung:

- MongoDB de luu du lieu nghiep vu goc.
- Neo4j de luu Knowledge Graph.
- PGPR lam phuong phap recommendation chinh.
- XAI de giai thich vi sao he thong dua ra goi y.
- FastAPI lam backend API.
- Next.js lam frontend web.

Muc tieu cua he thong la ho tro ket noi cac ben trong he sinh thai nghien cuu va doi moi sang tao:

- Goi y expert phu hop cho mot project.
- Goi y funder phu hop cho mot project.
- Goi y enterprise phu hop cho mot project.
- Goi y project tuong tu.
- Goi y project cho expert.
- Giai thich ket qua goi y bang reasoning paths tren Knowledge Graph.
- Cho nguoi dung dang ky, quan ly ho so, tao project va xem project cua minh.

Bon doi tuong chinh da chot:

- Expert
- Enterprise
- Funder
- Project

Luu y quan trong: he thong khong tach role `researcher` rieng. Nguoi nghien cuu, giang vien, chuyen gia ca nhan deu nam trong nhom `expert`.

## 2. Kien truc da chot

Kien truc runtime hien tai duoc chot theo huong tach ro router, service, repository va recommendation engine:

```text
Frontend
   |
   v
FastAPI Router
   |
   v
Service Layer
   |------------------|----------------------|------------------|
   |                  |                      |                  |
   v                  v                      v                  v
AuthService    RecommendationService   GraphService      EntityService
   |                  |                      |
   |                  v                      v
   |           PGPRRecommender         PGPRGraphRepository
   |                  |                      |
   v                  v                      v
EntityMatchingService              Neo4j (KG + PGPR queries)
   |
   v
ProvisionalKGSyncService
   |
   v
AuthRepository / MongoDBRepository
   |
   v
MongoDB
```

Y nghia:

- Frontend chi goi API, khong xu ly logic PGPR.
- Router chi nhan request, validate input va tra response.
- Service layer xu ly business logic.
- `MongoDBRepository` / `AuthRepository` doc/ghi du lieu tu MongoDB.
- `PGPRRecommender` la recommendation engine.
- `PGPRGraphRepository` la adapter/repository rieng de PGPR, graph API va Provisional KG Sync truy van Neo4j.
- PGPR runtime khong goi Neo4j driver truc tiep (da refactor xong — xem `NHAT_KY_REFACTOR_PGPR.md`).
- `EntityMatchingService` chay truoc khi sync de giam duplicate.
- `ProvisionalKGSyncService` upsert entity user-created vao Neo4j voi trang thai chua xac thuc.
- Cac script build/train/offline (`pgpr_kg.py`, `pgpr_train.py`) van co the truy cap Neo4j truc tiep, nhung khong tinh la runtime API.

## 3. Backend hien tai da co

Backend dung FastAPI, to chuc theo cac nhom chinh:

```text
backend/
  api/
    deps.py
    v1/endpoints/
  services/
  repositories/
  models/
  pgpr/
```

### 3.1 API da co

Health:

- `GET /api/v1/health`

Entities:

- `GET /api/v1/entities/projects`
- `GET /api/v1/entities/experts`
- `GET /api/v1/entities/funders`
- `GET /api/v1/entities/enterprises`
- `GET /api/v1/entities/{entity_type}/{entity_id}`

Recommendations:

- `POST /api/v1/recommendations/policy` — ho tro `mode` (`public` | `personal` | `admin_debug`) va `current_user_id`
- `POST /api/v1/recommendations/projects/{project_id}/overview`
- `POST /api/v1/recommendations/experts` — route legacy, tuong thich
- `POST /api/v1/recommendations/funders`
- `POST /api/v1/recommendations/explain` — route legacy explain

Explanations:

- `POST /api/v1/explanations` — mode `rule` / `llm` / `auto`, `force_refresh`

Graph:

- `GET /api/v1/graph/paths` — ho tro `mode` va `current_user_id`
- `GET /api/v1/graph/entities/{entity_type}/{entity_id}/neighbors`

Evaluation:

- `GET /api/v1/evaluation/summary` — MVP: tom tat smoke test, chua phai pipeline offline

Auth/User/Project:

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `GET /api/v1/users/me`
- `PUT /api/v1/users/me`
- `POST /api/v1/users/me/projects`
- `GET /api/v1/users/me/projects`

Admin (MVP, chua bao ve role admin):

- `POST /api/v1/admin/kg-sync/{entity_type}/{entity_id}/retry`
- `POST /api/v1/admin/entities/{entity_type}/{entity_id}/verify`
- `POST /api/v1/admin/entities/{entity_type}/{entity_id}/reject`
- `POST /api/v1/admin/entities/{entity_type}/{entity_id}/disable-kg`
- `POST /api/v1/admin/entities/{entity_type}/{source_entity_id}/merge`

### 3.2 Service layer da co

| Service | Vai tro |
|---------|---------|
| `HealthService` | Kiem tra MongoDB, Neo4j, Redis, PGPR |
| `EntityService` | Danh sach va chi tiet entity |
| `RecommendationService` | PGPR, XAI, cache explanation, provisional rules |
| `GraphService` | Graph paths va neighbors, loc theo mode |
| `EvaluationService` | Tom tat MVP tu artifact test |
| `AuthService` | Register, login, profile, project; dieu phoi matching + sync |
| `EntityMatchingService` | Duplicate detection MVP truoc sync |
| `ProvisionalKGSyncService` | Sync entity moi vao Neo4j, verify/reject/disable/merge |
| `AdminAuditLogService` | Ghi audit log cho action admin |

### 3.3 Repository layer da co

| Repository | Vai tro |
|------------|---------|
| `MongoDBRepository` | Entity list/detail tu MongoDB |
| `PGPRGraphRepository` | Neo4j cho PGPR, graph API, provisional upsert/filter |
| `AuthRepository` | Account, profile, project, entity user-created |
| `Neo4jRepository` | Neo4j tong quat neu can cho luong khac |

## 4. PGPR va Recommendation hien tai

PGPR la phuong phap recommendation chinh cua he thong.

Da lam duoc:

- Load PGPR policy/data.
- Recommendation runtime di qua `RecommendationService -> PGPRRecommender -> PGPRGraphRepository -> Neo4j`.
- Ho tro nhieu cap source/target (15 cap trong test policy).
- Response recommendation co:
  - `id`, `name`, `score`, `reasoning_paths`, `path_diversity`, `explanation`
  - Them cho Provisional KG: `raw_score`, `final_score`, `stored_trust_weight`, `runtime_source_weight`, `trust_override_reason`, `uses_provisional_data`, `provisional_nodes_count`, `data_quality_level`, `data_quality_notes`, `verification_badges`

Reasoning paths co them:

- `relations`, `node_types`, `entity_names`, `entities`, `score`, `length`

Provisional rules (backend):

- `mode=public`: an target `owner_only` cua nguoi khac, an target `recommendable_as_target=false`, loc rejected/disabled/hidden.
- `mode=personal`: owner xem duoc entity `owner_only` cua minh; `runtime_source_weight=1.0` khi source la current user.
- `final_score = raw_score * runtime_source_weight * target_weight` (khong ghi de stored trust_weight).
- Mot so filter visibility/participation trong Cypher query path (`PGPRGraphRepository`).

Luu y:

- Dashboard frontend hien chua truyen `mode` / `current_user_id` — mac dinh dung `public`.
- Frontend chua hien badge/can bao provisional tren ket qua recommendation.

## 5. XAI hien tai

Da co API:

```http
POST /api/v1/explanations
```

Mode ho tro: `rule`, `llm`, `auto`.

Da lam duoc:

- Rule-based explanation chay duoc; LLM optional, fallback rule khi loi.
- Cache explanation trong `RecommendationService` (khong cache o frontend).
- `force_refresh` de tao lai giai thich.
- Rule explanation them canh bao khi `uses_provisional_data=true`.
- Frontend: nut Giai thich chi tiet, Tao lai giai thich, confidence card, reasoning paths mini graph.

Chua lam tren UI:

- Badge unverified/verified tren tung node trong reasoning path graph.

## 6. Graph visualization hien tai

Da co graph neighbors UI (`/graph/neighbors`).

Tinh nang da co:

- Node-edge, mau theo type, keo tha, zoom, reset layout, click/hover, collision.
- Graph API ho tro loc theo `mode` (public/personal/admin_debug).

Han che:

- Layout custom SVG/force, chua dung engine chuyen dung.
- Graph lon van de roi mat.
- Frontend graph page chua expose chon mode personal/admin.

## 7. Frontend hien tai da co

Frontend dung Next.js.

| Trang | Trang thai |
|-------|------------|
| `/dashboard` | Recommendation + XAI demo |
| `/search` | Entity browser |
| `/entities/[type]/[id]` | Chi tiet + recommendation panel |
| `/projects/[id]/overview` | 4 nhom goi y |
| `/graph/neighbors` | Graph visualization |
| `/evaluation` | Tom tat MVP |
| `/auth/login`, `/auth/register` | Auth MVP |
| `/auth/onboarding` | Co file, chua day du flow |
| `/profile` | Verification + KG status, duplicate warning |
| `/projects/create`, `/projects/my` | Project user + badge KG status |

Auth MVP:

- Token trong `localStorage`, gui `Authorization: Bearer ...`.
- Sau register redirect ve `/profile` (khong con `/dashboard`).
- Chua production-ready (xem muc 11.3).

## 8. Register, Provisional KG Sync va trang thai du lieu

### 8.1 Luong register hien tai

```text
POST /api/v1/auth/register
  -> tao app_users (account_verification_status = email_unverified)
  -> EntityMatchingService.match_user_entity()
  -> tao hoac link entity trong experts/enterprises/funders
  -> ProvisionalKGSyncService.sync_entity_as_unverified() (neu khong merge_required)
  -> tra linked_entity + match_status trong response
```

### 8.2 Trang thai da co tren MongoDB / Neo4j

| Field | Y nghia ngan |
|-------|----------------|
| `account_verification_status` | Trang thai account (`email_unverified`, ...) |
| `entity_verification_status` | `unverified`, `verified`, `rejected`, ... |
| `kg_sync_status` | `not_synced`, `syncing`, `synced_unverified`, `synced_verified`, `merge_required`, `sync_failed`, `disabled`, `rejected`, ... |
| `visibility` | `limited`, `public`, `private`, `hidden`, `disabled` |
| `participation_scope` | `owner_only`, `public`, `disabled` |
| `allow_as_source` | Duoc lam source recommendation |
| `recommendable_as_target` | Duoc recommend lam target (public) |
| `allow_as_intermediate_node` | Duoc nam giua path |
| `trust_weight` | He so tin cay (0.5 unverified, 1.0 verified) |
| `duplicate_candidates` | Danh sach candidate khi weak match |
| `claim_status` | `pending_review` khi `merge_required` |
| `match_status` | `created_new`, `matched_existing`, `merge_required` |

Entity moi khi register (no match):

- `source = user_registration`
- `entity_verification_status = unverified`
- `kg_sync_status`: `not_synced` -> `syncing` -> `synced_unverified` (hoac `sync_failed` neu Neo4j loi)
- `participation_scope = owner_only`, `recommendable_as_target = false` (chua public rong rai)
- Sync sang Neo4j qua `upsert_provisional_entity` + topic tu `research_topics` chuan

### 8.3 Duplicate matching MVP (da co backend)

| Ket qua | Hanh vi |
|---------|---------|
| Strong match (email, ORCID, website/domain, ...) | Link entity cu, khong tao record moi |
| Weak match (ten tuong tu + org) | Tao entity moi, `kg_sync_status = merge_required`, `duplicate_candidates`, khong sync Neo4j ngay |
| No match | Tao entity moi, sync `synced_unverified` |

Chua co:

- API/UI **claim entity** (chi co field `claim_status`).
- Match phone rieng biet nhu ke hoach day du.
- Admin UI de review/merge — chi co Admin API + audit log.

### 8.4 Create project

```text
POST /api/v1/users/me/projects
  -> luu MongoDB (source = user_created, status unverified)
  -> ProvisionalKGSyncService.sync_entity_as_unverified("project", ...)
```

Project moi co the vao KG voi `synced_unverified`, owner_only, dung lam source trong personal mode.

### 8.5 Admin API (backend MVP)

Da co verify / reject / disable-kg / merge / retry-sync + `AdminAuditLogService`.

Han che:

- **Chua kiem tra role admin** — moi user co token deu goi duoc endpoint.
- **Chua co trang admin** tren frontend.
- Merge MVP: soft-disable source, relink user sang target; chua chuyen het relationship phuc tap trong KG.

Chi tiet thiet ke: `KE_HOACH_PROVISIONAL_KG_SYNC.md`, nhat ky trien khai: `NHAT_KY_REFACTOR_PGPR.md` Phase 7–8.

## 9. Chu de nghien cuu hien tai

Topic chuan (option tren form register):

- AI trong y te, Computer Vision, Machine Learning, Deep Learning, Xu ly ngon ngu tu nhien, Internet of Things, Khoa hoc du lieu, Knowledge Graph, Robotics, Nang luong tai tao, San xuat thong minh, An toan thong tin

Option `Khac` -> `custom_research_topics`:

- Luu tren MongoDB va property Neo4j node.
- **Khong** tao `ResearchTopic` relationship tu custom topic (chi `research_topics` chuan duoc `upsert_topic_relationships`).
- Can admin map sang topic chuan truoc khi co tac dong KG manh hon.

## 10. Tong hop nhung gi da lam duoc

### Backend

- [x] Tach Router / Service / Repository
- [x] Health, Entity, Recommendation, Explanation, Graph, Evaluation API
- [x] Auth + User profile + User projects API
- [x] PGPR runtime qua `PGPRGraphRepository` (khong query Neo4j truc tiep trong recommender)
- [x] Reasoning paths day du node/entity names
- [x] Explanation cache service layer + `force_refresh`
- [x] Provisional KG Sync: register + create project -> Neo4j `synced_unverified`
- [x] Entity matching MVP (strong/weak/no match)
- [x] Provisional recommendation rules (`mode`, trust, visibility)
- [x] Graph API loc theo mode
- [x] Admin API verify/reject/disable/merge/retry + audit log
- [x] MongoDB unique index `app_users.email`

### Frontend

- [x] Dashboard, Search, Entity detail, Project overview, Graph neighbors, Evaluation
- [x] Auth login/register/logout, Profile, Create/My projects
- [x] Profile + My Projects hien verification / KG sync status
- [x] Register redirect `/profile`, research topic options + custom
- [x] XAI dialog, confidence, reasoning paths mini graph

### Tai lieu

- `KIEN_TRUC_DA_CHOT.md`, `NHAT_KY_REFACTOR_PGPR.md`, `KE_HOACH_PROVISIONAL_KG_SYNC.md`
- `KE_HOACH_HOAN_THIEN_HE_THONG.md`, `KE_HOACH_UPGRADE_UI_AUTH_VERIFICATION.md`
- `CHECKLIST_REFACTOR_KIEN_TRUC_PGPR.md`, `DEMO_CASES.md`
- `TONG_QUAN_HE_THONG_HIEN_TAI.md` (file nay)

## 11. Nhung gi chua lam hoac chua day du

### 11.1 Verification va duplicate (con thieu)

Da co (MVP):

- Field verification/sync tren user va entity
- Duplicate matching email/identifier + fuzzy ten
- Admin verify/reject/disable/merge qua API

Chua day du:

- Claim entity (API + UI)
- Admin role protection tren API
- Admin review dashboard UI
- Duplicate candidate UI cho user
- Match phone, quy trinh review email account
- Migration/backfill field moi cho data crawl cu

### 11.2 Provisional KG Sync (con thieu)

Da co (MVP):

- Sync entity/project moi vao Neo4j
- Trang thai `synced_unverified`, retry sync, Neo4j constraints co ban
- Topic relationship tu `research_topics` chuan

Chua day du:

- Admin UI danh sach pending review / sync_failed
- Sync skill/location relationship khi verified
- Test tu dong day du (checklist Phase I trong ke hoach)
- Dam bao 100% entity cu trong MongoDB da co field/status moi

### 11.3 Auth production

Chua co: JWT chuan + expire, refresh token, HttpOnly cookie, email verification, password reset, phan quyen admin ro rang.

### 11.4 UI web chinh thuc

Chua co day du:

- Landing page chinh thuc
- Onboarding theo role hoan chinh
- Claim entity UI
- Admin dashboard
- Recommendation `mode=personal` tren dashboard
- Canh bao provisional / badge tren ket qua goi y va XAI path
- Visual system dong nhat toan bo web

### 11.5 Evaluation nghien cuu

`GET /evaluation/summary` chi la MVP (doc `api_test_results.json` + placeholder baseline).

Chua co: ground truth, baseline that, Precision@K, Recall@K, NDCG@K, MRR, bao cao thuc nghiem.

### 11.6 Deploy

Chua co: production config day du, Docker compose production, deploy URL public, logging/monitoring.

## 12. Rui ro hien tai

### 12.1 Sync that bai hoac lech MongoDB–Neo4j

Neu Neo4j down hoac loi Cypher: register van 200 nhung `kg_sync_status = sync_failed`, entity khong vao KG.

Can retry qua Admin API hoac xu ly lai sync.

### 12.2 Duplicate entity

Weak match tao entity moi + `merge_required` — van co nguy co 2 record cho cung nguoi neu admin chua merge.

Strong match giam rui ro nhung phu thuoc data crawl co email/identifier khop.

### 12.3 Entity unverified trong public recommendation

Da co filter/limit nhung chua hoan hien tren moi query path.

User moi co the dung personal mode (backend) nhung UI chua expose.

### 12.4 Admin API khong bao ve role

Bat ky user dang nhap co the goi verify/merge — rui ro cao neu deploy public.

### 12.5 Topic custom

Custom topic luu property, khong thanh ResearchTopic — van can quy trinh map thu cong.

### 12.6 Auth MVP

Token localStorage khong phu hop production.

## 13. Viec nen lam tiep theo theo thu tu uu tien

### Uu tien 1: Dong bo bao mat va admin

- Them role `admin` + bao ve Admin API
- Trang admin: pending review, sync_failed, verify/reject/merge/retry
- (Tuy chon) Claim entity API + UI

### Uu tien 2: Hoan thien UX provisional

- Dashboard: `mode` personal/public, hien `uses_provisional_data` / badges
- Graph page: chon mode
- XAI path: badge unverified tren node

### Uu tien 3: Cung co KG Sync

- Test checklist Phase I (`KE_HOACH_PROVISIONAL_KG_SYNC.md`)
- Backfill status cho entity crawl cu
- Skill/location sync khi verified

### Uu tien 4: Evaluation pipeline

- Ground truth, baseline, metrics, bang so sanh PGPR

### Uu tien 5: Auth production + Deploy

- JWT/cookie, CORS production, Docker, huong dan deploy

## 14. Ket luan hien trang

He thong da vuot xa muc demo API don gian:

- Core PGPR + XAI + graph + entity browser + auth/project MVP **chay duoc**.
- **Provisional KG Sync MVP** da co: entity user moi co the vao Neo4j voi `synced_unverified`, co matching duplicate co ban, co rule recommendation theo visibility/trust, co Admin API backend.

Diem manh cho do an: recommendation tren KG, giai thich path, tiep nhan du lieu moi co kiem soat tin cay.

Diem can lam tiep de “san pham hoan chien”:

- Admin UI + bao ve role
- Claim entity + review duplicate day du
- Frontend personal mode va canh bao provisional
- Evaluation that + deploy production

Noi ngan gon: **da co loi de demo recommendation voi du lieu moi trong KG**, nhung con thieu lop quan tri (admin UI, security), polish UI, evaluation va deploy de tro thanh do an/san pham hoan chinh.
