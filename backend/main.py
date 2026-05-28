from contextlib import asynccontextmanager
import logging
import os
import time

import uvicorn
from fastapi import Request
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.deps import get_pgpr_graph_repo
from api.v1.endpoints import admin, auth, entities, evaluation, explanations, graph, health, recommendations, taxonomy
from services.auth_service import AuthService

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s",
    force=True,
)
logger = logging.getLogger("backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application startup complete.")
    _ensure_root_admin()
    yield
    try:
        get_pgpr_graph_repo().close()
    except Exception:
        pass


app = FastAPI(
    title="R&D Recommendation API",
    description="Hệ thống gợi ý PGPR + XAI cho lĩnh vực R&D",
    version="1.0.0",
    lifespan=lifespan,
)

def _cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "http://localhost:9002,http://127.0.0.1:9002")
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    return origins or ["http://localhost:9002"]


def _ensure_root_admin() -> None:
    email = os.getenv("ROOT_ADMIN_EMAIL", "admin@example.com").strip().lower()
    password = os.getenv("ROOT_ADMIN_PASSWORD", "Admin@123456")
    name = os.getenv("ROOT_ADMIN_NAME", "System Root Admin")
    try:
        service = AuthService()
        existing = service.repo.find_user_by_email(email)
        if existing:
            if existing.get("account_role") != "root_admin":
                service.repo.set_user_account_role(str(existing["_id"]), "root_admin")
                logger.info("Updated root admin account role: %s", email)
            return
        service.create_admin_user(
            {
                "email": email,
                "password": password,
                "full_name": name,
                "role": "expert",
            },
            account_role="root_admin",
        )
        logger.info("Created root admin account: %s", email)
    except Exception as exc:
        logger.warning("Could not ensure root admin account: %s", exc)


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    print(f"API REQUEST: {request.method} {request.url.path}", flush=True)
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    print(
        f"API RESPONSE: {request.method} {request.url.path} -> {response.status_code} {duration_ms:.1f}ms",
        flush=True,
    )
    logger.info(
        '%s %s -> %s %.1fms',
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


app.include_router(
    recommendations.router,
    prefix="/api/v1/recommendations",
    tags=["Recommendations"],
)
app.include_router(
    explanations.router,
    prefix="/api/v1/explanations",
    tags=["Explanations"],
)
app.include_router(
    graph.router,
    prefix="/api/v1/graph",
    tags=["Graph"],
)
app.include_router(
    health.router,
    prefix="/api/v1",
    tags=["Health"],
)
app.include_router(
    entities.router,
    prefix="/api/v1/entities",
    tags=["Entities"],
)
app.include_router(
    evaluation.router,
    prefix="/api/v1/evaluation",
    tags=["Evaluation"],
)
app.include_router(
    auth.router,
    prefix="/api/v1",
    tags=["Auth"],
)
app.include_router(
    admin.router,
    prefix="/api/v1/admin",
    tags=["Admin"],
)
app.include_router(
    taxonomy.router,
    prefix="/api/v1/taxonomy",
    tags=["Taxonomy"],
)


@app.get("/")
def read_root():
    return {"status": "ok", "message": "Hệ thống PGPR Backend đang chạy trơn tru!"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info", access_log=True)
