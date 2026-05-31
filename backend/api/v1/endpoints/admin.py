from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import get_auth_service, get_current_admin_user, get_current_root_admin
from models.schemas import AdminCreateUserRequest, EmbeddingRecomputeRequest
from repositories.auth_repo import AuthRepository
from services.admin_audit_log_service import AdminAuditLogService
from services.auth_service import AuthService
from api.deps import get_embedding_admin_service
from services.embedding_admin_service import EmbeddingAdminService
from services.provisional_kg_sync_service import ProvisionalKGSyncService

router = APIRouter()

REVIEW_KG_STATUSES = {
    "unverified",
    "synced_unverified",
    "synced_verified",
    "merge_required",
    "sync_failed",
    "verified",
    "rejected",
    "not_synced",
    "syncing",
    "sync_partial",
    "disabled",
}


class MergeEntityRequest(BaseModel):
    target_entity_id: str
    reason: str = ""


@router.get("/entities")
async def list_entities_for_review(
    entity_type: str | None = None,
    kg_sync_status: str | None = None,
    entity_verification_status: str | None = None,
    limit: int = 50,
    page: int = 1,
    current_user: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    _ = current_user
    if kg_sync_status and kg_sync_status not in REVIEW_KG_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid kg_sync_status: {kg_sync_status}")
    repo = AuthRepository()
    rows = repo.list_entities_for_admin(
        entity_type=entity_type,
        kg_sync_status=kg_sync_status,
        entity_verification_status=entity_verification_status,
        limit=min(max(limit, 1), 100),
        page=max(page, 1),
    )
    return {
        "status": "success",
        "data": [repo._json_safe(row) for row in rows],
        "count": len(rows),
    }


@router.get("/entities/{entity_type}/{entity_id}")
async def get_entity_for_review(
    entity_type: str,
    entity_id: str,
    current_user: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    _ = current_user
    repo = AuthRepository()
    entity = repo.find_entity_by_id(entity_type, entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    return {"status": "success", "data": repo._json_safe(entity)}


@router.get("/audit-logs")
async def list_audit_logs(
    limit: int = 50,
    page: int = 1,
    current_user: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    _ = current_user
    repo = AuthRepository()
    rows = repo.list_admin_audit_logs(limit=min(max(limit, 1), 100), page=max(page, 1))
    return {
        "status": "success",
        "data": [repo._json_safe(row) for row in rows],
        "count": len(rows),
    }


@router.post("/kg-sync/{entity_type}/{entity_id}/retry")
async def retry_kg_sync(
    entity_type: str,
    entity_id: str,
    current_user: Dict[str, Any] = Depends(get_current_admin_user),
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
    current_user: Dict[str, Any] = Depends(get_current_admin_user),
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
    current_user: Dict[str, Any] = Depends(get_current_admin_user),
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
    current_user: Dict[str, Any] = Depends(get_current_admin_user),
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
    current_user: Dict[str, Any] = Depends(get_current_admin_user),
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


@router.get("/embedding/pipeline-status")
async def embedding_pipeline_status(
    current_user: Dict[str, Any] = Depends(get_current_admin_user),
    service: EmbeddingAdminService = Depends(get_embedding_admin_service),
) -> Dict[str, Any]:
    _ = current_user
    return {"status": "success", "data": service.pipeline_status()}


@router.get("/embedding/jobs")
async def list_embedding_jobs(
    status: str | None = None,
    entity_type: str | None = None,
    limit: int = 50,
    page: int = 1,
    current_user: Dict[str, Any] = Depends(get_current_admin_user),
    service: EmbeddingAdminService = Depends(get_embedding_admin_service),
) -> Dict[str, Any]:
    _ = current_user
    data = service.list_jobs(status=status, entity_type=entity_type, limit=limit, page=page)
    return {"status": "success", **data}


@router.post("/embedding/retry-failed")
async def retry_failed_embedding_jobs(
    limit: int = 50,
    reason: str = "",
    entity_type: str | None = None,
    error_type: str | None = None,
    include_permanent: bool = False,
    current_user: Dict[str, Any] = Depends(get_current_admin_user),
    service: EmbeddingAdminService = Depends(get_embedding_admin_service),
) -> Dict[str, Any]:
    try:
        data = service.retry_failed_jobs(
            admin_user_id=str(current_user["id"]),
            limit=min(max(limit, 1), 200),
            reason=reason,
            entity_type=entity_type,
            error_type=error_type,
            include_permanent=include_permanent,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "success", "data": data}


@router.post("/entities/{entity_type}/{entity_id}/embedding/recompute")
async def admin_recompute_entity_embedding(
    entity_type: str,
    entity_id: str,
    payload: EmbeddingRecomputeRequest | None = None,
    current_user: Dict[str, Any] = Depends(get_current_admin_user),
    service: EmbeddingAdminService = Depends(get_embedding_admin_service),
) -> Dict[str, Any]:
    body = payload or EmbeddingRecomputeRequest()
    try:
        data = service.recompute_entity(
            entity_type,
            entity_id,
            actor_user_id=str(current_user["id"]),
            is_admin=True,
            reason=body.reason,
            source="api.admin.recompute",
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "success", "data": data}


@router.get("/users")
async def list_admin_users(
    limit: int = 50,
    page: int = 1,
    current_user: Dict[str, Any] = Depends(get_current_root_admin),
) -> Dict[str, Any]:
    _ = current_user
    repo = AuthRepository()
    rows = repo.list_users_for_admin(limit=min(max(limit, 1), 100), page=max(page, 1))
    return {"status": "success", "data": [repo._json_safe(row) for row in rows], "count": len(rows)}


@router.post("/users/create-admin")
async def create_admin_user(
    payload: AdminCreateUserRequest,
    current_user: Dict[str, Any] = Depends(get_current_root_admin),
    service: AuthService = Depends(get_auth_service),
) -> Dict[str, Any]:
    repo = AuthRepository()
    try:
        user = service.create_admin_user(payload.model_dump(), account_role="admin")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    AdminAuditLogService(repo).log(
        admin_user_id=current_user["id"],
        action="create_admin",
        entity_type="app_user",
        entity_id=user["id"],
        before={},
        after=user,
    )
    return {"status": "success", "data": user}


@router.post("/users/{user_id}/promote-admin")
async def promote_admin(
    user_id: str,
    current_user: Dict[str, Any] = Depends(get_current_root_admin),
) -> Dict[str, Any]:
    repo = AuthRepository()
    before = repo.find_user_by_id(user_id) or {}
    if before.get("account_role") == "root_admin":
        raise HTTPException(status_code=400, detail="User is already root_admin")
    user = repo.set_user_account_role(user_id, "admin")
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    AdminAuditLogService(repo).log(
        admin_user_id=current_user["id"],
        action="promote_admin",
        entity_type="app_user",
        entity_id=user_id,
        before=before,
        after=user,
    )
    return {"status": "success", "data": repo._json_safe(user)}


@router.post("/users/{user_id}/demote-admin")
async def demote_admin(
    user_id: str,
    current_user: Dict[str, Any] = Depends(get_current_root_admin),
) -> Dict[str, Any]:
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Root admin cannot demote itself")
    repo = AuthRepository()
    before = repo.find_user_by_id(user_id) or {}
    if before.get("account_role") == "root_admin":
        raise HTTPException(status_code=400, detail="Cannot demote root_admin")
    user = repo.set_user_account_role(user_id, "user")
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    AdminAuditLogService(repo).log(
        admin_user_id=current_user["id"],
        action="demote_admin",
        entity_type="app_user",
        entity_id=user_id,
        before=before,
        after=user,
    )
    return {"status": "success", "data": repo._json_safe(user)}
