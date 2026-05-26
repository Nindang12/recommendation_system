# Ke hoach Provisional KG Sync

> Cap nhat: 2026-05-25  
> Muc dich: lap ke hoach nang cap he thong de entity moi cua user co the vao Knowledge Graph ngay, nhung van bi danh dau chua xac thuc va bi gioi han anh huong den recommendation.

## 1. Ly do can Provisional KG Sync

Hien tai luong du lieu moi cua user dang co van de:

```text
Register / Create Project
-> tao entity trong MongoDB
-> entity chua vao Neo4j
-> PGPR/Graph khong biet entity moi
-> user moi khong dung recommendation day du ngay duoc
```

Neu cho entity moi vao Neo4j ngay ma khong kiem soat, he thong co rui ro:

- Duplicate node voi data da crawl san.
- PGPR ranking bi sai.
- XAI reasoning path kho giai thich.
- KG bi nhieu neu user nhap sai.

Giai phap chot:

```text
Provisional KG Sync
```

Y nghia: entity moi duoc sync vao Neo4j ngay de co the dung recommendation, nhung node do co trang thai `unverified`, `limited visibility`, `participation_scope` bi gioi han va `trust_weight` thap hon entity da xac thuc.

## 2. Kien truc muc tieu

Luong register/create entity moi:

```text
Frontend
   |
   v
FastAPI Router
   |
   v
AuthService / UserProjectService
   |
   v
EntityMatchingService
   |
   v
AuthRepository / MongoRepository
   |
   v
ProvisionalKGSyncService
   |
   v
PGPRGraphRepository / KGRepository
   |
   v
Neo4j
```

Luong recommendation sau khi co provisional node:

```text
Frontend
   |
   v
RecommendationService
   |
   v
PGPRRecommender
   |
   v
PGPRGraphRepository
   |
   v
Neo4j
   |
   v
Visibility/Participation Filter
   |
   v
Trust-aware Scoring
   |
   v
XAI Explanation co badge unverified
```

Nguyen tac:

- Register khong sync thang vao KG truoc khi matching.
- Duplicate matching phai chay truoc Provisional KG Sync.
- Node unverified duoc vao KG nhung khong co quyen luc ngang node verified.
- Khong chi nhan `trust_weight` o cuoi. Phai loc `visibility` va `participation_scope` truoc/trong khi query path.
- Node sai khong xoa cung ngay, chi disable/soft delete.
- XAI phai noi ro khi ket qua dua tren du lieu chua xac thuc.

## 3. Trang thai du lieu can thiet ke

### 3.1 Trang thai xac thuc account va entity

Can phan biet ro xac thuc tai khoan va xac thuc entity nghiep vu.

Trong `app_users`, nen dung:

```text
account_verification_status
```

Gia tri de xuat:

```text
email_unverified
email_verified
blocked
```

Trong `experts`, `enterprises`, `funders`, `projects`, nen dung:

```text
entity_verification_status
```

Gia tri de xuat:

```text
unverified
pending_review
verified
rejected
```

Y nghia cua `entity_verification_status`:

| Trang thai | Y nghia |
|---|---|
| `unverified` | Moi tao, chua duoc xac thuc |
| `pending_review` | Dang cho admin/he thong review |
| `verified` | Da duoc xac thuc |
| `rejected` | Bi tu choi |

### 3.2 kg_sync_status

Dung de mo ta trang thai entity voi Neo4j.

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

Y nghia:

| Trang thai | Y nghia |
|---|---|
| `not_synced` | Chua vao Neo4j |
| `syncing` | Dang sync sang Neo4j |
| `synced_unverified` | Da vao Neo4j nhung chua xac thuc |
| `synced_verified` | Da vao Neo4j va da verified |
| `merge_required` | Nghi trung entity cu, can review/merge |
| `sync_failed` | Sync that bai, can retry |
| `sync_partial` | Neo4j co the da co node/relationship nhung MongoDB chua update hoan tat |
| `disabled` | Van con trong KG de audit nhung khong tham gia recommendation |
| `rejected` | Bi tu choi, khong duoc recommend |

### 3.3 visibility

Dung de mo ta node co nen hien thi trong UI/API hay khong.

```text
public
limited
private
hidden
disabled
```

De xuat:

- `verified`: `public`
- `unverified`: `limited`
- `merge_required`: `private` hoac `limited`
- `rejected`: `hidden`
- `disabled`: `disabled`

### 3.4 participation_scope

Dung de mo ta node co duoc tham gia recommendation/PGPR o pham vi nao.

```text
public
owner_only
admin_only
disabled
```

Bang mapping de xuat:

| Trang thai | visibility | participation_scope |
|---|---|---|
| Verified | `public` | `public` |
| Unverified moi tao | `limited` | `owner_only` |
| Merge required | `private` hoac `limited` | `owner_only` hoac `admin_only` |
| Rejected | `hidden` | `disabled` |
| Disabled | `disabled` | `disabled` |

Ly do can tach field nay:

- `visibility` tra loi cau hoi: node co duoc hien tren UI/API khong.
- `participation_scope` tra loi cau hoi: node co duoc tham gia recommendation/PGPR khong.
- User moi co the dung node cua chinh minh, nhung node do khong nen lam nhieu recommendation cua nguoi khac.

### 3.5 trust_weight

Dung de giam anh huong cua node chua xac thuc trong PGPR.

```text
verified: 1.0
unverified: 0.5
merge_required: 0.3
rejected: 0.0
disabled: 0.0
```

`trust_weight` khong duoc la co che duy nhat. He thong can 2 tang:

```text
Tang 1: visibility/participation filter truoc hoac trong query path
Tang 2: trust-aware scoring sau khi co score
```

Cong thuc MVP sau khi da loc path:

```text
final_score = pgpr_score * trust_weight
```

Neu source node la entity cua chinh current user, co the ap dung rule rieng:

```text
source belongs to current_user -> source_trust_weight = 1.0 trong personal mode
target unverified cua nguoi khac -> giam diem hoac an
merge_required khong thuoc current_user -> an khoi public mode
rejected/disabled -> loai truoc khi tinh path
```

Luu y: khong duoc update `trust_weight` luu trong MongoDB/Neo4j thanh `1.0` chi vi user dang dung personal mode. `trust_weight` luu tru van phan anh muc tin cay that cua entity.

Dung runtime override:

```json
{
  "stored_trust_weight": 0.5,
  "runtime_source_weight": 1.0,
  "trust_override_reason": "current_user_personal_mode"
}
```

Nhu vay data van trung thuc, nhung user moi van co the dung ho so cua minh lam source de tim recommendation.

### 3.6 Versioning

Nen them version de sau nay migrate/debug de hon:

```json
{
  "kg_schema_version": 1,
  "provisional_sync_version": 1
}
```

Y nghia:

- Biet node nao sync theo logic cu/moi.
- De migrate khi thay doi KG schema.
- De debug khi PGPR/XAI tra ket qua bat thuong.

## 4. Schema du lieu de xuat

### 4.1 app_users

```json
{
  "id": "usr_001",
  "email": "expert@example.com",
  "role": "expert",
  "status": "active",
  "account_verification_status": "email_unverified",
  "linked_entity": {
    "id": "exp_001",
    "type": "expert",
    "match_status": "created_new",
    "claim_status": null
  },
  "created_at": "...",
  "updated_at": "..."
}
```

### 4.2 Expert / Enterprise / Funder

```json
{
  "id": "exp_001",
  "name": "Nguyen Van A",
  "email": "expert@example.com",
  "source": "user_registration",
  "user_id": "usr_001",
  "entity_verification_status": "unverified",
  "kg_sync_status": "synced_unverified",
  "visibility": "limited",
  "participation_scope": "owner_only",
  "allow_as_source": true,
  "trust_weight": 0.5,
  "recommendable_as_target": false,
  "allow_as_intermediate_node": false,
  "duplicate_candidates": [],
  "matched_existing_entity_id": null,
  "kg_schema_version": 1,
  "provisional_sync_version": 1,
  "research_topics": ["computer-vision"],
  "custom_research_topics": [],
  "created_at": "...",
  "updated_at": "..."
}
```

### 4.3 Project do user tao

```json
{
  "id": "prj_user_001",
  "title": "AI for Medical Imaging",
  "owner_id": "usr_001",
  "owner_entity_id": "exp_001",
  "source": "user_created",
  "entity_verification_status": "unverified",
  "kg_sync_status": "synced_unverified",
  "visibility": "limited",
  "participation_scope": "owner_only",
  "allow_as_source": true,
  "trust_weight": 0.5,
  "recommendable_as_target": false,
  "allow_as_intermediate_node": false,
  "kg_schema_version": 1,
  "provisional_sync_version": 1,
  "research_topics": ["ai-healthcare", "computer-vision"],
  "custom_research_topics": [],
  "created_at": "...",
  "updated_at": "..."
}
```

## 5. Luong register moi

### 5.1 Truong hop match manh voi entity da co

Vi du:

- Trung email.
- Trung ORCID.
- Trung ResearcherID.
- Trung website/domain voi enterprise/funder.

Flow:

```text
Register
-> tao app_user
-> EntityMatchingService tim entity da co
-> match manh
-> khong tao entity moi
-> link user voi entity cu
-> tao claim_status = pending_review
-> khong tao duplicate node trong Neo4j
```

Ket qua:

```json
{
  "linked_entity": {
    "id": "exp_001",
    "type": "expert",
    "match_status": "matched_existing",
    "claim_status": "pending_review"
  }
}
```

### 5.2 Truong hop match yeu/nghi trung

Vi du:

- Ten gan giong.
- Cung organization.
- Cung linh vuc.
- Thieu dinh danh manh.

Flow:

```text
Register
-> tao app_user
-> tao entity moi trong MongoDB
-> luu duplicate_candidates
-> set entity_verification_status = unverified
-> set kg_sync_status = merge_required
-> khong sync relationship rong
-> neu can cho user dung ngay thi chi sync node co lap hoac owner_only
-> admin review sau
```

Ket qua:

```json
{
  "entity_verification_status": "unverified",
  "kg_sync_status": "merge_required",
  "visibility": "private",
  "participation_scope": "owner_only",
  "allow_as_source": true,
  "trust_weight": 0.3,
  "recommendable_as_target": false,
  "allow_as_intermediate_node": false,
  "duplicate_candidates": ["exp_001", "exp_004"]
}
```

Rule quan trong:

- `merge_required` khong nen tham gia public recommendation.
- Neu sync vao Neo4j, chi sync node toi thieu de owner co the dung lam source.
- Khong cho node `merge_required` lam intermediate node.
- Khong cho node `merge_required` lam target cho nguoi khac.

### 5.3 Truong hop khong match entity nao

Flow:

```text
Register
-> tao app_user
-> tao entity moi trong MongoDB
-> set entity_verification_status = unverified
-> ProvisionalKGSyncService sync sang Neo4j
-> set kg_sync_status = synced_unverified
-> user co the dung recommendation ngay
```

Ket qua:

```json
{
  "entity_verification_status": "unverified",
  "kg_sync_status": "synced_unverified",
  "visibility": "limited",
  "participation_scope": "owner_only",
  "allow_as_source": true,
  "recommendable_as_target": false,
  "allow_as_intermediate_node": false,
  "trust_weight": 0.5
}
```

Trong schema nay:

- `allow_as_source = true`: entity moi cua owner duoc dung lam source trong personal mode.
- `recommendable_as_target = false`: entity nay khong duoc lam target recommendation cho nguoi khac.
- `allow_as_intermediate_node = false`: entity nay khong duoc nam giua path.

`allow_as_intermediate_node = false` chi cam node lam node trung gian, khong cam node lam source cua chinh current user trong personal mode.

## 6. Relationship duoc sync ngay

Chi sync ngay cac relationship it rui ro.

Rule rieng cho topic:

- `research_topics` chuan -> duoc sync ngay sang Topic trong Neo4j.
- `custom_research_topics` -> phase dau khong sync ngay sang Neo4j.
- Admin/map custom topic sang topic chuan sau roi moi sync.

Neu muon dung custom topic cho recommendation ngay, chi nen:

- Dung content-based tam thoi ngoai KG; hoac
- Tao `CustomTopic` voi `participation_scope = owner_only`, khong public, khong lam topic chuan.

Khuyen nghi cho MVP: chi sync topic chuan, custom topic luu MongoDB de review sau.

### 6.1 Nen sync ngay

Expert:

```text
Expert -> INTERESTED_IN -> Topic
Expert -> HAS_SKILL -> Skill
Expert -> LOCATED_IN -> Location
```

Enterprise:

```text
Enterprise -> FOCUSES_ON -> Topic
Enterprise -> OPERATES_IN -> Industry
Enterprise -> LOCATED_IN -> Location
```

Funder:

```text
Funder -> FOCUSES_ON -> Topic
Funder -> SUPPORTS_SECTOR -> Industry
Funder -> LOCATED_IN -> Location
```

Project:

```text
Project -> HAS_TOPIC -> Topic
Project -> REQUIRES_SKILL -> Skill
Project -> LOCATED_IN -> Location
Project -> CREATED_BY -> Expert
```

Khong nen tao node `User` trong Knowledge Graph o phase nay. `app_users` la account dang nhap, con KG nen uu tien entity nghiep vu. Voi project do user tao, luu trace bang property:

```text
p.owner_user_id = "usr_001"
p.owner_entity_id = "exp_001"
```

Sau nay neu can audit/account graph rieng moi can can nhac node `User`.

### 6.2 Khong nen sync ngay khi chua verified

```text
Expert -> WORKS_AT -> Organization
Expert -> HAS_PUBLICATION -> Publication
Expert -> HAS_GRANT -> Grant
Enterprise -> FUNDED -> Project
Enterprise -> PARTNERS_WITH -> Project
Funder -> FUNDED -> Project
Funder -> INVESTED_IN -> Project
```

Ly do:

- Day la cac quan he co tinh khang dinh manh.
- Neu sai se lam KG nhieu nang.
- Nen chi tao sau khi verified hoac admin approve.

## 7. Thiet ke Neo4j node

### 7.1 Expert node

```cypher
MERGE (e:Expert {id: $entity_id})
SET
  e.name = $name,
  e.email = $email,
  e.source = "user_registration",
  e.user_id = $user_id,
  e.entity_verification_status = "unverified",
  e.kg_sync_status = "synced_unverified",
  e.visibility = "limited",
  e.participation_scope = "owner_only",
  e.allow_as_source = true,
  e.trust_weight = 0.5,
  e.recommendable_as_target = false,
  e.allow_as_intermediate_node = false,
  e.kg_schema_version = 1,
  e.provisional_sync_version = 1,
  e.active = true,
  e.created_at = datetime(),
  e.updated_at = datetime()
```

### 7.2 Project node

```cypher
MERGE (p:Project {id: $project_id})
SET
  p.title = $title,
  p.name = $title,
  p.description = $description,
  p.owner_user_id = $owner_user_id,
  p.owner_entity_id = $owner_entity_id,
  p.source = "user_created",
  p.entity_verification_status = "unverified",
  p.kg_sync_status = "synced_unverified",
  p.visibility = "limited",
  p.participation_scope = "owner_only",
  p.allow_as_source = true,
  p.trust_weight = 0.5,
  p.recommendable_as_target = false,
  p.allow_as_intermediate_node = false,
  p.kg_schema_version = 1,
  p.provisional_sync_version = 1,
  p.active = true,
  p.created_at = datetime(),
  p.updated_at = datetime()
```

### 7.3 Disable/Reject khong xoa node ngay

```cypher
MATCH (n {id: $entity_id})
SET
  n.entity_verification_status = "rejected",
  n.kg_sync_status = "rejected",
  n.active = false,
  n.visibility = "hidden",
  n.participation_scope = "disabled",
  n.trust_weight = 0,
  n.updated_at = datetime()
```

Ly do:

- De audit.
- De debug.
- De rollback neu admin duyet nham.
- Tranh lam gay relationship/path dot ngot.

## 8. PGPR va recommendation rule

Nguyen tac quan trong: khong duoc chi nhan `trust_weight` vao final score sau khi PGPR da tao path. Node unverified phai duoc kiem soat tu luc query/path expansion.

Can co 2 tang:

```text
Tang 1: loc visibility/participation_scope truoc hoac trong khi query path
Tang 2: tinh score voi trust_weight sau khi path hop le
```

### 8.1 Personal mode

Dung khi current user dung entity cua minh de tim recommendation.

Quy tac:

- Cho phep source node unverified neu `source.user_id == current_user.id`.
- Source node cua current user co the tam tinh `trust_weight = 1.0`.
- Target unverified cua nguoi khac van giam diem hoac an.
- Merge-required cua nguoi khac khong nen hien.
- Node rejected/disabled bi loai.
- Node co `allow_as_intermediate_node = false` khong duoc lam node trung gian.

### 8.2 Public/system mode

Dung cho recommendation chung.

Quy tac:

- Verified duoc uu tien.
- Unverified owner_only khong duoc tham gia public recommendation.
- Unverified public/limited neu co sau nay thi bi giam diem va khong lam intermediate quan trong.
- Merge-required bi an.
- Rejected/disabled khong tham gia.
- Target phai co `recommendable_as_target = true`.

### 8.3 Scoring de xuat

MVP sau khi path da qua filter:

```python
final_score = pgpr_score * trust_weight
```

Nang cao hon:

```python
final_score = pgpr_score * source_weight * target_weight * path_weight
```

Trong do:

- `source_weight`: muc tin cay cua source.
- `target_weight`: muc tin cay cua target.
- `path_weight`: muc tin cay cua cac node trung gian trong path.

### 8.4 Rule cho project unverified

Project do user tao nhung chua verified:

- Owner xem duoc.
- Owner dung project de tim expert/funder/enterprise duoc.
- Nguoi khac khong nen thay project nay trong public recommendation.
- Project chua verified khong nen lam target recommendation cho expert khac.

Schema de xuat:

```json
{
  "visibility": "limited",
  "participation_scope": "owner_only",
  "recommendable_as_target": false
}
```

Sau khi admin verify:

```json
{
  "entity_verification_status": "verified",
  "kg_sync_status": "synced_verified",
  "visibility": "public",
  "participation_scope": "public",
  "allow_as_source": true,
  "recommendable_as_target": true,
  "allow_as_intermediate_node": true,
  "trust_weight": 1.0
}
```

Rule verified mac dinh cho moi entity:

```json
{
  "entity_verification_status": "verified",
  "kg_sync_status": "synced_verified",
  "visibility": "public",
  "participation_scope": "public",
  "trust_weight": 1.0,
  "allow_as_source": true,
  "recommendable_as_target": true,
  "allow_as_intermediate_node": true
}
```

Neu mot loai entity cu the khong nen lam intermediate node thi cau hinh rieng theo type sau. Mac dinh verified nen co quyen tham gia day du.

### 8.5 Graph API cung phai filter provisional data

Graph neighbors khong duoc bo qua rule `visibility` va `participation_scope`. Neu khong, node hidden/unverified van co the lo ra qua graph visualization.

Graph API nen co mode:

```text
personal
public
admin_debug
```

Public graph:

- An `hidden`, `disabled`, `rejected`.
- An `owner_only` cua nguoi khac.
- Khong expand qua node co `allow_as_intermediate_node = false`.
- Chi hien target public/recommendable neu phu hop context.

Personal graph:

- Owner duoc xem node cua minh.
- Owner duoc expand tu source cua minh neu `allow_as_source = true`.
- Van khong hien private node cua nguoi khac.

Admin debug graph:

- Co the xem toan bo node/status de review.
- Can hien badge status ro rang.

## 9. XAI can nang cap

Neu reasoning path co node unverified, explanation phai noi ro.

Vi du:

```text
Goi y nay dua tren ho so moi tao cua ban, hien dang o trang thai chua xac thuc.
He thong tim thay diem chung giua ban va du an qua topic "Computer Vision" va "AI trong y te".
Sau khi ho so duoc xac thuc, ket qua co the duoc cap nhat chinh xac hon.
```

Reasoning path UI nen hien badge:

```text
Expert A [Unverified] -> INTERESTED_IN -> Computer Vision -> HAS_TOPIC -> Project B [Verified]
```

Can them vao XAI response:

```json
{
  "uses_provisional_data": true,
  "data_quality_level": "medium",
  "provisional_nodes_count": 1,
  "data_quality_notes": [
    "Source entity is unverified",
    "This recommendation uses provisional KG data"
  ],
  "verification_badges": {
    "source": "unverified",
    "target": "verified"
  }
}
```

Quy tac `data_quality_level` de xuat:

| Truong hop | data_quality_level |
|---|---|
| Tat ca node/path verified | `high` |
| Source la current user unverified, target verified | `medium` |
| Path co nhieu node unverified | `low` |
| Co node `merge_required` | `low` |
| Co rejected/disabled | Khong nen tra recommendation |

## 10. API can them hoac sua

### 10.1 Provisional KG Sync API

```http
POST /api/v1/kg-sync/provisional/{entity_type}/{entity_id}
```

Dung de sync 1 entity sang Neo4j voi trang thai unverified.

### 10.2 Verification API cho user

```http
GET /api/v1/users/me/verification
POST /api/v1/users/me/claim-entity
```

Dung de:

- User xem trang thai xac thuc.
- User claim entity da co san trong data crawl.

### 10.3 Admin Verification API

```http
GET /api/v1/admin/verifications
POST /api/v1/admin/entities/{entity_type}/{entity_id}/verify
POST /api/v1/admin/entities/{entity_type}/{entity_id}/reject
POST /api/v1/admin/entities/{entity_type}/{entity_id}/disable-kg
POST /api/v1/admin/entities/{entity_type}/{entity_id}/merge
```

Dung de:

- Xem entity pending/merge-required.
- Verify entity.
- Reject entity.
- Disable node trong KG.
- Merge duplicate entity.

Can phan biet `reject` va `disable-kg`:

`reject`:

- Entity/ho so khong hop le.
- `entity_verification_status = rejected`.
- `kg_sync_status = rejected`.
- `participation_scope = disabled`.
- Khong recommend.

`disable-kg`:

- Entity co the van con hop le trong MongoDB.
- Tam thoi khong cho tham gia KG/recommendation.
- Dung khi loi sync, nghi ngo du lieu, can audit hoac can tam dung KG.
- Khong nhat thiet doi `entity_verification_status` thanh `rejected`.

Vi du disable KG:

```json
{
  "entity_verification_status": "unverified",
  "kg_sync_status": "disabled",
  "visibility": "disabled",
  "participation_scope": "disabled",
  "trust_weight": 0
}
```

### 10.4 Recommendation API can bo sung context

Recommendation request nen co them optional context:

```json
{
  "source_id": "exp_user_001",
  "source_type": "expert",
  "target_type": "project",
  "limit": 5,
  "language": "vi",
  "mode": "personal"
}
```

Mode:

```text
personal
public
admin_debug
```

## 10.5 Co che sync an toan va rollback

Can tranh loi lech trang thai:

```text
Neo4j sync thanh cong
MongoDB update kg_sync_status that bai
```

Neu khong xu ly, MongoDB co the tuong entity chua sync trong khi Neo4j da co node.

Luong an toan de xuat:

```text
1. MongoDB set kg_sync_status = syncing
2. ProvisionalKGSyncService upsert Neo4j node/relationships
3. Neu thanh cong: MongoDB set kg_sync_status = synced_unverified
4. Neu loi: MongoDB set kg_sync_status = sync_failed + sync_error
5. Neu loi nua chung: MongoDB set kg_sync_status = sync_partial + sync_error
6. Retry bang idempotent upsert
```

Neo4j bat buoc dung `MERGE`, khong dung `CREATE`, de retry khong tao trung node.

Relationship cung nen co id hoac MERGE theo cap node + relationship type:

```cypher
MATCH (a {id: $source_id})
MATCH (b {id: $target_id})
MERGE (a)-[r:HAS_TOPIC]->(b)
SET r.provisional_sync_version = 1,
    r.updated_at = datetime()
```

Can co API/admin action retry:

```http
POST /api/v1/admin/kg-sync/{entity_type}/{entity_id}/retry
```

## 10.6 Neo4j constraints va index

Dung `MERGE` la can thiet, nhung chua du an toan neu khong co unique constraint. Can tao constraint cho cac label chinh:

```cypher
CREATE CONSTRAINT expert_id_unique IF NOT EXISTS
FOR (e:Expert)
REQUIRE e.id IS UNIQUE;

CREATE CONSTRAINT project_id_unique IF NOT EXISTS
FOR (p:Project)
REQUIRE p.id IS UNIQUE;

CREATE CONSTRAINT enterprise_id_unique IF NOT EXISTS
FOR (e:Enterprise)
REQUIRE e.id IS UNIQUE;

CREATE CONSTRAINT funder_id_unique IF NOT EXISTS
FOR (f:Funder)
REQUIRE f.id IS UNIQUE;

CREATE CONSTRAINT topic_id_unique IF NOT EXISTS
FOR (t:Topic)
REQUIRE t.id IS UNIQUE;

CREATE CONSTRAINT skill_id_unique IF NOT EXISTS
FOR (s:Skill)
REQUIRE s.id IS UNIQUE;

CREATE CONSTRAINT location_id_unique IF NOT EXISTS
FOR (l:Location)
REQUIRE l.id IS UNIQUE;

CREATE CONSTRAINT industry_id_unique IF NOT EXISTS
FOR (i:Industry)
REQUIRE i.id IS UNIQUE;
```

MongoDB cung can index/unique:

```text
app_users.email unique
experts.email index
experts.identifiers.ORCID index neu co
enterprises.website/domain index neu co
funders.website/domain index neu co
```

## 10.7 Chong race condition khi register

Can xu ly truong hop user bam submit 2 lan hoac 2 request register chay dong thoi.

Rule:

- `app_users.email` phai unique.
- Tao user bang atomic insert.
- Neu email da ton tai, request sau fail hoac tra ve account da co tuy policy.
- Duplicate matching khong duoc la lop bao ve duy nhat.
- Entity email/identifier nen co index de query nhanh va giam race condition.
- Neu 2 request tao entity cung luc, Neo4j constraint + MERGE phai chan duplicate node.

Flow de xuat:

```text
1. Try insert app_users voi unique email
2. Neu duplicate email -> return 409 hoac link existing account flow
3. Chay EntityMatchingService
4. Tao/link entity
5. Provisional KG Sync bang idempotent upsert
```

## 11. Service can tao/sua

### 11.1 EntityMatchingService

File de xuat:

```text
backend/services/entity_matching_service.py
```

Nhiem vu:

- Tim duplicate candidate.
- Phan loai match: strong/medium/weak/none.
- Tra ve matched entity hoac candidate list.

Rule MVP:

```text
Strong:
- same email
- same ORCID/ResearcherID
- same website/domain

Medium:
- similar name + same organization
- similar name + same phone

Weak:
- similar name
- same topic + same location
```

### 11.2 ProvisionalKGSyncService

File de xuat:

```text
backend/services/provisional_kg_sync_service.py
```

Nhiem vu:

```python
class ProvisionalKGSyncService:
    def sync_entity_as_unverified(entity_type, entity_id):
        pass

    def retry_sync(entity_type, entity_id):
        pass

    def verify_entity(entity_type, entity_id):
        pass

    def reject_entity(entity_type, entity_id):
        pass

    def disable_entity(entity_type, entity_id):
        pass

    def merge_entities(source_entity_id, target_entity_id):
        pass
```

Yeu cau:

- Sync phai idempotent.
- Truoc sync set MongoDB `kg_sync_status = syncing`.
- Sau sync thanh cong set `synced_unverified` hoac `synced_verified`.
- Neu loi set `sync_failed` hoac `sync_partial`.
- Khong duoc tao duplicate node/relationship khi retry.

### 11.3 PGPRGraphRepository can bo sung

Can them method:

```python
upsert_provisional_entity(...)
upsert_provisional_relationships(...)
update_entity_verification_status(...)
disable_entity(...)
merge_entity_relationships(...)
mark_entity_merged_into(...)
```

### 11.4 RecommendationService can bo sung

Can them:

- Personal/public mode.
- Apply trust weight.
- Filter `visibility`.
- Filter `participation_scope`.
- Filter `recommendable_as_target`.
- Filter `allow_as_intermediate_node`.
- Gan warning vao response neu dung provisional data.

### 11.5 XAI service/explainer can bo sung

Can them:

- Data quality notes.
- Verification badges.
- Cau giai thich rieng cho provisional data.

### 11.6 AdminAuditLogService

Can co audit log cho cac hanh dong admin:

```text
backend/services/admin_audit_log_service.py
```

Collection de xuat:

```text
admin_audit_logs
```

Moi action nen luu:

```json
{
  "admin_user_id": "usr_admin",
  "action": "verify_entity",
  "entity_type": "expert",
  "entity_id": "exp_001",
  "before": {},
  "after": {},
  "reason": "Thong tin khop voi email to chuc",
  "created_at": "..."
}
```

Can log toi thieu cac action:

- `verify_entity`
- `reject_entity`
- `disable_kg`
- `merge_entity`
- `retry_kg_sync`

## 12. UI can nang cap

### 12.1 Sau register

Can hien:

```text
Tai khoan da duoc tao.
Ho so cua ban da duoc them vao Knowledge Graph voi trang thai chua xac thuc.
Ban co the nhan goi y ngay, nhung ket qua co the thay doi sau khi ho so duoc duyet.
```

### 12.2 Profile page

Can hien:

- Verification badge: `Unverified`, `Pending Review`, `Verified`, `Rejected`.
- KG status: `Not synced`, `Synced unverified`, `Synced verified`, `Merge required`.
- Trust weight.
- Linked entity.
- Duplicate candidates neu co.
- Nut claim entity neu he thong tim thay entity co san.

### 12.3 Recommendation UI

Can hien:

- Badge neu source/target/path co provisional data.
- Warning nhe:

```text
Goi y nay co su dung du lieu chua xac thuc.
```

- Score da tinh sau trust weight.
- Co the hien raw score trong admin/debug mode.

### 12.4 Admin UI

Can co cac tab:

- Pending Review
- Synced Unverified
- Merge Required
- Verified
- Rejected/Disabled

Moi item can co:

- Entity info.
- Duplicate candidates.
- KG status.
- Nut verify.
- Nut reject.
- Nut merge.
- Nut disable KG.

## 13. Checklist trien khai day du

### Phase A - Data model va status

- [ ] Them enum/constant cho `account_verification_status`.
- [ ] Them enum/constant cho `entity_verification_status`.
- [ ] Them enum/constant cho `kg_sync_status`.
- [ ] Them field `visibility`.
- [ ] Them field `participation_scope`.
- [ ] Them field `allow_as_source`.
- [ ] Them field `trust_weight`.
- [ ] Them field `recommendable_as_target`.
- [ ] Them field `allow_as_intermediate_node`.
- [ ] Them field `duplicate_candidates`.
- [ ] Them field `matched_existing_entity_id`.
- [ ] Them field `claim_status`.
- [ ] Them field `kg_schema_version`.
- [ ] Them field `provisional_sync_version`.
- [ ] Cap nhat schema response user/entity.
- [ ] Them MongoDB unique index cho `app_users.email`.
- [ ] Them MongoDB index cho email/identifier/domain cua entity neu co.
- [ ] Them Neo4j unique constraints cho Expert/Project/Enterprise/Funder/Topic/Skill/Location/Industry.

### Phase B - Duplicate matching

- [ ] Tao `EntityMatchingService`.
- [ ] Match exact email.
- [ ] Match ORCID/ResearcherID cho expert.
- [ ] Match website/domain cho enterprise/funder.
- [ ] Match fuzzy name.
- [ ] Match name + organization.
- [ ] Match name + phone.
- [ ] Luu duplicate candidates vao MongoDB.
- [ ] Tra `match_status` trong register response.

### Phase C - Provisional KG Sync

- [ ] Tao `ProvisionalKGSyncService`.
- [ ] Them method upsert node vao `PGPRGraphRepository`.
- [ ] Sync Expert unverified.
- [ ] Sync Enterprise unverified.
- [ ] Sync Funder unverified.
- [ ] Sync Project unverified.
- [ ] Sync topic relationship.
- [ ] Chi sync `research_topics` chuan.
- [ ] Khong sync `custom_research_topics` trong MVP.
- [ ] Sync skill relationship.
- [ ] Sync location relationship.
- [ ] Khong sync relationship manh khi chua verified.
- [ ] Update MongoDB `kg_sync_status` sau khi sync.
- [ ] Neu sync loi, luu status/error de retry.

### Phase D - Register/Create Project flow

- [ ] Register goi `EntityMatchingService`.
- [ ] Strong match: link entity cu, khong tao duplicate.
- [ ] Weak match: tao entity moi, set `merge_required`.
- [ ] No match: tao entity moi, sync `synced_unverified`.
- [ ] Create project sync project unverified vao Neo4j.
- [ ] Register response tra `linked_entity`, `account_verification_status`, `entity_verification_status`, `kg_sync_status`, `match_status`.

### Phase E - Recommendation trust/visibility

- [ ] Them recommendation mode: `personal`, `public`.
- [ ] Loc visibility/participation truoc hoac trong query path, khong chi nhan trust_weight o cuoi.
- [ ] Filter rejected/disabled.
- [ ] Filter merge_required khong thuoc current user.
- [ ] Filter owner_only trong public mode.
- [ ] Cho phep source current user neu `allow_as_source = true`.
- [ ] Filter `recommendable_as_target = false` khi node la target public.
- [ ] Filter `allow_as_intermediate_node = false` khi node nam giua path.
- [ ] Apply `trust_weight`.
- [ ] Khong update stored `trust_weight` khi personal mode override.
- [ ] Response tra `stored_trust_weight`, `runtime_source_weight`, `trust_override_reason` neu co override.
- [ ] Neu source la current user, cho phep personal mode.
- [ ] Response tra `score`, `final_score`, `trust_weight`.
- [ ] Response tra warning neu co provisional data.

### Phase F - XAI provisional awareness

- [ ] XAI doc verification status cua source/target/path.
- [ ] Them `data_quality_notes`.
- [ ] Them `data_quality_level`.
- [ ] Them `uses_provisional_data`.
- [ ] Them `provisional_nodes_count`.
- [ ] Them `verification_badges`.
- [ ] Explanation noi ro neu dung unverified data.
- [ ] Reasoning path UI hien badge unverified/verified.

### Phase G - Admin verification

- [ ] API list pending review.
- [ ] API verify entity.
- [ ] API reject entity.
- [ ] API disable KG node.
- [ ] API merge duplicate entity.
- [ ] Update MongoDB va Neo4j dong bo khi verify/reject/disable.
- [ ] Merge phase dau co the soft-disable source duplicate truoc, chua can chuyen het relationship phuc tap.
- [ ] Khi merge MVP, chuyen `app_users.linked_entity` tu source sang target.
- [ ] Khi merge MVP, set source `matched_existing_entity_id = target_id`.
- [ ] Khi merge MVP, set Neo4j source `merged_into = target_id`.
- [ ] Ghi admin audit log khi verify/reject/disable/merge.

### Phase G2 - Sync safety va retry

- [ ] Truoc sync set `kg_sync_status = syncing`.
- [ ] Neo4j upsert dung `MERGE`, khong dung `CREATE`.
- [ ] Relationship upsert idempotent.
- [ ] Sync thanh cong update MongoDB sang `synced_unverified`.
- [ ] Sync loi update MongoDB sang `sync_failed`.
- [ ] Loi nua chung update MongoDB sang `sync_partial`.
- [ ] Luu `sync_error`.
- [ ] Tao retry sync API/admin action.
- [ ] Retry sync khong tao duplicate node.
- [ ] Retry sync khong tao duplicate relationship.

### Phase G3 - Graph API visibility

- [ ] Them graph mode: `personal`, `public`, `admin_debug`.
- [ ] Public graph an hidden/disabled/rejected.
- [ ] Public graph an owner_only cua nguoi khac.
- [ ] Public graph khong expand qua `allow_as_intermediate_node = false`.
- [ ] Personal graph cho owner xem node cua minh.
- [ ] Personal graph van khong hien private node cua nguoi khac.
- [ ] Admin debug graph hien status/badge day du.

### Phase G4 - Admin audit log

- [ ] Tao collection `admin_audit_logs`.
- [ ] Tao `AdminAuditLogService`.
- [ ] Log before/after khi verify entity.
- [ ] Log before/after khi reject entity.
- [ ] Log before/after khi disable KG.
- [ ] Log before/after khi merge entity.
- [ ] Log before/after khi retry sync.

### Phase H - Frontend UI

- [ ] Register success screen hien KG sync status.
- [ ] Profile hien verification badge.
- [ ] Profile hien KG status.
- [ ] Profile hien duplicate candidates.
- [ ] Recommendation hien provisional warning.
- [ ] XAI path hien badge.
- [ ] Admin verification page.
- [ ] Admin merge/reject/verify controls.

### Phase I - Test va demo

- [ ] Test register no-match -> synced_unverified.
- [ ] Test register strong-match -> link existing, khong duplicate.
- [ ] Test register weak-match -> merge_required.
- [ ] Test create project -> synced_unverified.
- [ ] Test recommendation personal mode voi unverified source.
- [ ] Test recommendation public mode giam diem unverified.
- [ ] Test reject -> node hidden/trust_weight 0.
- [ ] Test verify -> trust_weight 1.0.
- [ ] Test XAI co warning unverified.
- [ ] Test register cung email 2 lan khong tao 2 Expert node.
- [ ] Test retry sync khong tao duplicate node.
- [ ] Test retry sync khong tao duplicate relationship.
- [ ] Test weak match khong xuat hien trong public recommendation.
- [ ] Test rejected node khong xuat hien trong graph neighbors public.
- [ ] Test owner_only cua nguoi khac khong xuat hien trong graph public.
- [ ] Test disabled source sau merge khong con lam source recommendation.
- [ ] Test user sau merge duoc chuyen sang target entity.
- [ ] Test project unverified khong duoc recommend lam target cho nguoi khac.
- [ ] Test custom topic khong duoc sync vao Topic chuan.
- [ ] Test personal mode tra runtime override nhung stored trust_weight khong doi.
- [ ] Test admin action co audit log.
- [ ] Ghi demo case vao `DEMO_CASES.md`.

## 14. Thu tu nen lam de an toan

Nen lam theo thu tu:

1. Them data fields/status vao MongoDB schema va response.
2. Them MongoDB unique/index va Neo4j constraints.
3. Tao duplicate matching MVP.
4. Them sync state machine: `syncing`, `sync_failed`, `sync_partial`, retry.
5. Tao ProvisionalKGSyncService chi sync node + topic/skill/location bang idempotent upsert.
6. Noi register/create project voi ProvisionalKGSyncService.
7. Them filter `visibility` + `participation_scope` + `allow_as_source` truoc/trong query path.
8. Them `trust_weight` vao recommendation scoring sau khi path hop le, chi runtime override cho personal mode.
9. Them rule project unverified chi owner dung duoc.
10. Them rule Graph API visibility theo mode.
11. Them XAI warning/badge/data quality level.
12. Them UI profile/recommendation status.
13. Them admin verify/reject/disable MVP va audit log.
14. Them merge MVP: chuyen user link sang target va soft-disable source.
15. Sau cung moi lam merge relationship day du.

Khong nen lam merge phuc tap ngay dau, vi merge relationship trong KG de phat sinh bug. Phase dau co the:

```text
merge_required -> admin chon target entity -> source duplicate bi disabled -> user linked sang target
```

Merge MVP can lam ro:

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

Sau do moi nang cap chuyen relationship tu duplicate sang target.

## 15. Dinh nghia hoan thanh

Tinh nang Provisional KG Sync duoc xem la hoan thanh khi:

- [ ] User moi dang ky xong co entity trong MongoDB.
- [ ] Entity moi duoc sync sang Neo4j voi `synced_unverified`.
- [ ] Entity moi co `entity_verification_status`, `visibility`, `participation_scope`, `allow_as_source`, `trust_weight`.
- [ ] Duplicate strong match khong tao node moi.
- [ ] Duplicate weak match gan `merge_required`.
- [ ] Duplicate weak match khong tham gia public recommendation.
- [ ] Neo4j co unique constraints de giam duplicate khi retry/concurrent request.
- [ ] PGPR dung duoc entity moi trong personal mode.
- [ ] PGPR loc participation truoc/trong query path.
- [ ] PGPR khong de unverified node anh huong ngang verified node trong public mode.
- [ ] Runtime override source weight khong lam doi stored trust_weight.
- [ ] Graph API public khong lo node hidden/owner_only cua nguoi khac.
- [ ] XAI noi ro khi dung provisional data.
- [ ] Admin co the verify/reject/disable entity.
- [ ] Admin action duoc luu audit log.
- [ ] Reject/disable dung soft delete, khong xoa node cung.
- [ ] Retry sync khong tao duplicate node/relationship.
- [ ] Merge MVP chuyen user link sang target entity.
- [ ] UI hien trang thai verification va KG sync ro rang.

## 16. Ket luan

Provisional KG Sync la huong thiet ke phu hop voi he thong hien tai vi no giup user moi dung recommendation ngay sau khi dang ky, nhung van kiem soat rui ro du lieu sai va duplicate.

Diem quan trong nhat khong phai la sync ngay hay khong, ma la:

```text
Sync ngay, nhung node chua xac thuc khong duoc co quyen luc ngang node verified.
```

Neu lam dung, day se la mot diem manh lon cua do an: he thong khong chi recommend tren data tinh, ma co kha nang tiep nhan du lieu moi, gan muc tin cay, dua vao Knowledge Graph co kiem soat va giai thich minh bach bang XAI.
