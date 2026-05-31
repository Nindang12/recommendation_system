# Ke hoach xu ly Cold-Start bang RabbitMQ + GraphSAGE

Tai lieu nay dung de chot ke hoach xu ly bai toan cold-start cho Expert / Enterprise / Funder / Project moi tao trong he thong recommendation PGPR + Knowledge Graph.

**Dinh vi:** Day la ke hoach cho **he thong ung dung van hanh that** — **ban ung dung van hanh dau tien (initial deployable version)**, khong phai prototype MVP. Sau Phase 7.1, he thong da co RabbitMQ, outbox, DLQ, worker heartbeat, audit, admin monitoring, rate limit, retry filter.

**Ghi chu ve checklist trong file nay:** Cac checklist o muc 3-19 la **thiet ke / yeu cau kien truc goc** (spec ban dau). Trang thai hoan thanh thuc te duoc theo doi trong [`CHECKLIST_SCALE_UP_COLD_START_HYBRID.md`](CHECKLIST_SCALE_UP_COLD_START_HYBRID.md) (Phase 0-12). Khong tick o day khong co nghia la chua lam — xem checklist tong de biet phase nao da xong.

Muc tieu chinh:

- Entity moi tao co the vao he thong nhanh, khong bat user doi train lai PGPR.
- He thong ghi data realtime vao MongoDB / Neo4j truoc.
- Tac vu tinh embedding / cap nhat khong gian bieu dien duoc dua vao RabbitMQ de xu ly bat dong bo.
- PGPR recommendation co the dung duoc ca entity moi thong qua hybrid logic: graph path + candidate generation + embedding.

---

## 1. Kien truc tong the can dat

```mermaid
flowchart TD
    A["Frontend"] --> B["FastAPI Router"]
    B --> C["Service Layer"]
    C --> D["MongoRepository"]
    C --> E["ProvisionalKGSyncService"]
    D --> F["MongoDB"]
    E --> G["Neo4j KG"]
    E --> H["RabbitMQ Publisher"]
    H --> I["RabbitMQ Exchange: kg.events"]
    I --> J["Queue: embedding.jobs"]
    J --> K["Embedding Worker"]
    K --> L["Graph Feature Extractor"]
    L --> G
    K --> M["GraphSAGE-lite / GraphSAGE Model"]
    M --> N["Embedding Store"]
    N --> F
    N --> G
    O["RecommendationService"] --> P["PGPRRecommender"]
    P --> Q["Hybrid Candidate + PGPR Path Ranking"]
    Q --> G
    Q --> N
```

---

## 2. Nguyen tac thiet ke

- [ ] Luong tao user / project khong duoc bi cham vi AI embedding.
- [ ] MongoDB van la noi luu entity nghiep vu day du.
- [ ] Neo4j van la Knowledge Graph phuc vu PGPR / XAI / Graph UI.
- [ ] RabbitMQ chi dung de xu ly cac job nang hoac bat dong bo.
- [ ] Worker phai idempotent, retry khong duoc tao duplicate node / duplicate embedding.
- [ ] Khi embedding chua san sang, recommendation phai co fallback.
- [ ] Entity unverified van bi gioi han theo `participation_scope`, `trust_weight`, `allow_as_source`, `recommendable_as_target`.
- [ ] GraphSAGE khong thay the PGPR, ma bo sung embedding cho cold-start va candidate ranking.

---

## 3. Trang thai du lieu can bo sung

Can bo sung / chuan hoa cac field cho entity trong MongoDB va Neo4j.

```json
{
  "embedding": {
    "status": "pending",
    "job_id": null,
    "last_event_id": null,
    "retry_count": 0,
    "max_retry": 3,
    "model": null,
    "version": 0,
    "dimension": 128,
    "source_hash": null,
    "last_queued_at": null,
    "last_processed_at": null,
    "updated_at": null,
    "error": null,
    "error_type": null,
    "vector": null,
    "normalized": false,
    "signal": "no_signal",
    "locked_by": null,
    "locked_at": null
  }
}
```

Neu can query nhanh trong MongoDB/Neo4j, co the duplicate them field top-level:

```json
{
  "embedding_status": "pending"
}
```

Nhung day chi la denormalized field. Source of truth van la object `embedding.status`.

Enum de dung thong nhat:

- [ ] `pending`: chua publish thanh cong vao RabbitMQ. Trang thai nay thuong xay ra khi entity moi tao xong nhung RabbitMQ dang down, hoac KG sync chua thanh cong.
- [ ] `queued`: da publish event vao RabbitMQ.
- [ ] `processing`: worker dang xu ly.
- [ ] `ready`: embedding da tinh xong.
- [ ] `stale`: profile/project da thay doi, embedding cu khong con khop voi source data va can recompute.
- [ ] `failed`: xu ly loi, can retry.
- [ ] `skipped`: worker bo qua vi entity khong hop le hoac da bi disabled/rejected.

Ghi chu quan trong:

- [ ] `embedding.status=pending` khong co nghia la worker dang doi xu ly. `pending` nghia la job chua vao queue thanh cong.
- [ ] `embedding.status=queued` moi co nghia la job da vao RabbitMQ va dang cho worker.
- [ ] `embedding.job_id` dung de trace job hien tai.
- [ ] `embedding.last_event_id` dung de biet event nao da tao ra embedding moi nhat.
- [ ] `embedding.retry_count` dung cho retry va admin monitoring.
- [ ] `embedding.dimension` phai co de tranh nham version vector 64/128/256.
- [ ] `embedding.source_hash` la hash tu topic/skill/location/industry. Neu source data thay doi va hash khac hash cu thi set `embedding.status=stale`.
- [ ] `embedding.error_type` gom `temporary`, `permanent`, `validation`.
- [ ] `embedding.normalized=true` neu vector da L2-normalize.
- [ ] `embedding.signal` gom `ok`, `low_signal`, `no_signal`.

Chuan tinh `embedding.source_hash`:

```text
source_hash = sha256(normalized_json({
  entity_type,
  entity_id,
  research_topics,
  skills,
  industry,
  location,
  relevant_relationship_ids,
  embedding_version
}))
```

Rule:

- [ ] Tat ca service phai dung cung mot ham `compute_embedding_source_hash`.
- [ ] JSON truoc khi hash phai sort key, sort array, normalize lowercase/trim text.
- [ ] `relevant_relationship_ids` chi gom quan he co anh huong embedding, vi du topic/skill/location/industry/project relation.
- [ ] Neu chi thay doi email/phone/social link thi khong nhat thiet lam stale embedding.
- [ ] Neu thay doi topic/skill/location/industry/relationship quan trong thi bat buoc set `embedding.status=stale`.

Checklist:

- [ ] Them field embedding vao entity MongoDB.
- [ ] Them field embedding vao node Neo4j neu can query truc tiep tu graph.
- [ ] Khong luu embedding vao JWT/session.
- [ ] Khong coi `embedding.status=ready` la verified. Verified va embedding la hai trang thai khac nhau.
- [ ] Khong coi `embedding.status=ready` la recommendation da public duoc. Recommendation con phu thuoc `entity_verification_status`, `participation_scope`, `recommendable_as_target`.

Them field runtime/response de UI biet kha nang goi y:

```json
{
  "recommendation_readiness": "personal_hybrid_ready"
}
```

Enum de xuat:

- [ ] `not_ready`: chua co KG sync hoac entity bi disabled/rejected.
- [ ] `fallback_only`: chua co embedding, chi dung Cypher/rule fallback.
- [ ] `personal_hybrid_ready`: source cua chinh user co the dung hybrid trong personal mode.
- [ ] `public_hybrid_ready`: entity verified/public co the tham gia recommendation cong khai.

---

## 4. RabbitMQ setup

De xuat dung RabbitMQ cho ban ung dung van hanh dau tien (initial deployable version) vi de cai, de van hanh, phu hop voi he thong ung dung thuc (khong con la prototype don gian).

### 4.1 Exchange va queue

- [ ] Exchange: `kg.events`
- [ ] Exchange type: `topic`
- [ ] Queue chinh: `embedding.jobs`
- [ ] Dead-letter exchange: `kg.events.dlx`
- [ ] Dead-letter queue: `embedding.jobs.dlq`
- [ ] Routing keys:
  - [ ] `kg.entity.created`
  - [ ] `kg.entity.updated`
  - [ ] `kg.project.created`
  - [ ] `kg.project.updated`
  - [ ] `kg.embedding.recompute`

### 4.2 Bien moi truong

Can them vao `.env.example`:

```env
RABBITMQ_URL=amqp://guest:guest@localhost:5672/
RABBITMQ_EXCHANGE=kg.events
RABBITMQ_EMBEDDING_QUEUE=embedding.jobs
RABBITMQ_EMBEDDING_DLX=kg.events.dlx
RABBITMQ_EMBEDDING_DLQ=embedding.jobs.dlq
EMBEDDING_MODEL_NAME=graphsage_lite_v1
EMBEDDING_VERSION=1
EMBEDDING_DIMENSION=128
EMBEDDING_MAX_RETRY=3
EMBEDDING_RETRY_BACKOFF_SECONDS=30,120,600
```

Checklist:

- [ ] Them RabbitMQ vao docker-compose neu co.
- [ ] Them env config cho backend.
- [ ] Them health check RabbitMQ vao `/api/v1/health`, nhung chi nen la optional.
- [ ] Neu RabbitMQ chua chay, luong register / create project khong duoc fail.
- [ ] Neu publish event loi, set `embedding.status=pending` hoac `failed` de retry sau.

### 4.3 Retry/backoff policy

Initial deployable version de xuat:

- [ ] `max_retry=3`.
- [ ] Backoff lan 1: 30 giay.
- [ ] Backoff lan 2: 2 phut.
- [ ] Backoff lan 3: 10 phut.
- [ ] Qua `max_retry` thi dua message vao `embedding.jobs.dlq`.

Phan loai loi:

- [ ] `temporary`: Neo4j timeout, RabbitMQ reconnect, MongoDB transient error -> retry.
- [ ] `validation`: entity thieu du lieu toi thieu de tao embedding -> khong retry lien tuc, can user/admin bo sung data.
- [ ] `permanent`: entity rejected/disabled/hidden -> skip hoac dua vao DLQ tuy nhu cau audit.

---

## 5. Event schema

Moi message dua vao queue nen co schema on dinh.

```json
{
  "event_id": "evt_...",
  "job_id": "job_...",
  "event_type": "kg.entity.created",
  "schema_version": 1,
  "entity_type": "expert",
  "entity_id": "user_exp_001",
  "user_id": "usr_001",
  "source": "user_registration",
  "kg_sync_status": "synced_unverified",
  "entity_verification_status": "unverified",
  "embedding_version": 1,
  "embedding_source_hash": "sha256_of_topics_skills_location_industry",
  "created_at": "2026-05-28T10:00:00Z"
}
```

Checklist:

- [ ] Tao model/schema cho event.
- [ ] Moi event phai co `event_id`.
- [ ] Moi event phai co `job_id` neu day la embedding job co the retry/monitor.
- [ ] Moi event phai co `entity_type` va `entity_id`.
- [ ] Moi event phai co `embedding_version` de worker biet co can tinh lai khong.
- [ ] Moi event nen co `embedding_source_hash` de worker phat hien event cu/stale.
- [ ] Event khong nen chua toan bo profile data de tranh message qua lon.
- [ ] Worker se dung `entity_id` de load data moi nhat tu MongoDB / Neo4j.
- [ ] Worker khong duoc de event cu ghi de embedding moi hon. Phai so sanh `embedding_version`, `embedding.last_event_id`, `embedding.source_hash`, va thoi gian update.
- [ ] Neu source hash trong event khac source hash hien tai cua entity, worker phai bo qua event cu hoac publish recompute moi.

### 5.1 Thoi diem publish event

Khong publish embedding event truoc khi node Neo4j ton tai. Worker can doc graph neighborhood, nen luong dung phai la:

```text
MongoDB entity/project created
  -> ProvisionalKGSyncService sync Neo4j thanh cong
  -> publish embedding event vao RabbitMQ
  -> set embedding.status = queued
```

Rule theo event type:

- [ ] `kg.entity.created`: publish sau khi entity da sync Neo4j thanh cong.
- [ ] `kg.entity.updated`: publish khi topic/skill/location/industry thay doi va Neo4j da update xong.
- [ ] `kg.project.created`: publish sau khi project da sync Neo4j thanh cong.
- [ ] `kg.project.updated`: publish khi thong tin recommendation-critical cua project thay doi.
- [ ] `kg.embedding.recompute`: publish khi admin bam recompute, hoac sau verify/merge can tinh lai.

Neu KG sync failed:

- [ ] Khong publish embedding event.
- [ ] Set `embedding.status=pending`.
- [ ] Ghi `embedding.error` hoac `kg_sync_error`.
- [ ] Chi publish sau khi retry KG sync thanh cong.

### 5.2 Outbox pattern

Ban dau co the publish truc tiep va neu loi thi set `embedding.status=pending`. De van hanh on dinh, da trien khai outbox pattern qua collection:

```text
embedding_event_outbox
```

Luong outbox:

- [ ] API tao entity/project.
- [ ] Ghi outbox event vao MongoDB.
- [ ] Publisher co gang publish RabbitMQ.
- [ ] Publish thanh cong -> mark outbox `published`.
- [ ] Publish that bai -> outbox giu `pending` de retry.
- [ ] Background job retry outbox pending theo backoff.

---

## 5.3 State transition va stale job

Can quy dinh ro truong hop profile/project thay doi trong luc job cu dang queued/processing.

Rule:

- [ ] Moi job co `job_id` va `embedding_source_hash`.
- [ ] Entity chi duoc ghi ket qua embedding neu `message.job_id == embedding.job_id` va `message.embedding_source_hash == embedding.source_hash` hien tai.
- [ ] Neu source hash thay doi khi job cu dang `queued` hoac `processing`, publish event moi voi `job_id` moi.
- [ ] Job cu tro thanh obsolete/stale, worker cu neu xu ly xong phai skip, khong duoc set `ready` hoac `failed` de ghi de job moi.
- [ ] Chi job co source hash moi nhat moi duoc set `embedding.status=ready`.

State transition de xuat:

```text
pending -> queued -> processing -> ready
pending -> failed
queued/processing + source_hash_changed -> stale -> queued(new job)
ready + source_hash_changed -> stale -> queued(new job)
failed + retry -> queued
rejected/disabled -> skipped
```

Concurrency/lock:

```json
{
  "embedding": {
    "locked_by": null,
    "locked_at": null
  }
}
```

Initial deployable version co the chay mot worker va chua can distributed lock phuc tap, nhung logic update nen atomic:

- [ ] Worker chi duoc set `processing` neu `embedding.status in ["queued", "stale", "failed"]`.
- [ ] Worker chi duoc set `processing` neu `embedding.job_id == message.job_id`.
- [ ] Khi set `processing`, cap nhat `embedding.locked_by` va `embedding.locked_at`.
- [ ] Neu lock qua han, worker khac co the retry theo policy.

---

## 6. Backend Publisher Service

Can tao service rieng:

```text
backend/services/event_publisher_service.py
backend/infrastructure/rabbitmq_client.py
```

Nhiem vu:

- [ ] Ket noi RabbitMQ.
- [ ] Declare exchange / queue neu chua co.
- [ ] Publish event chi sau khi entity/project moi duoc sync vao KG thanh cong.
- [ ] Xu ly loi RabbitMQ khong lam fail API chinh.
- [ ] Cap nhat `embedding.status=queued` neu publish thanh cong.
- [ ] Cap nhat `embedding.status=pending` hoac `failed` neu publish that bai.
- [ ] Cap nhat `embedding.job_id`, `embedding.last_event_id`, `embedding.last_queued_at`, `embedding.retry_count`.
- [ ] Cap nhat `embedding.source_hash` dua tren topic/skill/location/industry hien tai.

Noi can goi publisher:

- [ ] Sau khi register va tao/link entity moi, dong thoi Provisional KG Sync thanh cong.
- [ ] Sau khi user tao project moi va project sync Neo4j thanh cong.
- [ ] Sau khi user cap nhat profile co thay doi topic / skill / location / industry va KG update thanh cong.
- [ ] Sau khi admin verify/merge entity neu can tinh lai embedding.

---

## 7. Embedding Worker

Can tao worker chay doc lap:

```text
backend/workers/embedding_worker.py
```

Trach nhiem:

- [ ] Consume message tu `embedding.jobs`.
- [ ] Check entity co ton tai khong.
- [ ] Check entity co bi `rejected`, `disabled`, `hidden` khong.
- [ ] Set `embedding.status=processing`.
- [ ] Load graph neighborhood tu Neo4j.
- [ ] Tinh embedding.
- [ ] Ghi embedding vao MongoDB / Neo4j.
- [ ] Set `embedding.status=ready`.
- [ ] Neu loi, set `embedding.status=failed`, ghi `embedding.error`, `embedding.error_type`.
- [ ] Ack message khi xu ly thanh cong.
- [ ] Nack/requeue neu loi tam thoi.
- [ ] Day vao DLQ neu vuot qua `embedding.max_retry`.

Checklist idempotency:

- [ ] Neu `embedding.status=ready` va `embedding.version` da moi nhat thi skip.
- [ ] Neu message cu hon version hien tai thi skip.
- [ ] Neu `embedding.source_hash` hien tai khac source hash trong message thi skip event cu va publish recompute moi.
- [ ] Worker khong dung `CREATE` khi update Neo4j.
- [ ] Worker chi update node bang `MERGE` / `MATCH SET`.
- [ ] Worker phai ghi log ro entity nao dang xu ly.

---

## 8. Graph Feature Extractor

Can tao lop trich xuat dac trung graph:

```text
backend/services/graph_feature_service.py
```

Nguon dac trung:

- [ ] Topic / research topic cua entity.
- [ ] Research direction suy ra tu topic.
- [ ] Skill / technology.
- [ ] Location.
- [ ] Industry / sector.
- [ ] Quan he project-expert-enterprise-funder neu co.
- [ ] Trang thai verified/unverified.
- [ ] Trust weight.

Output de worker dung:

```json
{
  "entity_id": "user_exp_001",
  "entity_type": "expert",
  "node_features": {},
  "neighbors_1hop": [],
  "neighbors_2hop": [],
  "neighbor_embeddings": []
}
```

Checklist:

- [ ] Viet Cypher lay hang xom 1-hop.
- [ ] Viet Cypher lay hang xom 2-hop co gioi han.
- [ ] Khong expand qua node `disabled/rejected/hidden`.
- [ ] Respect `participation_scope`.
- [ ] Respect `allow_as_intermediate_node`.
- [ ] Co fallback neu hang xom chua co embedding.
- [ ] Khi aggregate neighbor embeddings, bo qua neighbor `rejected/disabled/hidden`.
- [ ] Khi aggregate trong public context, bo qua `owner_only` cua user khac.
- [ ] Giam trong so neighbor `unverified`.
- [ ] Khong dung `merge_required` lam neighbor chinh.
- [ ] Khong de provisional/duplicate node lam nhiem embedding cua entity moi.

---

## 9. GraphSAGE-lite baseline for the initial deployable system

De co embedding on dinh cho he thong van hanh, nen dung GraphSAGE-lite lam baseline truoc khi train GraphSAGE real (Phase 10).

Y tuong:

- Lay embedding co san cua Topic / Skill / Industry / Location.
- Neu neighbor chua co embedding, tao vector deterministic bang hash/text feature.
- Entity moi = weighted mean cua neighbor embeddings.
- Ap dung trust/verification weight.

Nguon embedding ban dau cho Topic / Skill / Industry / Location:

- [ ] Baseline dung deterministic text embedding hoac hashing vector co dinh dimension 128.
- [ ] Cung mot label, vi du `Computer Vision`, phai sinh ra cung mot vector neu cung `embedding.model` va `embedding.version`.
- [ ] Ham de xuat: `get_or_create_text_embedding(label, dimension=128, model_version=1)`.
- [ ] Sau nay khi co GraphSAGE/PyG that, co the migrate vector nhung phai tang `embedding.version`.

Cong thuc baseline:

```text
entity_embedding =
  mean(
    topic_embeddings * topic_weight,
    skill_embeddings * skill_weight,
    industry_embeddings * industry_weight,
    location_embeddings * location_weight
  )
```

Trong so de xuat:

- [ ] Topic: 0.40
- [ ] Skill / technology: 0.30
- [ ] Industry / sector: 0.15
- [ ] Location: 0.05
- [ ] Existing graph relation: 0.10

Checklist:

- [ ] Tao `EmbeddingService`.
- [ ] Tao ham `get_or_create_text_embedding`.
- [ ] Tao ham `aggregate_neighbor_embeddings`.
- [ ] Chuan hoa vector ve cung dimension, de xuat 128.
- [ ] Vector sau khi aggregate phai L2-normalize.
- [ ] Similarity mac dinh dung cosine similarity.
- [ ] Neu vector la zero-vector thi khong normalize, set warning/no_signal va khong cho score cao.
- [ ] Neu entity co du topic/skill/location/industry toi thieu, set `embedding.signal=ok`.
- [ ] Neu entity chi co mot it tin hieu, set `embedding.signal=low_signal`.
- [ ] Neu entity gan nhu chi co name/basic info, set `embedding.signal=no_signal`.
- [ ] Luu `embedding.model=graphsage_lite_v1`.
- [ ] Luu `embedding.version=1`.
- [ ] Luu `embedding.dimension=128`.
- [ ] Luu `embedding.normalized=true` neu da normalize.
- [ ] Test entity moi co topic/skill thi sinh duoc embedding.
- [ ] Test entity khong co du lieu thi `embedding.status=failed` voi `embedding.error_type=validation` hoac tao zero-vector co canh bao.

Rule cho `no_signal`:

- [ ] Neu `embedding.signal=no_signal`, `evidence_level` khong duoc la `embedding_only`.
- [ ] Recommendation mode nen la `fallback_until_embedding_ready_or_enough_data`.
- [ ] Score cap de xuat `max_score=0.40`.
- [ ] UI nen hien canh bao: "Ho so chua du du lieu topic/skill/location de goi y chinh xac."

---

## 10. GraphSAGE real model (Phase 10 — sau Evaluation)

Sau khi ban ung dung van hanh dau tien on dinh va co evaluation baseline (Phase 8), moi nang cap sang GraphSAGE that.

De xuat model:

- Framework: PyTorch Geometric.
- Model: GraphSAGE 2 layers.
- Aggregator: mean.
- Hidden dimension: 128.
- Output dimension: 128.
- Neighbor sampling: `[10, 5]`.
- Training task:
  - Link prediction giua entity va project.
  - Hoac contrastive learning dua tren edge trong KG.

Artifact can luu:

```text
backend/artifacts/models/graphsage_v1.pt
backend/artifacts/models/graphsage_config.json
backend/artifacts/models/node_feature_encoder.pkl
```

Checklist:

- [ ] Export graph tu Neo4j thanh training dataset.
- [ ] Tao node feature encoder.
- [ ] Train GraphSAGE offline.
- [ ] Luu model artifact.
- [ ] Worker load model khi startup.
- [ ] Worker inference entity moi khong can retrain.
- [ ] Co script retrain dinh ky neu graph lon len.

---

## 11. Luu embedding

Can chot noi luu embedding.

Khuyen nghi:

- MongoDB luu metadata embedding de quan ly status.
- Neo4j luu vector ngan gon neu can query tu graph.
- Neu sau nay can vector search lon, them vector DB sau.

MongoDB:

```json
{
  "embedding": {
    "status": "ready",
    "job_id": "job_...",
    "last_event_id": "evt_...",
    "retry_count": 0,
    "max_retry": 3,
    "model": "graphsage_lite_v1",
    "version": 1,
    "dimension": 128,
    "source_hash": "sha256_of_topics_skills_location_industry",
    "vector": [],
    "normalized": true,
    "last_queued_at": "...",
    "last_processed_at": "...",
    "updated_at": "...",
    "error": null,
    "error_type": null
  }
}
```

Neo4j:

```cypher
MATCH (n {id: $entity_id})
SET
  n.embedding_status = "ready",
  n.embedding_model = "graphsage_lite_v1",
  n.embedding_version = 1,
  n.embedding_dimension = 128,
  n.embedding_source_hash = $source_hash,
  n.embedding_normalized = true,
  n.embedding_updated_at = datetime(),
  n.embedding_vector = $vector
```

Checklist:

- [ ] Khong ghi vector qua lon vao response API mac dinh.
- [ ] API detail chi hien embedding status, khong show full vector.
- [ ] Neu vector ghi Neo4j loi, MongoDB phai ghi `sync_partial`.
- [ ] Co job retry neu MongoDB ready nhung Neo4j chua co vector.
- [ ] Initial deployable version co the luu vector 128 chieu trong MongoDB va optional Neo4j.
- [ ] Production/scale nen chuyen sang vector index hoac vector DB rieng de tranh document/node phinh to.

---

## 12. Tich hop vao RecommendationService

Khi user goi recommendation:

Rule bat buoc:

- [ ] Embedding similarity chi dung de mo rong candidate, rerank nhe, va ho tro cold-start.
- [ ] Embedding similarity khong duoc thay the reasoning path/evidence.
- [ ] Result chi dua tren embedding ma khong co path/evidence khong duoc co score qua cao.
- [ ] XAI khong duoc giai thich embedding-only result nhu ket qua chac chan.

### 12.0 Embedding candidate search

Initial deployable version (Python cosine search):

- [ ] Load embedding cua source entity.
- [ ] Load embedding cua candidate theo `target_type` tu MongoDB hoac Neo4j.
- [ ] Chi lay candidate thoa visibility/participation/recommendable rule.
- [ ] Bo qua candidate `rejected/disabled/hidden`.
- [ ] Bo qua target `owner_only` cua user khac trong public mode.
- [ ] Tinh cosine similarity trong Python voi tap candidate nho/trung binh.
- [ ] Lay `top_k` candidate dua vao PGPR/path search tiep.

Scale phase:

- [ ] Dung Neo4j vector index neu luu vector trong Neo4j.
- [ ] Hoac dung vector DB rieng neu so entity/vector lon.
- [ ] Van phai filter permission/visibility truoc hoac sau vector search.

Response nen co them:

```json
{
  "scoring_method": "hybrid_embedding_path",
  "evidence_level": "path_supported"
}
```

Enum de xuat cho `evidence_level`:

- [ ] `path_supported`: co reasoning path/evidence ro.
- [ ] `embedding_only`: chi co embedding similarity, khong co path tot.
- [ ] `fallback_only`: dang dung Cypher/rule fallback vi embedding chua ready.

Score cap:

- [ ] Neu `evidence_level=embedding_only`, cap score de xuat `max_score=0.65`.
- [ ] Neu `evidence_level=fallback_only`, cap score de xuat `max_score=0.55`.
- [ ] Neu entity/result la `unverified` va `evidence_level=embedding_only`, cap score de xuat `max_score=0.50`.
- [ ] Neu entity/result la `unverified` va `evidence_level=fallback_only`, cap score de xuat `max_score=0.45`.
- [ ] Neu `embedding.signal=no_signal`, cap score de xuat `max_score=0.40`.
- [ ] Neu entity/result la `verified` va `evidence_level=path_supported`, co the dung score PGPR day du sau khi ap dung trust/policy.
- [ ] Neu `reasoning_paths=[]`, result phai bi giam score hoac loai tru tuy mode.

### 12.1 Neu source la entity cu da co embedding

- [ ] Chay PGPR nhu hien tai.
- [ ] Dung embedding de re-rank neu can.
- [ ] XAI van uu tien reasoning path.

### 12.2 Neu source la entity moi va embedding ready

- [ ] Dung embedding de tim candidate lien quan.
- [ ] Chay PGPR/path search trong tap candidate.
- [ ] Tra ket qua hybrid.

### 12.3 Neu source la entity moi va embedding chua ready

- [ ] Dung Cypher candidate generator tam thoi.
- [ ] Dung rule/path scoring fallback.
- [ ] Response phai co canh bao:

```json
{
  "cold_start": true,
  "embedding_status": "queued",
  "recommendation_mode": "fallback_until_embedding_ready"
}
```

### 12.4 Neu embedding bi stale

Khi user cap nhat profile/project va source hash thay doi, embedding cu phai chuyen sang `stale` trong luc cho worker recompute.

Response nen co:

```json
{
  "cold_start": true,
  "embedding_status": "stale",
  "recommendation_mode": "fallback_until_embedding_recomputed",
  "message": "Ho so vua thay doi, he thong dang cap nhat du lieu goi y."
}
```

Rule:

- [ ] Stale embedding khong duoc dung nhu embedding ready.
- [ ] Co the dung fallback/path co canh bao.
- [ ] UI hien ro trang thai dang cap nhat du lieu goi y.

Checklist:

- [ ] Them `recommendation_mode`.
- [ ] Them `cold_start`.
- [ ] Them `embedding_status`.
- [ ] Them `recommendation_readiness`.
- [ ] Them `scoring_method`.
- [ ] Them `evidence_level`.
- [ ] Khong tra score cao neu khong co path va embedding chua ready.
- [ ] Neu `reasoning_paths=[]`, score phai bi giam hoac result bi loai tru tuy mode.
- [ ] XAI phai noi ro ket qua dang o cold-start mode.

---

## 13. Action Masking cho PGPR

Muc tieu: PGPR khong bi "mu" voi node moi.

Checklist:

- [ ] Tao CandidateMaskService.
- [ ] Candidate mask dua tren topic/skill/industry/location/embedding similarity.
- [ ] Personal mode cho phep source unverified cua current user.
- [ ] Public mode an node owner_only cua user khac.
- [ ] Merge_required khong duoc lam intermediate node.
- [ ] Rejected/disabled phai bi loai tru hoan toan.
- [ ] PGPR chi search trong candidate/action space da duoc mask.

---

## 14. API can them

### User/internal API

- [ ] `GET /api/v1/entities/{type}/{id}/embedding-status`
- [ ] `POST /api/v1/entities/{type}/{id}/embedding/recompute`

### Admin API

- [ ] `GET /api/v1/admin/embedding/jobs`
- [ ] `POST /api/v1/admin/embedding/retry-failed`
- [ ] `POST /api/v1/admin/entities/{type}/{id}/embedding/recompute`

### Health API

- [ ] `/api/v1/health` them RabbitMQ optional status.
- [ ] `/api/v1/health` them worker status neu co heartbeat.

Security/rate limit:

- [ ] User chi duoc recompute embedding cho linked entity cua chinh ho.
- [ ] User chi duoc recompute embedding cho project do ho so huu.
- [ ] Admin/root admin duoc recompute moi entity.
- [ ] Can rate limit recompute de tranh spam queue.
- [ ] Rate limit initial deployable version de xuat: moi entity chi duoc user recompute 1 lan / 5 phut.
- [ ] Admin recompute phai ghi audit log.

---

## 15. Monitoring va audit

Can theo doi de demo va debug.

Checklist:

- [ ] Log khi publish event.
- [ ] Log khi worker consume event.
- [ ] Log thoi gian tinh embedding.
- [ ] Log loi vao `embedding_error`.
- [ ] Ghi audit log khi admin recompute embedding.
- [ ] Dem so job:
  - [ ] queued
  - [ ] processing
  - [ ] ready
  - [ ] failed
  - [ ] dlq
- [ ] Admin UI hien danh sach failed jobs.

---

## 16. Test checklist

### Unit test

- [ ] Event schema validate dung.
- [ ] Publisher khong lam fail API khi RabbitMQ down.
- [ ] Worker skip event cu.
- [ ] Worker cu khong duoc ghi de embedding moi hon.
- [ ] Worker retry khong tao duplicate.
- [ ] GraphSAGE-lite sinh vector dung dimension.
- [ ] GraphSAGE-lite vector phai L2-normalize neu khong phai zero-vector.
- [ ] Deterministic text embedding cung label phai cho cung vector.
- [ ] Source hash thay doi thi embedding cu duoc danh dau `stale`.
- [ ] `compute_embedding_source_hash` sort key/sort array/normalize text on dinh.
- [ ] Worker chi set processing neu `embedding.job_id == message.job_id`.
- [ ] Worker bo qua job obsolete khi source hash khac hash hien tai.

### Integration test

- [ ] Register expert moi -> entity created -> event queued.
- [ ] Worker consume -> embedding ready.
- [ ] Create project moi -> event queued -> embedding ready.
- [ ] RabbitMQ down -> register van thanh cong -> `embedding.status=pending`.
- [ ] RabbitMQ up lai -> retry publish thanh cong.
- [ ] Failed worker job vao DLQ sau so lan retry.
- [ ] Khong publish embedding event neu KG sync failed.
- [ ] Outbox pending duoc publish lai khi RabbitMQ online, neu da lam outbox phase sau.
- [ ] Update profile topic/skill/location/industry -> `embedding.status=stale` hoac `queued`.
- [ ] Worker recompute -> `embedding.status=ready` voi source hash moi.
- [ ] Update project topic/requirement -> publish recompute event.
- [ ] Hai worker xu ly gan dong thoi khong duoc ghi de ket qua moi hon.

### Recommendation test

- [ ] Entity moi embedding pending -> fallback mode, score khong duoc cao bat thuong.
- [ ] Entity moi embedding ready -> hybrid mode.
- [ ] Entity embedding stale -> fallback hoac warning mode.
- [ ] Embedding-only result bi cap score.
- [ ] Unverified + embedding-only bi cap score thap hon verified + embedding-only.
- [ ] Unverified + fallback-only bi cap score thap hon verified + fallback-only.
- [ ] `embedding.signal=no_signal` khong duoc sinh `embedding_only` confidence cao.
- [ ] Embedding candidate search chi lay candidate qua visibility/permission filter.
- [ ] Response co `evidence_level` va `scoring_method`.
- [ ] Source unverified cua current user duoc dung lam source.
- [ ] Unverified cua user khac khong duoc lam target public.
- [ ] Rejected/disabled khong xuat hien trong recommendation.
- [ ] Neu khong co reasoning path, XAI khong duoc giai thich nhu ket qua chac chan.

---

## 17. Lo trinh trien khai de xuat

### Phase A - RabbitMQ infrastructure

- [ ] Them RabbitMQ env config.
- [ ] Them RabbitMQ client.
- [ ] Them publisher service.
- [ ] Them health optional cho RabbitMQ.
- [ ] Them event schema.
- [ ] Chua can GraphSAGE real o phase nay.

### Phase B - Hoan thien Provisional KG Sync truoc khi queue

- [ ] Hoan thien sync topic/skill/location/industry sang Neo4j.
- [ ] Dam bao filter provisional/rejected/disabled dung trong candidate query.
- [ ] Dam bao entity moi co `participation_scope`, `allow_as_source`, `recommendable_as_target`.
- [ ] Chi khi KG sync thanh cong moi cho phep publish embedding event.

### Phase C - Publish event tu luong hien tai

- [ ] Register expert/enterprise/funder publish event sau KG sync thanh cong.
- [ ] Create project publish event sau KG sync thanh cong.
- [ ] Update profile/project publish recompute event sau KG update thanh cong.
- [ ] Update MongoDB embedding status/job id/event id.
- [x] Outbox pattern da trien khai (`embedding_event_outbox` + outbox publisher).

### Phase D - Worker (initial deployable version)

- [ ] Tao embedding worker.
- [ ] Consume event.
- [ ] Load entity + graph neighbors.
- [ ] Tinh GraphSAGE-lite embedding.
- [ ] Luu embedding vao MongoDB / Neo4j.
- [ ] Retry va DLQ.

### Phase E - Recommendation integration

- [ ] Them embedding status vao recommendation response.
- [ ] Them fallback mode khi embedding chua ready.
- [ ] Them hybrid mode khi embedding ready.
- [ ] Giam/loai ket qua khong co path va khong co embedding support.
- [ ] Them `evidence_level`, `scoring_method`, `recommendation_readiness`.
- [ ] Cap nhat XAI warning cho cold-start.

### Phase F - Admin/Monitoring

- [ ] Admin UI xem embedding status.
- [ ] Admin retry failed jobs.
- [ ] Audit log recompute/retry.
- [ ] Dashboard thong ke queue/job.

### Phase G - Admin/Monitoring hardening (Phase 7.1)

- [x] Worker heartbeat + liveness alive/stale/unknown.
- [x] DLQ visibility (count, alert, sample peek/requeue).
- [x] Recompute reason + audit default.
- [x] Retry-failed filters (`error_type`, `limit`, `include_permanent` + reason).

---

## 17.1 Lo trinh con lai (Phase 8-12)

Thu tu uu tien sau Phase 7.1:

| Phase | Ten | Ly do |
|-------|-----|-------|
| **8** | Evaluation & Quality Assurance | Can baseline truoc khi doi model/ranking |
| **9** | Production Deployment | Dong goi van hanh that: docker, health, backup |
| **10** | GraphSAGE Real Model / Model Lifecycle | Can ground truth + evaluation de so sanh lite vs real |
| **11** | Data Governance nang cao | Merge/duplicate/provisional policy mo rong |
| **12** | Security Hardening | RBAC sau cung, sau khi pipeline on dinh |

### Phase 8 - Evaluation & Quality Assurance

- [ ] Tao ground truth dataset.
- [ ] Script `run_evaluation.py`.
- [ ] Baseline: random, topic overlap, graph heuristic.
- [ ] Chay PGPR only, embedding only, hybrid.
- [ ] Metric: Precision@K, Recall@K, NDCG@K, MRR, coverage, cold-start success rate, explanation coverage, latency p50/p95.
- [ ] Xuat report JSON/CSV/Markdown.
- [ ] Dinh nghia regression threshold cho model/ranking moi.
- [ ] Regression gate: neu hybrid/model moi lam NDCG@K hoac MRR giam qua nguong thi khong duoc promote/deploy.

### Phase 9 - Production Deployment

- [x] `docker-compose.production.yml`.
- [x] Service: backend API, frontend, embedding_worker, outbox_publisher.
- [x] MongoDB / Neo4j / RabbitMQ persistence + volume + backup.
- [x] Test restore MongoDB/Neo4j tu backup mau (scripts + opt-in test).
- [x] RabbitMQ durable queue + persistent messages.
- [x] Health check backend/worker/rabbitmq; restart policy.
- [x] `.env.production.example`.

### Phase 10 - GraphSAGE Real Model / Model Lifecycle

Dieu kien bat dau:

- [ ] GraphSAGE-lite chay on.
- [ ] Embedding ready rate on.
- [ ] Hybrid recommendation da co evaluation so bo (Phase 8).
- [ ] Du lieu du lon de train.

Checklist:

- [ ] Export graph snapshot.
- [ ] Build node feature encoder.
- [ ] Train GraphSAGE real (PyG).
- [ ] Evaluate GraphSAGE-lite vs GraphSAGE real.
- [ ] Model registry/versioning; worker load model by version.
- [ ] Rollback model neu evaluation te hon baseline.

### Phase 11 - Data Governance nang cao

- [ ] Merge/duplicate entity policy mo rong.
- [ ] Provisional node lifecycle audit.
- [ ] Admin tooling cho data quality.

### Phase 12 - Security Hardening

- [ ] RBAC chi tiet hon cho admin pipeline.
- [ ] Secret management / production env hardening.
- [ ] Rate limit va abuse protection mo rong.

---

## 18. Dieu kien hoan thanh ban ung dung van hanh dau tien

Da dat (Phase 0-7.1):

- [x] User tao Expert moi, API tra ket qua nhanh.
- [x] Entity moi duoc sync vao Neo4j voi status unverified/owner_only.
- [x] RabbitMQ + outbox nhan event embedding.
- [x] Worker tinh embedding thanh cong (GraphSAGE-lite baseline).
- [x] Profile/Admin hien `embedding.status=ready` hoac `embedding_status=ready`.
- [x] Recommendation hybrid; fallback khi embedding chua ready.
- [x] Admin pipeline: jobs, retry-failed, heartbeat, DLQ, audit reason.
- [x] Rate limit recompute; RBAC user/admin.

Con lai cho ban van hanh day du (Phase 8-12):

- [x] Evaluation baseline (Phase 8) truoc khi doi model.
- [x] Production deploy docker + backup (Phase 9).
- [ ] GraphSAGE real chi sau evaluation (Phase 10).

---

## 19. Ghi chu kien truc quan trong

- RabbitMQ khong lam PGPR thong minh hon; RabbitMQ chi giup xu ly bat dong bo va on dinh tai.
- GraphSAGE / embedding layer moi la phan giup entity moi co bieu dien toan hoc.
- PGPR van can path/evidence de giai thich.
- Best design cho he thong nay la hybrid:
  - Cypher de lay candidate nhanh.
  - Embedding de giam cold-start.
  - PGPR de ranking/path reasoning.
  - XAI de giai thich va canh bao chat luong du lieu.


