# Checklist hoan thien he thong R&D Recommendation

Ngay tao: 2026-05-27  
Cap nhat audit: 2026-05-27 (Phase 10 — xem `NHAT_KY_REFACTOR_PGPR.md`)

Muc tieu: dua he thong tu MVP dang chay duoc len muc hoan thien cho demo do an, co frontend chinh thuc, backend on dinh, quan tri du lieu, XAI ro rang, evaluation va deploy.

**Tien do tong quan:** ~65% MVP demo — con thieu evaluation day du, test tu dong, deploy, va mot so sync KG (skill/location/industry).

---

## 1. On dinh recommendation hien tai

- [x] Dam bao `Project -> Expert` public demo luon tra ket qua. *(Da test 15/15 khi Neo4j/Mongo chay — `api_test_results.json`)*
- [x] Dam bao `Expert -> Project` personal mode cho user moi luon tra ket qua neu co topic match. *(Phase 9 — topic mapping + personal mode)*
- [x] Dam bao moi recommendation co `reasoning_paths` hoac co `fallback_reason` ro rang. *(Phase 10)*
- [x] Khong hien score cao neu khong co evidence/path. *(Cap score <= 0.55 khi khong co paths — Phase 10)*
- [x] Phan biet score tu PGPR policy va score tu Cypher/Heuristic fallback. *(`scoring_method`)*
- [x] Them badge response: `scoring_method = pgpr_policy | cypher_fallback | hybrid`. *(Schema + PGPR + dashboard)*
- [x] XAI khong noi qua chac khi dung fallback hoac data unverified. *(Canh bao trong `_explain_rule`)*
- [x] Kiem tra lai cac cap goi y:
  - [x] Project -> Expert
  - [x] Project -> Funder
  - [x] Project -> Enterprise
  - [x] Project -> Similar Project *(mot so item khong co paths — policy rollout)*
  - [x] Expert -> Project
  - [x] Expert -> Expert
  - [x] Enterprise -> Expert
  - [x] Funder -> Project

---

## 2. Lam sach warning va logging backend

- [x] Xoa cac property resolver khong ton tai trong Neo4j schema. *(`pgpr_graph_repo.py` — bo `topic_name`, `skill_name`, `tech_id`, ...)*
- [x] Kiem tra khong con warning:
  - [x] `topic_name`
  - [x] `skill_name`
  - [x] `tech_id`
  - [x] `direction_name`
  - [x] `industry_name`
- [x] Log moi API request:
  - [x] Method
  - [x] Path
  - [x] Status code
  - [x] Duration
- [x] Log ro recommendation dang dung:
  - [x] PGPR policy
  - [x] Cypher fallback
  - [ ] Cache hit/miss *(chi co log explanation cache; recommendation cache chua log hit/miss)*
- [x] Giam log Neo4j warning gay nhieu man hinh.

---

## 3. Provisional KG Sync

- [x] Hoan thien schema cho entity moi:
  - [x] `entity_verification_status`
  - [x] `kg_sync_status`
  - [x] `visibility`
  - [x] `participation_scope`
  - [x] `trust_weight`
  - [x] `allow_as_source`
  - [x] `recommendable_as_target`
  - [x] `allow_as_intermediate_node`
  - [x] `kg_schema_version`
  - [x] `provisional_sync_version`
- [x] Sync expert moi vao Neo4j voi cac relationship an toan:
  - [x] Topic
  - [ ] Skill
  - [ ] Location
- [ ] Sync enterprise moi vao Neo4j:
  - [ ] Industry
  - [x] Topic
  - [ ] Location
- [ ] Sync funder moi vao Neo4j:
  - [ ] Topic ho tro
  - [ ] Location
  - [ ] Funding focus
- [x] Sync project user tao:
  - [x] Topic
  - [ ] Skill yeu cau
  - [ ] Location
  - [x] Owner entity
- [x] Custom topic:
  - [x] Luu MongoDB truoc.
  - [x] Khong sync public ngay vao KG.
  - [ ] Cho admin map custom topic sang topic chuan. *(API/UI map chua co — chi luu `custom_research_topics`)*
- [x] Retry sync khong tao duplicate node/relationship.
- [x] Neu sync loi thi luu `sync_error`.
- [x] Them trang/admin view de xem entity `sync_failed`. *(`/admin` filter `sync_failed`)*

---

## 4. Duplicate Matching va Claim Entity

- [x] Khi user register, kiem tra duplicate theo:
  - [x] Email
  - [x] ORCID
  - [x] ResearcherID
  - [ ] Scopus ID
  - [x] Ten + organization
  - [x] Website/domain voi enterprise/funder
- [x] Strong match:
  - [x] Khong tao entity moi.
  - [x] Link user vao entity cu.
  - [x] Tao claim pending review.
- [x] Weak match:
  - [x] Tao duplicate candidates.
  - [x] Gan `kg_sync_status = merge_required`.
  - [x] Chi cho owner dung node nay.
- [x] No match:
  - [x] Tao entity moi.
  - [x] Sync Neo4j dang `synced_unverified`.
- [x] Admin merge:
  - [x] Chuyen `app_users.linked_entity` sang target.
  - [x] Source entity set disabled.
  - [x] Neo4j source set `merged_into`.
  - [x] Khong xoa node ngay.

---

## 5. Admin UI

- [x] Tao layout admin rieng. *(`/admin` — dung Navbar chung)*
- [x] Trang danh sach entity can review.
- [x] Filter theo status:
  - [x] `unverified` *(qua `entity_verification_status` — API ho tro)*
  - [x] `synced_unverified`
  - [x] `merge_required`
  - [x] `sync_failed`
  - [x] `verified`
  - [x] `rejected`
- [x] Trang detail entity admin.
- [x] Hien duplicate candidates.
- [x] Button:
  - [x] Verify
  - [x] Reject
  - [x] Disable KG
  - [x] Retry KG Sync
  - [x] Merge
- [x] Form nhap ly do khi admin thao tac.
- [x] Trang audit log. *(Tren `/admin`)*

---

## 6. Auth va Role UI

- [x] Register chon dung 4 doi tuong:
  - [x] Expert
  - [x] Enterprise
  - [x] Funder
  - [ ] Project owner/creator neu can *(project tao sau register)*
- [x] Khong tao role `researcher` rieng, neu co thi gan chung vao Expert.
- [x] Profile hien:
  - [x] Account verification
  - [x] Entity verification
  - [x] KG sync status
  - [x] Linked entity
  - [x] Trust weight
  - [x] Duplicate warning neu co
- [x] Profile expert co field rieng:
  - [x] Chu de nghien cuu
  - [ ] Skill
  - [x] Organization
  - [ ] ORCID/ResearcherID neu co *(form register chua day du)*
- [ ] Profile enterprise/funder co field rieng.
- [x] Logout clear token va state dung.

---

## 7. Frontend Recommendation UX

- [x] Dashboard hien ro mode:
  - [x] Public mode
  - [x] Personal mode
  - [ ] Admin debug mode neu co
- [x] Neu user chua login:
  - [x] Van cho demo public data.
  - [ ] Goi y login neu muon dung profile ca nhan.
- [x] Neu user login:
  - [x] Auto dien source ID bang linked entity cua user.
  - [x] Chay personal mode cho linked entity cua user.
- [x] Ket qua recommendation hien:
  - [x] Score
  - [x] Scoring method
  - [x] Data quality level
  - [x] Verified/unverified badge
  - [x] So reasoning paths
- [x] Neu `reasoning_paths = 0`:
  - [x] Khong hien nhu recommendation chac chan.
  - [x] Hien fallback reason ro rang.
- [x] Nut tao lai explanation dung cache/service layer.

---

## 8. XAI va Reasoning Paths

- [x] Reasoning path hien dang KG:
  - [x] Source node
  - [x] Relationship
  - [x] Evidence node
  - [x] Relationship
  - [x] Target node
- [x] Evidence node co ten that, khong hien `Evidence 1` neu backend co data.
- [x] Hover node hien full name.
- [ ] Hien badge cho unverified/provisional nodes. *(Canh bao text — chua badge tren path graph)*
- [x] XAI giai thich:
  - [x] Vi sao goi y.
  - [x] Duong path nao quan trong.
  - [x] Score den tu dau.
  - [x] Canh bao neu data chua xac thuc.
- [x] Phan biet:
  - [x] PGPR explanation
  - [x] Cypher fallback explanation
  - [x] LLM explanation neu bat mode LLM

---

## 9. Graph Visualization

- [x] Graph neighbors co mode:
  - [x] public
  - [x] personal
  - [x] admin_debug
- [x] Public graph an:
  - [x] hidden
  - [x] disabled
  - [x] rejected
  - [x] owner_only cua nguoi khac
- [x] Personal graph cho owner xem node cua minh.
- [ ] Admin graph xem duoc tat ca. *(API co — UI chua co toggle admin_debug)*
- [x] Node khong chong len nhau.
- [x] Drag node co collision/repulsion tot hon.
- [x] Keo node thi node lien quan di theo nhe.
- [x] Click node hien detail panel.
- [ ] Filter label/relationship.
- [ ] Search node trong graph.

---

## 10. Project Overview

- [x] Trang project overview dung API:
  - [x] `/api/v1/recommendations/projects/{project_id}/overview`
- [x] Hien 4 nhom:
  - [x] Experts
  - [x] Funders
  - [x] Enterprises
  - [x] Similar projects
- [x] Moi nhom co:
  - [x] Top 3-5 ket qua
  - [x] Score
  - [x] Explanation ngan
  - [x] Link detail
- [x] Neu 1 nhom loi thi nhom khac van hien.

---

## 11. Evaluation Pipeline

- [ ] Tao tap test recommendation.
- [ ] Tao baseline:
  - [ ] Keyword/content matching
  - [ ] Topic overlap
- [ ] Chay PGPR tren cung tap test.
- [ ] Tinh metric:
  - [ ] Precision@5
  - [ ] Recall@5
  - [ ] NDCG@5
  - [ ] HitRate@5
- [ ] Luu ket qua vao artifact/report.
- [x] Tao trang frontend Evaluation.
- [ ] So sanh baseline vs PGPR. *(MVP summary — metrics null)*
- [x] Ghi han che cua evaluation neu dataset nho.

---

## 12. Testing

- [ ] Backend unit/integration tests:
  - [ ] Health API
  - [ ] Entity list/detail
  - [ ] Recommendation public
  - [ ] Recommendation personal
  - [ ] Explanation cache
  - [ ] Graph neighbors
  - [ ] Provisional KG sync
  - [ ] Admin verify/reject/merge
- [ ] Test duplicate:
  - [ ] Register cung email khong tao 2 account.
  - [ ] Strong match khong tao duplicate entity.
  - [ ] Retry sync khong tao duplicate Neo4j node.
- [ ] Test security/visibility:
  - [ ] Public khong thay owner_only cua nguoi khac.
  - [ ] Rejected/disabled khong vao recommendation.
  - [ ] Owner xem duoc node cua minh trong personal mode.
- [x] Frontend typecheck PASS.
- [x] Backend compile PASS.

---

## 13. Deployment

- [x] Tao `.env.example` day du cho backend.
- [ ] Tao `.env.production` mau cho frontend.
- [ ] Chuan hoa CORS production.
- [ ] Docker compose:
  - [ ] Backend
  - [ ] MongoDB
  - [ ] Neo4j
  - [ ] Redis optional
- [x] Seed data script.
- [ ] Build frontend production.
- [ ] Deploy backend.
- [ ] Deploy frontend.
- [ ] Kiem tra API URL production.
- [ ] Viet huong dan run tu dau.

---

## 14. Bao cao va Demo

- [x] Viet mo ta kien truc tong the. *(`TONG_QUAN_HE_THONG_HIEN_TAI.md`, `KIEN_TRUC_DA_CHOT.md`)*
- [x] Viet luong recommendation. *(`PGPR_QUY_TRINH_HOAT_DONG.md`)*
- [x] Viet Provisional KG Sync. *(`KE_HOACH_PROVISIONAL_KG_SYNC.md`)*
- [x] Viet XAI/reasoning paths.
- [x] Viet admin governance. *(API + Admin UI Phase 10)*
- [ ] Viet evaluation.
- [x] Viet han che:
  - [x] Dataset nho.
  - [x] Node moi chua co trong PGPR vocab.
  - [x] Fallback score la heuristic.
  - [x] Duplicate matching chua hoan hao.
- [x] Tao demo cases. *(`DEMO_CASES.md`)*

---

## 15. Uu tien thuc hien gan nhat

- [x] 1. Lam sach warning/logging backend.
- [x] 2. Dam bao recommendation nao cung co evidence path hoac fallback reason.
- [x] 3. Hoan thien XAI hien `scoring_method` va data quality.
- [x] 4. Tao Admin UI verify/reject/merge.
- [ ] 5. Hoan thien duplicate matching. *(MVP xong — Scopus, claim UI day du chua)*
- [ ] 6. Lam Evaluation pipeline.
- [ ] 7. Chuan bi deploy.
