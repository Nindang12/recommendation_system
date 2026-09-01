from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_current_user, get_embedding_admin_service, get_entity_service, rate_limit
from models.schemas import EmbeddingRecomputeRequest
from services.embedding_admin_service import EmbeddingAdminService
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


@router.get("/{entity_type}/{entity_id}/embedding-status")
async def get_entity_embedding_status(
    entity_type: str,
    entity_id: str,
    current_user: dict = Depends(get_current_user),
    service: EmbeddingAdminService = Depends(get_embedding_admin_service),
) -> Dict[str, Any]:
    is_admin = (current_user or {}).get("account_role") in {"admin", "root_admin"}
    try:
        data = service.get_embedding_status(
            entity_type,
            entity_id,
            actor_user_id=str(current_user["id"]),
            is_admin=is_admin,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "success", "data": data}


@router.post("/{entity_type}/{entity_id}/embedding/recompute")
async def recompute_entity_embedding(
    entity_type: str,
    entity_id: str,
    payload: EmbeddingRecomputeRequest | None = None,
    _: None = Depends(rate_limit("embedding_recompute", limit=20, window_seconds=60)),
    current_user: dict = Depends(get_current_user),
    service: EmbeddingAdminService = Depends(get_embedding_admin_service),
) -> Dict[str, Any]:
    is_admin = (current_user or {}).get("account_role") in {"admin", "root_admin"}
    body = payload or EmbeddingRecomputeRequest()
    try:
        data = service.recompute_entity(
            entity_type,
            entity_id,
            actor_user_id=str(current_user["id"]),
            is_admin=is_admin,
            reason=body.reason,
            source="api.user.recompute" if not is_admin else "api.admin.recompute",
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        detail = str(exc)
        status = 429 if detail.startswith("Rate limit") else 404
        raise HTTPException(status_code=status, detail=detail) from exc
    return {"status": "success", "data": data}


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
