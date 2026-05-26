# Checklist refactor PGPR theo kien truc da chot

## 1. Muc tieu refactor

Kien truc da chot:

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

Muc tieu:

- Router chi nhan request va tra response.
- Service Layer xu ly workflow nghiep vu.
- MongoRepository chi phu trach du lieu entity/profile trong MongoDB.
- PGPRRecommender/XAI phu trach recommendation va explanation.
- PGPRRecommender khong truy cap Neo4j driver truc tiep.
- PGPRRecommender lay graph/path/candidate data thong qua `PGPRGraphRepository`.
- `PGPRGraphRepository` la lop duy nhat chua query Neo4j phuc vu PGPR.

## 2. Nguyen tac khi refactor

- Khong sua tat ca trong mot lan.
- Moi buoc refactor xong phai test import/app.
- Giu tuong thich tam thoi neu PGPRRecommender dang phu thuoc `self.driver`.
- Uu tien tao adapter/repository truoc, chuyen query sau.
- Neu khong chac query nao dang dung, giu lai va chuyen sau.
- Khong thay doi scoring/ranking khi dang refactor database access.
- Refactor xong phai cap nhat tai lieu kien truc.

## 3. Phase 0 - Khao sat hien trang

Muc tieu: biet chinh xac PGPR dang truy cap Neo4j o dau.

Checklist:

- [x] Tim tat ca cho dung `GraphDatabase` trong `pgpr/`.
- [x] Tim tat ca cho dung `driver.session`.
- [x] Tim tat ca cho dung `session.run`.
- [x] Liet ke cac ham query Neo4j trong `pgpr_recommendation.py`.
- [x] Liet ke cac ham query Neo4j trong `pgpr_env.py`.
- [x] Liet ke cac ham query Neo4j trong `pgpr_kg.py`.
- [x] Phan loai query thanh cac nhom:
  - [x] Health/connection.
  - [x] Neighbor expansion.
  - [x] Reasoning paths.
  - [x] Candidate retrieval.
  - [x] Entity/profile info.
  - [x] Training/build KG.

Lenh goi y:

```powershell
Select-String -Path pgpr\*.py -Pattern "GraphDatabase|driver.session|session.run"
```

Ket qua can co:

- [x] Danh sach cac ham can refactor.
- [x] Quyet dinh ham nao chuyen truoc, ham nao de sau.

## 4. Phase 1 - Tao PGPRGraphRepository

Muc tieu: tao repository/adapter rieng cho Neo4j phuc vu PGPR.

File can tao:

```text
backend/repositories/pgpr_graph_repo.py
```

Class can co:

```python
class PGPRGraphRepository:
    def __init__(self, driver=None): ...
    def close(self): ...
    def check_health(self) -> bool: ...
    def run_read(self, query: str, **params): ...
    def run_write(self, query: str, **params): ...
```

Checklist:

- [x] Tao file `repositories/pgpr_graph_repo.py`.
- [x] Load `.env` bang `load_dotenv(find_dotenv())`.
- [x] Doc `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` tu environment.
- [x] Ho tro inject `driver` tu ngoai vao.
- [x] Neu khong co driver thi tu tao driver.
- [x] Co co che biet repository co so huu driver hay khong.
- [x] Tao `check_health()`.
- [x] Tao `run_read()`.
- [x] Tao `run_write()` neu can.
- [x] Tao `close()`.
- [x] Dam bao return data da convert ve `dict`.

Test sau Phase 1:

```powershell
python -m compileall repositories
```

Ket qua can co:

- [x] Compile pass.
- [x] Import `PGPRGraphRepository` khong loi.

## 5. Phase 2 - Inject PGPRGraphRepository vao PGPRRecommender

Muc tieu: PGPRRecommender nhan graph repository tu ben ngoai.

File can sua:

```text
backend/pgpr/pgpr_recommendation.py
```

Huong sua:

```python
def __init__(
    self,
    ...,
    graph_repo: Optional[PGPRGraphRepository] = None,
    driver: Optional[Any] = None,
):
    self.graph_repo = graph_repo or PGPRGraphRepository(driver=driver)
    self.driver = self.graph_repo.driver
```

Checklist:

- [x] Import `PGPRGraphRepository`.
- [x] Them param `graph_repo` vao `PGPRRecommender.__init__`.
- [x] Neu co `graph_repo` thi dung graph repo do.
- [x] Neu khong co `graph_repo` thi tao moi `PGPRGraphRepository`.
- [x] Giu `self.driver` tam thoi de cac ham cu chua vo.
- [x] Sua `_owns_driver` thanh co che phu hop voi graph repo.
- [x] Sua `close()` de khong dong shared driver sai cach.
- [x] Dam bao `_env = KGEnv(..., driver=self.driver, ...)` van chay.

Test sau Phase 2:

```powershell
python -m compileall pgpr repositories
```

Ket qua can co:

- [x] Compile pass.
- [x] Tao `PGPRRecommender()` khong loi import.

## 6. Phase 3 - Sua Dependency Injection

Muc tieu: toan app dung chung singleton `PGPRGraphRepository`.

File can sua:

```text
backend/api/deps.py
```

Can them:

```python
_pgpr_graph_repo = None

def get_pgpr_graph_repo() -> PGPRGraphRepository:
    global _pgpr_graph_repo
    if _pgpr_graph_repo is None:
        _pgpr_graph_repo = PGPRGraphRepository()
    return _pgpr_graph_repo
```

Sua `get_pgpr_recommender()`:

```python
_pgpr_recommender = PGPRRecommender(
    graph_repo=get_pgpr_graph_repo(),
    max_path_length=5,
    gamma=0.99,
    top_k_paths=10,
    enable_cache=True,
)
```

Checklist:

- [x] Import `PGPRGraphRepository`.
- [x] Tao global `_pgpr_graph_repo`.
- [x] Tao dependency `get_pgpr_graph_repo`.
- [x] Inject graph repo vao `PGPRRecommender`.
- [x] Khong tao nhieu Neo4j driver moi request.
- [x] App import duoc.

Test sau Phase 3:

```powershell
python -m compileall main.py api pgpr repositories services
```

```powershell
python - <<'PY'
from main import app
print("app import ok")
PY
```

Ket qua can co:

- [x] Compile pass.
- [x] App import pass.
- [x] `/openapi.json` pass.

## 7. Phase 4 - Chuyen query reasoning paths

Muc tieu: `find_reasoning_paths` khong query Neo4j truc tiep trong PGPRRecommender nua.

File can sua:

```text
backend/repositories/pgpr_graph_repo.py
backend/pgpr/pgpr_recommendation.py
```

Them vao `PGPRGraphRepository`:

```python
def find_reasoning_paths(
    self,
    source_id: str,
    source_type: str,
    target_id: str,
    target_type: str,
    max_path_length: int,
    limit: int,
):
    ...
```

Checklist:

- [x] Copy query reasoning path tu `PGPRRecommender.find_reasoning_paths`.
- [x] Dua query vao `PGPRGraphRepository.find_reasoning_paths`.
- [x] Repository chi tra raw path records/dicts.
- [x] PGPRRecommender giu logic scoring/dedup/format path neu can.
- [x] PGPRRecommender.find_reasoning_paths goi `self.graph_repo.find_reasoning_paths(...)`.
- [x] Khong thay doi output public cua `find_reasoning_paths`.

Test sau Phase 4:

- [x] Compile pass.
- [x] Test `POST /api/v1/recommendations/policy` voi Project -> Expert.
- [x] Response van co `reasoning_paths`.

## 8. Phase 5 - Chuyen query entity info

Muc tieu: cac ham lay thong tin entity tu Neo4j di qua graph repository.

Ham can chuyen truoc:

```text
PGPRRecommender._get_expert_info
PGPRRecommender._get_generic_entity_info
```

Them vao `PGPRGraphRepository`:

```python
def get_expert_info(self, expert_id: str) -> dict: ...
def get_generic_entity_info(self, entity_id: str, entity_type: str) -> dict: ...
```

Checklist:

- [x] Chuyen query `_get_expert_info`.
- [x] Chuyen query `_get_generic_entity_info`.
- [x] PGPRRecommender chi goi graph repo.
- [x] Output khong doi.

Test sau Phase 5:

- [x] Compile pass.
- [x] Recommendation response van co `name`.
- [x] Recommendation response van co metadata/extra neu truoc do co.

## 9. Phase 6 - Chuyen candidate queries theo nhom

Muc tieu: chuyen dan cac query lay candidate tu PGPRRecommender sang PGPRGraphRepository.

### 9.1 Nhom Project source

Ham can xu ly:

- [x] `_find_candidate_experts_for_project`
- [x] `_find_candidate_funders_for_project`
- [x] `_find_candidate_enterprises_for_project`
- [x] `_find_candidate_projects_for_project`

Test:

- [x] Project -> Expert.
- [x] Project -> Funder.
- [x] Project -> Enterprise.
- [x] Project -> Project.

### 9.2 Nhom Expert source

Ham can xu ly:

- [x] `_find_candidate_projects_for_expert`
- [x] `_find_candidate_funders_for_expert`
- [x] `_find_candidate_enterprises_for_expert`
- [x] `_find_candidate_experts_for_expert`

Test:

- [x] Expert -> Project.
- [x] Expert -> Funder.
- [x] Expert -> Enterprise.
- [x] Expert -> Expert.

### 9.3 Nhom Enterprise source

Ham can xu ly:

- [x] `_find_candidate_experts_for_enterprise`
- [x] `_find_candidate_projects_for_enterprise`
- [x] `_find_candidate_funders_for_enterprise`
- [x] `_find_candidate_enterprises_for_enterprise`

Test:

- [x] Enterprise -> Expert.
- [x] Enterprise -> Project.
- [x] Enterprise -> Funder.
- [x] Enterprise -> Enterprise.

### 9.4 Nhom Funder source

Ham can xu ly:

- [x] `_find_candidate_experts_for_funder`
- [x] `_find_candidate_projects_for_funder`
- [x] `_find_candidate_enterprises_for_funder`

Test:

- [x] Funder -> Expert.
- [x] Funder -> Project.
- [x] Funder -> Enterprise.

## 10. Phase 7 - Xu ly KGEnv va policy-guided paths

Muc tieu: dam bao policy-guided inference cung khong phu thuoc driver truc tiep neu co query DB.

Can kiem tra:

- [x] `KGEnv` co dung `driver.session` khong.
- [x] `KGEnv.get_neighbors` co lay tu `kg.adj_list` hay query Neo4j.
- [x] `policy_guided_paths` co query Neo4j truc tiep khong.
- [x] Neu co query truc tiep, chuyen sang `PGPRGraphRepository`.
- [x] Neu chi dung in-memory KG thi giu nguyen.

Ket qua mong muon:

```text
Policy-guided path reasoning van hoat dong.
Driver/session access neu co se nam trong repository.
```

## 11. Phase 8 - Xoa direct Neo4j access khoi PGPRRecommender

Muc tieu: PGPRRecommender khong con query database truc tiep.

Checklist:

- [x] Search `GraphDatabase` trong `pgpr_recommendation.py` khong con can thiet.
- [x] Search `driver.session` trong `pgpr_recommendation.py`.
- [x] Search `session.run` trong `pgpr_recommendation.py`.
- [x] Neu con query, chuyen sang `PGPRGraphRepository`.
- [x] Neu con `self.driver`, chi giu neu can cho KGEnv tam thoi.
- [x] Cap nhat comment/docstring.

Lenh kiem tra:

```powershell
Select-String -Path pgpr\pgpr_recommendation.py -Pattern "GraphDatabase|driver.session|session.run"
```

Ket qua can co:

- [x] Khong con query Neo4j truc tiep trong PGPRRecommender, hoac chi con cac diem legacy duoc ghi chu ro.

## 12. Phase 9 - Test he thong sau refactor

### 12.1 Test compile/import

```powershell
python -m compileall main.py api repositories services models core pgpr
```

Checklist:

- [x] Compile pass.
- [x] `from main import app` pass.
- [x] `/openapi.json` pass.

### 12.2 Test health/entity API

- [x] `GET /`
- [x] `GET /api/v1/health`
- [x] `GET /api/v1/entities/projects`
- [x] `GET /api/v1/entities/experts`
- [x] `GET /api/v1/entities/funders`
- [x] `GET /api/v1/entities/enterprises`
- [x] `GET /api/v1/entities/project/{project_id}`

### 12.3 Test recommendation API

- [x] `POST /api/v1/recommendations/policy` Project -> Expert.
- [x] `POST /api/v1/recommendations/policy` Project -> Funder.
- [x] `POST /api/v1/recommendations/policy` Project -> Enterprise.
- [x] `POST /api/v1/recommendations/policy` Project -> Project.
- [x] `POST /api/v1/recommendations/projects/{project_id}/overview`.

### 12.4 Test response shape

Moi recommendation item can co:

- [x] `id`
- [x] `name`
- [x] `score`
- [x] `reasoning_paths`
- [x] `path_diversity` neu co
- [x] `explanation`
- [x] `metrics` neu co

## 13. Phase 10 - Cap nhat tai lieu

File can cap nhat:

```text
KIEN_TRUC_DA_CHOT.md
KE_HOACH_HOAN_THIEN_HE_THONG.md
README.md
```

Checklist:

- [x] Cap nhat so do kien truc.
- [x] Ghi ro `PGPRGraphRepository` la adapter Neo4j cho PGPR.
- [x] Ghi ro PGPR khong truy cap Neo4j truc tiep.
- [x] Ghi ro API lay entity khong qua PGPR.
- [x] Ghi ro API recommendation moi qua PGPR.
- [x] Them huong dan test API sau refactor.

## 14. Definition of Done

Refactor duoc xem la hoan thanh khi:

- [x] Co `PGPRGraphRepository`.
- [x] `PGPRRecommender` duoc inject graph repository.
- [x] `api/deps.py` dung singleton graph repository.
- [x] Router khong goi repository truc tiep.
- [x] Service layer dieu phoi dung workflow.
- [x] Entity API van chay qua `EntityService -> MongoRepository`.
- [x] Recommendation API chay qua `RecommendationService -> PGPRRecommender -> PGPRGraphRepository -> Neo4j`.
- [x] Health API chay qua `HealthService`.
- [x] Cac endpoint Phase 1 van import va OpenAPI duoc.
- [x] Recommendation response khong bi doi shape.
- [x] Tai lieu kien truc da cap nhat.

## 15. Thu tu uu tien ngan gon

Neu can lam nhanh, di theo thu tu nay:

1. [x] Tao `PGPRGraphRepository`.
2. [x] Inject `PGPRGraphRepository` vao `PGPRRecommender`.
3. [x] Sua `api/deps.py` dung singleton graph repo.
4. [x] Test app khong vo.
5. [x] Chuyen `find_reasoning_paths`.
6. [x] Chuyen `_get_expert_info` va `_get_generic_entity_info`.
7. [x] Chuyen candidate queries Project source.
8. [x] Test Project overview.
9. [x] Chuyen cac source type con lai.
10. [x] Xoa/ghi chu direct Neo4j access con lai.
11. [x] Cap nhat tai lieu.

## 16. Viec con lai sau refactor

Refactor runtime recommendation da xong. Cac viec con lai thuoc giai doan hoan thien san pham:

- [ ] Them FastAPI lifespan/shutdown de dong `PGPRGraphRepository` khi app dung.
- [ ] Khong refactor `pgpr_kg.py` va `pgpr_train.py` trong dot nay vi day la training/build pipeline, khong nam trong runtime API.
- [ ] Chuyen sang checklist tong the trong `KE_HOACH_HOAN_THIEN_HE_THONG.md` de lam frontend, graph API, deploy va evaluation.
