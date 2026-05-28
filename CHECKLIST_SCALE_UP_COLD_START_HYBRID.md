# Checklist scale-up Cold-Start Hybrid Recommendation

Tai lieu nay dung de theo doi tien do scale-up cold-start tu MVP sang he thong hybrid recommendation hoan chinh. Thu tu uu tien la an toan truoc: khong pha PGPR hien tai, moi phase deu co test rieng.

---

## Phase 0 - Safety Baseline

Muc tieu: dong bang hanh vi hien tai truoc khi them RabbitMQ/embedding/hybrid.

- [x] Khao sat cau truc backend/frontend hien tai.
- [x] Xac dinh entry point chinh cua backend/frontend.
- [x] Xac dinh luong recommendation hien tai: PGPR policy -> Cypher fallback -> provisional rules -> XAI.
- [x] Tao script snapshot response hien tai.
- [ ] Chay snapshot khi backend + MongoDB + Neo4j dang bat.
- [ ] Luu ket qua vao `backend/scripts/baseline_recommendation_snapshot.json`.
- [ ] Kiem tra snapshot co field cu: `id`, `name`, `score`, `reasoning_paths`, `explanation`, `xai_explanation`, `scoring_method`.

File lien quan:

- [x] `backend/scripts/baseline_recommendation_snapshot.py`
- [ ] `backend/scripts/baseline_recommendation_snapshot.json`

Test can chay:

- [ ] `python -m py_compile scripts/baseline_recommendation_snapshot.py`
- [ ] `python scripts/baseline_recommendation_snapshot.py`
- [ ] `GET /api/v1/health`
- [ ] `POST /api/v1/recommendations/policy`

---

## Phase 1 - Embedding Schema + Migration/Backfill

Muc tieu: them schema `embedding` object an toan cho data moi va data cu, chua thay doi ranking.

- [ ] Tao default embedding object.
- [ ] Them enum/status helper cho embedding.
- [ ] Them `compute_embedding_source_hash`.
- [ ] Backfill `embedding` cho `experts`.
- [ ] Backfill `embedding` cho `enterprises`.
- [ ] Backfill `embedding` cho `funders`.
- [ ] Backfill `embedding` cho `projects`.
- [ ] Neu update topic/skill/location/industry thi set `embedding.status=stale`.
- [ ] Khong lam thay doi response recommendation trong phase nay.

File du kien:

- [ ] `backend/services/embedding_metadata_service.py`
- [ ] `backend/services/provisional_status.py`
- [ ] `backend/repositories/auth_repo.py`
- [ ] `backend/repositories/mongodb_repo.py`
- [ ] `backend/scripts/backfill_embedding_metadata.py`

Test can chay:

- [ ] Backend compile.
- [ ] Backfill dry-run.
- [ ] Register user moi -> entity co `embedding.status=pending`.
- [ ] Entity cu -> co object `embedding` sau backfill.
- [ ] Recommendation snapshot field cu khong doi.

---

## Phase 2 - RabbitMQ Optional Infrastructure

Muc tieu: them RabbitMQ client/publisher nhung RabbitMQ down khong lam fail API.

- [ ] Them dependency RabbitMQ client.
- [ ] Them env config RabbitMQ.
- [ ] Them RabbitMQ health optional.
- [ ] Tao event schema versioned.
- [ ] Tao RabbitMQ client.
- [ ] Tao publisher service.
- [ ] Publish event chi sau khi Neo4j KG sync thanh cong.
- [ ] Neu RabbitMQ down, register/create project van thanh cong.
- [ ] Health tra `rabbitmq=unavailable_optional` khi RabbitMQ down, khong lam fail system health.

File du kien:

- [ ] `backend/models/events.py`
- [ ] `backend/infrastructure/rabbitmq_client.py`
- [ ] `backend/services/event_publisher_service.py`
- [ ] `backend/services/health_service.py`
- [ ] `backend/.env.example`
- [ ] `backend/requirements.txt`

Test can chay:

- [ ] RabbitMQ down -> register thanh cong.
- [ ] RabbitMQ down -> create project thanh cong.
- [ ] RabbitMQ up -> publish event thanh cong.
- [ ] Health API van `ok` khi RabbitMQ optional unavailable.

---

## Phase 3 - Worker + GraphSAGE-lite

Muc tieu: worker doc lap tao embedding 128 chieu bang GraphSAGE-lite.

- [ ] Tao worker entry point.
- [ ] Worker chay bang `python -m workers.embedding_worker`.
- [ ] Validate event schema.
- [ ] Set `embedding.status=processing`.
- [ ] Load graph neighborhood tu Neo4j.
- [ ] Tao deterministic text/hash embedding cho Topic/Skill/Industry/Location.
- [ ] Aggregate weighted mean.
- [ ] L2 normalize vector.
- [ ] Set `embedding.signal=ok|low_signal|no_signal`.
- [ ] Ghi embedding vao MongoDB/Neo4j.
- [ ] Set `embedding.status=ready`.
- [ ] Skip obsolete job dua tren job_id/source_hash.
- [ ] Xu ly temporary/validation/permanent error.

File du kien:

- [ ] `backend/workers/embedding_worker.py`
- [ ] `backend/services/graph_feature_service.py`
- [ ] `backend/services/embedding_service.py`
- [ ] `backend/repositories/embedding_repo.py`
- [ ] `backend/repositories/pgpr_graph_repo.py`

Test can chay:

- [ ] Worker consume event.
- [ ] Entity co topic/skill -> embedding ready.
- [ ] Entity chi co name -> no_signal, score cap ve sau.
- [ ] Event cu khong ghi de embedding moi.
- [ ] Vector dung dimension 128.
- [ ] Vector da normalize neu khong phai zero-vector.

---

## Phase 4 - Outbox Reliability

Muc tieu: khong mat event khi RabbitMQ/server loi.

- [ ] Tao collection `embedding_event_outbox`.
- [ ] Khi API tao/update entity/project, ghi outbox event.
- [ ] Publisher job publish RabbitMQ tu outbox.
- [ ] Publish thanh cong -> mark `published`.
- [ ] Publish loi -> giu `pending`.
- [ ] Retry pending theo backoff.
- [ ] Qua max retry -> mark failed/DLQ.

File du kien:

- [ ] `backend/services/outbox_publisher_service.py`
- [ ] `backend/repositories/embedding_outbox_repo.py`
- [ ] `backend/scripts/run_outbox_publisher.py`

Test can chay:

- [ ] RabbitMQ down -> outbox pending.
- [ ] RabbitMQ up -> outbox publish thanh cong.
- [ ] Crash/retry khong duplicate event.

---

## Phase 5 - Candidate Safety + Embedding Search

Muc tieu: moi candidate deu di qua mask chung truoc khi scoring.

Thu tu lam:

- [ ] Tao `CandidateMaskService`.
- [ ] Tao `entity_embeddings` store.
- [ ] Tao `EmbeddingCandidateService`.
- [ ] Embedding nearest search bang cosine trong Python cho MVP.
- [ ] Scale sau moi dung Neo4j vector index / vector DB.

File du kien:

- [ ] `backend/services/candidate_mask_service.py`
- [ ] `backend/services/embedding_candidate_service.py`
- [ ] `backend/repositories/embedding_repo.py`

Test can chay:

- [ ] owner_only cua user khac bi block.
- [ ] rejected/disabled/hidden bi block.
- [ ] merge_required khong lam intermediate node.
- [ ] recommendable_as_target=false bi block.
- [ ] admin_debug tra block reason.

---

## Phase 6 - Hybrid Recommendation Backward Compatible

Muc tieu: them hybrid ranking nhung khong pha response cu.

- [ ] Giu field cu: `id`, `name`, `score`, `reasoning_paths`, `explanation`, `xai_explanation`.
- [ ] Them field moi: `scoring_method`, `evidence_level`, `cold_start`, `embedding_status`, `recommendation_readiness`.
- [ ] Stage 1 candidate generation: PGPR/Cypher/embedding/topic-skill.
- [ ] Stage 2 filter bang CandidateMaskService.
- [ ] Stage 3 scoring: PGPR + embedding + overlap + graph evidence + freshness/profile quality.
- [ ] Stage 4 reranking/diversity/deduplicate/cap weak evidence.
- [ ] Stage 5 XAI multi-evidence.
- [ ] Cap score cho embedding_only/fallback_only/unverified/no_signal.

File du kien:

- [ ] `backend/services/recommendation_service.py`
- [ ] `backend/pgpr/pgpr_recommendation.py`
- [ ] `backend/models/schemas.py`
- [ ] `frontend/src/lib/api.ts`
- [ ] `frontend/src/app/dashboard/page.tsx`

Test can chay:

- [ ] Snapshot compare field cu.
- [ ] Fallback mode khi embedding pending/stale.
- [ ] Hybrid mode khi embedding ready.
- [ ] XAI warning khi cold-start/provisional/no_signal.
- [ ] Frontend dashboard render duoc.

---

## Phase 7 - Admin/Monitoring

Muc tieu: admin quan sat va xu ly embedding pipeline.

- [ ] API list embedding jobs.
- [ ] API retry failed jobs.
- [ ] API recompute entity embedding.
- [ ] User chi recompute entity/project cua minh.
- [ ] Admin recompute moi entity.
- [ ] Rate limit recompute.
- [ ] Audit log retry/recompute.
- [ ] Admin UI hien queue/job/model status.

File du kien:

- [ ] `backend/api/v1/endpoints/admin.py`
- [ ] `backend/api/v1/endpoints/entities.py`
- [ ] `frontend/src/lib/api.ts`
- [ ] `frontend/src/app/admin/page.tsx`

Test can chay:

- [ ] Admin retry failed job.
- [ ] User recompute entity cua nguoi khac bi 403.
- [ ] Audit log co action recompute/retry.

---

## Phase 8 - GraphSAGE Real Model

Chi bat dau khi:

- [ ] GraphSAGE-lite chay on.
- [ ] Embedding ready rate on.
- [ ] Hybrid recommendation da co evaluation so bo.
- [ ] Du lieu du lon de train.

Muc tieu:

- [ ] Export graph snapshot.
- [ ] Tao node feature encoder.
- [ ] Train GraphSAGE 2 layers bang PyTorch Geometric.
- [ ] Luu artifact model/config/encoder/metadata.
- [ ] Worker load model de inference.
- [ ] So sanh GraphSAGE-lite vs GraphSAGE real.

File du kien:

- [ ] `backend/ml/graphsage/`
- [ ] `backend/scripts/export_graph_snapshot.py`
- [ ] `backend/scripts/train_graphsage.py`
- [ ] `backend/artifacts/models/graphsage_v1.pt`
- [ ] `backend/artifacts/models/graphsage_config.json`
- [ ] `backend/artifacts/models/node_feature_encoder.pkl`
- [ ] `backend/artifacts/models/metadata.json`

---

## Phase 9 - Evaluation + Production

Muc tieu: do chat luong va dong goi deploy.

- [ ] Tao evaluation dataset/cases.
- [ ] Baseline random.
- [ ] Baseline topic overlap.
- [ ] Baseline graph heuristic.
- [ ] PGPR only.
- [ ] Embedding only.
- [ ] Hybrid.
- [ ] Precision@K, Recall@K, HitRate@K, NDCG@K, MRR.
- [ ] Coverage.
- [ ] Cold-start success rate.
- [ ] Explanation coverage.
- [ ] Latency.
- [ ] Time to first usable recommendation.
- [ ] Docker compose production: backend/frontend/MongoDB/Neo4j/RabbitMQ/worker.
- [ ] Logging/monitoring/security/RBAC.

---

## Ghi chu an toan

- [ ] Khong thay doi scoring PGPR core truoc khi co snapshot baseline.
- [ ] Moi phase phai chay test rieng.
- [ ] Neu phase nao lam recommendation field cu bien mat, phai rollback phase do.
- [ ] RabbitMQ va worker phai optional trong giai doan dau.
- [ ] GraphSAGE real khong lam truoc khi GraphSAGE-lite + evaluation on dinh.
