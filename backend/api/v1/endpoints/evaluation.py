from fastapi import APIRouter, Depends

from api.deps import get_evaluation_service
from services.evaluation_service import EvaluationService

router = APIRouter()


@router.get("/summary", summary="Evaluation summary (Phase 8 offline report)")
async def get_evaluation_summary(
    service: EvaluationService = Depends(get_evaluation_service),
):
    return service.get_summary()
