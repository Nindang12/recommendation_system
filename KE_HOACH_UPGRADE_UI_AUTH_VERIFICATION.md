# Ke hoach upgrade UI web chinh thuc va xac thuc nguoi dung

## 1. Muc tieu

Nang cap he thong tu ban demo ky thuat thanh giao dien web chinh thuc cho 4 doi tuong chinh:

- Expert
- Enterprise
- Funder
- Project

He thong can co luong nguoi dung ro rang:

- Dang ky tai khoan
- Dang nhap / dang xuat
- Trang ca nhan
- Tao project
- Quan ly project cua toi
- Gan tai khoan nguoi dung voi entity da co trong du lieu neu co the
- Danh dau tai khoan/entity moi la chua xac thuc

## 2. Van de hien tai

### 2.1 UI van dang o muc MVP

Da co:

- Login
- Register
- Logout
- Profile
- Create Project
- My Projects
- Dashboard goi y PGPR/XAI
- Entity detail
- Graph view

Han che:

- Giao dien chua dong nhat nhu mot web product chinh thuc.
- Mot so trang van thien ve demo ky thuat.
- Chua co luong onboarding ro rang cho tung role.
- Chua co trang quan ly trang thai xac thuc.
- Chua co trang admin/review de duyet entity moi hoac merge voi entity cu.

### 2.2 Van de trung du lieu voi data da cao

Tinh huong:

- He thong da co expert/enterprise/funder trong MongoDB do crawl/import du lieu.
- Sau do chinh nguoi do vao dang ky tai khoan moi.
- Neu tao record moi ngay lap tuc se bi trung:
  - 1 expert crawl san
  - 1 expert do user dang ky

Rui ro:

- Duplicate node khi convert sang Neo4j.
- PGPR goi y sai vi cung mot nguoi/to chuc co nhieu node.
- XAI reasoning path kho giai thich vi entity bi tach doi.
- Profile nguoi dung khong lien ket voi entity da co.

### 2.3 Entity moi chua nen duoc tin tuong ngay

Nguoi dung tu dang ky co the nhap sai hoac nhap thieu thong tin.

Vì vậy entity tao moi tu register khong nen xem la verified ngay.

Can gan tag/trang thai:

```json
{
  "verification_status": "unverified",
  "kg_sync_status": "pending_review"
}
```

Y nghia:

- `unverified`: chua xac thuc danh tinh/thong tin.
- `pending_review`: chua nen sync thang sang Neo4j.
- Chi sau khi duyet/match/merge moi chuyen sang `verified` va `ready_for_kg_sync`.

## 3. Kien truc mong muon

```text
Frontend
   |
   v
FastAPI Router
   |
   v
Service Layer
   |-------------------------------|
   v                               v
Auth/User Service          Entity Verification Service
   |                               |
   v                               v
MongoRepository             MongoRepository
   |                               |
   v                               v
app_users              experts / enterprises / funders / projects
                                   |
                                   v
                           KG Sync Pipeline
                                   |
                                   v
                                Neo4j
```

Nguyen tac:

- Auth chi quan ly account.
- Entity nghiep vu quan ly expert/enterprise/funder/project.
- Tai khoan user co the link den entity da co.
- Entity moi can duoc xac thuc truoc khi sync sang Neo4j.

## 4. Trang thai du lieu can them

### 4.1 User account

Collection: `app_users`

Can co:

```json
{
  "email": "user@example.com",
  "role": "expert",
  "status": "active",
  "verification_status": "unverified",
  "linked_entity": {
    "id": "exp_001",
    "type": "expert",
    "match_status": "claimed_existing"
  }
}
```

Trang thai de xuat:

- `unverified`: vua dang ky, chua xac thuc.
- `pending_review`: dang cho admin/he thong review.
- `verified`: da xac thuc.
- `rejected`: thong tin khong hop le.

### 4.2 Expert / Enterprise / Funder entity

Can co:

```json
{
  "source": "user_registration",
  "verification_status": "unverified",
  "kg_sync_status": "pending_review",
  "user_id": "...",
  "duplicate_candidates": [],
  "matched_existing_entity_id": null
}
```

Trang thai `kg_sync_status` de xuat:

- `pending_review`: moi tao, chua sync.
- `ready_for_kg_sync`: da duyet, co the dua sang Neo4j.
- `synced`: da sync sang Neo4j.
- `merge_required`: nghi ngo trung entity, can merge.
- `rejected`: khong dua vao KG.

## 5. Xu ly khi user dang ky ma data da co san

### 5.1 Luong de xuat

Khi user register:

1. Tao account trong `app_users`.
2. Kiem tra role:
   - expert
   - enterprise
   - funder
3. Tim entity co san trong MongoDB theo cac dau hieu:
   - Email
   - Ten day du / ten to chuc
   - Organization
   - Phone
   - ORCID / ResearcherID / website neu co
4. Neu tim thay match manh:
   - Khong tao entity moi.
   - Link user vao entity cu.
   - Gan `claim_status = pending_review`.
5. Neu chi match yeu:
   - Tao entity moi tam thoi.
   - Gan `duplicate_candidates`.
   - Gan `kg_sync_status = merge_required`.
6. Neu khong match:
   - Tao entity moi.
   - Gan `verification_status = unverified`.
   - Gan `kg_sync_status = pending_review`.

### 5.2 Matching rule ban dau

Match manh:

- Cung email.
- Cung ORCID/ResearcherID.
- Cung website domain doi voi enterprise/funder.

Match vua:

- Ten gan giong + cung organization.
- Ten gan giong + cung phone.

Match yeu:

- Ten gan giong nhung khac organization.
- Cung linh vuc/chuyen mon nhung thieu dinh danh.

## 6. API can bo sung

### 6.1 Auth/User

Da co MVP:

- [x] `POST /api/v1/auth/register`
- [x] `POST /api/v1/auth/login`
- [x] `POST /api/v1/auth/logout`
- [x] `GET /api/v1/users/me`
- [x] `PUT /api/v1/users/me`

Can nang cap:

- [ ] Register gan `verification_status = unverified`.
- [ ] Register chay duplicate matching.
- [ ] User response tra `linked_entity`.
- [ ] Profile hien thi trang thai xac thuc.

### 6.2 Entity Claim / Verification

Can tao:

```http
GET /api/v1/users/me/verification
POST /api/v1/users/me/claim-entity
GET /api/v1/admin/verifications
POST /api/v1/admin/verifications/{request_id}/approve
POST /api/v1/admin/verifications/{request_id}/reject
POST /api/v1/admin/entities/{entity_type}/{entity_id}/merge
```

Trang thai:

- [ ] User xem trang thai xac thuc.
- [ ] User claim entity da co.
- [ ] Admin xem danh sach pending.
- [ ] Admin approve/reject.
- [ ] Admin merge duplicate.

### 6.3 KG Sync

Can tao sau:

```http
GET /api/v1/admin/kg-sync/pending
POST /api/v1/admin/kg-sync/{entity_type}/{entity_id}
POST /api/v1/admin/kg-sync/run
```

Trang thai:

- [ ] Liet ke entity `ready_for_kg_sync`.
- [ ] Sync 1 entity sang Neo4j.
- [ ] Sync batch.
- [ ] Cap nhat `kg_sync_status = synced`.

## 7. UI web chinh thuc can nang cap

### 7.1 Public/Auth UI

- [ ] Landing page giai thich ngan gon he thong.
- [ ] Login page chinh thuc.
- [ ] Register page theo 3 role:
  - Expert
  - Enterprise
  - Funder
- [ ] Register co option topic chuan va `Khac`.
- [ ] Sau register hien thi trang thai:
  - Tai khoan da tao
  - Dang cho xac thuc
  - Co tim thay entity trung hay khong

### 7.2 User Dashboard

- [ ] Dashboard rieng cho user da dang nhap.
- [ ] Hien thi profile summary.
- [ ] Hien thi verification status.
- [ ] Hien thi linked entity.
- [ ] Quick actions:
  - Tao project
  - Xem My Projects
  - Chay recommendation
  - Cap nhat profile

### 7.3 Profile Page

- [ ] Hien thi badge `Unverified`, `Pending review`, `Verified`.
- [ ] Hien thi linked entity neu co.
- [ ] Hien thi duplicate candidates neu co.
- [ ] Cho user gui yeu cau claim entity da co.
- [ ] Cho user cap nhat topic chuan va custom topic.

### 7.4 Create Project

- [ ] Form tao project chuan hon.
- [ ] Field topic/linh vuc dung option co san.
- [ ] Project moi gan:
  - `owner_id`
  - `verification_status`
  - `kg_sync_status`
- [ ] Sau tao project co trang overview.

### 7.5 My Projects

- [ ] Danh sach project cua user.
- [ ] Badge trang thai:
  - draft
  - pending_review
  - ready_for_kg_sync
  - synced
- [ ] Nut chay recommendation.
- [ ] Nut xem graph neu da sync KG.

### 7.6 Admin/Review UI

Can co neu muon he thong chinh thuc hon:

- [ ] Admin dashboard.
- [ ] Pending users/entities.
- [ ] Duplicate candidates.
- [ ] Approve/reject verification.
- [ ] Merge entity.
- [ ] Trigger KG sync.

## 8. Checklist backend can lam tiep

- [ ] Them `verification_status` vao user va entity.
- [ ] Them `kg_sync_status = pending_review` cho entity tao tu register.
- [ ] Viet `EntityMatchingService`.
- [ ] Viet rule match theo email/name/organization/phone.
- [ ] Khi register, tim entity da co truoc khi tao moi.
- [ ] Neu match manh, link user voi entity cu.
- [ ] Neu match yeu, luu duplicate candidates.
- [ ] Tao API claim entity.
- [ ] Tao API admin verification.
- [ ] Tao API KG sync pending.

## 9. Checklist frontend can lam tiep

- [ ] Nang cap navbar theo role/user status.
- [ ] Them badge verification tren profile.
- [ ] Them trang verification status.
- [ ] Them UI claim entity.
- [ ] Them UI duplicate candidate review cho user.
- [ ] Them admin verification dashboard.
- [ ] Nang cap create project UI theo topic chuan.
- [ ] Nang cap my projects UI theo kg sync status.

## 10. Quyet dinh da chot

- He thong chi phuc vu 4 doi tuong chinh:
  - Expert
  - Enterprise
  - Funder
  - Project
- Khong tao role `researcher` rieng.
- Nguoi nghien cuu/giang vien/chuyen gia ca nhan nam trong `expert`.
- User moi dang ky phai co tag/trang thai `unverified`.
- Entity moi tu user khong sync sang Neo4j ngay.
- Entity moi can qua review/matching/merge truoc khi dua vao KG.

