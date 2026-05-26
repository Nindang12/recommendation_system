# Nhat ky refactor PGPR theo kien truc da chot

Ngay: 2026-05-23

## Muc tieu

Tach truy cap Neo4j khoi `PGPRRecommender`, dat query vao `PGPRGraphRepository`, inject singleton qua `api/deps.py`, giu nguyen shape response API.

## Phase 0 - Khao sat (da lam)

Ket qua grep truoc refactor:

| File | GraphDatabase | driver.session | session.run |
|------|---------------|----------------|-------------|
| `pgpr_recommendation.py` | co | nhieu | nhieu |
| `pgpr_env.py` | co (fallback driver) | - | - |
| `pgpr_kg.py` | co (train/build KG) | co | co |
| `pgpr_train.py` | co | co | co |

Quyet dinh: refactor tap trung `pgpr_recommendation.py` + DI app; `pgpr_kg` / `pgpr_train` giu nguyen (training pipeline).

## Phase 1 - Tao PGPRGraphRepository

**File moi:** `backend/repositories/pgpr_graph_repo.py`

- `__init__(driver=None)` — inject driver hoac tu tao; co `_owns_driver`
- `close()`, `check_health()`, `run_read()`, `run_write()`
- Doc env qua `load_dotenv(find_dotenv())`: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`
- Return record dang `dict`

**Ham query da chuyen vao repository:**

- `find_reasoning_paths` (raw records, khong scoring)
- `get_expert_info`, `get_generic_entity_info`
- `get_expert_participant_ids`, `get_exclude_target_ids`
- `find_all_reachable_experts_batch`, `find_candidate_experts_simple`, `find_candidate_experts_generic`
- Toan bo `find_candidate_*` theo nhom Project / Expert / Enterprise / Funder (18 ham)

**Script ho tro:** `backend/scripts/build_pgpr_graph_repo.py` (trich xuat tu `pgpr_recommendation.py` goc git).

## Phase 2 - Inject PGPRGraphRepository vao PGPRRecommender

**File:** `backend/pgpr/pgpr_recommendation.py`

- Them tham so `graph_repo: Optional[PGPRGraphRepository] = None`
- `self.graph_repo = graph_repo or PGPRGraphRepository(driver=driver)`
- `self.driver = self.graph_repo.driver` (tam thoi cho `KGEnv`)
- `close()` goi `graph_repo.close()` khi owns driver
- Xoa `_shared_driver` va import `GraphDatabase` trong recommender

## Phase 3 - Dependency Injection

**File:** `backend/api/deps.py`

- Them `_pgpr_graph_repo` singleton
- Them `get_pgpr_graph_repo()`
- `get_pgpr_recommender()` inject `graph_repo=get_pgpr_graph_repo()`

## Phase 4-6 - Chuyen query

| Nhom | Trang thai |
|------|------------|
| Reasoning paths | `find_reasoning_paths` goi `graph_repo.find_reasoning_paths`, giu scoring/dedup trong recommender |
| Entity info | `get_expert_info`, `get_generic_entity_info` qua graph repo |
| Candidate queries | Tat ca `_find_candidate_*` da xoa khoi recommender; goi `self.graph_repo.find_candidate_*` |
| Exclude keys / participants | `get_exclude_target_ids`, `get_expert_participant_ids` |

**Kiem tra sau refactor** (`pgpr_recommendation.py`):

```text
GraphDatabase: khong con
driver.session: khong con
session.run: khong con
```

## Phase 7 - KGEnv

- `KGEnv.get_neighbors` van dung `kg.adj_list` (in-memory), khong query Neo4j tung buoc
- `KGEnv` nhan `driver=self.graph_repo.driver` tu recommender — hop le tam thoi theo checklist

## Phase 8 - Direct Neo4j trong PGPRRecommender

**Hoan thanh** — recommender khong con query Neo4j truc tiep.

## Phase 9 - Test da chay

### 9.1 Compile / import (truoc khi chay server)

```powershell
cd backend
python -m compileall main.py api repositories services pgpr
python -c "from main import app; print('app ok')"
```

Ket qua: **PASS** — compile pass, `from main import app` pass.

### 9.2 Test API recommendation (server dang chay)

**Dieu kien:**

- Server: `uvicorn main:app --host 127.0.0.1 --port 8000` (tu `backend/`)
- Thoi gian chay: `2026-05-23` (~18 giay cho 15 case policy + health/overview)
- Script: `backend/scripts/test_recommendation_api.py`
- Ket qua chi tiet JSON: `backend/scripts/api_test_results.json`

**ID mau lay tu Mongo (entity API):**

| Entity | ID |
|--------|-----|
| Project | `prj_001` |
| Expert | `exp_001` |
| Funder | `fnd_001` |
| Enterprise | `ent_001` |

#### Health / OpenAPI

| Endpoint | HTTP | Thoi gian | Ket qua |
|----------|------|-----------|---------|
| `GET /` | 200 | 82 ms | `status: ok` |
| `GET /api/v1/health` | 200 | 322 ms | mongodb, neo4j, redis: connected; pgpr: ready |
| `GET /openapi.json` | 200 | 26 ms | OpenAPI 3.1.0, co day du route recommendations/entities/health |

#### `POST /api/v1/recommendations/policy` (limit=3)

Tat ca **15/15 PASS** (HTTP 200, `count=3` moi case):

| Luong | Thoi gian | reasoning_paths | explanation (XAI) |
|-------|-----------|-----------------|-----------------|
| Project -> Expert | 3847 ms | co | co |
| Project -> Funder | 1637 ms | co | co |
| Project -> Enterprise | 1491 ms | co | co |
| Project -> Project | 656 ms | khong* | co |
| Expert -> Project | 1655 ms | co | co |
| Expert -> Funder | 370 ms | khong* | co |
| Expert -> Enterprise | 1428 ms | co | co |
| Expert -> Expert | 584 ms | co | co |
| Enterprise -> Expert | 1322 ms | co | co |
| Enterprise -> Project | 1424 ms | co | co |
| Enterprise -> Funder | 357 ms | khong* | co |
| Enterprise -> Enterprise | 243 ms | khong* | co |
| Funder -> Expert | 290 ms | khong* | co |
| Funder -> Project | 1420 ms | co | co |
| Funder -> Enterprise | 261 ms | khong* | co |

\* Mot so cap tra ve item co `id`, `name`, `score`, `explanation` nhung `reasoning_paths` rong/null — hop le voi policy rollout (khong phai loi HTTP). Can theo doi neu product yeu cau paths cho moi cap.

**Shape item mau (Project -> Expert, item dau):**

- `id`, `name`, `score` — co
- `reasoning_paths` — 3 phan tu (`path`, `score`, `length`)
- `path_diversity` — co (vd: 46)
- `explanation.natural_language`, `explanation.visualization` — co
- `metrics` — co (`h_index`, ...)

#### Endpoint bo sung

| Endpoint | HTTP | Thoi gian | Ghi chu |
|----------|------|-----------|---------|
| `POST /api/v1/recommendations/projects/prj_001/overview?limit=3` | 200 | 43 ms | `data`: experts(3), funders(3), enterprises(3), similar_projects(3); moi nhom co `reasoning_paths` |
| `POST /api/v1/recommendations/experts` (`project_id=prj_001`) | 200 | 5 ms | `count=3`; tuong thich route cu |

#### Tong ket Phase 9.2

- **Policy matrix 15 cap entity: PASS**
- **Overview + legacy /experts: PASS**
- **Health + OpenAPI: PASS**
- Refactor `PGPRGraphRepository` khong lam vo API recommendation sau khi test thuc te.

## Phase 10 - Tai lieu kien truc

**Da cap nhat (2026-05-23):**

- [x] `KIEN_TRUC_DA_CHOT.md` — trang thai refactor da xong, phan biet repository, DI, huong dan test API
- [x] `KE_HOACH_HOAN_THIEN_HE_THONG.md` — danh dau refactor + test 15/15 trong Phase 3.4
- [x] `README.md` — cau truc `backend/`, chay API, test script, link tai lieu

## File thay doi / tao moi

| File | Hanh dong |
|------|-----------|
| `backend/repositories/pgpr_graph_repo.py` | **Tao moi** |
| `backend/pgpr/pgpr_recommendation.py` | Refactor lon |
| `backend/api/deps.py` | Them singleton graph repo |
| `backend/scripts/build_pgpr_graph_repo.py` | Script trich xuat (tuy chon) |
| `backend/scripts/patch_pgpr_recommendation.py` | Script patch (tuy chon) |
| `backend/scripts/restore_pgpr_methods.py` | Script khoi phuc policy methods (tuy chon) |
| `backend/scripts/test_recommendation_api.py` | Script test API (tai su dung) |
| `backend/scripts/api_test_results.json` | Ket qua test API lan chay 2026-05-23 |
| `NHAT_KY_REFACTOR_PGPR.md` | **Nhat ky nay** |

## Phase 2 backend — theo KE_HOACH (2026-05-23)

Trien khai muc **13.1 Backend API con thieu**:

| Hang muc | File / endpoint | Trang thai |
|----------|-----------------|------------|
| `POST /api/v1/explanations` | `api/v1/endpoints/explanations.py` | **Xong** — mode `rule` / `llm` / `auto` qua `RecommendationService.explain_recommendation` |
| `GET /api/v1/graph/paths` | `api/v1/endpoints/graph.py` + `services/graph_service.py` | **Xong** — Cypher qua `find_reasoning_paths_cypher` → `PGPRGraphRepository` |
| Lifespan dong graph repo | `main.py` `lifespan` | **Xong** — `get_pgpr_graph_repo().close()` on shutdown |
| `requirements.txt` | `backend/requirements.txt` | **Xong** |
| `.env.example` | `backend/.env.example` | **Xong** (placeholder, khong password that) |
| Demo cases | `DEMO_CASES.md` | **Xong** — 4 case + ID mau |
| TestClient | chay local | health 200, graph paths count=3, explain rule 200 |

**Ghi chu ky thuat:**

- Them `PGPRRecommender.find_reasoning_paths_cypher()` — path Cypher cho Graph API (khong bi `POLICY_ONLY_MODE` chan nhu `find_reasoning_paths`).
- Route cu `POST /api/v1/recommendations/explain` van hoat dong; mac dinh `mode=auto` (LLM + fallback rule).
- Frontend MVP (muc 13.2) **chua lam** trong dot nay.

## Phase 3 frontend MVP va XAI UX (2026-05-24)

Trien khai frontend Firebase Studio/Next.js thanh giao dien demo phu hop voi backend hien tai.

### Frontend da sua

| Hang muc | File | Trang thai |
|----------|------|------------|
| Root route vao dashboard | `frontend/src/app/page.tsx` | **Xong** - bo redirect sang login |
| Navigation | `frontend/src/components/navigation/navbar.tsx` | **Xong** - branding R&D Recommendation, bo auth/sign out khoi luong demo |
| API client | `frontend/src/lib/api.ts` | **Xong** - health, entities, recommendation, explanations, graph paths |
| Dashboard | `frontend/src/app/dashboard/page.tsx` | **Xong** - health, entity shortcuts, recommendation workspace, quick demo, result cards |
| Entity browser | `frontend/src/app/search/page.tsx` | **Xong** - tabs project/expert/funder/enterprise, search, goi API entity list |
| Entity detail | `frontend/src/app/entities/[type]/[id]/page.tsx` | **Xong** - goi API detail, metadata formatter, recommendation panel |
| Build script Windows | `frontend/package.json` | **Xong** - doi `build` thanh `next build` |
| Calendar type fix | `frontend/src/components/ui/calendar.tsx` | **Xong** - tuong thich `react-day-picker` hien tai |

### XAI detail flow da sua

- Ket qua recommendation tren dashboard chi hien preview ngan, score, path count, diversity.
- Nut **Giai thich chi tiet** goi that `POST /api/v1/explanations`.
- Dialog XAI hien:
  - natural language explanation
  - confidence dang card, khong hien JSON tho
  - reasoning paths dang path cards/chips, khong hien JSON tho
  - visualization text da format lai
- Nut **Tao lai giai thich** gui `force_refresh=true`.

### Cache XAI da chuyen dung kien truc service layer

Quyet dinh: khong de frontend quyet dinh cache nghiep vu XAI. Cache explanation nam trong backend `RecommendationService`.

Luong hien tai:

```text
Frontend
  -> POST /api/v1/explanations
  -> RecommendationService.explain_recommendation()
  -> core.cache
  -> PGPRExplainer / LLM fallback
```

**File backend da sua:**

| File | Noi dung |
|------|----------|
| `backend/services/recommendation_service.py` | Them cache-aside cho `explain_recommendation`, cache key, `_cache` metadata, `force_refresh` |
| `backend/models/schemas.py` | Them `force_refresh: bool = False` vao `ExplainRecommendationRequest` |
| `backend/api/v1/endpoints/explanations.py` | Truyen `force_refresh` xuong service |

**Cache key mau:**

```text
explanation:vi:auto:project:prj_001:expert:exp_002
```

**Kiem tra cache service:**

```json
{
  "first_hit": false,
  "second_hit": true,
  "key": "explanation:vi:rule:project:prj_001:expert:exp_002"
}
```

### Kiem tra da chay

```powershell
cd frontend
npm.cmd run typecheck
npm.cmd run build
```

Ket qua: **PASS**.

```powershell
cd backend
python -m compileall services models api
```

Ket qua: **PASS**.

## Sua loi P1 (2026-05-23, review sau refactor)

| Van de | Sua |
|--------|-----|
| `find_all_reachable_experts_batch` goi `_find_candidate_experts_generic(session, ...)` khong ton tai | Doi thanh `self.find_candidate_experts_generic(project_id, max_depth=...)` |
| `KGEnv.close()` dong driver inject tu `graph_repo` (singleton) | Them `KGEnv._owns_driver`; chi `driver.close()` khi env tu tao driver |

## Luu y / viec con lai

1. ~~Chay test API day du khi Neo4j/Mongo san sang.~~ **Da xong** — xem Phase 9.2.
2. ~~Cap nhat `KIEN_TRUC_DA_CHOT.md`, `README.md`.~~ **Da xong** — xem Phase 10.
3. `pgpr_kg.py`, `pgpr_train.py` van truy cap Neo4j truc tiep (training) — ngoai pham vi dot refactor nay.
4. ~~Dong app sach bang lifespan shutdown FastAPI.~~ **Da xong**.
5. Frontend da co MVP local, nhung chua deploy.
6. Evaluation pipeline va graph neighbors API van chua lam.

## So do sau refactor

```text
Frontend -> FastAPI Router -> Service Layer
                                    |
                    +---------------+---------------+
                    |                               |
            MongoRepository              PGPRRecommender / XAI
                    |                               |
               MongoDB                    PGPRGraphRepository
                                                    |
                                                Neo4j
```

## Phase 4 - Bo sung UI web, auth, project va graph UX (2026-05-24 den 2026-05-25)

Sau Phase 3, he thong duoc mo rong tu frontend demo recommendation thanh giao dien web co luong nguoi dung co ban.

### 4.1 Auth va user flow MVP

Da them/cap nhat cac luong:

| Hang muc | Trang thai | Ghi chu |
|---|---|---|
| Login | **Da lam** | Frontend goi backend auth API |
| Register | **Da lam** | Role chi con `expert`, `enterprise`, `funder` |
| Logout | **Da lam** | Stateless token, frontend xoa token |
| Profile page | **Da lam** | User xem/sua thong tin ca nhan |
| Create Project | **Da lam** | User tao project cua minh |
| My Projects | **Da lam** | User xem danh sach project da tao |
| Navbar theo auth state | **Da lam** | Hien login/profile/logout tuy trang thai |

Quyet dinh nghiep vu da chot:

- He thong phuc vu 4 doi tuong chinh:
  - Expert
  - Enterprise
  - Funder
  - Project
- Khong tao role `researcher` rieng.
- Researcher/giang vien/chuyen gia ca nhan nam chung trong `expert`.

### 4.2 Register tao entity nghiep vu

Khi user register:

```text
POST /api/v1/auth/register
-> tao account trong app_users
-> tao entity theo role trong experts/enterprises/funders
-> linked_entity tra ve frontend
```

Trang thai truoc khi co Provisional KG Sync:

- Entity moi duoc tao trong MongoDB.
- Entity co `source = user_registration`.
- Entity co `kg_sync_status = pending_kg_sync`.
- Entity chua co duplicate matching.
- Entity chua co verification status day du.
- Entity chua sync chinh thuc sang Neo4j.

### 4.3 Research topic option

Da doi field huong nghien cuu tu input tu do sang option co san.

Topic chuan:

- AI trong y te
- Computer Vision
- Machine Learning
- Deep Learning
- Xu ly ngon ngu tu nhien
- Internet of Things
- Khoa hoc du lieu
- Knowledge Graph
- Robotics
- Nang luong tai tao
- San xuat thong minh
- An toan thong tin

Da bo sung option `Khac`:

- Topic chuan luu vao `research_interests` / `research_topics`.
- Topic khac luu vao `custom_research_topics`.
- Quyet dinh sau nay: custom topic khong dua thang vao KG neu chua review/map.

### 4.4 Project Overview page

Da bo sung trang overview project:

```http
POST /api/v1/recommendations/projects/{project_id}/overview
```

Frontend hien 4 nhom:

- experts
- funders
- enterprises
- similar projects

Muc tieu: dashboard/project detail co the demo dep hon thay vi chi goi tung recommendation rieng le.

### 4.5 Graph visualization UI

Da nang cap graph neighbors UI theo huong gan voi Neo4j Browser hon.

Da lam:

- Graph node-edge dang Knowledge Graph.
- Mau node theo type.
- Zoom in/out.
- Reset layout.
- Keo tha node.
- Click node hien thong tin chi tiet.
- Hover node hien ten day du.
- Them collision/relaxation de node giam de len nhau.
- Khi keo node, node lien ket bi keo nhe theo nhu hieu ung day thun.
- Results overview hien count theo node type va relationship type.

Han che con lai:

- Chua manh bang Neo4j Browser.
- Layout van la custom SVG/force logic.
- Neu graph qua lon van co the roi mat.

### 4.6 Sua UI metadata va XAI reasoning paths

Da sua nhieu loi hien thi:

- Metadata khong con show JSON tho.
- Nested metadata duoc format lai thanh key/value de doc hon.
- Sua loi table/card bi tran width.
- Dinh dang datetime de de nhin hon.
- Confidence khong con hien JSON, da thanh card.
- Reasoning paths khong con hien relation text thuan, da doi sang mini node-edge graph.
- Source/evidence/target hien ro hon.
- Hover node de xem ten day du.
- Xoa phan visualization text vi gay roi UI.

Ly do phai sua backend:

- Reasoning path ban dau chi co relation names.
- Frontend khong the hien evidence node that.
- Da sua PGPR recommendation de `reasoning_paths` tra them:
  - `relations`
  - `node_types`
  - `entity_names`
  - `entities`

## Phase 5 - Tai lieu tong quan va ke hoach UI/Auth/Verification (2026-05-25)

### 5.1 Tao/cap nhat tai lieu tong quan he thong

Da cap nhat file:

```text
TONG_QUAN_HE_THONG_HIEN_TAI.md
```

Noi dung ghi lai:

- He thong dang build la gi.
- Muc tieu nghiep vu.
- 4 doi tuong chinh.
- Kien truc da chot.
- Backend da co.
- Frontend da co.
- PGPR/XAI/Graph da co.
- Auth/User/Project da co.
- Nhung gi chua lam:
  - verification
  - duplicate matching
  - KG sync pipeline
  - evaluation
  - deploy
  - UI web chinh thuc

### 5.2 Tao ke hoach upgrade UI/Auth/Verification

Da tao file:

```text
KE_HOACH_UPGRADE_UI_AUTH_VERIFICATION.md
```

Noi dung chot:

- Can UI web chinh thuc.
- User dang ky nhung data crawl da co san thi phai xu ly duplicate.
- User/entity moi phai co trang thai chua xac thuc.
- Can claim entity.
- Can admin review.
- Can merge duplicate.
- Can KG sync pipeline.

Trang thai: day la ke hoach, chua phai code hoan thien.

## Phase 6 - Thiet ke Provisional KG Sync (2026-05-25)

### 6.1 Tao ke hoach Provisional KG Sync

Da tao file:

```text
KE_HOACH_PROVISIONAL_KG_SYNC.md
```

Y tuong chot:

```text
Entity moi duoc dua vao Neo4j ngay de user co the dung recommendation,
nhung node do bi danh dau unverified va bi gioi han anh huong.
```

Ten co che:

```text
Provisional KG Sync
```

Ly do:

- Neu cho entity moi nam o MongoDB thoi thi PGPR/Graph khong biet entity moi.
- User moi tao account/project se khong dung recommendation day du ngay.
- Neu sync thang vao KG khong kiem soat thi gay duplicate/noise.

### 6.2 Cac diem thiet ke da chot trong ke hoach

Da chot cac field/trang thai:

| Field | Y nghia |
|---|---|
| `account_verification_status` | Trang thai xac thuc account |
| `entity_verification_status` | Trang thai xac thuc entity nghiep vu |
| `kg_sync_status` | Trang thai sync voi Neo4j |
| `visibility` | Node co hien ra UI/API khong |
| `participation_scope` | Node co duoc tham gia recommendation/PGPR o pham vi nao |
| `allow_as_source` | Node co duoc lam source khong |
| `recommendable_as_target` | Node co duoc lam target recommendation khong |
| `allow_as_intermediate_node` | Node co duoc nam giua path khong |
| `trust_weight` | He so tin cay cua node |
| `kg_schema_version` | Version KG schema |
| `provisional_sync_version` | Version logic sync provisional |

Trang thai `kg_sync_status` da chot:

```text
not_synced
syncing
synced_unverified
synced_verified
merge_required
sync_failed
sync_partial
disabled
rejected
```

### 6.3 Rule quan trong da chot

Khong chi dung:

```text
final_score = pgpr_score * trust_weight
```

Vi neu chi nhan diem o cuoi, node unverified van co the tham gia tao path nhu node verified.

Rule moi:

```text
Tang 1: filter visibility/participation_scope truoc hoac trong query path
Tang 2: tinh trust_weight sau khi path hop le
```

Personal mode:

- Source la entity cua current user duoc dung neu `allow_as_source = true`.
- Source owner_only van dung duoc trong personal mode.
- Target/intermediate cua nguoi khac bi han che.

Public mode:

- An owner_only cua nguoi khac.
- An rejected/disabled/hidden.
- Khong cho node `allow_as_intermediate_node = false` nam giua path.
- Target public phai co `recommendable_as_target = true`.

### 6.4 Rule project unverified

Project user tao nhung chua verified:

- Owner xem duoc.
- Owner dung lam source de tim expert/funder/enterprise duoc.
- Nguoi khac khong thay trong public recommendation.
- Chua lam target recommendation cho expert khac.

Default:

```json
{
  "visibility": "limited",
  "participation_scope": "owner_only",
  "allow_as_source": true,
  "recommendable_as_target": false,
  "allow_as_intermediate_node": false
}
```

### 6.5 Rule custom topic

Da chot:

- `research_topics` chuan duoc sync sang Neo4j.
- `custom_research_topics` khong sync vao Topic chuan trong MVP.
- Custom topic can admin/map sau.

### 6.6 Rule merge MVP

Phase dau khong merge relationship phuc tap.

Merge MVP:

```text
Admin chon merge source -> target
1. app_users.linked_entity.id = target_id
2. source_entity.kg_sync_status = disabled
3. source_entity.matched_existing_entity_id = target_id
4. Neo4j source.active = false
5. Neo4j source.participation_scope = disabled
6. Neo4j source.merged_into = target_id
7. Khong xoa source
```

### 6.7 Rule audit/admin

Da chot can co:

- verify entity
- reject entity
- disable KG
- retry sync
- merge entity
- admin audit log

## Phase 7 - Trien khai backend Provisional KG Sync buoc dau (2026-05-25)

### 7.1 Them constants/status nen tang

Tao file moi:

```text
backend/services/provisional_status.py
```

Noi dung:

- Hang so cho `account_verification_status`.
- Hang so cho `entity_verification_status`.
- Hang so cho `kg_sync_status`.
- Hang so cho `visibility`.
- Hang so cho `participation_scope`.
- `KG_SCHEMA_VERSION = 1`.
- `PROVISIONAL_SYNC_VERSION = 1`.
- Helper:
  - `default_unverified_state()`
  - `verified_state()`

### 7.2 Them duplicate matching MVP

Tao file moi:

```text
backend/services/entity_matching_service.py
```

Da lam:

- `EntityMatchingService.match_user_entity(role, user)`.
- Strong match:
  - email
  - ORCID/ResearcherID/website/domain neu co
- Weak match:
  - fuzzy name
  - name + organization
- Tra ve:
  - `matched_existing`
  - `merge_required`
  - `created_new`

Ghi chu: day la MVP matching, chua phai matching day du san xuat.

### 7.3 Them admin audit log service

Tao file moi:

```text
backend/services/admin_audit_log_service.py
```

Da lam:

- `AdminAuditLogService.log(...)`.
- Ghi action admin vao collection `admin_audit_logs`.
- Luu:
  - `admin_user_id`
  - `action`
  - `entity_type`
  - `entity_id`
  - `before`
  - `after`
  - `reason`
  - `created_at`

### 7.4 Cap nhat AuthRepository

File sua:

```text
backend/repositories/auth_repo.py
```

Da them:

- `ensure_indexes()`.
- Unique index `app_users.email`.
- Index cho entity email/user_id/name.
- Index project owner/project_id.
- Index audit logs.
- `get_entity_collection()`.
- `entity_id_field()`.
- `find_entity_by_id()`.
- `find_strong_entity_match()`.
- `find_entity_candidates_by_name()`.
- `update_entity_status()`.
- `insert_admin_audit_log()`.
- `relink_users_from_entity()`.

Da sua `create_role_entity()`:

- Nhan `match_result`.
- Strong match thi tra entity da co, khong tao duplicate.
- Weak match thi tao entity moi voi `kg_sync_status = merge_required`.
- No match thi tao entity moi voi `kg_sync_status = not_synced`.
- Entity moi co:
  - `entity_verification_status = unverified`
  - `visibility`
  - `participation_scope`
  - `allow_as_source`
  - `recommendable_as_target`
  - `allow_as_intermediate_node`
  - `trust_weight`
  - `duplicate_candidates`
  - `kg_schema_version`
  - `provisional_sync_version`

Da sua `create_project()`:

- Project user tao co:
  - `source = user_created`
  - `owner_user_id`
  - `owner_entity_id`
  - `entity_verification_status = unverified`
  - `kg_sync_status = not_synced`
  - `visibility = limited`
  - `participation_scope = owner_only`
  - `allow_as_source = true`
  - `recommendable_as_target = false`
  - `allow_as_intermediate_node = false`
  - `trust_weight = 0.5`

### 7.5 Cap nhat PGPRGraphRepository

File sua:

```text
backend/repositories/pgpr_graph_repo.py
```

Da them:

- `ensure_constraints()`.
- `upsert_provisional_entity()`.
- `upsert_topic_relationships()`.
- `update_entity_verification_status()`.
- `disable_entity()`.
- `get_entity_status()`.

Neo4j constraints duoc tao neu co the:

- Expert id/expert_id
- Project id/project_id
- Enterprise id/enterprise_id
- Funder id/funder_id
- ResearchTopic topic_id
- Skill skill_id
- Location location_id
- Industry industry_id

Upsert dung `MERGE`, khong dung `CREATE`, de retry khong tao duplicate.

Da them filter trong:

- `find_reasoning_paths(...)`
- `find_entity_neighbors(...)`

Filter theo:

- `mode = public | personal | admin_debug`
- `visibility`
- `participation_scope`
- `allow_as_intermediate_node`
- `current_user_id`

### 7.6 Them ProvisionalKGSyncService

Tao file moi:

```text
backend/services/provisional_kg_sync_service.py
```

Da lam:

- `sync_entity_as_unverified(entity_type, entity_id)`.
- `retry_sync(entity_type, entity_id)`.
- `verify_entity(entity_type, entity_id)`.
- `reject_entity(entity_type, entity_id)`.
- `disable_entity(entity_type, entity_id)`.
- `merge_entities(entity_type, source_entity_id, target_entity_id)`.

Sync flow:

```text
MongoDB set kg_sync_status = syncing
-> Neo4j MERGE node
-> Neo4j MERGE topic relationships cho research_topics chuan
-> MongoDB set kg_sync_status = synced_unverified
```

Neu loi:

```text
MongoDB set kg_sync_status = sync_failed
MongoDB luu sync_error
```

Ghi chu:

- Register/create project khong bi fail chi vi Neo4j sync loi.
- Sync loi co the retry sau.

### 7.7 Cap nhat AuthService

File sua:

```text
backend/services/auth_service.py
```

Register flow moi:

```text
register
-> validate email/password
-> create_user(account_verification_status=email_unverified)
-> EntityMatchingService.match_user_entity()
-> AuthRepository.create_role_entity(match_result)
-> set linked_entity
-> neu khong matched_existing thi ProvisionalKGSyncService.sync_entity_as_unverified()
-> cap nhat linked_entity theo ket qua sync
-> tra auth response
```

Create project flow moi:

```text
create_project
-> lay linked_entity cua user
-> gan owner_entity_id vao project
-> tao project trong MongoDB
-> ProvisionalKGSyncService.sync_entity_as_unverified("project", project_id)
-> tra project response
```

Response user/project co them:

- `account_verification_status`
- `entity_verification_status`
- `kg_sync_status`
- `visibility`
- `participation_scope`
- `allow_as_source`
- `recommendable_as_target`
- `allow_as_intermediate_node`
- `trust_weight`
- `match_status`
- `duplicate_candidates`

### 7.8 Cap nhat schemas

File sua:

```text
backend/models/schemas.py
```

Da them:

- `RecommendationRequest.mode`.
- `RecommendationRequest.current_user_id`.
- `RecommendationItem.final_score`.
- `RecommendationItem.raw_score`.
- `RecommendationItem.stored_trust_weight`.
- `RecommendationItem.runtime_source_weight`.
- `RecommendationItem.trust_override_reason`.
- `RecommendationItem.uses_provisional_data`.
- `RecommendationItem.provisional_nodes_count`.
- `RecommendationItem.data_quality_level`.
- `RecommendationItem.data_quality_notes`.
- `RecommendationItem.verification_badges`.
- `UserPublic.account_verification_status`.

### 7.9 Cap nhat RecommendationService

File sua:

```text
backend/services/recommendation_service.py
```

Da them:

- `mode`.
- `current_user_id`.
- Cache key co mode/current_user.
- `_apply_provisional_rules()`.
- `_is_target_visible()`.
- `_is_provisional()`.
- `_data_quality_level()`.

Rule hien tai:

- Public mode an target `owner_only`.
- Public mode an target `recommendable_as_target = false`.
- Personal mode cho owner xem target owner_only cua minh.
- Tinh `final_score = raw_score * runtime_source_weight * target_weight`.
- Khong doi stored trust weight.
- Neu source la current user personal mode:
  - `runtime_source_weight = 1.0`
  - `trust_override_reason = current_user_personal_mode`

Response recommendation co them:

- `raw_score`
- `final_score`
- `stored_trust_weight`
- `runtime_source_weight`
- `trust_override_reason`
- `uses_provisional_data`
- `provisional_nodes_count`
- `data_quality_level`
- `data_quality_notes`
- `verification_badges`

### 7.10 Cap nhat XAI warning

File sua:

```text
backend/services/recommendation_service.py
```

Trong `_explain_rule()` da them:

- `uses_provisional_data`
- `data_quality_level`
- `provisional_nodes_count`
- `data_quality_notes`
- `verification_badges`

Neu recommendation dung provisional data, natural language explanation them canh bao:

```text
Goi y nay co su dung du lieu chua xac thuc. Ket qua co the thay doi sau khi ho so duoc duyet.
```

### 7.11 Cap nhat GraphService va Graph API

File sua:

```text
backend/services/graph_service.py
backend/api/v1/endpoints/graph.py
backend/api/deps.py
```

Da them:

- `mode = public | personal | admin_debug`.
- `current_user_id` optional.
- `get_optional_current_user()`.

Graph public:

- an `hidden`
- an `disabled`
- an `rejected`
- an `owner_only` cua nguoi khac
- khong expand qua node `allow_as_intermediate_node = false`

Graph personal:

- owner xem duoc node cua minh.
- van khong hien private node cua nguoi khac.

Graph admin_debug:

- co the xem day du de review.

### 7.12 Cap nhat Recommendation API

File sua:

```text
backend/api/v1/endpoints/recommendations.py
```

Da truyen xuong service:

- `mode`
- `current_user_id`

Cho cac route:

- `/api/v1/recommendations/experts`
- `/api/v1/recommendations/funders`
- `/api/v1/recommendations/policy`

### 7.13 Them Admin API

Tao file moi:

```text
backend/api/v1/endpoints/admin.py
```

Dang ky trong:

```text
backend/main.py
```

API da them:

```http
POST /api/v1/admin/kg-sync/{entity_type}/{entity_id}/retry
POST /api/v1/admin/entities/{entity_type}/{entity_id}/verify
POST /api/v1/admin/entities/{entity_type}/{entity_id}/reject
POST /api/v1/admin/entities/{entity_type}/{entity_id}/disable-kg
POST /api/v1/admin/entities/{entity_type}/{source_entity_id}/merge
```

Moi action admin co ghi audit log:

- retry KG sync
- verify entity
- reject entity
- disable KG
- merge entity

### 7.14 Merge MVP da lam

Trong `ProvisionalKGSyncService.merge_entities()`:

```text
source -> target
```

Da lam:

- Tim source entity.
- Tim target entity.
- Relink user tu source sang target:
  - `app_users.linked_entity.id = target_id`
- Source entity:
  - `kg_sync_status = disabled`
  - `visibility = disabled`
  - `participation_scope = disabled`
  - `active = false`
  - `trust_weight = 0`
  - `matched_existing_entity_id = target_id`
  - `merged_into = target_id`
- Neo4j source:
  - disabled
  - `merged_into = target_id`
- Khong xoa source.
- Chua chuyen relationship phuc tap tu source sang target.

### 7.15 Kiem tra da chay

Compile backend:

```powershell
cd backend
python -m compileall main.py api services repositories models pgpr
```

Ket qua:

```text
PASS
```

Smoke test FastAPI:

```powershell
from fastapi.testclient import TestClient
from main import app
client = TestClient(app)
GET /api/v1/health
```

Ket qua:

```text
routes 32
health 200
```

Response health:

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

### 7.16 Gioi han hien tai sau khi implement

Da lam backend foundation, nhung chua hoan thien het san pham.

Con thieu:

- Chua co UI admin verify/reject/disable/merge/retry.
- Chua test register thuc te qua frontend sau khi sync Neo4j.
- Chua test race condition register dong thoi.
- Chua test duplicate strong/weak voi data that.
- Chua refactor sau toan bo tung Cypher candidate query trong PGPR de tat ca query deu filter provisional tu goc.
- Graph/reasoning paths da co filter mode, nhung candidate recommendation fallback van can test voi data unverified that.
- Merge MVP chua chuyen relationship tu source duplicate sang target.
- Chua co migration cho entity cu de them cac field moi.

### 7.17 Huong tiep theo sau Phase 7

Nen lam tiep theo thu tu:

1. Test register user moi voi role expert.
2. Kiem tra MongoDB entity moi co dung status khong.
3. Kiem tra Neo4j co node `synced_unverified` khong.
4. Test personal recommendation voi source la entity moi.
5. Test public recommendation khong hien node owner_only cua nguoi khac.
6. Them UI profile hien:
   - account verification
   - entity verification
   - KG sync status
   - trust weight
   - duplicate candidates
7. Them UI admin review.
8. Viet migration/backfill cho data cu.

## Phase 8 - Test that Provisional KG Sync va cap nhat frontend status UI (2026-05-26)

Muc tieu cua phase nay:

- Kiem tra luong Provisional KG Sync bang data that, khong chi compile.
- Dam bao user register xong co entity trong MongoDB va Neo4j.
- Dam bao project user tao cung vao Neo4j voi status unverified.
- Hien thi trang thai verification/KG sync tren frontend de user hieu he thong dang lam gi.

## 8.1 Test register -> tao entity -> provisional sync Neo4j

### Da lam

Chay smoke test bang FastAPI `TestClient`:

```text
POST /api/v1/auth/register
```

Payload test:

- role: `expert`
- research_interests:
  - `computer-vision`
  - `ai-healthcare`
- custom_research_topics:
  - topic test tam thoi

### Ket qua lan dau

Register tra `200`, tuc la account va MongoDB entity duoc tao.

Nhung `linked_entity.kg_sync_status` tra ve:

```text
sync_failed
```

MongoDB entity co:

```text
entity_verification_status = unverified
kg_sync_status = sync_failed
visibility = limited
participation_scope = owner_only
allow_as_source = true
recommendable_as_target = false
allow_as_intermediate_node = false
trust_weight = 0.5
```

Neo4j chua co node tuong ung.

### Loi tim thay

Neo4j bao loi Cypher:

```text
Invalid input 'ON'
```

Nguyen nhan:

Trong `PGPRGraphRepository.upsert_provisional_entity()`, query dat:

```cypher
MERGE ...
SET ...
ON CREATE SET ...
```

Neo4j yeu cau `ON CREATE SET` phai dat ngay sau `MERGE`, truoc `SET` chung.

### Muc dich cua test nay

Test nay giup phat hien loi ma compile Python khong thay duoc:

- Python compile van PASS.
- API register van 200.
- Nhung Neo4j sync that bai do sai cu phap Cypher runtime.

Neu khong test that, frontend co the hien user da dang ky thanh cong nhung entity khong vao KG, lam PGPR khong dung duoc user moi.

## 8.2 Sua loi Cypher upsert Neo4j

### File da sua

```text
backend/repositories/pgpr_graph_repo.py
```

### Noi dung sua

Sua thu tu query trong `upsert_provisional_entity()`:

Tu sai:

```cypher
MERGE (n:Label {id_prop: $entity_id})
SET n += $props,
    n.updated_at = datetime()
ON CREATE SET n.created_at = datetime()
```

Thanh dung:

```cypher
MERGE (n:Label {id_prop: $entity_id})
ON CREATE SET n.created_at = datetime()
SET n += $props,
    n.updated_at = datetime()
```

Sua tuong tu trong `upsert_topic_relationships()`:

- `ON CREATE SET` cua topic duoc dat ngay sau `MERGE (t:ResearchTopic ...)`.
- Sau do moi `SET` cac property chung.

### Lam the de lam gi

Muc dich:

- Dam bao Provisional KG Sync thuc su tao/update node trong Neo4j.
- Dam bao retry sync khong fail do sai Cypher.
- Giu dung nguyen tac idempotent upsert bang `MERGE`.

## 8.3 Retry entity bi sync_failed

### Da lam

Sau khi sua Cypher, retry lai entity test bi fail bang:

```text
ProvisionalKGSyncService.retry_sync("expert", entity_id)
```

### Ket qua sau retry lan 1

MongoDB:

```text
kg_sync_status = synced_unverified
sync_error = None
```

Neo4j co node, nhung phat hien:

```text
neo4j.kg_sync_status = not_synced
```

Trong khi MongoDB la:

```text
mongodb.kg_sync_status = synced_unverified
```

### Loi tim thay

Trong `ProvisionalKGSyncService._neo4j_properties()`, property `kg_sync_status` cho Neo4j dang lay theo state ban dau:

```text
not_synced
```

Thay vi gan:

```text
synced_unverified
```

### Lam the de lam gi

Muc dich cua check nay:

- Dam bao MongoDB va Neo4j khong bi lech trang thai.
- Neu MongoDB noi `synced_unverified` ma Neo4j noi `not_synced`, UI/admin/recommendation se kho debug.
- Trang thai KG phai dong nhat giua 2 database.

## 8.4 Sua mapping kg_sync_status khi sync Neo4j

### File da sua

```text
backend/services/provisional_kg_sync_service.py
```

### Noi dung sua

Trong `_neo4j_properties()`:

Neu entity la provisional/unverified va khong phai `merge_required`, Neo4j phai ghi:

```text
kg_sync_status = synced_unverified
```

Neu verified:

```text
kg_sync_status = synced_verified
```

Neu merge_required:

```text
kg_sync_status = merge_required
```

### Ket qua sau retry lan 2

MongoDB:

```text
kg_sync_status = synced_unverified
entity_verification_status = unverified
visibility = limited
participation_scope = owner_only
trust_weight = 0.5
```

Neo4j:

```json
{
  "trust_weight": 0.5,
  "entity_verification_status": "unverified",
  "kg_sync_status": "synced_unverified",
  "visibility": "limited",
  "participation_scope": "owner_only",
  "allow_as_source": true,
  "recommendable_as_target": false,
  "allow_as_intermediate_node": false
}
```

### Lam the de lam gi

Muc dich:

- Dong bo dung trang thai giua MongoDB va Neo4j.
- Bao dam admin/recommendation/XAI co the doc status tu Neo4j va hieu day la node provisional da sync.
- Tranh viec retry lap lai vo ich vi Neo4j tuong node chua sync.

## 8.5 Test register moi sau khi sua loi

### Da lam

Dang ky user test moi:

```text
POST /api/v1/auth/register
```

Email test dang:

```text
codex.provisional.ok.<timestamp>@example.com
```

### Ket qua

API tra `200`.

`linked_entity` tra ve:

```json
{
  "type": "expert",
  "kg_sync_status": "synced_unverified",
  "entity_verification_status": "unverified",
  "visibility": "limited",
  "participation_scope": "owner_only",
  "allow_as_source": true,
  "recommendable_as_target": false,
  "allow_as_intermediate_node": false,
  "trust_weight": 0.5,
  "match_status": "created_new"
}
```

### Lam the de lam gi

Muc dich:

- Xac nhan register moi khong con can retry thu cong.
- User moi dang ky xong co entity vao KG ngay o trang thai provisional.
- Dat dung muc tieu cua Provisional KG Sync: user dung duoc he thong som, nhung node van chua co quyen luc ngang verified data.

## 8.6 Test create project -> provisional sync Neo4j

### Da lam

Login bang user test vua tao:

```text
POST /api/v1/auth/login
```

Tao project:

```text
POST /api/v1/users/me/projects
```

Project test:

```text
Codex Provisional Project Smoke Test
```

### Ket qua API

API tra `200`.

Response project co:

```json
{
  "kg_sync_status": "synced_unverified",
  "entity_verification_status": "unverified",
  "visibility": "limited",
  "participation_scope": "owner_only",
  "allow_as_source": true,
  "recommendable_as_target": false,
  "allow_as_intermediate_node": false,
  "trust_weight": 0.5
}
```

### Ket qua MongoDB

Project co:

```text
kg_sync_status = synced_unverified
entity_verification_status = unverified
visibility = limited
participation_scope = owner_only
trust_weight = 0.5
owner_entity_id = user_exp_...
sync_error = None
```

### Ket qua Neo4j

Neo4j project node co:

```json
{
  "trust_weight": 0.5,
  "entity_verification_status": "unverified",
  "kg_sync_status": "synced_unverified",
  "visibility": "limited",
  "participation_scope": "owner_only",
  "allow_as_source": true,
  "recommendable_as_target": false,
  "allow_as_intermediate_node": false
}
```

### Lam the de lam gi

Muc dich:

- Dam bao khong chi expert moi sync duoc, project user tao cung vao KG.
- Project chua verified chi owner dung lam source duoc.
- Project chua verified khong bi recommend public cho nguoi khac.
- Dat dung rule da chot: project unverified owner_only, khong lam target public.

## 8.7 Cap nhat frontend API type

### File da sua

```text
frontend/src/lib/api.ts
```

### Da them vao type `UserProfile.linked_entity`

- `entity_verification_status`
- `visibility`
- `participation_scope`
- `allow_as_source`
- `recommendable_as_target`
- `allow_as_intermediate_node`
- `trust_weight`
- `match_status`
- `duplicate_candidates`

### Da them vao type `RecommendationItem`

- `raw_score`
- `final_score`
- `stored_trust_weight`
- `runtime_source_weight`
- `trust_override_reason`
- `uses_provisional_data`
- `provisional_nodes_count`
- `data_quality_level`
- `data_quality_notes`
- `verification_badges`

### Da them vao `api.recommend()`

Them params optional:

```text
mode
currentUserId
```

### Lam the de lam gi

Muc dich:

- Frontend hieu cac field backend moi tra ve.
- Tranh TypeScript loi khi hien verification/KG status.
- Chuan bi cho personal/public recommendation mode tren UI.

## 8.8 Cap nhat register flow frontend

### File da sua

```text
frontend/src/app/auth/register/page.tsx
```

### Noi dung sua

Sau khi register thanh cong, doi redirect:

Tu:

```text
/dashboard
```

Thanh:

```text
/profile
```

### Lam the de lam gi

Muc dich:

- User moi dang ky xong thay ngay trang thai ho so.
- User biet ho so da vao KG hay chua.
- Giai thich ro he thong dang de ho so o trang thai `unverified/synced_unverified`.
- Tranh user dang ky xong vao dashboard ma khong hieu profile/KG status cua minh la gi.

## 8.9 Cap nhat Profile UI hien verification/KG status

### File da sua

```text
frontend/src/app/profile/page.tsx
```

### Da them khoi trang thai

Profile hien:

- Account verification.
- Entity verification.
- Knowledge Graph status.
- Trust weight.
- Linked entity.
- Participation scope.
- Match status.

Neu `kg_sync_status = synced_unverified`, UI hien thong bao:

```text
Ho so cua ban da duoc dua vao Knowledge Graph o trang thai chua xac thuc.
Ban co the dung de nhan goi y ca nhan, nhung ket qua co the thay doi sau khi duoc duyet.
```

Neu co duplicate candidates, UI hien canh bao:

```text
He thong phat hien ho so co kha nang trung voi data da co. Can admin review/merge truoc khi public rong rai.
```

### Lam the de lam gi

Muc dich:

- Bien cac status backend thanh thong tin user doc duoc.
- Giai thich tai sao user co the dung recommendation nhung van chua verified.
- Giam nham lan giua account, entity va KG sync status.
- Chuan bi UI cho luong admin review/merge sau nay.

## 8.10 Cap nhat My Projects UI

### File da sua

```text
frontend/src/app/projects/my/page.tsx
```

### Da them hien thi

Moi project hien:

- Badge status project.
- Badge KG sync status.
- Entity verification.
- Participation scope.
- Trust weight.

### Lam the de lam gi

Muc dich:

- User biet project da vao KG hay chua.
- User biet project con `unverified` nen chua public rong rai.
- User hieu vi sao project cua minh co the dung lam source recommendation nhung chua duoc recommend cho nguoi khac.

## 8.11 Kiem tra sau khi sua

### Backend compile

Da chay:

```powershell
cd backend
python -m compileall main.py api services repositories models pgpr
```

Ket qua:

```text
PASS
```

### Frontend typecheck

Da chay:

```powershell
cd frontend
npm.cmd run typecheck
```

Ket qua:

```text
PASS
```

### Smoke tests

Da test:

| Test | Ket qua |
|---|---|
| Register expert moi | `200`, linked_entity `synced_unverified` |
| Retry entity sync_failed | Thanh `synced_unverified` |
| Kiem tra MongoDB expert | Status dung |
| Kiem tra Neo4j expert | Status dung |
| Login user test | `200` |
| Create project | `200`, project `synced_unverified` |
| Kiem tra MongoDB project | Status dung |
| Kiem tra Neo4j project | Status dung |

## 8.12 Du lieu test da tao

Da tao mot vai user/project test de kiem tra luong that.

Email test dang:

```text
codex.provisional.<timestamp>@example.com
codex.provisional.ok.<timestamp>@example.com
```

Project test:

```text
Codex Provisional Project Smoke Test
```

Ghi chu:

- Day la data test trong MongoDB/Neo4j.
- Co the xoa sau neu can lam sach database demo.

## 8.13 Trang thai sau Phase 8

Da hoan thanh:

- Register moi sync duoc entity sang Neo4j.
- Entity moi co status `synced_unverified`.
- Project moi sync duoc sang Neo4j.
- MongoDB va Neo4j dong bo dung status.
- Frontend profile hien verification/KG status.
- Frontend my projects hien KG status.
- Typecheck/compile deu PASS.

Con thieu:

- Chua co UI admin verify/reject/disable/merge/retry.
- Chua test recommendation personal mode bang UI.
- Chua test public recommendation an owner_only cua nguoi khac bang UI.
- Chua migration/backfill field moi cho data cu.
- Chua xoa/quan ly data test.
- Chua them trang admin audit log UI.

---

# Phase 9 - Fix loi recommendation cho entity user moi

Ngay cap nhat: 2026-05-26

## 9.1 Van de phat hien

Khi chay dashboard voi source:

```text
source_type = expert
source_id = user_exp_6a1528217705a46bd4e0f3e7
target_type = project
```

Frontend hien `0 ket qua`.

Nguyen nhan gom 3 phan:

- Dashboard dang goi recommendation mac dinh o `public mode`, trong khi entity moi tao tu register co `participation_scope = owner_only`.
- Provisional KG sync tao relationship `Expert -> INTERESTED_IN -> ResearchTopic`, nhung query PGPR Expert -> Project lai tim `Expert -> HAS_EXPERIENCE_IN -> ResearchTopic`.
- Topic frontend luu la `cybersecurity`, trong khi KG seed dang dung topic chuan nhu `topic_fraud_detection`, `topic_computer_vision`, ... Nen expert moi bi noi vao topic co lap, khong co project nao cung topic.

## 9.2 Da sua backend

File:

```text
backend/repositories/pgpr_graph_repo.py
```

Da sua `upsert_topic_relationships()`:

- Expert moi sync vao Neo4j se tao ca 2 relationship:
  - `INTERESTED_IN`
  - `HAS_EXPERIENCE_IN`
- Muc dich:
  - Giu y nghia ho so nguoi dung qua `INTERESTED_IN`.
  - Dong thoi tuong thich voi query PGPR hien tai dang dung `HAS_EXPERIENCE_IN`.

File:

```text
backend/services/provisional_kg_sync_service.py
```

Da them mapping tu topic cua UI sang topic chuan trong KG:

```text
cybersecurity -> topic_fraud_detection
computer-vision -> topic_computer_vision
renewable-energy -> topic_solar_forecasting, topic_grid_stability_prediction
smart-manufacturing -> topic_predictive_maintenance
...
```

Muc dich:

- Entity moi khong bi sync vao topic co lap.
- PGPR co the tim candidate project thong qua topic da ton tai trong KG.
- Custom topic van khong sync rong vao KG, tranh lam rac graph.

File:

```text
backend/pgpr/pgpr_recommendation.py
```

Da sua `_fallback_score_by_rank()`:

- Truoc day neu chi co 1 candidate fallback thi score thanh `0.0`.
- Sau sua, 1 candidate fallback co score co ban `0.65`.

Muc dich:

- Khi node moi chua co trong vocab PGPR va phai dung Cypher/Heuristic fallback, ket qua demo khong bi hien nhu khong co do phu hop.

File:

```text
backend/services/recommendation_service.py
```

Da doi cache key recommendation tu `v2` sang `v3`.

Muc dich:

- Tranh lay lai cache cu da luu ket qua score `0.0`.
- Dam bao ket qua sau khi sua scoring/topic mapping duoc tinh lai.

## 9.3 Da sua frontend

File:

```text
frontend/src/app/dashboard/page.tsx
```

Da them `useAuth()` vao dashboard.

Khi source ID trung voi `user.linked_entity.id` va source type trung voi linked entity type:

```text
recommendation mode = personal
current_user_id = user.id
```

Nguoc lai:

```text
recommendation mode = public
```

Muc dich:

- User moi co the dung chinh ho so `owner_only/unverified` cua minh lam source recommendation.
- Van giu public mode cho demo data va entity khong thuoc user hien tai.

Dashboard cung hien badge:

```text
personal mode
public mode
```

## 9.4 Da retry sync entity dang loi

Da retry sync:

```text
expert/user_exp_6a1528217705a46bd4e0f3e7
```

Ket qua:

```text
kg_sync_status = synced_unverified
research_topics = ["cybersecurity"]
```

Neo4j hien co:

```text
Expert user_exp_6a1528217705a46bd4e0f3e7
  - HAS_EXPERIENCE_IN -> cybersecurity
  - HAS_EXPERIENCE_IN -> topic_fraud_detection
  - INTERESTED_IN -> cybersecurity
  - INTERESTED_IN -> topic_fraud_detection
```

Kiem tra candidate:

```text
Expert -> topic_fraud_detection <- Project prj_003
```

## 9.5 Ket qua test

Da test API:

```http
POST /api/v1/recommendations/policy
```

Payload:

```json
{
  "source_id": "user_exp_6a1528217705a46bd4e0f3e7",
  "source_type": "expert",
  "target_type": "project",
  "limit": 5,
  "language": "vi",
  "mode": "personal",
  "current_user_id": "6a1528217705a46bd4e0f3e6"
}
```

Ket qua:

```text
200 OK
count = 1
prj_003 - SecurePay AI Fraud Intelligence
score = 0.65
data_quality_level = medium
```

Da chay backend compile:

```powershell
python -m compileall main.py api services repositories models pgpr
```

Ket qua:

```text
PASS
```

Da chay frontend typecheck:

```powershell
npm.cmd run typecheck
```

Ket qua:

```text
PASS
```

## 9.6 Ghi chu con lai

- Source user moi van la `unverified`, nen recommendation tra `data_quality_level = medium`.
- Ket qua nay di qua Cypher/Heuristic fallback vi node user moi chua co trong vocab/policy embedding PGPR da train.
- Ve sau neu muon PGPR policy model tinh diem day du cho node moi, can co pipeline update vocab/triples/embedding/policy hoac thiet ke online feature scoring rieng.
