import logging

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_recommendation_service
from models.schemas import ExplainRecommendationRequest, ExplanationResponse
from services.recommendation_service import RecommendationService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post(
    "",
    response_model=ExplanationResponse,
    summary="Generate explanation for a recommendation (rule / llm / auto)",
)
async def create_explanation(
    request: ExplainRecommendationRequest,
    service: RecommendationService = Depends(get_recommendation_service),
) -> ExplanationResponse:
    try:
        explanation = await service.explain_recommendation(
            recommendation=request.recommendation,
            target_type=request.target_type,
            source_context=request.source_context,
            language=request.language,
            mode=request.mode,
            force_refresh=request.force_refresh,
        )
        return ExplanationResponse(status="success", data=explanation)
    except Exception as exc:  # noqa: BLE001
        logger.exception("create_explanation failed")
        raise HTTPException(status_code=500, detail="Internal error") from exc
