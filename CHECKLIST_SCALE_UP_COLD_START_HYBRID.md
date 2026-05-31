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
- [ ] `docker compose build/up` xac nhan tren may deploy (PyTorch image nang — chay tay lan dau).
- [ ] Test restore that tren ban copy staging (`RUN_PHASE9_RESTORE_TEST=1`).

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

- [ ] GraphSAGE-lite chay on.
- [ ] Embedding ready rate on.
- [ ] Hybrid recommendation da co evaluation so bo (Phase 8).
- [ ] Du lieu du lon de train.

Muc tieu:

- [ ] Export graph snapshot.
- [ ] Tao node feature encoder.
- [ ] Train GraphSAGE 2 layers bang PyTorch Geometric.
- [ ] Luu artifact model/config/encoder/metadata.
- [ ] Evaluate GraphSAGE-lite vs GraphSAGE real (dung Phase 8 metrics).
- [ ] Model registry / versioning.
- [ ] Worker load model theo version.
- [ ] Rollback model neu evaluation te hon baseline.

File du kien:

- [ ] `backend/ml/graphsage/`
- [ ] `backend/scripts/export_graph_snapshot.py`
- [ ] `backend/scripts/train_graphsage.py`
- [ ] `backend/artifacts/models/graphsage_v1.pt`
- [ ] `backend/artifacts/models/graphsage_config.json`
- [ ] `backend/artifacts/models/node_feature_encoder.pkl`
- [ ] `backend/artifacts/models/metadata.json`

---

## Phase 11 - Data Governance nang cao

- [ ] Merge/duplicate entity policy mo rong.
- [ ] Provisional node lifecycle audit.
- [ ] Admin tooling cho data quality / orphan cleanup.
- [ ] Chinh sach retention cho outbox / audit / DLQ samples.

---

## Phase 12 - Security Hardening

- [ ] RBAC chi tiet cho admin pipeline (retry permanent, model rollback, ...).
- [ ] Secret management / production env hardening.
- [ ] Rate limit va abuse protection mo rong.
- [ ] Security review truoc go-live.

---

## Ghi chu an toan

- [ ] Khong thay doi scoring PGPR core truoc khi co snapshot baseline.
- [ ] Moi phase phai chay test rieng.
- [ ] Neu phase nao lam recommendation field cu bien mat, phai rollback phase do.
- [ ] RabbitMQ va worker phai optional trong giai doan dau (da dat — hien la initial deployable version co day du monitoring).
- [ ] GraphSAGE real (Phase 10) khong lam truoc khi GraphSAGE-lite + evaluation (Phase 8) on dinh.
- [ ] Production deploy (Phase 9) nen co truoc hoac song song voi model nang cao, nhung evaluation baseline nen co truoc GraphSAGE real.
