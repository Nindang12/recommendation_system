from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_entity_service
from services.entity_service import EntityService

router = APIRouter()


@router.get("/projects")
async def list_projects(
    search: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    page: int = Query(default=1, ge=1),
    service: EntityService = Depends(get_entity_service),
) -> Dict[str, Any]:
    return await _list_entities(service, "project", search=search, limit=limit, page=page)


@router.get("/experts")
async def list_experts(
    search: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    page: int = Query(default=1, ge=1),
    service: EntityService = Depends(get_entity_service),
) -> Dict[str, Any]:
    return await _list_entities(service, "expert", search=search, limit=limit, page=page)


@router.get("/funders")
async def list_funders(
    search: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    page: int = Query(default=1, ge=1),
    service: EntityService = Depends(get_entity_service),
) -> Dict[str, Any]:
    return await _list_entities(service, "funder", search=search, limit=limit, page=page)


@router.get("/enterprises")
async def list_enterprises(
    search: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    page: int = Query(default=1, ge=1),
    service: EntityService = Depends(get_entity_service),
) -> Dict[str, Any]:
    return await _list_entities(service, "enterprise", search=search, limit=limit, page=page)


@router.get("/{entity_type}/{entity_id}")
async def get_entity_detail(
    entity_type: str,
    entity_id: str,
    service: EntityService = Depends(get_entity_service),
) -> Dict[str, Any]:
    try:
        entity = await service.get_entity(entity_type, entity_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="MongoDB is unavailable") from exc

    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    return {
        "status": "success",
        "data": entity,
    }


async def _list_entities(
    service: EntityService,
    entity_type: str,
    search: Optional[str],
    limit: int,
    page: int,
) -> Dict[str, Any]:
    try:
        return await service.list_entities(
            entity_type=entity_type,
            search=search,
            limit=limit,
            page=page,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="MongoDB is unavailable") from exc
