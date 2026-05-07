import asyncio
import logging
import sys
from pprint import pprint

# Sửa lỗi in tiếng Việt trên console Windows
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# Thiết lập logging để dễ nhìn
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_repository_layer():
    print("\n--- 1. TEST REPOSITORY LAYER ---")
    from repositories.neo4j_repo import Neo4jRepository
    
    try:
        neo4j_repo = Neo4jRepository()
        print("Khởi tạo Neo4jRepository thành công!")
        # Bạn có thể gọi thử một hàm trong repo ở đây (ví dụ: lấy project mẫu)
        # result = neo4j_repo.get_some_data()
        print("-> Layer Database/Repository hoạt động bình thường.")
    except Exception as e:
        logger.error("Lỗi ở Repository Layer:", exc_info=True)


async def test_service_layer():
    print("\n--- 2. TEST SERVICE LAYER & PGPR ---")
    from api.deps import get_pgpr_recommender, get_pgpr_explainer
    from services.recommendation_service import RecommendationService
    
    try:
        # Lấy singletons
        recommender = get_pgpr_recommender()
        explainer = get_pgpr_explainer()
        
        # Khởi tạo service không cần qua API HTTP
        service = RecommendationService(recommender=recommender, explainer=explainer)
        print("Khởi tạo RecommendationService thành công!")
        
        # Chạy thử một case (sửa project_id thành một ID có thật trong DB của bạn)
        test_project_id = "prj_001" 
        print(f"Đang gọi lấy gợi ý cho Project: {test_project_id}...")
        
        results = await service.get_expert_recommendations(project_id=test_project_id, limit=2)
        print(f"Thành công! Lấy được {len(results)} kết quả.")
        if results:
            print("Kết quả mẫu đầu tiên:")
            pprint(results[0])
            
    except Exception as e:
        logger.error("Lỗi ở Service Layer:", exc_info=True)


def test_api_layer():
    print("\n--- 3. TEST API / ROUTER LAYER ---")
    from fastapi.testclient import TestClient
    from main import app
    
    try:
        client = TestClient(app)
        
        # Gọi thử health check
        response = client.get("/")
        print("GET / -> Status:", response.status_code)
        print("Response:", response.json())
        
        # Test lỗi đầu vào (Validation Error)
        # Giả lập gửi request sai format hoặc thiếu project_id
        res_error = client.post("/api/v1/recommendations/experts", json={"limit": 5})
        print("\nTest bắt lỗi Validation (POST /experts không có project_id) -> Status:", res_error.status_code)
        print("Lỗi trả về:", res_error.json())
        
    except Exception as e:
        logger.error("Lỗi ở API Layer:", exc_info=True)

async def main():
    print("BẮT ĐẦU KIỂM TRA CÁC LAYER\n" + "="*30)
    await test_repository_layer()
    await test_service_layer()
    test_api_layer()
    print("\n" + "="*30 + "\nHOÀN TẤT KIỂM TRA!")

if __name__ == "__main__":
    asyncio.run(main())
