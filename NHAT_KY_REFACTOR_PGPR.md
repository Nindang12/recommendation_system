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

---

# Phase 10 - Audit checklist hoan thien he thong (2026-05-27)

Muc tieu: doi chieu `CHECKLIST_HOAN_THIEN_HE_THONG_MOI.md` voi code hien tai, hoan thien cac muc uu tien 1-4, cap nhat checklist va ghi nhat ky.

## 10.1 Ket qua audit tong quan

| Nhom | Trang thai | Ghi chu |
|------|------------|---------|
| Recommendation on dinh | **Da cai tien** | `scoring_method`, `fallback_reason`, cap score khi khong co paths |
| Warning/logging backend | **Da lam** | Sua Cypher label; log API + log phuong phap scoring |
| Provisional KG Sync | **~80%** | Topic/owner OK; skill/location/industry sync day du chua |
| Duplicate matching | **MVP** | Thieu Scopus; claim UI day du chua |
| Admin UI | **MVP xong** | Trang `/admin` + detail + audit log |
| Auth/Profile | **~85%** | 3 role register; profile status OK |
| Frontend recommendation UX | **~90%** | Badge scoring/data quality/fallback tren dashboard |
| XAI / Graph / Overview | **Da co** | Thieu admin_debug toggle graph, filter graph |
| Evaluation | **MVP** | Trang summary; chua pipeline metric |
| Testing tu dong | **Chua** | Chi compile + typecheck |
| Deploy | **Chua** | `.env.example` backend co |

Checklist file da cap nhat: `CHECKLIST_HOAN_THIEN_HE_THONG_MOI.md`.

## 10.2 Backend — scoring_method va fallback_reason

### Van de

- Response recommendation chua phan biet ro PGPR policy vs Cypher/heuristic.
- Mot so item co score cao nhung `reasoning_paths` rong.
- XAI co the noi qua chac khi dung fallback.

### Da sua

| File | Noi dung |
|------|----------|
| `backend/pgpr/pgpr_recommendation.py` | Gan `scoring_method=pgpr_policy` hoac `cypher_fallback`; `fallback_reason` khi khong co paths; cap score <= 0.55; path co field `source` |
| `backend/services/recommendation_service.py` | `_apply_scoring_metadata()`; cache key `v4`; log `methods={...}`; XAI canh bao khi `cypher_fallback` |
| `backend/models/schemas.py` | Them `scoring_method`, `fallback_reason` |

### Luong metadata

```text
PGPRRecommender
  -> scoring_method tren tung item
RecommendationService._apply_provisional_rules
  -> trust_weight, data_quality_level
RecommendationService._apply_scoring_metadata
  -> fallback_reason, cap score neu khong co paths
RecommendationService._enrich_with_xai
  -> canh bao provisional + fallback
```

## 10.3 Backend — lam sach Neo4j property warnings

### File

`backend/repositories/pgpr_graph_repo.py`

### Sua

- `find_reasoning_paths`: bo `n.industry_name`, `n.tech_id` khoi `coalesce` entity names.
- `find_entity_neighbors`: bo `n.topic_name`, `n.direction_name`, `n.industry_name`, `n.country_name`; dung `topic_id`, `industry_id`, `location_id`, ...

Muc dich: giam warning Neo4j "property key does not exist" khi schema khong co field do.

## 10.4 Backend — Admin API list/detail/audit

### File

| File | Endpoint / ham |
|------|----------------|
| `backend/repositories/auth_repo.py` | `list_entities_for_admin()`, `list_admin_audit_logs()` |
| `backend/api/v1/endpoints/admin.py` | `GET /entities`, `GET /entities/{type}/{id}`, `GET /audit-logs` |

Cac endpoint POST verify/reject/disable/retry/merge **da co tu Phase 7**.

## 10.5 Frontend — Admin UI

### File moi

| File | Mo ta |
|------|-------|
| `frontend/src/app/admin/page.tsx` | Danh sach entity + filter KG/type + audit log |
| `frontend/src/app/admin/entities/[type]/[id]/page.tsx` | Detail + Verify/Reject/Disable/Retry/Merge + ly do |

### File sua

| File | Noi dung |
|------|----------|
| `frontend/src/lib/api.ts` | Admin client methods + types |
| `frontend/src/components/navigation/navbar.tsx` | Link Admin khi da login |
| `frontend/src/app/dashboard/page.tsx` | Badge scoring method, data quality, unverified, fallback_reason |

**Luu y bao mat:** Admin UI/API MVP — moi user dang nhap deu goi duoc admin (chua co role `admin`).

## 10.6 Kiem tra da chay

```powershell
cd backend
python -m compileall main.py api services repositories models pgpr
```

Ket qua: **PASS**

```powershell
cd frontend
npm.cmd run typecheck
```

Ket qua: **PASS**

Smoke TestClient (Neo4j khong chay tren may audit):

- `GET /api/v1/health` -> 200
- `POST /api/v1/recommendations/policy` -> 200, `count=0` (Neo4j refused) — logic logging `methods={}` van chay

Khi Neo4j/Mongo san sang, nen chay lai:

```powershell
cd backend
python scripts/test_recommendation_api.py
```

## 10.7 Viec con lai sau Phase 10

1. Evaluation pipeline that (`backend/evaluation/`) voi Precision@5, NDCG@5, ...
2. Test tu dong pytest cho auth, provisional sync, visibility, admin.
3. Role admin that + bao ve endpoint `/api/v1/admin/*`.
4. Sync skill/location/industry cho enterprise/funder/project provisional.
5. UI map custom topic -> topic chuan (admin).
6. Graph UI: toggle `admin_debug`, filter/search node.
7. Docker compose + deploy + `.env.production` frontend.
8. Log recommendation cache hit/miss (tuong tu explanation cache).

---

# Phase 11 - Phan quyen admin goc va admin thuong (2026-05-27)

Muc tieu: sua Admin UI/API tu trang MVP "moi user dang nhap deu vao duoc" thanh co phan quyen that:

```text
user -> khong vao duoc admin
admin -> quan tri entity/KG
root_admin -> quan tri entity/KG + tao/promote/demote admin
```

## 11.1 Tach quyen he thong khoi role nghiep vu

### Van de

Truoc do field `role` dang duoc dung cho nghiep vu:

```text
expert | enterprise | funder
```

Neu dung tiep `role=admin` thi se pha luong tao/link entity.

### Da lam

Them field moi:

```text
account_role = user | admin | root_admin
```

File da sua:

```text
backend/models/schemas.py
backend/services/auth_service.py
frontend/src/lib/api.ts
```

Muc dich:

- `role` van la loai entity nghiep vu.
- `account_role` moi la quyen he thong.
- User expert/enterprise/funder van hoat dong binh thuong.

## 11.2 Root admin tu dong duoc tao boi he thong

### Da lam

Them logic startup trong:

```text
backend/main.py
```

Khi backend startup:

```text
doc ROOT_ADMIN_EMAIL tu env
neu email chua co -> tao user account_role=root_admin
neu email da co nhung chua phai root_admin -> update thanh root_admin
```

Them bien env mau:

```text
ROOT_ADMIN_EMAIL=admin@example.com
ROOT_ADMIN_PASSWORD=Admin@123456
ROOT_ADMIN_NAME=System Root Admin
```

File:

```text
backend/.env.example
```

Muc dich:

- Demo khong can tao admin thu cong trong database.
- He thong luon co mot root admin goc de quan tri.

## 11.3 Script tao root admin

File moi:

```text
backend/scripts/create_root_admin.py
```

Tac dung:

```powershell
python scripts/create_root_admin.py
```

Script se:

- Doc `ROOT_ADMIN_EMAIL`, `ROOT_ADMIN_PASSWORD`, `ROOT_ADMIN_NAME`.
- Tao root admin neu chua co.
- Neu user email da co thi promote len `root_admin`.

Muc dich:

- Co cach seed admin ro rang khi deploy/demo.
- Khong phu thuoc hoan toan vao startup.

## 11.4 Bao ve Admin API

### Da lam

Them dependency:

```text
get_current_admin_user
get_current_root_admin
```

File:

```text
backend/api/deps.py
```

Quyen:

```text
get_current_admin_user:
  chap nhan admin/root_admin

get_current_root_admin:
  chi chap nhan root_admin
```

Sua Admin API:

```text
backend/api/v1/endpoints/admin.py
```

Ket qua:

- `/api/v1/admin/entities/*` can `admin` hoac `root_admin`.
- `/api/v1/admin/audit-logs` can `admin` hoac `root_admin`.
- `/api/v1/admin/kg-sync/*` can `admin` hoac `root_admin`.
- `/api/v1/admin/users/*` chi `root_admin`.

Muc dich:

- User thuong khong the verify/reject/merge entity.
- Root admin moi co quyen tao admin khac.

## 11.5 API quan ly admin users

Them repository methods:

```text
AuthRepository.list_users_for_admin()
AuthRepository.set_user_account_role()
```

File:

```text
backend/repositories/auth_repo.py
```

Them API:

```http
GET  /api/v1/admin/users
POST /api/v1/admin/users/create-admin
POST /api/v1/admin/users/{user_id}/promote-admin
POST /api/v1/admin/users/{user_id}/demote-admin
```

Quyen:

```text
root_admin only
```

Muc dich:

- Root admin xem danh sach user.
- Root admin tao admin moi.
- Root admin promote user thanh admin.
- Root admin demote admin ve user.
- Khong cho demote root admin.

## 11.6 Frontend Admin UI

File da sua:

```text
frontend/src/components/navigation/navbar.tsx
frontend/src/app/admin/page.tsx
frontend/src/lib/api.ts
```

Thay doi:

- Navbar chi hien link Admin neu:

```text
account_role = admin | root_admin
```

- Trang `/admin` chan user thuong.
- Root admin thay them khu vuc `Quan ly admin`.
- Root admin co form tao admin moi.
- Root admin co nut:
  - Promote admin
  - Demote user

Muc dich:

- Giao dien khong lam user thuong thay chuc nang khong co quyen.
- Root admin co luong quan tri admin ngay tren web.

## 11.7 Kiem tra da chay

### Compile/backend

```powershell
python -m compileall main.py api services repositories models scripts/create_root_admin.py
```

Ket qua:

```text
PASS
```

# Phase 25 - Bat dau scale-up Cold-Start Hybrid Recommendation (2026-05-28)

Muc tieu:

- Bat dau trien khai ke hoach scale-up cold-start theo thu tu an toan.
- Chua them RabbitMQ/embedding vao luong chay chinh ngay.
- Truoc tien dong bang response hien tai cua recommendation de sau nay so sanh va tranh lam vo PGPR/frontend.

## 25.1 Tao baseline recommendation snapshot script

Da tao file:

```text
backend/scripts/baseline_recommendation_snapshot.py
```

Da lam:

- Script goi `GET /api/v1/health`.
- Script tu lay sample entity id tu:
  - `/api/v1/entities/projects`
  - `/api/v1/entities/experts`
  - `/api/v1/entities/funders`
  - `/api/v1/entities/enterprises`
- Script goi cac case recommendation hien tai qua:
  - `POST /api/v1/recommendations/policy`
- Script luu response day du vao:

```text
backend/scripts/baseline_recommendation_snapshot.json
```

- Script tom tat shape cua item recommendation:
  - `id`
  - `name`
  - `score`
  - `reasoning_paths`
  - `explanation`
  - `xai_explanation`
  - `scoring_method`
  - `uses_provisional_data`
  - `data_quality_level`

Lam the de:

- Co baseline truoc khi them RabbitMQ/GraphSAGE-lite/hybrid ranking.
- Sau moi phase co the so sanh response shape cu co bi vo khong.
- Bao ve frontend hien tai, vi dashboard/entities dang phu thuoc cac field cu.

Lenh chay du kien:

```powershell
cd backend
python scripts/baseline_recommendation_snapshot.py
```

Ghi chu:

- Khi ghi nhat ky nay, backend localhost `127.0.0.1:8000` chua chay nen snapshot chua duoc tao thanh cong.
- Can bat backend + MongoDB + Neo4j roi chay script nay truoc khi vao Phase 1.

## 25.2 Tao checklist scale-up cold-start hybrid

Da tao file:

```text
CHECKLIST_SCALE_UP_COLD_START_HYBRID.md
```

Noi dung checklist:

- Phase 0 - Safety Baseline.
- Phase 1 - Embedding Schema + Migration/Backfill.
- Phase 2 - RabbitMQ Optional Infrastructure.
- Phase 3 - Worker + GraphSAGE-lite.
- Phase 4 - Outbox Reliability.
- Phase 5 - Candidate Safety + Embedding Search.
- Phase 6 - Hybrid Recommendation Backward Compatible.
- Phase 7 - Admin/Monitoring.
- Phase 8 - GraphSAGE Real Model.
- Phase 9 - Evaluation + Production.

Lam the de:

- Co danh sach viec can lam theo thu tu nho, de kiem soat rui ro.
- Moi phase deu co file du kien va test bat buoc.
- Dam bao RabbitMQ/worker/GraphSAGE that khong duoc lam qua som khi chua co baseline va GraphSAGE-lite on dinh.

## 25.3 Tinh trang sau buoc nay

Da hoan thanh:

- [x] Khao sat project.
- [x] Tao script snapshot baseline.
- [x] Tao checklist scale-up cold-start hybrid.
- [x] Ghi nhat ky cong viec va muc dich.

Chua lam:

- [ ] Chua them RabbitMQ.
- [ ] Chua them embedding schema vao database.
- [ ] Chua tao worker.
- [ ] Chua doi recommendation scoring.
- [ ] Chua chay baseline snapshot vi backend hien khong ket noi duoc o `127.0.0.1:8000`.

# Phase 28 - Fix hien thi matched existing entity tren Profile (2026-05-27)

Van de:

- Khi user dang ky trung voi entity co san, he thong link dung `matched_existing`.
- Nhung linked entity trong UI van fallback theo state cua entity user-created:
  - `kg_sync_status = not_synced`
  - `participation_scope = owner_only`
  - `trust_weight = 0.5`
- Profile cung khong co thong bao nao noi ro tai khoan da duoc link voi ho so co san.

Nguyen nhan:

- Du lieu crawl/seed cu trong MongoDB co the khong co cac field provisional moi nhu `trust_weight`, `kg_sync_status`, `participation_scope`.
- `_linked_entity_response()` dung default cho entity moi tao, nen entity matched existing bi hien nham la chua sync/chua tin cay.

Da lam:

File:

```text
backend/services/auth_service.py
frontend/src/app/profile/page.tsx
```

- Neu `match_status = matched_existing`, backend fallback linked entity thanh state cua entity co san:
  - `kg_sync_status = synced_verified`
  - `entity_verification_status = verified`
  - `visibility = public`
  - `participation_scope = public`
  - `recommendable_as_target = true`
  - `allow_as_intermediate_node = true`
  - `trust_weight = 1.0`
- UI Profile them thong bao mau xanh:
  - he thong da tim thay ho so co san
  - tai khoan da lien ket voi entity do
  - entity co the dung cho recommendation voi trust weight day du

Lam the de:

- Matched existing khong bi nham voi provisional entity moi tao.
- User hieu vi sao ho so cua minh duoc link voi data co san.
- Trust weight hien dung hon cho data crawl/seed da ton tai trong he thong.

Kiem tra:

```powershell
cd backend
python -m compileall main.py api services repositories models
```

Ket qua:

```text
PASS
```

```powershell
cd frontend
npm.cmd run typecheck
```

Ket qua:

```text
PASS
```

# Phase 27 - Them mo ta field va fix profile form bi chop khi nhap (2026-05-27)

Muc tieu: form dong trong Profile phai de hieu hon voi nguoi dung, dong thoi khong bi nhap nhay/chop moi khi user go thay doi.

Da lam:

- Mo rong `RoleField` tren frontend voi:
  - `description`
  - `placeholder`
- Renderer hien mo ta ngan duoi label cho field thuong va field array object.
- Them placeholder cho cac field de user biet nen nhap gi.
- Bo sung mo ta cu the cho cac field de gay nham lan:
  - `Research capacity / Cong nghe`
  - `Ten cong nghe`
  - `Ky nang/phuong phap`
  - `Nhu cau cong nghe`
  - `Huong tai tro`
- Sua GSAP ScrollTrigger tren Profile:
  - Khong chay animation khi dang edit.
  - Khong phu thuoc vao `profile` state nua.
  - Khi user go input, page khong bi animate/reveal lai gay cam giac reload.

Lam the de:

- User hieu "Cong nghe" la framework/nen tang/tool/thiet bi cu the nhu PyTorch, Neo4j, Docker, CUDA.
- Trai nghiem nhap lieu muot hon, khong con bi chop moi lan state thay doi.

Kiem tra:

```powershell
cd frontend
npm.cmd run typecheck
```

Ket qua:

```text
PASS
```

# Phase 26 - Tao form dong theo schema doi tuong trong Profile (2026-05-27)

Da lam:

- Profile detail form duoc chuyen sang form dong theo `expert`, `enterprise`, `funder`.
- Them renderer cho field `array<object>` voi nut `Them muc` va nut xoa tung item.
- Them select option cho cac field nen chuan hoa: gioi tinh, hoc ham/hoc vi, muc do thanh thao, trang thai, loai tai tro.
- Expert co cac section: basic info, identifiers/contact, academic profile, research capacity, academic metrics, activities/outputs.
- Enterprise co cac section: basic info/metrics, representatives, R&D profile, outputs/investment/relations.
- Funder co cac section: basic info/representatives, funding strategy, programs/history/impact.
- Backend `auth_repo.py` dong bo `profile_data` ve entity nested tuong ung, thay vi chi luu trong `app_users.profile_data`.

Lam the de:

- User co the nhap du lieu co cau truc giong schema mau trong `add_data`.
- Cac field array object khong con phai nhap JSON/textarea thu cong.
- Entity MongoDB sau khi update co the phuc vu convert sang Neo4j va PGPR recommendation tot hon.

Kiem tra:

```powershell
cd frontend
npm.cmd run typecheck
```

Ket qua:

```text
PASS
```

```powershell
cd backend
python -m compileall main.py api services repositories models
```

Ket qua:

```text
PASS
```

# Phase 26 - Tao form dong theo schema doi tuong trong Profile (2026-05-27)

Muc tieu: phan chinh sua thong tin chi tiet khong con la vai field don le, ma tro thanh form dong theo tung doi tuong `expert`, `enterprise`, `funder`, bam "Them muc" cho cac truong dang array object, va dung select cho cac field nen chuan hoa.

## 26.1 Mo rong schema form tren frontend

File:

```text
frontend/src/app/profile/page.tsx
```

Da lam:

- Mo rong `RoleField.kind` de ho tro:
  - `text`
  - `number`
  - `textarea`
  - `date`
  - `select`
  - `array`
- Them cac option chuan:
  - `genderOptions`
  - `academicRankOptions`
  - `proficiencyOptions`
  - `statusOptions`
  - `fundingTypeOptions`
- Tao `schemaRoleSections` rieng cho tung doi tuong.

Lam the de:

- Form co the sinh UI tu schema cau hinh.
- Sau nay them field trong `add_data` chi can them vao config, khong can viet lai UI tung input.

## 26.2 Expert dynamic form

Da them cac nhom:

- `Basic info`
- `Identifiers va lien he`
- `Academic profile`
- `Research capacity`
- `Academic metrics`
- `Activities and outputs`

Ho tro array object:

- `academic_profile.degrees`
- `academic_profile.affiliation_history`
- `research_capacity.technology`
- `research_capacity.skills_methods`
- `research_capacity.applied_industries`
- `activities_and_outputs.list_outputs`
- `activities_and_outputs.collaborators`
- `activities_and_outputs.grant_history`
- `activities_and_outputs.projects_participation`

## 26.3 Enterprise dynamic form

Da them cac nhom:

- `Basic info va metrics`
- `Representatives`
- `R&D profile`
- `Outputs, investment va relations`

Ho tro array object:

- `basic_info.industries`
- `organization_metrics.certifications`
- `rd_profile.rd_focus_directions`
- `rd_profile.technology_needs`
- `rd_profile.rd_capacity.labs`
- `rd_profile.rd_capacity.equipment`
- `investment_and_markets.investment_history`
- `outputs_and_transfers.commercialized_assets`
- `outputs_and_transfers.patent_outputs`
- `relations.rd_projects`
- `relations.worked_experts`

## 26.4 Funder dynamic form

Da them cac nhom:

- `Basic info va representatives`
- `Funding strategy`
- `Programs, history va impact`

Ho tro array object:

- `representatives`
- `funding_strategy.funding_directions`
- `funding_strategy.focus_regions`
- `funding_strategy.focus_sectors`
- `programs`
- `funding_history.funded_projects`
- `funding_history.annual_grant_history`

## 26.5 Renderer cho array object

File:

```text
frontend/src/app/profile/page.tsx
```

Da lam:

- Them `renderRoleField()`.
- Them `renderScalarField()`.
- Them nut `Them muc` cho field `array`.
- Them nut xoa tung item bang icon trash.
- Moi item trong array render theo cac field con duoc khai bao trong schema.

Lam the de:

- User nhap duoc du lieu co cau truc thay vi textarea JSON.
- Du lieu luu vao `profile_data` dung dang nested object/array gan voi schema `add_data`.

## 26.6 Dong bo profile_data ve entity nested

File:

```text
backend/repositories/auth_repo.py
```

Da lam:

- Khi user update profile, repository khong chi luu trong `app_users.profile_data`.
- Cac section trong `profile_data` duoc day ve entity nested tuong ung:
  - Expert: `academic_profile`, `research_capacity`, `academic_metrics`, `activities_and_outputs`, `governance`
  - Enterprise: `representatives`, `rd_profile`, `organization_metrics`, `investment_and_markets`, `outputs_and_transfers`, `relations`, `governance`
  - Funder: `representatives`, `funding_strategy`, `programs`, `funding_history`, `impact_metrics`, `relations`, `governance`
- Giu lai cac field he thong/provisional KG o top-level.

Lam the de:

- Form dong khong chi hien tren UI ma that su cap nhat entity MongoDB theo schema nested.
- Du lieu sau khi user bo sung co the phuc vu pipeline MongoDB -> Neo4j va PGPR recommendation.

## 26.7 Kiem tra

Da chay:

```powershell
cd frontend
npm.cmd run typecheck
```

Ket qua:

```text
PASS
```

Da chay:

```powershell
cd backend
python -m compileall main.py api services repositories models
```

Ket qua:

```text
PASS
```

# Phase 25 - Them research topic taxonomy va auto-map research direction (2026-05-27)

Muc tieu: he thong co danh muc `research topic` chuan, moi topic biet no thuoc `research_directions` nao. Khi user chon topic luc register/profile, backend se tu luu them `parent_direction` de phuc vu MongoDB schema, KG sync va recommendation.

## 25.1 Them taxonomy dung chung cho backend

File:

```text
backend/models/research_taxonomy.py
```

Da lam:

- Tao danh sach `RESEARCH_DIRECTIONS`.
- Tao danh sach `RESEARCH_TOPICS`.
- Moi topic co:
  - `value`
  - `label`
  - `direction`
- Them map:
  - `ALLOWED_RESEARCH_TOPICS`
  - `RESEARCH_TOPIC_DIRECTION_MAP`
  - `RESEARCH_DIRECTION_LABEL_MAP`
  - `RESEARCH_TOPIC_LABEL_MAP`
- Them helper:
  - `research_topic_direction()`
  - `research_direction_label()`

Lam the de:

- Backend khong con validate topic bang set hard-code trong `schemas.py`.
- Co mot nguon su that duy nhat cho topic -> direction.

## 25.2 Cap nhat validation schema

File:

```text
backend/models/schemas.py
```

Da lam:

- Xoa set `ALLOWED_RESEARCH_TOPICS` cu.
- Import `ALLOWED_RESEARCH_TOPICS` tu `models.research_taxonomy`.

Lam the de:

- Register/update profile chi chap nhan topic nam trong taxonomy chuan.
- Khi them topic moi chi can cap nhat taxonomy.

## 25.3 Auto-map topic sang research direction khi luu MongoDB

File:

```text
backend/repositories/auth_repo.py
```

Da lam:

- `_topic_objects()` khong con luu topic chi co `name` va `parent_direction = None`.
- Topic chuan duoc luu theo dang:

```json
{
  "id": "computer-vision",
  "name": "Computer Vision",
  "parent_direction": "computer-vision-multimedia",
  "parent_direction_label": "Thi giac may tinh va da phuong tien"
}
```

- Custom topic duoc luu rieng voi:

```json
{
  "name": "...",
  "parent_direction": "custom_pending_mapping",
  "parent_direction_label": "Can admin mapping",
  "mapping_status": "pending_review"
}
```

- Project user tao moi tu `keywords` cung duoc auto-map `parent_direction` neu keyword trung topic chuan.

Lam the de:

- Data moi van dung schema `add_data`.
- KG/recommendation co the biet topic thuoc direction nao.
- Topic custom khong bi dua nham vao taxonomy public khi chua duyet/map.

## 25.4 Them Taxonomy API

File:

```text
backend/api/v1/endpoints/taxonomy.py
backend/main.py
```

Da lam:

- Tao endpoint:

```http
GET /api/v1/taxonomy/research-topics
```

- Response gom:
  - `directions`
  - `topics`
  - `count`

Lam the de:

- Frontend/admin sau nay co the lay danh muc tu backend thay vi hard-code.
- Thuan tien cho viec quan tri taxonomy ve sau.

## 25.5 Cap nhat frontend topic list

File:

```text
frontend/src/lib/research-topics.ts
frontend/src/app/auth/register/page.tsx
frontend/src/app/profile/page.tsx
```

Da lam:

- Mo rong `researchTopicOptions` tu list phang thanh list co `direction`.
- Them `researchDirectionOptions`.
- Them helper:
  - `researchTopicLabel()`
  - `researchDirectionLabel()`
  - `researchTopicDirection()`
  - `researchTopicsByDirection()`
- Register page hien topic theo nhom research direction.
- Profile page hien topic theo nhom research direction.
- Khi chon topic, UI hien "Huong nghien cuu tu dong nhan dien".

Lam the de:

- User nhin vao biet topic thuoc huong nghien cuu nao.
- Data nhap vao thong nhat, giam topic rac.

## 25.6 Kiem tra

Da chay:

```powershell
cd backend
python -m compileall main.py api services repositories models
```

Ket qua:

```text
PASS
```

Da chay:

```powershell
cd frontend
npm.cmd run typecheck
```

Ket qua:

```text
PASS
```

# Phase 21 - Chuan hoa luu entity theo schema add_data (2026-05-27)

Muc tieu: cac entity moi do user dang ky/cap nhat/tao project phai duoc luu theo cau truc du lieu co san trong folder `add_data`, khong tao mot schema phang rieng gay lech voi MongoDB va pipeline convert sang Neo4j.

## 21.1 Chuan hoa luu Expert / Enterprise / Funder

File:

```text
backend/repositories/auth_repo.py
```

Da lam:

- Them helper doc nested path, hien thi ten/email, build location, topic objects, skill objects va governance mac dinh.
- `create_role_entity()` khong con luu cac field phang nhu `name`, `phone`, `organization`, `skills`, `research_topics`, `profile_data` o top-level nua.
- Expert moi duoc luu theo cac khoi:
  - `expert_id`
  - `basic_info`
  - `identifiers`
  - `contact_info`
  - `academic_profile`
  - `research_capacity`
  - `academic_metrics`
  - `activities_and_outputs`
  - `governance`
- Enterprise moi duoc luu theo cac khoi:
  - `enterprise_id`
  - `basic_info`
  - `representatives`
  - `rd_profile`
  - `outputs_and_transfers`
  - `relations`
  - `governance`
- Funder moi duoc luu theo cac khoi:
  - `funder_id`
  - `basic_info`
  - `representatives`
  - `funding_strategy`
  - `programs`
  - `funding_history`
  - `impact_metrics`
  - `relations`
  - `governance`
- Chi giu them cac field he thong can thiet o top-level:
  - `user_id`
  - `source`
  - `entity_verification_status`
  - `kg_sync_status`
  - `visibility`
  - `participation_scope`
  - `allow_as_source`
  - `recommendable_as_target`
  - `allow_as_intermediate_node`
  - `trust_weight`
  - `duplicate_candidates`
  - `matched_existing_entity_id`
  - `claim_status`
  - `kg_schema_version`
  - `provisional_sync_version`
  - `created_at`
  - `updated_at`

Muc dich:

- Du lieu user tao ra dong nhat voi du lieu crawl/seed trong `add_data`.
- Giam nguy co pipeline convert MongoDB -> Neo4j bi lech schema.
- Van giu duoc cac thuoc tinh rieng phuc vu auth, provisional sync, trust weight va admin review.

## 21.2 Chuan hoa update profile vao nested schema

File:

```text
backend/repositories/auth_repo.py
```

Da lam:

- `update_role_entity_from_user()` cap nhat vao nested path:
  - `basic_info.name`
  - `basic_info.location`
  - `contact_info.phones`
  - `contact_info.emails`
  - `contact_info.social_links`
  - `research_capacity.research_topics`
  - `research_capacity.technology`
  - `research_capacity.skills_methods`
  - `rd_profile.rd_focus_topics`
  - `funding_strategy.funding_topics`
- Khong tiep tuc ghi de bang cac field phang top-level.

Muc dich:

- Khi user sua profile, MongoDB van giu dung cau truc entity goc.
- Cac thong tin quan trong cho recommendation nhu topic, skill, location duoc dat dung vi tri ma data seed dang dung.

## 21.3 Chuan hoa project user tao

File:

```text
backend/repositories/auth_repo.py
```

Da lam:

- `create_project()` chuyen payload frontend thanh schema project gan voi `add_data`:
  - `project_id`
  - `basic_info.title`
  - `basic_info.description`
  - `basic_info.research_directions`
  - `basic_info.research_topics`
  - `basic_info.keywords`
  - `basic_info.location`
  - `requirements_and_timeline.status`
  - `requirements_and_timeline.required_skills`
  - `requirements_and_timeline.technology_readiness_level`
  - `requirements_and_timeline.budget`
  - `rd_profile`
  - `relations`
  - `follow_up_opportunities`
  - `governance`
- Van giu top-level `owner_id`, `owner_user_id`, `owner_entity_id` va cac field provisional KG.

Muc dich:

- Project user tao sau nay co the dua vao cung pipeline KG voi project seed.
- Khong tao them schema project rieng chi phuc vu UI.

## 21.4 Cap nhat doc du lieu nested cho profile, admin, entity list

File:

```text
backend/services/auth_service.py
backend/repositories/mongodb_repo.py
```

Da lam:

- Profile response doc fallback tu nested entity:
  - `basic_info.name`
  - `basic_info.location`
  - `contact_info`
  - `research_capacity`
  - `rd_profile`
  - `funding_strategy`
- Linked entity name lay tu `basic_info.name` / `basic_info.title` neu khong co field phang.
- My Projects response lay title/summary/status/budget/TRL tu nested project schema.
- Entity list/detail API co the search va normalize nested fields:
  - `basic_info.name`
  - `basic_info.title`
  - `basic_info.description`
  - `academic_profile.current_affiliation.org_name`

Muc dich:

- UI va API cu van doc duoc entity moi theo schema nested.
- Van tuong thich voi data cu dang co field phang neu con ton tai trong database.

## 21.5 Cap nhat Provisional KG Sync doc nested entity

File:

```text
backend/services/provisional_kg_sync_service.py
```

Da lam:

- Sync Neo4j khong con chi doc:
  - `entity.skills`
  - `entity.research_topics`
  - `entity.location`
- Them helper doc nested:
  - Expert: `research_capacity.research_topics`, `research_capacity.skills_methods`, `research_capacity.technology`
  - Enterprise: `rd_profile.rd_focus_topics`
  - Funder: `funding_strategy.funding_topics`
  - Project: `basic_info.research_topics`, `requirements_and_timeline.required_skills`
  - Location: `basic_info.location`
- Neo4j properties `name`, `title`, `summary`, `country`, `province`, `district` deu co fallback tu nested schema.

Muc dich:

- Entity moi luu dung schema van sync duoc vao Knowledge Graph.
- PGPR recommendation tiep tuc co topic/skill/location de tao relationship.

## 21.6 Kiem tra

Da chay:

```powershell
cd backend
python -m compileall main.py api services repositories models
```

Ket qua:

```text
PASS
```

Ghi chu:

- Thay doi nay ap dung cho du lieu moi/cap nhat tu thoi diem nay tro di.
- Cac document cu da luu theo schema phang van doc duoc nho fallback, nhung neu muon lam sach database thi can mot script migration rieng.

---

# Phase 23 - Backfill profile tu entity da matched/merged

Ngay cap nhat: 2026-05-27

## 23.1 Van de

Sau khi user match/merge voi entity cu, profile van hien mot so field trong `app_users` bi trong, vi frontend doc:

```text
user.phone
user.organization
user.social_links
user.profile_data
```

Trong khi data day du lai nam trong entity nghiep vu:

```text
experts / enterprises / funders
```

Vi vay user co the da linked dung entity cu nhung cac o nhu `So dien thoai`, social link, identifier, academic profile van trong.

## 23.2 Sua AuthService tra profile co fallback tu linked entity

File:

```text
backend/services/auth_service.py
```

Da lam:

- Khi `_public_user()` tra profile, service doc lai linked entity trong MongoDB.
- Neu user field trong thi lay fallback tu entity.
- Khong ghi de field user da tu nhap.

Cac field duoc backfill:

- `full_name`
- `organization`
- `phone`
- `address`
- `country`
- `province`
- `district`
- `skills`
- `bio`
- `social_links`
- `profile_data`
- `research_interests`

Muc dich:

- User da matched/merged voi data cu se thay thong tin profile day du hon.
- Profile khong con trong o nhung field entity da co du lieu.

## 23.3 Ho tro nhieu dang schema entity

File:

```text
backend/services/auth_service.py
```

Da lam:

- Them helper `_get_path()` de doc nested field.
- Phone duoc lay theo thu tu:

```text
user.phone
entity.phone
entity.contact_info.phone
entity.contact_info.phones[0]
entity.representatives[0].phone
```

- Organization duoc lay theo thu tu:

```text
user.organization
entity.organization
entity.academic_profile.current_affiliation.org_name
entity.basic_info.name
```

- Social links duoc merge tu:

```text
entity.social_links
entity.contact_info.social_links
entity.profile_data.contact_info.social_links
user.social_links
```

- ORCID duoc fallback tu:

```text
entity.identifiers.ORCID
profile_data.identifiers.ORCID
```

- `profile_data` duoc merge tu cac block entity san co:

```text
basic_info
identifiers
contact_info
academic_profile
research_capacity
academic_metrics
activities_and_outputs
funding_strategy
rd_profile
organization_metrics
investment_mandates
programs
relations
governance
```

Muc dich:

- Phu hop voi data crawl co schema giau hon app_user.
- Khong can copy tay toan bo entity vao user document moi hien duoc tren UI.

## 23.4 Kiem tra

Da chay:

```powershell
cd backend
python -m compileall main.py api services repositories models
```

Ket qua:

```text
PASS
```

Da chay:

```powershell
cd frontend
npm.cmd run typecheck
```

Ket qua:

```text
PASS
```

# Phase 24 - Chuan hoa luu entity theo schema add_data (2026-05-27)

Ghi chu: muc chi tiet da duoc ghi trong file nay o phan "Chuan hoa luu entity theo schema add_data". Phase nay duoc danh dau lai o cuoi nhat ky de the hien dung thu tu cong viec moi nhat.

Da lam:

- Backend khong con tao entity user moi theo schema phang rieng.
- Expert/Enterprise/Funder moi duoc luu theo cac khoi nested giong data trong `add_data`: `basic_info`, `contact_info`, `research_capacity`, `rd_profile`, `funding_strategy`, `relations`, `governance`.
- Project user tao moi duoc luu theo schema project nested: `basic_info`, `requirements_and_timeline`, `rd_profile`, `relations`, `follow_up_opportunities`, `governance`.
- Chi cac field he thong can thiet moi nam o top-level: `user_id`, `owner_id`, `source`, `entity_verification_status`, `kg_sync_status`, `visibility`, `participation_scope`, `trust_weight`, `duplicate_candidates`, `matched_existing_entity_id`, `kg_schema_version`, `provisional_sync_version`, timestamps.
- Profile/API/Admin/KG sync duoc cap nhat de doc nested fields, dong thoi van fallback duoc data cu dang co field phang.

Lam the de:

- Giu du lieu MongoDB thong nhat voi pipeline crawl/seed/convert KG.
- Tranh viec user-created data va crawled data co hai schema khac nhau.
- Bao toan logic Provisional KG Sync, duplicate matching, admin review va PGPR recommendation.

Kiem tra:

```powershell
cd backend
python -m compileall main.py api services repositories models
```

Ket qua:

```text
PASS
```

---

# Phase 22 - Sua luong duplicate/merge user tren Admin va Profile

Ngay cap nhat: 2026-05-27

## 22.1 Khong hien canh bao duplicate sai tren Profile khi da matched existing

File:

```text
backend/services/auth_service.py
frontend/src/app/profile/page.tsx
```

Da lam:

- Sua `_linked_entity_response()` de chi dua `duplicate_candidates` vao `linked_entity` khi entity that su o trang thai `merge_required`.
- Neu user match manh voi entity cu (`matched_existing`) thi khong giu duplicate candidates trong profile nua.
- Profile chi hien canh bao duplicate khi:

```text
linked_entity.kg_sync_status == "merge_required"
va duplicate_candidates.length > 0
```

Muc dich:

- Tranh truong hop user da link dung vao entity cu/verified nhung profile van bao "can admin merge".
- Giao dien user phan biet ro:
  - matched existing: da link vao data cu
  - merge required: can admin review/merge

## 22.2 Refresh linked_entity theo entity moi nhat khi user mo Profile

File:

```text
backend/services/auth_service.py
frontend/src/app/profile/page.tsx
```

Da lam:

- Them `_fresh_linked_entity()` trong `AuthService`.
- Khi API `/users/me` tra ve user, service se doc lai entity that trong MongoDB va cap nhat cac field:
  - kg_sync_status
  - entity_verification_status
  - visibility
  - participation_scope
  - trust_weight
  - duplicate_candidates
- Neu linked entity stale thi update lai vao user document.
- Profile goi `refresh()` khi mount de lay lai status moi tu backend thay vi chi dung localStorage cu.

Muc dich:

- Sau khi admin verify/reject/merge, user reload profile se thay trang thai moi.
- Khong con chi hien status cu cua user trong localStorage.

## 22.3 Admin queue hien duplicate candidates va nut Merge nhanh

File:

```text
frontend/src/app/admin/page.tsx
frontend/src/lib/api.ts
backend/repositories/auth_repo.py
```

Da lam:

- Admin list entity tra them:
  - duplicate_candidates
  - matched_existing_entity_id
  - merged_into
- Bang `Entity review queue` them cot `Duplicate`.
- Neu entity co duplicate candidates:
  - hien so candidate
  - hien candidate dau tien
  - hien nut `Merge` nhanh dan sang detail voi target da dien san
- Neu entity da merge thi queue hien `Da merge vao <target_id>`.

Muc dich:

- Admin nhin vao queue biet ngay entity nao can merge.
- Khong phai mo detail roi moi phat hien duplicate.

## 22.4 Admin detail co giao dien merge ro rang hon

File:

```text
frontend/src/app/admin/entities/[type]/[id]/page.tsx
```

Da lam:

- Doc query param `mergeTarget` de auto dien target entity ID khi admin bam nut Merge tu queue.
- Doi `Duplicate candidates` tu raw JSON thanh card de doc:
  - ten candidate
  - id
  - match strength
  - similarity neu co
- Moi candidate co nut:
  - `Chon lam target merge`
  - `Xem entity cu`
- Them canh bao trong form merge:

```text
Merge se vo hieu hoa entity hien tai, chuyen user dang link voi entity nay sang target entity, va luu audit log.
```

Muc dich:

- Admin co luong merge that su thay vi chi co input target ID trong form.
- Giam nguy co nhap sai target ID.

## 22.5 Merge cap nhat linked_entity day du hon

File:

```text
backend/repositories/auth_repo.py
```

Da lam:

- Khi `relink_users_from_entity()` chuyen user tu source entity sang target entity, linked entity moi co them:
  - visibility
  - participation_scope
  - allow_as_source
  - recommendable_as_target
  - allow_as_intermediate_node
  - trust_weight
  - duplicate_candidates = []

Muc dich:

- Sau merge, user khong bi mat cac field can cho recommendation/profile.
- Profile khong con hien duplicate candidates cu sau khi da merge.

## 22.6 Kiem tra

Da chay:

```powershell
cd backend
python -m compileall main.py api services repositories models
```

Ket qua:

```text
PASS
```

Da chay:

```powershell
cd frontend
npm.cmd run typecheck
```

Ket qua:

```text
PASS
```

---

# Phase 21 - Chuyen dashboard tu demo sang multi recommendation theo user

Ngay cap nhat: 2026-05-27

## 21.1 Dashboard dung linked entity cua user lam source

File:

```text
frontend/src/app/dashboard/page.tsx
```

Da lam:

- Bo luong demo nhap tay `source_type`, `source_id`, `target_type`.
- Dashboard lay `user.linked_entity` cua tai khoan dang dang nhap lam source recommendation.
- Neu tai khoan chua co linked entity thi UI hien canh bao va khong cho chay recommendation.
- Hien source hien tai gom:
  - ten entity
  - id
  - type
  - KG status
  - participation scope

Muc dich:

- Bien dashboard thanh giao dien nguoi dung that su co the dung.
- Giam loi do user nhap sai source id.
- Dam bao recommendation ca nhan chay theo dung expert/enterprise/funder dang dang nhap.

## 21.2 Them multi recommendation mot luot

File:

```text
frontend/src/app/dashboard/page.tsx
```

Da lam:

- Them nut `Goi y tat ca nhom`.
- Khi bam nut, frontend goi song song API:
  - source -> project
  - source -> expert
  - source -> enterprise
  - source -> funder
- Tat ca request chay o `personal mode` va gui `current_user_id`.
- Moi nhom co tab/nut rieng de xem ket qua.
- Neu mot nhom loi, cac nhom con lai van hien duoc ket qua.
- Hien tong so ket qua cua tat ca nhom.

Muc dich:

- Phu hop voi luong moi: user dang nhap co the nhan goi y nhieu loai entity trong mot lan.
- Gan voi bai toan he thong R&D: expert/enterprise/funder can xem project, doi tac, chuyen gia va don vi tai tro lien quan.

## 21.3 Chinh lai noi dung dashboard khong con la demo

File:

```text
frontend/src/app/dashboard/page.tsx
```

Da lam:

- Doi tieu de tu `Dashboard demo he thong goi y R&D` thanh `Dashboard goi y R&D ca nhan`.
- Doi mo ta thanh luong recommendation ca nhan.
- Entity shortcut doi text tu `Browse data` thanh `Browse & recommend`.
- Nut phu tro link sang graph cua source hien tai va trang entities.

Muc dich:

- UI khong con tao cam giac chi la trang demo bao ve.
- Dieu huong nguoi dung vao cac tac vu that: xem goi y, duyet entity, xem graph.

## 21.4 Entities page hien tat ca entity va recommend theo user source

File:

```text
frontend/src/app/search/page.tsx
```

Da lam:

- Them tab `Tat ca` de fetch ca 4 nhom entity:
  - projects
  - experts
  - funders
  - enterprises
- Khi chon `Tat ca`, frontend goi list API cua 4 collection va gom ket qua len mot man hinh.
- Moi entity card co:
  - nut `Recommend entity`
  - nut `Chi tiet`
- Khi bam `Recommend entity`, frontend dung linked entity cua user lam source va goi:

```http
POST /api/v1/recommendations/policy
```

voi:

```json
{
  "source_id": "linked_entity.id",
  "source_type": "linked_entity.type",
  "target_type": "entity.type",
  "mode": "personal"
}
```

- Vi API hien tai chua nhan `target_id`, frontend tam thoi recommend theo `target_type` va highlight entity dang chon neu entity do nam trong top ket qua.

Muc dich:

- Dung voi yeu cau: khi user vao Entities thi thay tat ca entity va co thao tac recommend entity.
- Van giu dung kien truc hien tai, khong chen logic recommendation truc tiep vao UI ngoai API service.

## 21.5 Kiem tra

Da chay:

```powershell
cd frontend
npm.cmd run typecheck
```

Ket qua:

```text
PASS
```

## 21.6 Them API recommend mot target entity cu the

File:

```text
backend/models/schemas.py
backend/api/v1/endpoints/recommendations.py
backend/services/recommendation_service.py
frontend/src/lib/api.ts
frontend/src/app/search/page.tsx
```

Da lam:

- Them `target_id` vao `RecommendationRequest`.
- Them endpoint:

```http
POST /api/v1/recommendations/entity
```

- Endpoint yeu cau:

```json
{
  "source_id": "...",
  "source_type": "expert",
  "target_id": "...",
  "target_type": "project",
  "mode": "personal",
  "current_user_id": "..."
}
```

- Them service method `evaluate_target_entity()`.
- Service se:
  - chay recommendation theo `target_type` voi limit lon hon de xem target co nam trong top khong;
  - neu target nam trong top thi tra ve item do kem `matched_requested_entity=true` va `matched_rank`;
  - neu target khong nam trong top thi tim reasoning paths truc tiep bang KG/Cypher;
  - neu khong co path thi tra score 0 va ghi `fallback_reason` ro rang;
  - van ap dung provisional visibility/trust rule;
  - van enrich XAI va chuan hoa response.
- Frontend `api.recommendEntity()` goi endpoint moi.
- Trang Entities dung endpoint moi khi bam `Recommend entity`.

Muc dich:

- Dung dung yeu cau moi: source la expert/enterprise/funder dang dang nhap, target la entity cu the user dang bam.
- Khong con chi recommend theo nhom roi highlight nua.
- Cho phep UI hien ro entity do co nam trong top recommendation hay chi la direct KG evaluation.

## 21.7 Kiem tra sau khi them endpoint target-specific

Da chay:

```powershell
cd backend
python -m compileall main.py api services repositories models
```

Ket qua:

```text
PASS
```

Da chay:

```powershell
cd frontend
npm.cmd run typecheck
```

Ket qua:

```text
PASS
```

### Frontend typecheck

```powershell
npm.cmd run typecheck
```

Ket qua:

```text
PASS
```

### Smoke test quyen

Da test bang `TestClient`:

```text
root admin login admin@example.com -> 200, account_role=root_admin
GET /api/v1/admin/users bang root token -> 200
GET /api/v1/admin/entities bang root token -> 200
register user thuong moi -> 200, account_role=user
GET /api/v1/admin/entities bang user token -> 403
```

Ket qua:

```text
PASS
```

## 11.8 Du lieu test tao them

Root admin:

```text
admin@example.com
```

User test quyen:

```text
codex.regular.<timestamp>@example.com
```

Ghi chu:

- Root admin can giu de demo.
- User test co the xoa sau neu can lam sach database.

## 11.9 Viec con lai sau Phase 11

- Chua co UI doi mat khau admin.
- Chua co co che khoa admin account.
- Chua co email verification that.
- Chua co rule "khong duoc xoa/demote root admin cuoi cung" vi hien chi co 1 root admin va API da chan demote root admin.
- Neo4j constraint notification van co the hien khi register/sync vi `ensure_constraints()` chay lai; day la notification thong tin, khong phai loi.

---

# Phase 12 - Nang cap giao dien Admin Console voi GSAP ScrollTrigger (2026-05-27)

Muc tieu: sua giao dien admin tu bang quan tri thô thanh mot console dung cho admin review du lieu, scan trang thai KG nhanh hon, va co hieu ung reveal nhe khi cuon trang.

## 12.1 Them GSAP

Da cai package:

```text
gsap
```

File cap nhat:

```text
frontend/package.json
frontend/package-lock.json
```

Muc dich:

- Dung `ScrollTrigger` de reveal cac khoi admin khi cuon.
- Lam UI co cam giac dashboard chinh thuc hon nhung khong anh huong logic backend.

## 12.2 Nang cap trang `/admin`

File:

```text
frontend/src/app/admin/page.tsx
```

Da lam:

- Doi hero thanh `Admin Console` voi thong tin account va role hien tai.
- Them summary cards:
  - Tong entity
  - Can review
  - Verified
  - Rejected
  - Sync failed
- Cai thien bang review entity:
  - Badge mau theo `kg_sync_status`
  - Badge mau theo `entity_verification_status`
  - Hien trust weight
  - Hien sync error neu co
  - Nut `Review` thay cho `Chi tiet`
- Tach khu vuc `Root admin controls`:
  - Tao admin moi
  - Promote user thanh admin
  - Demote admin ve user
- Cai thien audit log:
  - Dang timeline/card gon hon
  - Hien action, entity, admin user, thoi gian, ly do
- Them GSAP ScrollTrigger:
  - `.admin-reveal`
  - `.admin-scroll-reveal`

Muc dich:

- Admin vao trang nhin ngay he thong co bao nhieu entity can review.
- Root admin thay ro phan quan ly admin rieng.
- Bang entity de scan va thao tac hon.

## 12.3 Nang cap trang detail admin entity

File:

```text
frontend/src/app/admin/entities/[type]/[id]/page.tsx
```

Da lam:

- Doi layout thanh 2 cot:
  - Cot trai: thong tin entity va duplicate candidates.
  - Cot phai: ly do thao tac, action buttons, merge form.
- Them badge trang thai:
  - KG status
  - Verification status
  - Scope
- Them cac action button co icon:
  - Verify entity
  - Reject entity
  - Disable KG
  - Retry KG sync
  - Merge vao target
- Them GSAP ScrollTrigger reveal:
  - `.admin-detail-reveal`

Muc dich:

- Admin bấm vao mot entity co the review thong tin va thao tac trong mot man hinh ro rang.
- Cac hanh dong nguy hiem nhu reject/disable/merge duoc gom trong panel rieng.

## 12.4 Kiem tra

Da chay:

```powershell
cd frontend
npm.cmd run typecheck
```

Ket qua:

```text
PASS
```

## 12.5 Ghi chu con lai

- Chua them Playwright screenshot de test hieu ung va responsive.
- Chua them tab rieng bang component `Tabs`; hien tai root admin controls nam duoi entity queue.
- Neu muon UI admin production hon nua, co the them:
  - filter theo `entity_verification_status`
  - search entity
  - confirm dialog truoc reject/disable/merge
  - toast success/error

# Phase 13 - Tach register thanh onboarding nhieu buoc (2026-05-27)

Muc tieu: khong bat user nhap qua nhieu thong tin ngay luc dang ky. Register chi thu thap cac field can thiet de tao account, tao/link entity nghiep vu, chay duplicate matching/provisional KG sync va co du du lieu ban dau de recommendation. Cac thong tin dai hoac co the bo sung sau se de trong trang Profile.

## 13.1 Cap nhat luong register frontend

File:

```text
frontend/src/app/auth/register/page.tsx
```

Da lam:

- Chia form dang ky thanh 3 buoc:
  - Buoc 1: chon doi tuong `expert`, `enterprise`, `funder`.
  - Buoc 2: nhap thong tin bat buoc gom ho ten/ten don vi, to chuc, email, password.
  - Buoc 3: chon `Chu de nghien cuu / linh vuc quan tam` tu danh muc chuan va co option `Khac`.
- Them progress theo buoc de user biet dang o dau trong qua trinh onboarding.
- Them validate tung buoc:
  - Khong cho qua buoc account neu thieu ten/email/password.
  - Mat khau xac nhan phai khop.
  - Neu khong chon topic chuan thi phai nhap topic custom khi chon `Khac`.
- Payload gui ve backend van giu tuong thich voi API hien co:
  - `email`, `password`, `full_name`, `role`, `organization`
  - `research_interests`
  - `custom_research_topics`
  - cac field phu nhu `phone`, `address`, `bio`, `username` gui rong de user bo sung sau trong Profile.

Muc dich:

- Giam ma sat luc dang ky.
- Van dam bao co du du lieu quan trong nhat cho entity va recommendation.
- Tranh nhap tu do qua nhieu lam KG/recommendation kho chuan hoa.

## 13.2 Them hieu ung GSAP ScrollTrigger cho register

File:

```text
frontend/src/app/auth/register/page.tsx
```

Da lam:

- Dung `gsap` va `ScrollTrigger` de reveal cac khoi register khi vao trang/cuon trang.
- Dung animation nhe cho `.register-step` khi chuyen buoc.

Muc dich:

- Lam trang dang ky giong onboarding chinh thuc hon.
- Tao cam giac tung lop thong tin ro rang, khong con la mot form dai.

## 13.3 Chuan hoa danh muc topic hien thi

File:

```text
frontend/src/lib/research-topics.ts
```

Da lam:

- Sua lai label topic bi loi encoding.
- Dung label ASCII ro nghia:
  - `AI trong y te`
  - `Xu ly ngon ngu tu nhien`
  - `Khoa hoc du lieu`
  - `Nang luong tai tao`
  - `San xuat thong minh`
  - `An toan thong tin`

Muc dich:

- UI register/profile khong con hien chu loi ma hoa.
- Topic option thong nhat hon voi du lieu KG/recommendation.

## 13.4 Kiem tra

Da chay:

```powershell
cd frontend
npm.cmd run typecheck
```

Ket qua:

```text
PASS
```

## 13.5 Ghi chu con lai

- Trang Profile da co cac field de user bo sung sau: username, organization, phone, address, bio, research topics va custom topics.
- Mot so text trong Profile cu van co dau hieu loi encoding o cac phan khac; can co mot pass rieng de lam sach toan bo UI text neu muon polish truoc demo.

# Phase 14 - Bo sung skill/location vao register va profile edit mode (2026-05-27)

Muc tieu: register khong chi tao account ma phai lay du cac tin hieu quan trong cho recommendation ban dau. Profile khong nen hien nhu form dang chinh sua lien tuc; user phai bam `Chinh sua` moi bat dau thay doi thong tin.

## 14.1 Register them buoc skill/location

File:

```text
frontend/src/app/auth/register/page.tsx
frontend/src/lib/profile-options.ts
frontend/src/lib/api.ts
```

Da lam:

- Chuyen register tu 3 buoc thanh 4 buoc:
  - Chon doi tuong.
  - Thong tin bat buoc.
  - Skill & location.
  - Chu de nghien cuu.
- Them danh muc skill chuan:
  - Python
  - Machine Learning
  - Deep Learning
  - Computer Vision
  - NLP
  - Knowledge Graph
  - Data Analysis
  - IoT
  - Cybersecurity
  - Cloud Computing
  - Project Management
  - R&D Commercialization
- Them location dang select co cap:
  - Country mac dinh `VN`.
  - Tinh/thanh.
  - Quan/huyen theo tinh/thanh.
- Validate register:
  - Bat buoc chon it nhat 1 skill.
  - Bat buoc co country/province/district.
  - Van bat buoc co research topic hoac topic custom.

Muc dich:

- Skill/location tao them tin hieu matching cho PGPR/XAI.
- Location duoc chuan hoa thanh country/province/district thay vi user nhap text tu do.

## 14.2 Backend luu skill/location vao account va entity

File:

```text
backend/models/schemas.py
backend/services/auth_service.py
backend/repositories/auth_repo.py
```

Da lam:

- Them field vao `RegisterRequest`, `ProfileUpdateRequest`, `UserPublic`:
  - `country`
  - `province`
  - `district`
  - `skills`
- Khi register tao role entity `expert/enterprise/funder`, entity se luu:
  - `country`
  - `province`
  - `district`
  - `location`
  - `skills`
- Them `AuthRepository.update_role_entity_from_user()` de khi user sua Profile thi entity nghiep vu duoc cap nhat theo.

Muc dich:

- Du lieu user va entity khong bi lech nhau.
- Recommendation engine sau nay lay entity tu Mongo/Neo4j van co skill/location.

## 14.3 Sync skill/location sang Neo4j provisional KG

File:

```text
backend/services/provisional_kg_sync_service.py
backend/repositories/pgpr_graph_repo.py
```

Da lam:

- Them `upsert_skill_relationships()`:
  - Expert -> `HAS_SKILL` -> Skill
  - Enterprise -> `USES_SKILL` -> Skill
  - Funder -> `SUPPORTS_SKILL` -> Skill
  - Project -> `REQUIRES_SKILL` -> Skill
- Them `upsert_location_relationship()`:
  - Entity -> `LOCATED_IN` -> Location
- Khi sync provisional entity, he thong sync them:
  - topic relationships
  - skill relationships
  - location relationship
- Khi user update Profile, backend cap nhat role entity va goi sync lai KG neu co linked entity.

Muc dich:

- User moi co the dung recommendation tot hon ngay sau register.
- XAI/graph co them path qua Skill va Location, khong chi dua vao ResearchTopic.

## 14.4 Profile co che do xem/chinh sua

File:

```text
frontend/src/app/profile/page.tsx
```

Da lam:

- Profile mac dinh o che do xem.
- Them panel trang thai:
  - `Profile dang o che do xem`
  - nut `Chinh sua`
- Khi bam `Chinh sua`, cac input/select/checkbox moi cho thay doi.
- Them nut `Huy` de quay lai du lieu user hien tai trong local auth state.
- Nut `Luu thay doi` chi active khi dang edit.
- Them UI sua:
  - country
  - province
  - district
  - skills

Muc dich:

- Profile giong trang ca nhan that hon, khong phai mot form sua lien tuc.
- User chu dong bat dau chinh sua, giam nguy co sua nham.

## 14.5 Kiem tra

Da chay:

```powershell
cd backend
python -m compileall main.py api services repositories models
```

Ket qua:

```text
PASS
```

Da chay:

```powershell
cd frontend
npm.cmd run typecheck
```

Ket qua:

```text
PASS
```

## 14.6 Ghi chu con lai

- Hien tai skill/location sync bang MERGE them relation moi, chua co buoc xoa relation cu neu user bo chon skill/location trong Profile.
- Location option moi la danh muc MVP, can mo rong neu demo can nhieu tinh/thanh hon.
- Custom topic van duoc luu rieng va can admin map/duyet truoc khi dua public vao KG.

# Phase 15 - Dung country-state-city va them ky nang khac (2026-05-27)

Muc tieu: thay danh muc location hard-code bang package co san de user chon quoc gia/vung lanh tho/tinh-thanh/thanh pho linh hoat hon. Dong thoi them option `Khac` cho skill giong `Chu de nghien cuu` de user nhap ky nang chua co trong danh muc chuan.

## 15.1 Cai package country-state-city

Da chay:

```powershell
cd frontend
npm.cmd i country-state-city
```

File cap nhat:

```text
frontend/package.json
frontend/package-lock.json
```

Muc dich:

- Lay danh sach country/state/city tu package thay vi tu hard-code.
- De mo rong dia diem cho user ngoai Vietnam neu can.

## 15.2 Cap nhat helper location

File:

```text
frontend/src/lib/profile-options.ts
```

Da lam:

- Import:
  - `Country`
  - `State`
  - `City`
- Tao helper:
  - `countryOptions()`
  - `provinceOptions(countryCode)`
  - `districtOptions(countryCode, stateCode)`
  - `firstProvince(countryCode)`
  - `firstDistrict(countryCode, stateCode)`
- Giu ten field frontend/backend hien tai:
  - `country`
  - `province`
  - `district`

Muc dich:

- Khong lam vo schema backend hien co.
- Nhung UI location khong con bi gioi han trong danh sach tinh/thanh hard-code.

## 15.3 Register dung country-state-city

File:

```text
frontend/src/app/auth/register/page.tsx
```

Da lam:

- Country select lay tu `countryOptions()`.
- Province/state select lay theo country dang chon.
- District/city select lay theo country + province/state dang chon.
- Neu mot country khong co state/city trong package, UI dung fallback `No state/region` hoac `No city/district` de form khong bi ket.
- Khi doi country:
  - tu dong chon province dau tien cua country do.
  - tu dong chon city dau tien cua province do.
- Khi doi province:
  - tu dong chon city dau tien cua province moi.

Muc dich:

- Location user nhap co cau truc hon.
- Giam loi nhap tu do khi sync sang KG.

## 15.4 Them skill Khac

File frontend:

```text
frontend/src/app/auth/register/page.tsx
frontend/src/app/profile/page.tsx
frontend/src/lib/api.ts
```

File backend:

```text
backend/models/schemas.py
backend/services/auth_service.py
backend/repositories/auth_repo.py
backend/services/provisional_kg_sync_service.py
```

Da lam:

- Them field:

```text
custom_skills: List[str]
```

- Register:
  - Co checkbox `Khac` trong phan skill.
  - Neu khong chon skill chuan thi phai nhap skill khac.
  - Gui `custom_skills` ve backend.
- Profile:
  - Co checkbox `Khac` trong phan skill.
  - Khi bat `Khac`, hien input nhap nhieu skill cach nhau bang dau phay.
  - Khi tat `Khac`, clear `custom_skills`.
- Backend:
  - Luu `custom_skills` trong user.
  - Copy `custom_skills` vao entity `expert/enterprise/funder`.
  - Provisional KG sync gop `skills + custom_skills` de tao relation voi node `Skill`.

Muc dich:

- User co the khai bao ky nang chua nam trong danh muc chuan.
- He thong van giu du lieu custom rieng de admin co the chuan hoa sau.

## 15.5 Kiem tra

Da chay:

```powershell
cd backend
python -m compileall main.py api services repositories models
```

Ket qua:

```text
PASS
```

Da chay:

```powershell
cd frontend
npm.cmd run typecheck
```

Ket qua:

```text
PASS
```

## 15.6 Ghi chu con lai

- `country-state-city` cung cap state/city theo ma ISO; field backend van ten `province/district` de giu tuong thich, nhung y nghia thuc te luc nay la state/city.
- Can them UI/admin mapping neu muon gop custom skill vao danh muc skill chuan sau nay.
- Van chua co logic xoa relation skill/location cu trong Neo4j khi user bo chon skill/location.

# Phase 16 - Toi uu UX Profile: co ban / chi tiet / chinh sua (2026-05-27)

Muc tieu: Profile khong hien nhu mot form dai ngay tu dau. User mac dinh chi thay thong tin co ban, co nut xem chi tiet rieng, va chi khi bam `Chinh sua` moi co the cap nhat cac field trong profile.

## 16.1 Profile mac dinh chi hien thong tin co ban

File:

```text
frontend/src/app/profile/page.tsx
```

Da lam:

- Trang Profile mac dinh hien card thong tin co ban:
  - Ten / ten don vi
  - Email
  - Role
  - To chuc
  - Dia diem
  - Account status
  - Entity status
  - KG sync status
  - Trust weight
  - Linked entity / scope / match
- Khong hien toan bo form chi tiet ngay khi vao trang.

Muc dich:

- User nhin trang profile gon va de hieu hon.
- Thong tin KG quan trong van hien ro de user biet trang thai ho so.

## 16.2 Them nut xem thong tin chi tiet

Da lam:

- Them nut `Xem thong tin chi tiet`.
- Khi bam, hien toan bo form chi tiet o che do read-only.
- Nut co the doi thanh `An chi tiet` de thu gon lai.

Muc dich:

- User co the xem day du profile khi can.
- Khong ep user phai nhin form dai neu chi muon xem thong tin co ban.

## 16.3 Chinh sua moi mo input

Da lam:

- Nut `Chinh sua` se:
  - bat `isEditing = true`
  - tu dong mo phan chi tiet
  - cho phep sua cac input/select/checkbox.
- Nut `Huy chinh sua` se:
  - quay lai du lieu user hien tai trong auth state
  - tat edit mode
  - reset trang thai dirty.

Muc dich:

- Giam nguy co user sua nham.
- Tach ro che do xem va che do cap nhat.

## 16.4 Nut luu chi hien khi co thay doi

Da lam:

- Bo nut `Luu thay doi` khoi header.
- Nut `Luu thay doi` chi hien o cuoi form khi:

```text
isEditing = true
isDirty = true
```

- Moi thay doi field deu goi `updateProfile()` va set `isDirty = true`.

Muc dich:

- UI dung mong doi cua user: co sua thi moi hien nut luu.
- Nut luu nam cuoi form, dung luong nhap thong tin dai.

## 16.5 Cac field user co the sua

Trong edit mode, user co the sua cac field profile da thiet ke cho luong MongoDB hien tai:

- full_name
- username
- role
- organization
- phone
- address
- country
- province/state
- district/city
- skills
- custom_skills
- research_interests
- custom_research_topics
- bio

Ghi chu:

- Email bi disable vi day la dinh danh account.
- Trang thai account/entity/KG khong cho user sua; cac field nay thuoc admin/system.

## 16.6 Kiem tra

Da chay:

```powershell
cd frontend
npm.cmd run typecheck
```

Ket qua:

```text
PASS
```

# Phase 17 - Profile hien field tuy theo doi tuong (2026-05-27)

Muc tieu: profile khong dung mot bo field chung cho tat ca user. Khi user la `expert`, `enterprise` hoac `funder`, phan chi tiet/chinh sua se hien cac nhom thong tin phu hop voi doi tuong do.

## 17.1 Them profile_data de luu thong tin mo rong

File backend:

```text
backend/models/schemas.py
backend/services/auth_service.py
backend/repositories/auth_repo.py
```

Da lam:

- Them field:

```text
profile_data: Dict[str, Any]
```

- `UserPublic` tra ve `profile_data`.
- `RegisterRequest` va `ProfileUpdateRequest` chap nhan `profile_data`.
- Khi tao/cap nhat role entity, Mongo entity luu them `profile_data`.

Muc dich:

- Khong lam schema account bi phang thanh rat nhieu field.
- Van luu duoc thong tin rieng theo tung loai doi tuong trong MongoDB.
- Sau nay admin/backend co the map cac field nay sang Neo4j/feature recommendation theo tung phase.

## 17.2 Frontend profile show field theo role

File:

```text
frontend/src/app/profile/page.tsx
frontend/src/lib/api.ts
```

Da lam:

- Them `profile_data?: Record<string, unknown>` vao type `UserProfile`.
- Them cau hinh `roleSections` cho:
  - `expert`
  - `enterprise`
  - `funder`
- Moi role co cac section rieng.

## 17.3 Expert fields

Profile expert hien them cac nhom:

- Thong tin ca nhan:
  - nam sinh
  - gioi tinh
  - quoc tich
  - ngon ngu uu tien
- Dinh danh nghien cuu:
  - ORCID
  - ResearcherID
  - Scopus ID
- Hoc thuat va nang luc:
  - hoc ham/hoc vi
  - don vi hien tai
  - phong lab/nhom nghien cuu
  - so cong bo
  - H-index
  - so trich dan

## 17.4 Enterprise fields

Profile enterprise hien them cac nhom:

- Thong tin doanh nghiep:
  - ma so thue
  - nam thanh lap
  - nganh/lĩnh vuc
  - quy mo
  - doanh thu
  - so nhan su
- Lien he va R&D:
  - nguoi dai dien phap ly
  - email lien he
  - huong R&D
  - nhu cau cong nghe
  - TRL mong muon
- Dau tu va chuyen giao:
  - innovation index
  - tai san da thuong mai hoa
  - project da tham gia

## 17.5 Funder fields

Profile funder hien them cac nhom:

- Thong tin nha tai tro:
  - loai nha tai tro
  - nang luc ngan sach
  - nguoi lien he
  - email lien he
- Chien luoc tai tro:
  - huong tai tro
  - linh vuc uu tien
  - khoang TRL uu tien
  - muc tai tro dien hinh
  - tieu chi hop le
- Chuong trinh va tac dong:
  - danh sach chuong trinh
  - project da tai tro
  - ty le project thanh cong
  - ty le thuong mai hoa

## 17.6 Luu nested profile_data

Da lam:

- Them helper `getNestedValue()`.
- Them helper `setNestedValue()`.
- Field co key dang dot path, vi du:

```text
academic_metrics.h_index
funding_strategy.focus_sectors
rd_profile.technology_needs
```

- Khi user sua, frontend cap nhat nested object trong `profile_data`.

Muc dich:

- Du lieu luu trong MongoDB gan voi thiet ke object cua tung doi tuong.
- Khong can tao hang chuc field phang trong schema API.

## 17.7 Kiem tra

Da chay:

```powershell
cd backend
python -m compileall main.py api services repositories models
```

Ket qua:

```text
PASS
```

Da chay:

```powershell
cd frontend
npm.cmd run typecheck
```

Ket qua:

```text
PASS
```

## 17.8 Ghi chu con lai

- Moi role da co cac field quan trong, nhung chua copy 100% tat ca field trong ban thiet ke anh vi qua dai.
- Project profile hien tai van o luong `Create Project`/`My Projects`, chua dua vao trang Profile user.
- Neu can day du hon, co the tiep tuc bo sung field vao `roleSections` ma khong can doi backend vi da co `profile_data`.

# Phase 18 - Them social links luc register va uu tien nhap thong tin chuyen gia co ban (2026-05-27)

Muc tieu: khi dang ky, user co the nhap cac social/academic links de he thong ve sau tu dong crawl/enrich data. Trong Profile, phan chinh sua uu tien cac thong tin co ban theo doi tuong truoc khi den skill/topic recommendation.

## 18.1 Register them social/academic links

File:

```text
frontend/src/app/auth/register/page.tsx
frontend/src/lib/api.ts
backend/models/schemas.py
backend/services/auth_service.py
backend/repositories/auth_repo.py
```

Da lam:

- Them cac field optional trong register:
  - Website / profile URL
  - LinkedIn
  - Google Scholar
  - ORCID
- Frontend gui ve backend trong object:

```json
{
  "social_links": {
    "website": "...",
    "linkedin": "...",
    "google_scholar": "...",
    "orcid": "..."
  }
}
```

- Backend luu `social_links` vao user va copy sang role entity.

Muc dich:

- User khong can nhap het profile ngay luc register.
- He thong co link nguon de build pipeline crawl/enrichment sau nay.

## 18.2 Profile cho sua social links

File:

```text
frontend/src/app/profile/page.tsx
```

Da lam:

- Them cac input social links trong Profile detail/edit mode:
  - Website / profile URL
  - LinkedIn
  - Google Scholar
  - ORCID
- Them helper `updateSocialLink()`.

Muc dich:

- User co the bo sung/sua link sau register.
- Social links tiep tuc nam trong profile, san sang cho pipeline auto-fetch.

## 18.3 Uu tien thong tin chuyen gia/doanh nghiep/nha tai tro co ban truoc

File:

```text
frontend/src/app/profile/page.tsx
```

Da lam:

- Di chuyen section `Thong tin rieng cho {role}` len truoc skill/topic.
- Khi user bam chinh sua, cac field rieng theo role se xuat hien truoc:
  - Expert: thong tin ca nhan, dinh danh nghien cuu, hoc thuat/nang luc.
  - Enterprise: thong tin doanh nghiep, lien he/R&D, dau tu/chuyen giao.
  - Funder: thong tin nha tai tro, chien luoc tai tro, chuong trinh/tac dong.
- Skill/topic recommendation nam sau phan profile chuyen mon.

Muc dich:

- User nhap thong tin nghiep vu co ban truoc.
- Skill/topic van quan trong cho recommendation, nhung khong lap tuc lan at phan ho so chuyen gia.

## 18.4 Kiem tra

Da chay:

```powershell
cd backend
python -m compileall main.py api services repositories models
```

Ket qua:

```text
PASS
```

# Phase 19 - Dieu chinh field co ban cua Expert profile (2026-05-27)

Muc tieu: lam phan chinh sua profile Expert gon va dung dang input hon. Bo cac field trung/lien quan den dia diem da co o phan location, va chuan hoa cac field nen chon theo option.

## 19.1 Bo field khong can trong Expert basic info

File:

```text
frontend/src/app/profile/page.tsx
```

Da lam:

- Bo `Quoc tich`.
- Bo `Ngon ngu uu tien`.
- Bo field `Dia chi` chung trong form profile, vi location da co:
  - Country
  - Tinh/Thanh
  - Quan/Huyen

Muc dich:

- Tranh trung lap thong tin dia diem.
- Giam so field user phai nhin thay khi bo sung profile.

## 19.2 Doi nam sinh sang date picker

Da lam:

- Doi field:

```text
basic_info.birth_year
```

thanh:

```text
basic_info.birth_date
```

- Render bang input:

```html
type="date"
```

Muc dich:

- Khi user bam vao co UI chon ngay/thang/nam giong lich cua browser.
- Du lieu ngay sinh day du hon nam sinh.

## 19.3 Gioi tinh va hoc ham/hoc vi dung option

Da lam:

- Them `kind = "select"` cho field dong trong `roleSections`.
- Gioi tinh co option:
  - Nam
  - Nu
  - Khac
  - Khong muon cung cap
- Hoc ham/hoc vi co option:
  - Cu nhan/Ky su
  - Thac si
  - Tien si
  - Pho giao su
  - Giao su
  - Khac

Muc dich:

- Du lieu nhap vao thong nhat hon.
- Giam loi do user go tu do.

## 19.4 Kiem tra

Da chay:

```powershell
cd frontend
npm.cmd run typecheck
```

Ket qua:

```text
PASS
```

# Phase 20 - Fix header va polish Profile voi GSAP ScrollTrigger (2026-05-27)

Muc tieu: sua header bi roi layout/brand xuong dong xau, dong thoi lam trang Profile gon va co hieu ung reveal nhe khi cuon.

## 20.1 Fix Navbar/Header

File:

```text
frontend/src/components/navigation/navbar.tsx
```

Da lam:

- Doi container header sang grid:

```text
brand | nav | account/status
```

- Brand co width on dinh hon, icon khong co lai, text dung `truncate`.
- Nav item co `shrink-0` va vung nav co `overflow-x-auto` de khong chen ep brand/account khi man hinh hep.
- Account/user name co `max-width` va `truncate` de khong day layout.
- FastAPI status duoc rut gon va truncate.
- Them shadow nhe cho header de tach khoi noi dung.

Muc dich:

- Khong con hien brand bi vo dong nhu anh chup.
- Header phu hop voi app dashboard hon, nhin gon va chuyen nghiep hon.

## 20.2 Them GSAP ScrollTrigger cho Profile

File:

```text
frontend/src/app/profile/page.tsx
```

Da lam:

- Import `gsap` va `ScrollTrigger`.
- Register plugin:

```ts
gsap.registerPlugin(ScrollTrigger)
```

- Them class animation:
  - `.profile-shell`
  - `.profile-reveal`
  - `.profile-detail`
  - `.profile-detail-reveal`
- Header/profile summary/warning/detail fields reveal nhe khi vao viewport.

Muc dich:

- Trang profile co cam giac chinh chu hon.
- Hieu ung nhe, khong lam roi UX cua dashboard.

## 20.3 Polish profile card/detail

Da lam:

- Them `shadow-sm` cho summary card va detail card.
- Gan reveal cho cac nhom thong tin quan trong.
- Giu layout gọn: thong tin co ban o tren, thong tin chi tiet o duoi khi user mo.

## 20.4 Kiem tra

Da chay:

```powershell
cd frontend
npm.cmd run typecheck
```

Ket qua:

```text
PASS
```

Da chay:

```powershell
cd frontend
npm.cmd run typecheck
```

Ket qua:

```text
PASS
```

# Phase 24 - Chuan hoa luu entity theo schema add_data (2026-05-27)

Ghi chu: muc chi tiet da duoc ghi trong file nay o phan "Chuan hoa luu entity theo schema add_data". Phase nay duoc danh dau lai o cuoi nhat ky de the hien dung thu tu cong viec moi nhat.

Da lam:

- Backend khong con tao entity user moi theo schema phang rieng.
- Expert/Enterprise/Funder moi duoc luu theo cac khoi nested giong data trong `add_data`: `basic_info`, `contact_info`, `research_capacity`, `rd_profile`, `funding_strategy`, `relations`, `governance`.
- Project user tao moi duoc luu theo schema project nested: `basic_info`, `requirements_and_timeline`, `rd_profile`, `relations`, `follow_up_opportunities`, `governance`.
- Chi cac field he thong can thiet moi nam o top-level: `user_id`, `owner_id`, `source`, `entity_verification_status`, `kg_sync_status`, `visibility`, `participation_scope`, `trust_weight`, `duplicate_candidates`, `matched_existing_entity_id`, `kg_schema_version`, `provisional_sync_version`, timestamps.
- Profile/API/Admin/KG sync duoc cap nhat de doc nested fields, dong thoi van fallback duoc data cu dang co field phang.

Lam the de:

- Giu du lieu MongoDB thong nhat voi pipeline crawl/seed/convert KG.
- Tranh viec user-created data va crawled data co hai schema khac nhau.
- Bao toan logic Provisional KG Sync, duplicate matching, admin review va PGPR recommendation.

Kiem tra:

```powershell
cd backend
python -m compileall main.py api services repositories models
```

Ket qua:

```text
PASS
```
