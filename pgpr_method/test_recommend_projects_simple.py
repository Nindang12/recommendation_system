"""
Test đơn giản: Đề xuất projects cho expert
"""

from pgpr_recommendation import PGPRRecommender, print_pgpr_recommendations

# Khởi tạo
engine = PGPRRecommender(max_path_length=5, data_dir='pgpr_data')

# Đề xuất projects cho expert
recs = engine.recommend_projects_for_expert_pgpr('EXP_0001', limit=5)

# In kết quả
print_pgpr_recommendations(recs, "Gợi ý projects cho EXP_0001", show_detailed=True)

# Đóng connection
engine.close()
