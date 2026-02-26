# Multi-Entity Explainable Recommendation Framework based on PGPR

Framework gợi ý đa thực thể có giải thích (Explainable) dựa trên Policy-Guided Path Reasoning (PGPR) trong Knowledge Graph R&D.

---

## 1. Các thực thể và quan hệ trong KG

| Thực thể | Mô tả | ID property |
|----------|--------|-------------|
| **Project** | Dự án nghiên cứu | `project_id` |
| **Expert** | Chuyên gia | `expert_id` |
| **Funder** | Quỹ tài trợ | `funder_id` |
| **Enterprise** | Doanh nghiệp | `enterprise_id` |
| **ResearchField** | Lĩnh vực nghiên cứu | `field_id` |
| **MethodTechnique** | Phương pháp / Kỹ thuật | `name` (hoặc `tech_id`) |

Quan hệ chính: `BELONGS_TO`, `SUB_FIELD_OF`, `HAS_EXPERTISE_IN`, `HAS_SKILL`, `PARTICIPATES_IN`, `FUNDS`, `SUPPORTS`, `PARTNERS_WITH`, `OPERATES_IN`, `HAS_APPLICATION_EXPERIENCE_IN`, `UNDER_FIELD` (MethodTechnique→ResearchField), `COLLABORATES_WITH`.

---

## 2. Khi nguồn là **Project**

### 2.1 Project → Expert  
**Mục đích:** Tìm chuyên gia phù hợp tham gia dự án.

| Meta-path | Chuỗi quan hệ | Ý nghĩa logic |
|-----------|----------------|----------------|
| **P1** | Project -BELONGS_TO→ ResearchField ←HAS_EXPERTISE_IN- Expert | Dự án thuộc lĩnh vực X; chuyên gia có chuyên môn X → khớp trực tiếp lĩnh vực. |
| **P2** | Project -BELONGS_TO→ ResearchField -SUB_FIELD_OF*- ResearchField ←HAS_EXPERTISE_IN- Expert | Mở rộng qua hierarchy: dự án thuộc (hoặc liên quan) lĩnh vực con/cha; chuyên gia có chuyên môn lĩnh vực liên quan. |
| **P3** | Project ←PARTICIPATES_IN- Expert (gián tiếp qua project khác) | Chuyên gia đã tham gia dự án khác cùng lĩnh vực/tương tự (qua field hoặc funder). |
| **P4** | Project -BELONGS_TO→ ResearchField ←UNDER_FIELD- MethodTechnique ←HAS_SKILL- Expert | Dự án thuộc lĩnh vực có kỹ thuật Y; chuyên gia có kỹ năng Y → khớp phương pháp/kỹ thuật. |

**Ưu tiên PGPR:** P1, P2 (ngắn, dễ giải thích); P4 nếu KG có MethodTechnique/UNDER_FIELD/HAS_SKILL.

---

### 2.2 Project → Funder  
**Mục đích:** Tìm quỹ tài trợ phù hợp với lĩnh vực và nội dung dự án.

| Meta-path | Chuỗi quan hệ | Ý nghĩa logic |
|-----------|----------------|----------------|
| **P1** | Project -BELONGS_TO→ ResearchField ←SUPPORTS- Funder | Dự án thuộc lĩnh vực X; quỹ hỗ trợ lĩnh vực X. |
| **P2** | Project -BELONGS_TO→ ResearchField -SUB_FIELD_OF*- ResearchField ←SUPPORTS- Funder | Quỹ hỗ trợ lĩnh vực cha/con/anh em của lĩnh vực dự án. |
| **P3** | Project -BELONGS_TO→ ResearchField ←BELONGS_TO- Project2 ←FUNDS- Funder | Quỹ đã tài trợ dự án khác cùng (hoặc liên quan) lĩnh vực → portfolio phù hợp. |

**Ưu tiên PGPR:** P1, P2 (rõ ràng); P3 bổ sung tính “đã tài trợ lĩnh vực tương tự”.

---

### 2.3 Project → Enterprise  
**Mục đích:** Tìm doanh nghiệp có khả năng hợp tác hoặc chuyển giao công nghệ.

| Meta-path | Chuỗi quan hệ | Ý nghĩa logic |
|-----------|----------------|----------------|
| **P1** | Project -BELONGS_TO→ ResearchField -SUB_FIELD_OF*- ResearchField ←BELONGS_TO- Project2 ←PARTNERS_WITH- Enterprise | DN đang hợp tác với dự án cùng/liên quan lĩnh vực → có kinh nghiệm hợp tác R&D. |
| **P2** | Project -BELONGS_TO→ ResearchField (↔ Industry nếu có) ←OPERATES_IN- Enterprise | DN hoạt động trong lĩnh vực/ngành liên quan đến lĩnh vực dự án. |
| **P3** | Project ←PARTICIPATES_IN- Expert -HAS_APPLICATION_EXPERIENCE_IN→ Industry ←OPERATES_IN- Enterprise | Chuyên gia trong dự án có kinh nghiệm ứng dụng trong ngành mà DN hoạt động. |

**Ưu tiên PGPR:** P1 (rõ qua project-partner); P2/P3 khi có Industry/OPERATES_IN.

---

### 2.4 Project → Project  
**Mục đích:** Tìm dự án tương tự để tham khảo hoặc mở rộng hợp tác.

| Meta-path | Chuỗi quan hệ | Ý nghĩa logic |
|-----------|----------------|----------------|
| **P1** | Project -BELONGS_TO→ ResearchField ←BELONGS_TO- Project2 | Cùng lĩnh vực nghiên cứu. |
| **P2** | Project -BELONGS_TO→ ResearchField -SUB_FIELD_OF*- ResearchField ←BELONGS_TO- Project2 | Cùng hệ thống hierarchy (cha/con/anh em). |
| **P3** | Project ←FUNDS- Funder -FUNDS→ Project2 | Cùng quỹ tài trợ → hệ sinh thái tài trợ tương tự. |
| **P4** | Project ←PARTICIPATES_IN- Expert -PARTICIPATES_IN→ Project2 | Có chuyên gia chung → hợp tác hoặc mở rộng nhóm. |

**Ưu tiên PGPR:** P1, P2 (field-based); P3, P4 (funder/experts) cho đa dạng.

---

## 3. Khi nguồn là **Expert**

### 3.1 Expert → Project  
**Mục đích:** Gợi ý dự án phù hợp với chuyên môn của chuyên gia.

| Meta-path | Chuỗi quan hệ | Ý nghĩa logic |
|-----------|----------------|----------------|
| **P1** | Expert -HAS_EXPERTISE_IN→ ResearchField ←BELONGS_TO- Project | Dự án thuộc đúng lĩnh vực chuyên môn. |
| **P2** | Expert -HAS_EXPERTISE_IN→ ResearchField -SUB_FIELD_OF*- ResearchField ←BELONGS_TO- Project | Dự án thuộc lĩnh vực con/cha/anh em. |
| **P3** | Expert -PARTICIPATES_IN→ Project0 ←FUNDS- Funder -FUNDS→ Project | Dự án do cùng quỹ tài trợ với dự án chuyên gia đang tham gia. |

**Ưu tiên PGPR:** P1, P2 (field); P3 (funder portfolio).

---

### 3.2 Expert → Enterprise  
**Mục đích:** Gợi ý doanh nghiệp có nhu cầu phù hợp với chuyên môn.

| Meta-path | Chuỗi quan hệ | Ý nghĩa logic |
|-----------|----------------|----------------|
| **P1** | Expert -HAS_APPLICATION_EXPERIENCE_IN→ Industry ←OPERATES_IN- Enterprise | DN hoạt động trong ngành mà chuyên gia có kinh nghiệm ứng dụng. |
| **P2** | Expert -PARTICIPATES_IN→ Project ←PARTNERS_WITH- Enterprise | DN đang hợp tác với dự án mà chuyên gia tham gia. |

**Ưu tiên PGPR:** P1, P2 (ngắn, dễ giải thích).

---

### 3.3 Expert → Funder  
**Mục đích:** Gợi ý quỹ tài trợ phù hợp với lĩnh vực nghiên cứu của chuyên gia.

| Meta-path | Chuỗi quan hệ | Ý nghĩa logic |
|-----------|----------------|----------------|
| **P1** | Expert -PARTICIPATES_IN→ Project ←FUNDS- Funder | Quỹ đã tài trợ dự án mà chuyên gia tham gia. |
| **P2** | Expert -HAS_EXPERTISE_IN→ ResearchField ←SUPPORTS- Funder | Quỹ hỗ trợ đúng lĩnh vực chuyên môn. |
| **P3** | Expert -HAS_EXPERTISE_IN→ ResearchField -SUB_FIELD_OF*- ResearchField ←SUPPORTS- Funder | Quỹ hỗ trợ lĩnh vực liên quan (hierarchy). |

**Ưu tiên PGPR:** P1 (kinh nghiệm thực tế), P2, P3 (alignment lĩnh vực).

---

### 3.4 Expert → Expert  
**Mục đích:** Gợi ý chuyên gia tiềm năng để hợp tác nghiên cứu.

| Meta-path | Chuỗi quan hệ | Ý nghĩa logic |
|-----------|----------------|----------------|
| **P1** | Expert -HAS_EXPERTISE_IN→ ResearchField ←HAS_EXPERTISE_IN- Expert2 | Cùng lĩnh vực chuyên môn. |
| **P2** | Expert -PARTICIPATES_IN→ Project ←PARTICIPATES_IN- Expert2 | Cùng tham gia ít nhất một dự án (đã cộng tác). |
| **P3** | Expert -HAS_EXPERTISE_IN→ ResearchField -SUB_FIELD_OF*- ResearchField ←HAS_EXPERTISE_IN- Expert2 | Chuyên môn lĩnh vực liên quan (cha/con). |
| **P4** | Expert -HAS_SKILL→ MethodTechnique ←HAS_SKILL- Expert2 | Cùng kỹ năng phương pháp/kỹ thuật. |

**Ưu tiên PGPR:** P1, P2 (rõ ràng); P3, P4 (đa dạng, cross-field/cross-method).

---

## 4. Khi nguồn là **Funder**

### 4.1 Funder → Project  
**Mục đích:** Tìm dự án phù hợp để tài trợ.

| Meta-path | Chuỗi quan hệ | Ý nghĩa logic |
|-----------|----------------|----------------|
| **P1** | Funder -SUPPORTS→ ResearchField ←BELONGS_TO- Project | Dự án thuộc đúng lĩnh vực quỹ hỗ trợ. |
| **P2** | Funder -SUPPORTS→ ResearchField -SUB_FIELD_OF*- ResearchField ←BELONGS_TO- Project | Dự án thuộc lĩnh vực con/cha trong phạm vi hỗ trợ. |
| **P3** | Funder -FUNDS→ Project0 -BELONGS_TO→ ResearchField ←BELONGS_TO- Project | Dự án cùng (hoặc liên quan) lĩnh vực với dự án quỹ đã tài trợ. |

**Ưu tiên PGPR:** P1, P2 (policy SUPPORTS); P3 (portfolio consistency).

---

### 4.2 Funder → Expert  
**Mục đích:** Tìm chuyên gia tiềm năng trong lĩnh vực quỹ ưu tiên.

| Meta-path | Chuỗi quan hệ | Ý nghĩa logic |
|-----------|----------------|----------------|
| **P1** | Funder -FUNDS→ Project ←PARTICIPATES_IN- Expert | Chuyên gia từng tham gia dự án quỹ tài trợ. |
| **P2** | Funder -SUPPORTS→ ResearchField ←HAS_EXPERTISE_IN- Expert | Chuyên gia có chuyên môn đúng lĩnh vực quỹ hỗ trợ. |
| **P3** | Funder -SUPPORTS→ ResearchField -SUB_FIELD_OF*- ResearchField ←HAS_EXPERTISE_IN- Expert | Chuyên môn trong lĩnh vực liên quan. |

**Ưu tiên PGPR:** P1 (đã có quan hệ); P2, P3 (alignment lĩnh vực).

---

### 4.3 Funder → Enterprise  
**Mục đích:** Tìm doanh nghiệp chiến lược có thể đồng hành cùng các dự án.

| Meta-path | Chuỗi quan hệ | Ý nghĩa logic |
|-----------|----------------|----------------|
| **P1** | Funder -FUNDS→ Project ←PARTNERS_WITH- Enterprise | DN đang hợp tác với dự án quỹ tài trợ. |
| **P2** | Funder -SUPPORTS→ ResearchField ←BELONGS_TO- Project ←PARTNERS_WITH- Enterprise | DN hợp tác với dự án thuộc lĩnh vực quỹ hỗ trợ. |
| **P3** | Funder -FUNDS→ Project ←PARTICIPATES_IN- Expert -HAS_APPLICATION_EXPERIENCE_IN→ Industry ←OPERATES_IN- Enterprise | DN hoạt động trong ngành có chuyên gia từ dự án quỹ tài trợ. |

**Ưu tiên PGPR:** P1 (trực tiếp); P2, P3 (mở rộng qua field/industry).

---

## 5. Khi nguồn là **Enterprise**

### 5.1 Enterprise → Project  
**Mục đích:** Tìm dự án phù hợp để hợp tác hoặc đầu tư.

| Meta-path | Chuỗi quan hệ | Ý nghĩa logic |
|-----------|----------------|----------------|
| **P1** | Enterprise -PARTNERS_WITH→ Project0 -BELONGS_TO→ ResearchField ←BELONGS_TO- Project | Dự án cùng/liên quan lĩnh vực với dự án DN đã hợp tác. |
| **P2** | Enterprise -OPERATES_IN→ Industry ←HAS_APPLICATION_EXPERIENCE_IN- Expert -PARTICIPATES_IN→ Project | Dự án có chuyên gia có kinh nghiệm ứng dụng trong ngành của DN. |
| **P3** | Enterprise -PARTNERS_WITH→ Project0 ←FUNDS- Funder -FUNDS→ Project | Dự án cùng hệ sinh thái tài trợ với dự án DN đang hợp tác. |

**Ưu tiên PGPR:** P1 (field-based); P2 (industry-expert); P3 (funder).

---

### 5.2 Enterprise → Expert  
**Mục đích:** Tìm chuyên gia tư vấn hoặc hợp tác nghiên cứu.

| Meta-path | Chuỗi quan hệ | Ý nghĩa logic |
|-----------|----------------|----------------|
| **P1** | Enterprise -OPERATES_IN→ Industry ←HAS_APPLICATION_EXPERIENCE_IN- Expert | Chuyên gia có kinh nghiệm ứng dụng trong ngành DN. |
| **P2** | Enterprise -PARTNERS_WITH→ Project ←PARTICIPATES_IN- Expert | Chuyên gia tham gia dự án mà DN hợp tác. |

**Ưu tiên PGPR:** P1, P2 (ngắn, dễ giải thích).

---

### 5.3 Enterprise → Funder  
**Mục đích:** Tìm quỹ tài trợ liên quan đến lĩnh vực doanh nghiệp quan tâm.

| Meta-path | Chuỗi quan hệ | Ý nghĩa logic |
|-----------|----------------|----------------|
| **P1** | Enterprise -PARTNERS_WITH→ Project ←FUNDS- Funder | Quỹ tài trợ dự án mà DN hợp tác. |
| **P2** | Enterprise -PARTNERS_WITH→ Project -BELONGS_TO→ ResearchField ←SUPPORTS- Funder | Quỹ hỗ trợ lĩnh vực của dự án mà DN đang hợp tác. |
| **P3** | Enterprise -OPERATES_IN→ Industry (↔ ResearchField nếu có) ←SUPPORTS- Funder | Quỹ hỗ trợ lĩnh vực liên quan ngành DN (khi có link Field–Industry). |

**Ưu tiên PGPR:** P1 (trực tiếp); P2 (qua field).

---

### 5.4 Enterprise → Enterprise  
**Mục đích:** Tìm doanh nghiệp cùng lĩnh vực để hợp tác.

| Meta-path | Chuỗi quan hệ | Ý nghĩa logic |
|-----------|----------------|----------------|
| **P1** | Enterprise -OPERATES_IN→ Industry ←OPERATES_IN- Enterprise2 | Cùng ngành hoạt động. |
| **P2** | Enterprise -PARTNERS_WITH→ Project ←PARTNERS_WITH- Enterprise2 | Cùng hợp tác với ít nhất một dự án. |
| **P3** | Enterprise -PARTNERS_WITH→ Project -BELONGS_TO→ ResearchField ←BELONGS_TO- Project2 ←PARTNERS_WITH- Enterprise2 | DN khác hợp tác với dự án cùng lĩnh vực. |

**Ưu tiên PGPR:** P1 (cùng industry); P2 (cùng project); P3 (cùng field).

---

## 6. Tổng hợp cặp gợi ý và hàm tương ứng

| Nguồn | Đích | Hàm PGPR (trong code) |
|-------|------|------------------------|
| Project | Expert | `recommend_experts_for_project_pgpr` |
| Project | Funder | `recommend_funders_for_project_pgpr` |
| Project | Enterprise | `recommend_enterprises_for_project_pgpr` |
| Project | Project | `recommend_projects_for_project_pgpr` (similar projects) |
| Expert | Project | `recommend_projects_for_expert_pgpr` |
| Expert | Enterprise | `recommend_enterprises_for_expert_pgpr` |
| Expert | Funder | `recommend_funders_for_expert_pgpr` |
| Expert | Expert | `recommend_experts_for_expert_pgpr` (collaborators) |
| Funder | Project | `recommend_projects_for_funder_pgpr` |
| Funder | Expert | `recommend_experts_for_funder_pgpr` |
| Funder | Enterprise | `recommend_enterprises_for_funder_pgpr` |
| Enterprise | Project | `recommend_projects_for_enterprise_pgpr` |
| Enterprise | Expert | `recommend_experts_for_enterprise_pgpr` |
| Enterprise | Funder | `recommend_funders_for_enterprise_pgpr` |
| Enterprise | Enterprise | `recommend_enterprises_for_enterprise_pgpr` |

---

## 7. Triển khai PGPR

- Mỗi cặp (source_type, target_type) dùng **find_reasoning_paths(source_id, source_type, target_id, target_type)** với `max_path_length` (ví dụ 5).
- **Candidate retrieval:** truy vấn Cypher theo các meta-path trên (ví dụ field hierarchy, FUNDS, PARTNERS_WITH) để lấy danh sách ứng viên, sau đó gọi path finding cho từng candidate.
- **Scoring:** kết hợp điểm đường đi (relation weights, length penalty, diversity) và có thể thêm tín hiệu từ candidate (số project chung, số funder chung, v.v.).
- **Explainability:** mỗi gợi ý trả về `reasoning_paths` (chuỗi quan hệ + mô tả) và có thể dùng `get_recommendation_explanation()` / `analyze_path_patterns()` để tạo giải thích chi tiết.

Tài liệu này thống nhất với các hàm trong `pgpr_recommendation.py` và có thể mở rộng thêm meta-path khi KG bổ sung quan hệ (ví dụ Project–MethodTechnique, ResearchField–Industry).
