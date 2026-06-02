# Checklist scale-up Cold-Start Hybrid Recommendation

Tai lieu nay dung de theo doi tien do scale-up cold-start tu **ban ung dung van hanh dau tien (initial deployable version)** sang he thong hybrid recommendation van hanh day du. Thu tu uu tien la an toan truoc: khong pha PGPR hien tai, moi phase deu co test rieng.

**Trang thai hien tai (sau Phase 7.1):** He thong da co RabbitMQ, outbox, DLQ, worker heartbeat, audit, admin monitoring, rate limit, retry filter — khong con la prototype/MVP don gian.

---

## Phase 0 - Safety Baseline

Muc tieu: dong bang hanh vi hien tai truoc khi them RabbitMQ/embedding/hybrid.

- [x] Khao sat cau truc backend/frontend hien tai.
- [x] Xac dinh entry point chinh cua backend/frontend.
- [x] Xac dinh luong recommendation hien tai: PGPR policy -> Cypher fallback -> provisional rules -> XAI.
- [x] Tao script snapshot response hien tai.
- [x] Chay snapshot khi backend + MongoDB + Neo4j dang bat.
- [x] Luu ket qua vao `backend/scripts/baseline_recommendation_snapshot.json`.
- [x] Kiem tra snapshot co field cu: `id`, `name`, `score`, `reasoning_paths`, `explanation`, `xai_explanation`, `scoring_method`.

File lien quan:

- [x] `backend/scripts/baseline_recommendation_snapshot.py`
- [x] `backend/scripts/baseline_recommendation_snapshot.json`

Test can chay:

- [x] Compile snapshot script thong qua `scripts/compile_project.py` (khong can `py_compile` rieng).
- [x] `python scripts/baseline_recommendation_snapshot.py`
- [x] `GET /api/v1/health`
- [x] `POST /api/v1/recommendations/policy`

Ket qua baseline 2026-05-28:

- [x] Health API 200.
- [x] 8 policy cases thanh cong.
- [x] Failed cases: 0.
- [x] Sample ids: `project=prj_001`, `expert=exp_001`, `funder=fnd_001`, `enterprise=ent_001`.
- [x] Moi case co 3 ket qua.
- [x] Khong thieu field bat buoc `id`, `name`, `score`.

---

## Phase 1 - Embedding Schema + Migration/Backfill

Muc tieu: them schema `embedding` object an toan cho data moi va data cu, chua thay doi ranking.

- [x] Tao default embedding object.
- [x] Them enum/status helper cho embedding.
- [x] Them `compute_embedding_source_hash`.
- [x] Tao script backfill `embedding` cho `experts`.
- [x] Tao script backfill `embedding` cho `enterprises`.
- [x] Tao script backfill `embedding` cho `funders`.
- [x] Tao script backfill `embedding` cho `projects`.
- [x] Neu update topic/skill/location/industry thi set `embedding.status=stale`.
- [x] Khong lam thay doi response recommendation trong phase nay.

File du kien:

- [x] `backend/services/embedding_metadata_service.py`
- [x] `backend/services/provisional_status.py`
- [x] `backend/repositories/auth_repo.py`
- [x] `backend/repositories/mongodb_repo.py`
- [x] `backend/scripts/backfill_embedding_metadata.py`

Test can chay:

- [x] Backend compile cac file Phase 1.
- [x] Backfill dry-run.
- [x] Register user moi -> entity co `embedding.status=pending`.
- [x] Entity cu -> co object `embedding` sau backfill.
- [x] Recommendation snapshot field cu khong doi.

Ghi chu Phase 1:

- [x] Phase nay chi them metadata embedding va backfill script.
- [x] Chua them RabbitMQ.
- [x] Chua tao worker.
- [x] Chua thay doi scoring/recommendation ranking.

Ket qua dry-run 2026-05-28:

- [x] Backfill dry-run ghi `backend/scripts/embedding_backfill_report.json`.
- [x] Apply mode: `false`.
- [x] Missing embedding: 32.
- [x] Updated: 0.
- [x] Experts thieu embedding: 11.
- [x] Enterprises thieu embedding: 7.
- [x] Funders thieu embedding: 7.
- [x] Projects thieu embedding: 7.
- [x] Da chay backfill apply.
- [x] Backfill apply updated: 32.
- [x] Dry-run sau apply: missing embedding = 0.
- [x] Mau `expert`, `enterprise`, `funder`, `project` deu co `embedding.status=pending`, `dimension=128`, `source_hash`.
- [x] Snapshot sau Phase 1: 8 policy cases, failed = 0.
- [x] Smoke test Phase 1 pass: register -> pending, create project -> pending, update profile -> stale.
- [x] Snapshot sau Phase 1 smoke: 8 policy cases, failed = 0.
- [x] Entity API list/detail expose `metadata.embedding.status/dimension/source_hash` va khong tra `vector`.
- [x] Register enterprise moi -> `embedding.status=pending`.
- [x] Register funder moi -> `embedding.status=pending`.
- [x] Update non-source fields khong lam `embedding.status=stale`.
- [x] `embedding_status` top-level dong bo voi `embedding.status` cho pending/stale.
- [x] Them compile script an toan loai tru archived recovery file `scripts/restored_middle.py`.
- [x] Snapshot sau Phase 1 extended: 8 policy cases, failed = 0.

---

## Phase 2 - RabbitMQ Optional Infrastructure

Muc tieu: them RabbitMQ client/publisher nhung RabbitMQ down khong lam fail API.

- [x] Them dependency RabbitMQ client.
- [x] Them env config RabbitMQ.
- [x] Them RabbitMQ health optional.
- [x] Tao event schema versioned.
- [x] Tao RabbitMQ client.
- [x] Tao publisher service.
- [x] Publish event chi sau khi Neo4j KG sync thanh cong.
- [x] Neu RabbitMQ down, register/create project van thanh cong.
- [x] Health tra `rabbitmq=unavailable_optional` khi RabbitMQ down, khong lam fail system health.

File du kien:

- [x] `backend/models/events.py`
- [x] `backend/infrastructure/rabbitmq_client.py`
- [x] `backend/services/event_publisher_service.py`
- [x] `backend/services/health_service.py`
- [x] `backend/.env.example`
- [x] `backend/requirements.txt`
- [x] `backend/services/auth_service.py`
- [x] `backend/scripts/test_phase2_rabbitmq_optional.py`

Test can chay:

- [x] Backend compile active code.
- [x] RabbitMQ client health local -> `connected`.
- [x] RabbitMQ up -> health API co `rabbitmq=connected`.
- [x] RabbitMQ up -> register publish event thanh cong.
- [x] RabbitMQ up -> create project publish event thanh cong.
- [x] RabbitMQ up -> entity/project `embedding.status=queued`, co `job_id` va `last_event_id`.
- [x] Kiem tra queue length `embedding.jobs` va `embedding.jobs.dlq`.
- [x] Kiem tra sample message body co du contract cho worker Phase 3.
- [x] Tao script inspect/purge queue truoc khi chay worker.
- [x] KG sync failed -> khong publish event.
- [x] Update non-source field nhu `bio/phone` -> khong publish event.
- [x] Update source field nhu `topic/skill` -> publish `kg.entity.updated`.
- [x] Snapshot recommendation sau Phase 2: 8 policy cases, failed = 0.
- [x] RabbitMQ down -> register thanh cong.
- [x] RabbitMQ down -> create project thanh cong.
- [x] Health API van `ok` khi RabbitMQ optional unavailable.

Ket qua Phase 2 2026-05-28:

- [x] Da cai `pika` trong Python environment hien tai.
- [x] `python scripts/compile_project.py` pass 52 file.
- [x] `python -c "from infrastructure.rabbitmq_client import RabbitMQClient; print(RabbitMQClient().health())"` -> `connected`.
- [x] `python scripts/test_phase2_rabbitmq_optional.py` pass.
- [x] Test tao expert moi: `user_exp_6a17fff204682d90f52766cd` -> `embedding.status=queued`.
- [x] Test tao project moi: `user_prj_6a17fff304682d90f52766cf` -> `embedding.status=queued`.
- [x] RabbitMQ URL sai -> register/create project van thanh cong, embedding giu `pending`, `error_type=temporary`.
- [x] RabbitMQ URL sai -> health service `status=ok`, `rabbitmq=unavailable_optional`.
- [x] `python scripts/baseline_recommendation_snapshot.py --output scripts/baseline_recommendation_snapshot_after_phase2.json` -> 8 cases, failed = 0.
- [x] Queue inspect truoc guard test: `embedding.jobs=2`, `embedding.jobs.dlq=0`.
- [x] Sample message co `event_id`, `job_id`, `event_type`, `entity_type`, `entity_id`, `embedding_source_hash`, `kg_sync_status`, `entity_verification_status`.
- [x] Guard test sau bo sung: non-source update queue `4 -> 4`, source update queue `4 -> 5`, KG sync failed queue `5 -> 5`.
- [x] `python scripts/baseline_recommendation_snapshot.py --output scripts/baseline_recommendation_snapshot_after_phase2_guard.json` -> 8 cases, failed = 0.
- [x] Truoc khi chay worker Phase 3, da purge `embedding.jobs` test messages.
- [x] Tao clean seed expert/project moi cho worker Phase 3.
- [x] Sau seed: `embedding.jobs=2`, `embedding.jobs.dlq=0`.
- [x] Ghi seed job vao `backend/scripts/phase3_preflight_jobs.json`.

---

## Phase 3 - Worker + GraphSAGE-lite

Muc tieu: worker doc lap tao embedding 128 chieu bang GraphSAGE-lite.

- [x] Tao worker entry point.
- [x] Worker chay bang `python -m workers.embedding_worker`.
- [x] Validate event schema.
- [x] Set `embedding.status=processing`.
- [x] Load graph neighborhood tu Neo4j.
- [x] Tao deterministic text/hash embedding cho Topic/Skill/Industry/Location.
- [x] Aggregate weighted mean.
- [x] L2 normalize vector.
- [x] Set `embedding.signal=ok|low_signal|no_signal`.
- [x] Ghi embedding vao MongoDB/Neo4j.
- [x] Set `embedding.status=ready`.
- [x] Skip obsolete job dua tren job_id/source_hash.
- [x] Xu ly temporary/validation/permanent error.

File du kien:

- [x] `backend/workers/embedding_worker.py`
- [x] `backend/services/graph_feature_service.py`
- [x] `backend/services/embedding_service.py`
- [x] `backend/repositories/embedding_repo.py`
- [x] `backend/repositories/pgpr_graph_repo.py`
- [x] `backend/scripts/test_phase3_embedding_worker.py`

Test can chay:

- [x] Worker consume event.
- [x] Entity co topic/skill -> embedding ready.
- [x] Entity khong co signal -> `no_signal` direct encoder test.
- [x] Event cu khong ghi de embedding moi.
- [x] Vector dung dimension 128.
- [x] Vector da normalize neu khong phai zero-vector.
- [x] Queue sau worker: `embedding.jobs=0`, `embedding.jobs.dlq=0`.
- [x] Worker `--once` khi queue rong exit sach, khong loi.
- [x] Entity id khong ton tai -> worker skip sach.
- [x] `kg_sync_status=sync_failed` -> worker skip sach.
- [x] Entity rejected -> worker skip sach.
- [x] Malformed event -> worker nack, message vao DLQ.
- [x] Entity API sau khi co vector that khong expose `embedding.vector`.
- [x] Stale recompute E2E: update skill/topic -> queued -> worker -> ready voi source_hash moi.
- [x] Snapshot recommendation sau Phase 3: 8 policy cases, failed = 0.

Ket qua Phase 3 2026-05-28:

- [x] `python -m workers.embedding_worker --once` xu ly expert seed -> `ready`, `signal=ok`, `dimension=128`, `normalized=true`.
- [x] `python -m workers.embedding_worker --once` xu ly project seed -> `ready`, `signal=ok`, `dimension=128`, `normalized=true`.
- [x] MongoDB expert/project co `embedding.status=ready`, top-level `embedding_status=ready`, vector length 128, norm ~1.0.
- [x] Neo4j expert/project co `embedding_status=ready`, `embedding_model=graphsage_lite_v1`, vector length 128.
- [x] `python scripts/test_phase3_embedding_worker.py` pass.
- [x] `python scripts/test_phase3_worker_hardening.py` pass.
- [x] Tach `EmbeddingRepository` de worker ghi embedding qua repository rieng.
- [x] Them `PGPRGraphRepository.update_entity_embedding()` de khong dung generic verification method cho embedding.
- [x] `python scripts/baseline_recommendation_snapshot.py --output scripts/baseline_recommendation_snapshot_after_phase3.json` -> 8 cases, failed = 0.
- [x] `python scripts/baseline_recommendation_snapshot.py --output scripts/baseline_recommendation_snapshot_after_phase3_repo.json` -> 8 cases, failed = 0.
- [x] `python scripts/baseline_recommendation_snapshot.py --output scripts/baseline_recommendation_snapshot_after_phase3_hardening.json` -> 8 cases, failed = 0.

---

## Phase 4 - Outbox Reliability

Muc tieu: khong mat event khi RabbitMQ/server loi.

- [x] Tao collection `embedding_event_outbox`.
- [x] Khi API tao/update entity/project, ghi outbox event.
- [x] Publisher job publish RabbitMQ tu outbox.
- [x] Publish thanh cong -> mark `published`.
- [x] Publish loi -> giu `pending`.
- [x] Retry pending theo backoff.
- [x] Qua max retry -> mark failed/DLQ.

File du kien:

- [x] `backend/services/outbox_publisher_service.py`
- [x] `backend/repositories/embedding_outbox_repo.py`
- [x] `backend/scripts/run_outbox_publisher.py`
- [x] `backend/scripts/test_phase4_outbox_reliability.py`

Test can chay:

- [x] RabbitMQ down -> outbox pending.
- [x] RabbitMQ up -> outbox publish thanh cong.
- [x] Crash/retry khong duplicate event.
- [x] KG sync failed -> khong tao outbox event.
- [x] Qua max retry -> outbox `failed`.
- [x] Queue sach sau test.
- [x] `python scripts\test_phase4_outbox_reliability.py` -> PASS.
- [x] `python scripts\compile_project.py` -> compile passed.

---

## Phase 5 - Candidate Safety + Embedding Search

Muc tieu: moi candidate deu di qua mask chung truoc khi scoring.

Thu tu lam:

- [x] Tao `CandidateMaskService`.
- [x] Tao `entity_embeddings` store.
- [x] Tao `EmbeddingCandidateService`.
- [x] Embedding nearest search bang cosine trong Python (baseline cho initial deployable system).
- [x] Scale sau moi dung Neo4j vector index / vector DB.

File du kien:

- [x] `backend/services/candidate_mask_service.py`
- [x] `backend/services/embedding_candidate_service.py`
- [x] `backend/repositories/embedding_repo.py`
- [x] `backend/scripts/test_phase5_candidate_safety.py`

Test can chay:

- [x] owner_only cua user khac bi block.
- [x] rejected/disabled/hidden bi block.
- [x] merge_required khong lam intermediate node.
- [x] recommendable_as_target=false bi block.
- [x] admin_debug tra block reason.
- [x] Personal mode cho owner dung own owner_only candidate.
- [x] RecommendationService dung CandidateMaskService thay vi hard-code provisional filter.
- [x] PGPR policy result di qua CandidateMaskService.
- [x] Cypher fallback/direct entity/project overview di qua RecommendationService mask.
- [x] `admin_debug` recommendation/graph API chi admin/root_admin duoc goi.
- [x] Graph neighbors public/personal khong lo `owner_only` cua user khac, `hidden`, `rejected`.
- [x] Source chua co embedding ready/vector -> embedding candidates tra empty, khong crash.
- [x] Target vector `normalized=false`, sai dimension, zero/no_signal -> bi bo qua.
- [x] `python scripts\test_phase5_candidate_safety.py` -> PASS.
- [x] `python scripts\baseline_recommendation_snapshot.py --output scripts\baseline_recommendation_snapshot_after_phase5.json` -> 8 cases, failed = 0.
- [x] `python scripts\baseline_recommendation_snapshot.py --output scripts\baseline_recommendation_snapshot_after_phase5_hardening.json` -> 8 cases, failed = 0.
- [x] RabbitMQ queue sach sau Phase 5.

---

## Phase 6 - Hybrid Recommendation Backward Compatible

Muc tieu: them hybrid ranking nhung khong pha response cu.

- [x] Giu field cu: `id`, `name`, `score`, `reasoning_paths`, `explanation`, `xai_explanation`.
- [x] Them field moi: `scoring_method`, `evidence_level`, `cold_start`, `embedding_status`, `recommendation_readiness`.
- [x] Stage 1 candidate generation: PGPR/Cypher/embedding/topic-skill.
- [x] Stage 2 filter bang CandidateMaskService.
- [x] Stage 3 scoring: PGPR + embedding + overlap + graph evidence + freshness/profile quality.
- [x] Stage 4 reranking/diversity/deduplicate/cap weak evidence.
- [x] Stage 5 XAI multi-evidence.
- [x] Cap score cho embedding_only/fallback_only/unverified/no_signal.

File du kien:

- [x] `backend/services/recommendation_service.py`
- [x] `backend/services/hybrid_recommendation_service.py`
- [x] `backend/models/schemas.py`
- [x] `frontend/src/lib/api.ts`
- [x] `frontend/src/app/dashboard/page.tsx`

Test can chay:

- [x] `python scripts/test_phase6_hybrid_recommendation.py` -> PASS (gom hardening: hybrid_ready source moi, embedding-only cap, fallback/stale/failed, dedupe PGPR+embedding, score==final_score, XAI wording).
- [x] `python scripts/compile_project.py` -> compile passed.
- [x] Snapshot compare field cu: `baseline_recommendation_snapshot_after_phase6.json` -> 8 cases, failed = 0.
- [x] Fallback mode khi embedding pending/stale (unit test source context).
- [x] Hybrid mode khi embedding ready (pipeline merge PGPR + embedding + topic).
- [x] XAI warning khi cold-start/provisional/no_signal.
- [x] Frontend dashboard hien badge hybrid/cold-start/evidence.

---

## Phase 7 - Admin/Monitoring

Muc tieu: admin quan sat va xu ly embedding pipeline.

- [x] API list embedding jobs.
- [x] API retry failed jobs.
- [x] API recompute entity embedding.
- [x] User chi recompute entity/project cua minh.
- [x] Admin recompute moi entity.
- [x] Rate limit recompute.
- [x] Audit log retry/recompute.
- [x] Admin UI hien queue/job/model status.

File du kien:

- [x] `backend/api/v1/endpoints/admin.py`
- [x] `backend/api/v1/endpoints/entities.py`
- [x] `backend/services/embedding_admin_service.py`
- [x] `frontend/src/lib/api.ts`
- [x] `frontend/src/app/admin/page.tsx`

Test can chay:

- [x] `python scripts/test_phase7_embedding_admin.py` -> PASS.
- [x] Admin retry failed job.
- [x] User recompute entity cua nguoi khac bi 403.
- [x] Audit log co action recompute/retry.

### Phase 7.1 - Production hardening (pre Evaluation / Production deploy)

- [x] Worker heartbeats + `liveness` alive/stale/unknown (`WORKER_HEARTBEAT_STALE_SECONDS`).
- [x] DLQ count + alert + sample peek/requeue (khong giam message count).
- [x] Recompute reason + audit default admin/user; retry `include_permanent` bat buoc reason.
- [x] `retry-failed` filter `error_type`, `entity_type`, `limit`, `include_permanent` (mac dinh chi `temporary`).
- [x] Test `scripts/test_phase7_1_hardening.py` (10 case heartbeat/DLQ/reason/retry).

---

## Phase 8 - Evaluation & Quality Assurance

Muc tieu: lop kiem soat chat luong truoc khi doi model/ranking. Moi lan thay doi scoring/model phai co baseline de so sanh.

- [x] Tao ground truth dataset (`scripts/evaluation_cases.json`).
- [x] Tao script `run_evaluation.py`.
- [x] Baseline random.
- [x] Baseline topic overlap.
- [x] Baseline graph heuristic.
- [x] Chay PGPR only.
- [x] Chay embedding only.
- [x] Chay hybrid.
- [x] Xuat report JSON/CSV/Markdown.
- [x] Do Precision@K, Recall@K, NDCG@K, MRR.
- [x] Do coverage, cold-start success rate, latency p50/p95.
- [x] Do explanation coverage.
- [x] Time to first usable recommendation.
- [x] Dinh nghia regression threshold (`scripts/evaluation_config.json`).
- [x] Regression gate: `primary_metrics` = `ndcg_at_5`, `mrr` (Precision@5 informational).
- [x] Regression gate: neu hybrid/model moi lam metric chinh giam qua nguong thi khong duoc promote/deploy.

File:

- [x] `backend/evaluation/` (metrics, rankers, runner, regression_gate)
- [x] `backend/scripts/run_evaluation.py`
- [x] `backend/scripts/evaluation_cases.json`
- [x] `backend/scripts/evaluation_config.json`
- [x] `backend/scripts/evaluation_report.json` (+ `.csv`, `.md`)
- [x] `backend/scripts/evaluation_baseline_report.json`
- [x] `backend/scripts/test_phase8_evaluation.py`

Chay:

```powershell
cd backend
python scripts/test_phase8_evaluation.py
python scripts/run_evaluation.py
python scripts/run_evaluation.py --baseline scripts/evaluation_baseline_report.json
```

### Phase 8.1 - Evaluation hardening

- [x] 22 explicit ground-truth cases (`label_source=admin_review`) across project/expert/funder/enterprise directions.
- [x] 6 hybrid-ready cases + `scripts/seed_evaluation_hybrid_fixtures.py` + `--seed-hybrid` on run_evaluation.
- [x] Label metadata (`label_version`, `label_created_at`, `label_policy`) trong `evaluation_cases.json`.
- [x] Seed guard: `EVALUATION_ALLOW_SEED=true` bat buoc cho hybrid seed (dev/eval only; khong chay production that khong backup).
- [x] Shared PGPR recommender (`evaluation/pgpr_session.py`) trong mot run evaluation.
- [x] Report `baseline_comparison` (method, metric, current, baseline, delta, status) trong JSON/MD/API.
- [x] Test `scripts/test_phase8_1_hardening.py` PASS.

Chay:

```powershell
$env:EVALUATION_ALLOW_SEED="true"
python scripts/seed_evaluation_hybrid_fixtures.py
python scripts/test_phase8_1_hardening.py
python scripts/run_evaluation.py --seed-hybrid --baseline scripts/evaluation_baseline_report.json
```

---

## Phase 9 - Production Deployment

Muc tieu: dong goi **app** de van hanh that; **Mongo/Neo4j/Redis/RabbitMQ/Ollama chay san ngoai** (khong trung container DB).

Tong quan he thong: `deploy/SYSTEM_INVENTORY.md`.

Trang thai hien tai: **Phase 9 completed for app-only production smoke validation**.
Da build/up production compose that va chay restore staging smoke opt-in. Full destructive restore tu backup archive/dump that van nen chay tren staging rieng truoc go-live.

- [x] `docker-compose.production.yml` — backend, frontend, `embedding_worker`, `outbox_publisher`; map `host.docker.internal` + `authSource=admin` cho Mongo.
- [x] `docker-compose.infra.yml` — tuỳ chọn neu can gói DB trong Compose.
- [x] Mount `pgpr/pgpr_data` cho backend **va** worker (GraphSAGE-lite / graph features).
- [x] Cau hinh qua `.env` goc (khong bat buoc file `.env.production` rieng).
- [x] Backup infra ngoai: `deploy/backup/backup_external.ps1` (ten container Mongo/Neo4j).
- [x] Backup infra bundled: `deploy/backup/backup_all.ps1` + `docker-compose.infra.yml`.
- [x] Restore mau: `restore_*_sample.ps1`; test opt-in `test_phase9_restore_sample.py`.
- [x] RabbitMQ durable + persistent (code Phase 2–4; ket noi queue ngoai qua `.env`).
- [x] Healthcheck backend / worker; restart `unless-stopped`.
- [x] `.env.production.example` (mau); `LOG_LEVEL` / `LOG_FORMAT` trong `main.py`.
- [x] Inventory script: `system_inventory_check.py`.
- [x] `docker compose build/up` xac nhan tren may deploy (PyTorch image nang — da chay voi `BACKEND_PORT=8010` do port 8000 bi Windows giu bat thuong).
- [x] Test restore staging smoke opt-in (`RUN_PHASE9_RESTORE_TEST=1`) pass; full backup restore destructive can staging rieng neu go-live.
- [x] Phase 9 frontend runtime config validated:
  - [x] `NEXT_PUBLIC_API_BASE_URL` da cap nhat thanh `http://localhost:8010`.
  - [x] Frontend image da rebuild no-cache sau khi doi `NEXT_PUBLIC_*`.
  - [x] Navbar API label doc tu `API_BASE_URL`, khong hard-code `localhost:8000`.
  - [x] Frontend bundle khong con chuoi `localhost:8000`.
  - [x] Backend health OK tai `http://localhost:8010/api/v1/health`.

File:

- [x] `deploy/SYSTEM_INVENTORY.md`, `deploy/README.md`
- [x] `docker-compose.production.yml`, `docker-compose.infra.yml`
- [x] `backend/Dockerfile`, `frontend/Dockerfile`
- [x] `backend/scripts/worker_healthcheck.py`, `test_phase9_production_deploy.py`

Chay:

```powershell
docker compose -f docker-compose.production.yml up -d --build
cd backend
python scripts/system_inventory_check.py
python scripts/test_phase9_production_deploy.py
```

---

## Phase 10 - GraphSAGE Real Model / Model Lifecycle

Chi bat dau khi:

- [x] GraphSAGE-lite chay on (dat theo Phase 3/9).
- [x] Embedding ready rate on trong seed/dev sau drain queue (dat theo Phase 3/7).
- [x] Hybrid recommendation da co evaluation so bo (Phase 8/8.1 + baseline v2).
- [ ] Du lieu du lon de train.

Ghi chu: co the bat dau Phase 10 theo huong **model lifecycle/scaffold + training thu nghiem**. Chua promote GraphSAGE real thanh production model neu dataset van chu yeu la seed/demo.
Neu du lieu chua du hoac PyTorch Geometric/train khong on dinh, Phase 10 van co gia tri neu hoan thanh lifecycle/scaffold: export snapshot, feature encoder, dataset, artifact format, evaluation va registry. Ket luan hop le co the la: **GraphSAGE real chua du dieu kien promote**.

Trang thai hien tai: **Phase 10 candidate lifecycle ready**.

- Export snapshot that tu Neo4j da chay duoc.
- Dataset builder da tao positive/negative edges.
- Feature encoder, registry va artifact format da co.
- Active model pointer van giu `graphsage_lite_v1`.
- GraphSAGE real chua promote vi chua co PyTorch Geometric va du lieu hien tai con nho cho ky vong model production.
- Graph hien tai khoang 197 nodes / 499 edges: du de kiem tra pipeline, chua du manh de ky vong GraphSAGE real vuot GraphSAGE-lite.

Nguyen tac:

- [x] GraphSAGE-lite van la active baseline.
- [ ] GraphSAGE real chi la candidate model cho den khi pass evaluation/regression gate.
- [ ] Khong thay worker runtime sang GraphSAGE real neu chua promote model version.
- [ ] Khong promote neu regression gate fail hoac XAI/evidence coverage giam ro.
- [ ] Neu GraphSAGE real khong vuot baseline v2, giu GraphSAGE-lite lam active model.

Muc tieu:

### Phase 10.1 - Export graph snapshot

- [x] Tao read-only exporter cho node/edge snapshot tu Neo4j.
- [x] Luu snapshot versioned kem metadata ngay tao, label counts, relationship counts.
- [x] Khong ghi nguoc vao Mongo/Neo4j trong buoc export.
- [x] Snapshot khong export secret, password hash, token, email/phone neu khong can cho training.
- [x] Chi export feature can cho model: id, type, labels, topic/skill/industry/location/status/trust_weight.
- [x] Chay export snapshot that tu Neo4j production/dev sau khi bat Neo4j external.
  - Snapshot that: 197 nodes, 499 edges.
  - Output: `backend/artifacts/graph_snapshots/snapshot_20260601T160256_211731Z0000.json`.

### Phase 10.2 - Build feature encoder

- [x] Tao node feature encoder cho label/type, text label hash, topic/skill/industry/location features.
- [x] Luu encoder artifact versioned.
- [x] Dam bao encoder deterministic de cung input cho cung vector feature.

### Phase 10.3 - Build train/val/test dataset

- [x] Tao positive edges tu snapshot KG.
- [x] Tao negative samples co kiem soat va khong trung positive edge.
- [x] Negative sampling dung `random_seed` co dinh de ket qua train/evaluate tai lap duoc.
- [x] Tach train/val/test reproducible.
- [x] Ghi dataset stats va canh bao neu du lieu qua it.
- [x] Dataset tu snapshot that dat nguong toi thieu: 499 positive edges, 499 negative edges.
- [ ] Bo sung evaluation labels vao dataset builder khi co snapshot/label production du hon.

### Phase 10.4 - Train GraphSAGE candidate

- [ ] Train GraphSAGE 2 layers bang PyTorch Geometric.
- [x] Config candidate co `hidden_dim=128`, `output_dim=128`, neighbor sampling `[10,5]`.
- [x] Luu artifact model/config/encoder/metadata.
- [x] Model metadata co `model_status`, `training_data_version`, `evaluation_baseline`.
- [x] Train script canh bao neu positive edges/node count duoi nguong toi thieu; neu du lieu qua it thi chi tao report warning, khong promote.
- [x] Candidate model luu artifact rieng, khong overwrite active GraphSAGE-lite.
- [x] Neu PyTorch Geometric chua san sang, tao fallback training stub khong anh huong runtime.

### Phase 10.5 - Evaluate against baseline v2

- [x] Tao candidate evaluation report kem artifact voi `promote_allowed=false` khi data/PyG chua dat.
- [x] Tao candidate report tu snapshot that; model chua promote vi PyTorch Geometric unavailable.
- [ ] Evaluate GraphSAGE-lite vs GraphSAGE real candidate bang Phase 8 metrics khi co model GraphSAGE real train that.
- [ ] Chay regression gate voi baseline v2.
- [ ] So sanh cold-start success rate, explanation coverage, latency.

### Phase 10.6 - Promote/rollback model version

- [x] Model registry / versioning scaffold.
- [x] Co active model pointer, vi du `backend/artifacts/models/active_embedding_model.json`.
- [x] Registry/metadata co `model_status`: `candidate`, `active`, `rejected`, `archived`, `rollback`.
- [x] Candidate evaluation report duoc luu kem artifact, vi du `backend/artifacts/models/graphsage_real_v1_candidate/evaluation_report.json`.
- [ ] Promote candidate model chi khi evaluation pass.
- [ ] Worker load model theo version sau khi promote.
- [ ] Rollback model neu evaluation te hon baseline hoac runtime loi.

Pending note: GraphSAGE real training/promotion cho production de sau khi co du lieu lon hon va moi truong PyTorch Geometric san sang.

File du kien:

- [x] `backend/ml/graphsage/`
- [x] `backend/scripts/export_graph_snapshot.py`
- [x] `backend/scripts/train_graphsage.py`
- [ ] `backend/artifacts/models/graphsage_v1.pt`
- [x] `backend/artifacts/models/graphsage_real_v1_candidate/graphsage_config.json`
- [x] `backend/artifacts/models/graphsage_real_v1_candidate/node_feature_encoder.pkl`
- [x] `backend/artifacts/models/graphsage_real_v1_candidate/metadata.json`
- [x] `backend/artifacts/models/active_embedding_model.json`

---

## Phase 11 - Data Governance nang cao

- [x] Tao canonical taxonomy helper cho topic / skill / industry:
  - [x] `backend/models/canonical_taxonomy.py`
  - [x] Alias mapping cho cac cach viet pho bien: `AI y te`, `ML`, `torch`, `edtech`, ...
  - [x] Ham phat hien topic/skill/industry chua map de dua vao review queue.
- [x] Tao data quality score read-only cho entity/project:
  - [x] `backend/services/data_quality_service.py`
  - [x] Score, level, missing_fields, warnings, signals.
  - [x] Review status goi y: `verified`, `pending_review`, `needs_more_info`, `merge_required`, `rejected`.
  - [x] Tinh den topic, skill/technology, industry, location, KG status, verification, trust_weight, embedding signal, duplicate candidates.
- [x] Tao governance audit read-only:
  - [x] `backend/services/governance_audit_service.py`
  - [x] Entity quality audit.
  - [x] Orphan node audit tu Neo4j.
  - [x] Provisional lifecycle audit theo tuoi node.
  - [x] Retention summary cho outbox / audit / DLQ samples.
  - [x] Audit khong crash khi Mongo/Neo4j bi loi; report ghi ro source nao unavailable.
- [x] Tao script / test Phase 11:
  - [x] `backend/scripts/test_phase11_data_governance.py`
  - [x] `backend/scripts/run_phase11_governance_audit.py`
  - [x] `backend/scripts/phase11_governance_audit_report.json`
- [x] Chay governance audit voi Mongo credential dung:
  - [x] Xu ly `.env` co UTF-8 BOM de `MONGO_URI` duoc load dung.
  - [x] Report co Mongo entity quality, Neo4j orphan nodes, provisional lifecycle, retention summary.
  - [x] Ket qua hien tai: 193 entity, 145 poor, 14 fair, 22 good, 12 excellent.
  - [x] Review status hien tai: 168 needs_more_info, 7 pending_review, 9 merge_required, 9 rejected.
  - [x] 42 entity co warning taxonomy chua map.
- [x] API admin governance review queue read-only:
  - [x] `GET /api/v1/admin/governance/review-queue`
  - [x] Filter: `review_status`, `level`, `has_unmapped_taxonomy`, `has_duplicate_candidates`, `entity_type`, `limit`.
  - [x] Output co `entity_id`, `entity_type`, `name`, `data_quality`, `review_status`, `unmapped_taxonomy_values`, `duplicate_candidates_count`, `recommended_action`.
- [x] UI admin governance review queue:
  - [x] Them panel `Governance review queue` trong `/admin#review-queue`.
  - [x] Filter UI: review_status, quality level, unmapped taxonomy, duplicate candidates.
  - [x] Badge: quality, review_status, owner_only, unverified, unmapped_taxonomy.
  - [x] Hien recommended_action, missing_fields, warnings.
  - [x] Them modal `Map taxonomy` tu item co unmapped taxonomy.
  - [x] Them modal `Request info` cho item `needs_more_info`.
- [x] Taxonomy alias mapping action:
  - [x] `POST /api/v1/admin/governance/taxonomy-alias`
  - [x] Bat buoc `reason`.
  - [x] Ghi vao collection `taxonomy_aliases`.
  - [x] Ghi admin audit log.
  - [x] Chua rewrite entity hang loat.
  - [x] UI dung dropdown canonical topic/skill/industry thay vi bat admin nhap tay.
- [x] Orphan cleanup safe action:
  - [x] `POST /api/v1/admin/governance/orphans/{entity_type}/{entity_id}/mark-cleanup-candidate`
  - [x] Chi mark `cleanup_candidate=true`, khong physical delete.
  - [x] Ghi Mongo neu entity ton tai va mark Neo4j node.
  - [x] Ghi admin audit log.
  - [x] `GET /api/v1/admin/governance/orphans`
  - [x] `POST /api/v1/admin/governance/orphans/{entity_type}/{entity_id}/disable-from-recommendation`
  - [x] UI orphan panel co confirm modal va reason bat buoc.
- [x] Request-more-information workflow MVP:
  - [x] `POST /api/v1/admin/governance/entities/{entity_type}/{entity_id}/request-more-info`
  - [x] Luu collection `data_quality_requests`.
  - [x] Gan `latest_data_quality_request` vao entity.
  - [x] Ghi admin audit log.
  - [x] UI tao request tu item `needs_more_info`.
- [x] Retention policy dry-run:
  - [x] `backend/scripts/run_retention_policy.py --dry-run`
  - [x] Report: `backend/scripts/retention_policy_report.json`
  - [x] Co `matched_count`, `would_delete_count`, `applied_count`, `collection`, `cutoff_date`.
  - [x] Mac dinh khong xoa neu khong truyen `--apply`.
  - [x] `--apply` bat buoc co `--confirm-retention-delete` hoac `RETENTION_ALLOW_APPLY=true`.
- [x] Hardening tests cho mutating governance actions:
  - [x] Missing reason bi reject.
  - [x] Invalid canonical_id bi reject.
  - [x] Taxonomy alias action thanh cong va co audit log.
  - [x] Request-more-info tao request va gan `latest_data_quality_request`.
  - [x] Mark cleanup candidate set marker tren entity/graph.
  - [x] Soft-disable orphan bi `CandidateMaskService` block khoi public recommendation target.
- [x] Chay validation:
  - [x] `python scripts\test_phase11_data_governance.py`
  - [x] `python scripts\compile_project.py`
  - [x] `python scripts\run_phase11_governance_audit.py --limit 100`
  - [x] `python scripts\run_retention_policy.py --dry-run`
  - [x] `python scripts\run_retention_policy.py --apply` fail-safe neu khong co confirm.
  - [x] `cd frontend && npm run typecheck`
  - [x] `cd frontend && npm run build`
- [ ] Merge/duplicate entity policy mo rong o muc admin action:
  - [ ] Chuan hoa duplicate decision tree: strong match / weak match / no match.
  - [ ] Merge action can chuyen user.linked_entity sang target va soft-disable source.
  - [ ] Luu audit log truoc/sau merge.
- [ ] Review queue that cho entity/topic/skill/industry moi:
  - [x] Admin filter theo `review_status`.
  - [x] Map custom topic/skill vao canonical taxonomy bang alias action.
  - [x] Request more information cho ho so thieu du lieu.
- [ ] Orphan cleanup action:
  - [x] Preview orphan nodes.
  - [x] Mark cleanup candidate co audit log, khong xoa truc tiep mac dinh.
  - [x] Soft-disable khoi recommendation khi admin xac nhan.
- [ ] Retention enforcement:
  - [ ] Cron/script archive outbox da published.
  - [ ] Cleanup DLQ samples da xu ly.
  - [ ] Giu audit log toi thieu 365 ngay.

Ghi chu hien tai:

- Phase 11 da co lop audit/report-first, chua thuc hien cleanup/merge ghi du lieu that.
- Lan chay audit hien tai doc duoc Mongo va Neo4j.
- Neo4j phat hien 1 orphan Project owner_only.
- Nguon data hien tai co nhieu entity `poor/needs_more_info`; can dung review queue de xu ly truoc khi them data lon cho GraphSAGE real.

---

## Phase 12 - Security Hardening

- [x] RBAC chi tiet cho admin pipeline:
  - [x] `reject_entity`, `disable_kg`, `merge_entity` bat buoc co `reason`.
  - [x] Retry embedding job `permanent` / `include_permanent=true` bat buoc `root_admin` va `reason`.
  - [x] Root admin user-management tiep tuc chi root_admin duoc goi.
  - [x] Them test cho reason guard, root guard va rate-limit dependency.
- [x] Rate limit va abuse protection mo rong:
  - [x] In-memory rate limiter single-process.
  - [x] `RATE_LIMIT_ENABLED=true` trong `.env.example`.
  - [x] Rate limit cho register/login/profile update/create project.
  - [x] Rate limit cho user/admin embedding recompute.
  - [x] Rate limit cho admin governance/entity/embedding/user-management mutations.
  - [ ] Neu scale nhieu backend replicas, doi sang Redis-backed limiter.
- [x] Secret management / production env hardening:
  - [x] Them script `backend/scripts/check_phase12_security_config.py`.
  - [x] Script redact secret va tao `backend/scripts/phase12_security_config_report.json`.
  - [x] Kiem tra default `APP_AUTH_SECRET`, `ROOT_ADMIN_PASSWORD`, Neo4j password, RabbitMQ guest production, CORS wildcard, disabled rate limit.
  - [x] Them `deploy/SECURITY_HARDENING.md`.
  - [x] Rotate `APP_AUTH_SECRET` trong `.env` goc.
  - [x] Rotate `ROOT_ADMIN_PASSWORD` trong `.env` goc.
  - [x] Cap nhat password hash root admin hien co trong MongoDB theo password moi.
  - [x] Chay lai security config check: 0 issue.
  - [x] Kiem tra root admin login bang password moi: pass.
- [x] Frontend dependency audit:
  - [x] Chay `npm audit` trong `frontend` de lay report chi tiet.
  - [x] Luu `frontend/npm-audit-report.json` trong luc audit Phase 12; report tam da xoa sau cleanup.
  - [x] Luu `frontend/npm-audit-summary.json` trong luc audit Phase 12; report tam da xoa sau cleanup.
  - [x] Phan loai low/moderate/high/critical.
  - [x] Loai bo Genkit/Firebase Studio scaffold khong dung (`frontend/src/ai/*`) de giam attack surface.
  - [x] Go dependency khong dung: `genkit`, `@genkit-ai/google-genai`, `firebase`, `dotenv`, `genkit-cli`.
  - [x] Nang Next patch `15.5.9 -> 15.5.19`.
  - [x] Pin/override PostCSS `8.5.15`.
  - [x] `npm audit` hien tai: 0 vulnerability.
  - [x] Khong chay `npm audit fix --force`.
- [x] Security review truoc go-live:
  - [x] Backend compile pass.
  - [x] Phase 12 security hardening tests pass.
  - [x] Frontend build pass.
  - [x] Frontend typecheck pass.
  - [x] Production secret blockers da duoc rotate trong `.env`.

File:

- [x] `backend/services/rate_limit_service.py`
- [x] `backend/api/deps.py`
- [x] `backend/api/v1/endpoints/auth.py`
- [x] `backend/api/v1/endpoints/entities.py`
- [x] `backend/api/v1/endpoints/admin.py`
- [x] `backend/scripts/check_phase12_security_config.py`
- [x] `backend/scripts/test_phase12_security_hardening.py`
- [x] `deploy/SECURITY_HARDENING.md`
- [x] `frontend/package.json`
- [x] `frontend/package-lock.json`
- [x] `frontend/npm-audit-report.json`
- [x] `frontend/npm-audit-summary.json`

Validation:

- [x] `python scripts\compile_project.py` -> 101 files.
- [x] `python scripts\test_phase12_security_hardening.py` -> pass.
- [x] `python scripts\check_phase12_security_config.py` -> report generated, 0 issue sau khi rotate secret.
- [x] `cd frontend && npm audit --json` -> 0 vulnerabilities.
- [x] `cd frontend && npm run build` -> pass, Next.js 15.5.19.
- [x] `cd frontend && npm run typecheck` -> pass.

---

## Ghi chu an toan

- [ ] Khong thay doi scoring PGPR core truoc khi co snapshot baseline.
- [ ] Moi phase phai chay test rieng.
- [ ] Neu phase nao lam recommendation field cu bien mat, phai rollback phase do.
- [ ] RabbitMQ va worker phai optional trong giai doan dau (da dat — hien la initial deployable version co day du monitoring).
- [ ] GraphSAGE real (Phase 10) khong lam truoc khi GraphSAGE-lite + evaluation (Phase 8) on dinh.
- [ ] Production deploy (Phase 9) nen co truoc hoac song song voi model nang cao, nhung evaluation baseline nen co truoc GraphSAGE real.
