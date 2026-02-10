# Sửa lỗi: Command đúng để đề xuất Projects cho Expert

## ❌ Command SAI (đang gặp lỗi):

```python
recs = engine.recommend_projects_for_expert_pgpr('EXP_0001', limit=5, use_policy=True)
```

**Lỗi:** `TypeError: got an unexpected keyword argument 'use_policy'`

## ✅ Command ĐÚNG:

```python
recs = engine.recommend_projects_for_expert_pgpr('EXP_0001', limit=5)
```

**Giải thích:** Method `recommend_projects_for_expert_pgpr` không có parameter `use_policy`. Nó tự động sử dụng policy nếu có (như bạn thấy trong log: "PGPR policy loaded"), hoặc fallback về heuristic nếu không có.

## Command hoàn chỉnh:

```python
python -c "
from pgpr_recommendation import PGPRRecommender, print_pgpr_recommendations
engine = PGPRRecommender(max_path_length=5, data_dir='pgpr_data')
recs = engine.recommend_projects_for_expert_pgpr('EXP_0001', limit=5)
print_pgpr_recommendations(recs, 'Gợi ý projects cho EXP_0001', show_detailed=True)
engine.close()
"
```

## Các tham số hợp lệ:

```python
recommend_projects_for_expert_pgpr(
    expert_id: str,                    # Required: ID của expert
    limit: int = 10,                   # Optional: Số lượng (default: 10)
    status_filter: List[str] = None   # Optional: Lọc status (default: ['planning', 'recruiting', 'ongoing'])
)
```

## Ví dụ:

```python
# Cơ bản
recs = engine.recommend_projects_for_expert_pgpr('EXP_0001', limit=5)

# Với status filter
recs = engine.recommend_projects_for_expert_pgpr('EXP_0001', limit=5, status_filter=['recruiting'])

# Tất cả status
recs = engine.recommend_projects_for_expert_pgpr('EXP_0001', limit=5, status_filter=None)
```

---

**Lưu ý:** Policy đã được load tự động (như bạn thấy trong log), không cần truyền `use_policy=True`.
