import logging
from services.recommendation_service import RecommendationService
from pgpr.pgpr_recommendation import PGPRRecommender
from pgpr.pgpr_xai_explainer import PGPRExplainer

logger = logging.getLogger(__name__)

# Global singletons
_pgpr_recommender = None
_pgpr_explainer = None

def get_pgpr_recommender() -> PGPRRecommender:
    global _pgpr_recommender
    if _pgpr_recommender is None:
        logger.info("Khởi tạo PGPRRecommender (Singleton)...")
        _pgpr_recommender = PGPRRecommender(
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
        _pgpr_explainer = PGPRExplainer(language="vi", use_llm=True, ollama_model="llama3")
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

