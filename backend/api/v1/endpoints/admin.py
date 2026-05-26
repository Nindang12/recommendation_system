from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import get_current_user
from repositories.auth_repo import AuthRepository
from services.admin_audit_log_service import AdminAuditLogService
from services.provisional_kg_sync_service import ProvisionalKGSyncService

router = APIRouter()


class MergeEntityRequest(BaseModel):
    target_entity_id: str
    reason: str = ""


@router.post("/kg-sync/{entity_type}/{entity_id}/retry")
async def retry_kg_sync(
    entity_type: str,
    entity_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    service = ProvisionalKGSyncService()
    audit = AdminAuditLogService()
    before = AuthRepository().find_entity_by_id(entity_type, entity_id) or {}
    try:
        entity = service.retry_sync(entity_type, entity_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    audit.log(
        admin_user_id=current_user["id"],
        action="retry_kg_sync",
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=entity,
    )
    return {"status": "success", "data": AuthRepository()._json_safe(entity)}


@router.post("/entities/{entity_type}/{entity_id}/verify")
async def verify_entity(
    entity_type: str,
    entity_id: str,
    reason: str = "",
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    service = ProvisionalKGSyncService()
    repo = AuthRepository()
    before = repo.find_entity_by_id(entity_type, entity_id) or {}
    try:
        entity = service.verify_entity(entity_type, entity_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    AdminAuditLogService(repo).log(
        admin_user_id=current_user["id"],
        action="verify_entity",
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=entity,
        reason=reason,
    )
    return {"status": "success", "data": repo._json_safe(entity)}


@router.post("/entities/{entity_type}/{entity_id}/reject")
async def reject_entity(
    entity_type: str,
    entity_id: str,
    reason: str = "",
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    service = ProvisionalKGSyncService()
    repo = AuthRepository()
    before = repo.find_entity_by_id(entity_type, entity_id) or {}
    try:
        entity = service.reject_entity(entity_type, entity_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    AdminAuditLogService(repo).log(
        admin_user_id=current_user["id"],
        action="reject_entity",
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=entity,
        reason=reason,
    )
    return {"status": "success", "data": repo._json_safe(entity)}


@router.post("/entities/{entity_type}/{entity_id}/disable-kg")
async def disable_kg(
    entity_type: str,
    entity_id: str,
    reason: str = "",
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    service = ProvisionalKGSyncService()
    repo = AuthRepository()
    before = repo.find_entity_by_id(entity_type, entity_id) or {}
    try:
        entity = service.disable_entity(entity_type, entity_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    AdminAuditLogService(repo).log(
        admin_user_id=current_user["id"],
        action="disable_kg",
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=entity,
        reason=reason,
    )
    return {"status": "success", "data": repo._json_safe(entity)}


@router.post("/entities/{entity_type}/{source_entity_id}/merge")
async def merge_entity(
    entity_type: str,
    source_entity_id: str,
    payload: MergeEntityRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    service = ProvisionalKGSyncService()
    repo = AuthRepository()
    before = repo.find_entity_by_id(entity_type, source_entity_id) or {}
    try:
        entity = service.merge_entities(entity_type, source_entity_id, payload.target_entity_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    AdminAuditLogService(repo).log(
        admin_user_id=current_user["id"],
        action="merge_entity",
        entity_type=entity_type,
        entity_id=source_entity_id,
        before=before,
        after=entity,
        reason=payload.reason,
    )
    return {"status": "success", "data": repo._json_safe(entity)}
