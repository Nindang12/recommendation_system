from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends

from api.deps import get_health_service
from services.health_service import HealthService

router = APIRouter()


@router.get("/health")
async def health_check(
    service: HealthService = Depends(get_health_service),
) -> Dict[str, Any]:
    return await service.get_health()
