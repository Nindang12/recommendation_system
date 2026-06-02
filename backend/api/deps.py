import logging
import os
from services.recommendation_service import RecommendationService
from services.entity_service import EntityService
from services.health_service import HealthService
from services.graph_service import GraphService
from services.evaluation_service import EvaluationService
from services.auth_service import AuthService
from services.embedding_admin_service import EmbeddingAdminService
from services.governance_audit_service import GovernanceAuditService
from pgpr.pgpr_recommendation import PGPRRecommender
from pgpr.pgpr_xai_explainer import PGPRExplainer
from repositories.pgpr_graph_repo import PGPRGraphRepository
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from services.rate_limit_service import rate_limit_enabled, rate_limiter

logger = logging.getLogger(__name__)

# Global singletons
_pgpr_graph_repo = None
_pgpr_recommender = None
_pgpr_explainer = None
_auth_service = None
bearer_scheme = HTTPBearer(auto_error=False)


def get_pgpr_graph_repo() -> PGPRGraphRepository:
    global _pgpr_graph_repo
    if _pgpr_graph_repo is None:
        logger.info("Khoi tao PGPRGraphRepository (Singleton)...")
        _pgpr_graph_repo = PGPRGraphRepository()
    return _pgpr_graph_repo


def get_pgpr_recommender() -> PGPRRecommender:
    global _pgpr_recommender
    if _pgpr_recommender is None:
        logger.info("Khởi tạo PGPRRecommender (Singleton)...")
        _pgpr_recommender = PGPRRecommender(
            graph_repo=get_pgpr_graph_repo(),
            max_path_length=5,
            gamma=0.99,
            top_k_paths=10,
            enable_cache=True,
        )
    return _pgpr_recommender

def get_pgpr_explainer() -> PGPRExplainer:
    global _pgpr_explainer
    if _pgpr_explainer is None:
        logger.info("Khởi tạo PGPRExplainer (Singleton)...")
        model = os.getenv("OLLAMA_MODEL", "llama3")
        _pgpr_explainer = PGPRExplainer(
            language="vi", 
            use_llm=True, 
            ollama_model=model
        )
    return _pgpr_explainer


def get_recommendation_service() -> RecommendationService:
    """
    Dependency provider for RecommendationService.
    FastAPI can use this via Depends(get_recommendation_service).
    """
    return RecommendationService(
        recommender=get_pgpr_recommender(),
        explainer=get_pgpr_explainer()
    )


def get_entity_service() -> EntityService:
    return EntityService()


def get_health_service() -> HealthService:
    return HealthService()


def get_graph_service() -> GraphService:
    return GraphService(recommender=get_pgpr_recommender())


def get_evaluation_service() -> EvaluationService:
    return EvaluationService()


def get_auth_service() -> AuthService:
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service


def get_embedding_admin_service() -> EmbeddingAdminService:
    return EmbeddingAdminService()


def get_governance_audit_service() -> GovernanceAuditService:
    return GovernanceAuditService()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    service: AuthService = Depends(get_auth_service),
):
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Missing bearer token")
    try:
        return service.get_current_user(credentials.credentials)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def get_current_admin_user(current_user=Depends(get_current_user)):
    if current_user.get("account_role") not in {"admin", "root_admin"}:
        raise HTTPException(status_code=403, detail="Admin permission required")
    return current_user


def get_current_root_admin(current_user=Depends(get_current_user)):
    if current_user.get("account_role") != "root_admin":
        raise HTTPException(status_code=403, detail="Root admin permission required")
    return current_user


def require_non_empty_reason(reason: str | None, *, action: str = "this action") -> None:
    if not str(reason or "").strip():
        raise HTTPException(status_code=400, detail=f"Reason is required for {action}")


def require_root_role(current_user: dict, *, action: str) -> None:
    if current_user.get("account_role") != "root_admin":
        raise HTTPException(status_code=403, detail=f"Root admin permission required for {action}")


def rate_limit(scope: str, *, limit: int, window_seconds: int):
    async def dependency(request: Request) -> None:
        if not rate_limit_enabled():
            return
        client_host = request.client.host if request.client else "unknown"
        key = f"{scope}:{client_host}"
        allowed, retry_after = rate_limiter.check(
            key,
            limit=max(limit, 1),
            window_seconds=max(window_seconds, 1),
        )
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded for {scope}",
                headers={"Retry-After": str(retry_after)},
            )

    return dependency


def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    service: AuthService = Depends(get_auth_service),
):
    if credentials is None or credentials.scheme.lower() != "bearer":
        return None
    try:
        return service.get_current_user(credentials.credentials)
    except PermissionError:
        return None
