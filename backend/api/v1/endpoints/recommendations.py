import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_recommendation_service
from models.schemas import (
    RecommendationRequest, 
    RecommendationResponse, 
    ExplainRecommendationRequest
)
from services.recommendation_service import RecommendationService


router = APIRouter()
logger = logging.getLogger(__name__)


@router.post(
    "/experts",
    response_model=RecommendationResponse,
    summary="Recommend experts for a project using PGPR + XAI",
)
async def recommend_experts(
    request: RecommendationRequest,
    service: RecommendationService = Depends(get_recommendation_service),
) -> RecommendationResponse:
    """
    API Route - HTTP only:
    - parse & validate input
    - delegate to Service Layer
    - format HTTP response
    """
    try:
        if not request.project_id:
            raise HTTPException(status_code=422, detail="project_id is required for /experts")
        results = await service.get_recommendations_by_policy(
            source_id=request.project_id,
            source_type="project",
            target_type="expert",
            limit=request.limit,
            language=request.language,
        )
        return RecommendationResponse(
            status="success",
            data=results,
            count=len(results),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unhandled error in recommend_experts")
        raise HTTPException(status_code=500, detail="Internal error") from exc


@router.post(
    "/funders",
    response_model=RecommendationResponse,
    summary="Recommend funders for a project using PGPR + XAI",
)
async def recommend_funders_for_project(
    request: RecommendationRequest,
    service: RecommendationService = Depends(get_recommendation_service),
) -> RecommendationResponse:
    """
    Recommend funders from a source project.
    """
    try:
        if not request.project_id:
            raise HTTPException(status_code=422, detail="project_id is required for /funders")
        results = await service.get_recommendations_by_policy(
            source_id=request.project_id,
            source_type="project",
            target_type="funder",
            limit=request.limit,
            language=request.language,
        )
        return RecommendationResponse(
            status="success",
            data=results,
            count=len(results),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unhandled error in recommend_funders_for_project")
        raise HTTPException(status_code=500, detail="Internal error") from exc


@router.post(
    "/policy",
    response_model=RecommendationResponse,
    summary="Generic policy-based recommendation for all supported entity types",
)
async def recommend_by_policy(
    request: RecommendationRequest,
    service: RecommendationService = Depends(get_recommendation_service),
) -> RecommendationResponse:
    if not request.source_id or not request.source_type or not request.target_type:
        raise HTTPException(
            status_code=422,
            detail="source_id, source_type, target_type are required for /policy",
        )
    try:
        results = await service.get_recommendations_by_policy(
            source_id=request.source_id,
            source_type=request.source_type,
            target_type=request.target_type,
            limit=request.limit,
            language=request.language,
        )
        return RecommendationResponse(
            status="success",
            data=results,
            count=len(results),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unhandled error in recommend_by_policy")
        raise HTTPException(status_code=500, detail="Internal error") from exc

@router.post(
    "/explain",
    summary="Generate on-demand LLM explanation for a specific recommendation",
)
async def explain_recommendation(
    request: ExplainRecommendationRequest,
    service: RecommendationService = Depends(get_recommendation_service),
) -> Dict[str, Any]:
    try:
        explanation = await service.explain_single_recommendation(
            recommendation=request.recommendation,
            target_type=request.target_type,
            source_context=request.source_context,
            language=request.language,
        )
        return {
            "status": "success",
            "data": explanation
        }
    except Exception as exc:
        logger.exception("Unhandled error in explain_recommendation")
        raise HTTPException(status_code=500, detail="Internal error") from exc
