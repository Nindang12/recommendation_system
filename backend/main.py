import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import router từ file recommendations.py của bạn
# Sửa đường dẫn import tùy theo việc thư mục của bạn có tên là `api` hay `app.api`
from api.v1.endpoints import recommendations

app = FastAPI(
    title="R&D Recommendation API",
    description="Hệ thống gợi ý PGPR + XAI cho lĩnh vực R&D",
    version="1.0.0"
)

# Cấu hình CORS để Frontend (React/Vue/Angular) gọi được API mà không bị block
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Trong production nên giới hạn lại domain của Frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Gắn Router (Cổng API) vào App
app.include_router(
    recommendations.router, 
    prefix="/api/v1/recommendations", 
    tags=["Recommendations"]
)

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Hệ thống PGPR Backend đang chạy trơn tru!"}

if __name__ == "__main__":
    # Lệnh này giúp bạn chạy debug trực tiếp trong IDE nếu muốn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)