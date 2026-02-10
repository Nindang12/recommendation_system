# Command đúng để đề xuất Projects cho Expert

## ❌ Command SAI (trong terminal của bạn):

```python
python -c "
from pgpr_recommendation import PGPRRecommender, print_pgpr_recommendations
engine = PGPRRecommender(max_path_length=5, data_dir='pgpr_data')
recs = engine.recommend_project_for_expert_pgpr('EXP_0001', limit=5, use_policy=True)
engine.close()
"
```

**Lỗi:**
1. `recommend_project_for_expert_pgpr` → SAI (số ít)
2. `use_policy=True` → Parameter không tồn tại

## ✅ Command ĐÚNG:

### Cách 1: One-liner

```python
python -c "
from pgpr_recommendation import PGPRRecommender, print_pgpr_recommendations
engine = PGPRRecommender(max_path_length=5, data_dir='pgpr_data')
recs = engine.recommend_projects_for_expert_pgpr('EXP_0001', limit=5)
print_pgpr_recommendations(recs, 'Gợi ý projects cho EXP_0001', show_detailed=True)
engine.close()
"
```

### Cách 2: Chạy file script

```bash
python test_recommend_projects_simple.py
```

### Cách 3: Trong Python shell

```python
from pgpr_recommendation import PGPRRecommender, print_pgpr_recommendations

engine = PGPRRecommender(max_path_length=5, data_dir='pgpr_data')
recs = engine.recommend_projects_for_expert_pgpr('EXP_0001', limit=5)
print_pgpr_recommendations(recs, 'Gợi ý projects cho EXP_0001', show_detailed=True)
engine.close()
```

## Tham số của method `recommend_projects_for_expert_pgpr`:

```python
recommend_projects_for_expert_pgpr(
    expert_id: str,                    # Required: ID của expert
    limit: int = 10,                   # Optional: Số lượng projects (default: 10)
    status_filter: List[str] = None   # Optional: Lọc theo status (default: ['planning', 'recruiting', 'ongoing'])
)
```

## Ví dụ với các tùy chọn:

```python
# Cơ bản
recs = engine.recommend_projects_for_expert_pgpr('EXP_0001', limit=5)

# Chỉ lấy projects đang tuyển dụng
recs = engine.recommend_projects_for_expert_pgpr('EXP_0001', limit=5, status_filter=['recruiting'])

# Lấy tất cả projects (không lọc status)
recs = engine.recommend_projects_for_expert_pgpr('EXP_0001', limit=5, status_filter=None)
```

---

**Lưu ý:** Method này không có parameter `use_policy` vì nó tự động sử dụng policy nếu có, hoặc fallback về heuristic nếu không có policy.
