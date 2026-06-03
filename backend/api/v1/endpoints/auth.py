from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_auth_service, get_current_user, rate_limit
from models.schemas import (
    AuthResponse,
    LoginRequest,
    MyProjectsResponse,
    ProfileUpdateRequest,
    ProjectCreateRequest,
    RegisterRequest,
)
from services.auth_service import AuthService

router = APIRouter()


@router.post("/auth/register", response_model=AuthResponse)
async def register(
    payload: RegisterRequest,
    _: None = Depends(rate_limit("auth_register", limit=5, window_seconds=60)),
    service: AuthService = Depends(get_auth_service),
) -> Dict[str, Any]:
    try:
        data = service.register(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="MongoDB is unavailable") from exc
    return {"status": "success", "data": data}


@router.post("/auth/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    _: None = Depends(rate_limit("auth_login", limit=10, window_seconds=60)),
    service: AuthService = Depends(get_auth_service),
) -> Dict[str, Any]:
    try:
        data = service.login(payload.email, payload.password)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="MongoDB is unavailable") from exc
    return {"status": "success", "data": data}


@router.post("/auth/logout")
async def logout() -> Dict[str, str]:
    # Stateless token logout: frontend removes token.
    return {"status": "success"}


@router.get("/users/me")
async def me(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    return {"status": "success", "data": current_user}


@router.put("/users/me")
async def update_me(
    payload: ProfileUpdateRequest,
    _: None = Depends(rate_limit("profile_update", limit=30, window_seconds=60)),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> Dict[str, Any]:
    try:
        user = service.update_profile(current_user["id"], payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "success", "data": user}


@router.post("/users/me/projects")
async def create_my_project(
    payload: ProjectCreateRequest,
    _: None = Depends(rate_limit("project_create", limit=10, window_seconds=60)),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> Dict[str, Any]:
    project = service.create_project(current_user["id"], payload.model_dump())
    return {"status": "success", "data": project}


@router.get("/users/me/projects", response_model=MyProjectsResponse)
async def list_my_projects(
    limit: int = Query(default=50, ge=1, le=100),
    page: int = Query(default=1, ge=1),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> Dict[str, Any]:
    data = service.list_my_projects(current_user["id"], limit=limit, page=page)
    return {"status": "success", **data}


@router.delete("/users/me/projects/{project_id}")
async def delete_my_project(
    project_id: str,
    _: None = Depends(rate_limit("project_delete", limit=20, window_seconds=60)),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> Dict[str, Any]:
    try:
        project = service.delete_project(current_user["id"], project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "success", "data": project}
