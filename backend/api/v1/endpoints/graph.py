import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_optional_current_user
from api.deps import get_graph_service
from models.schemas import GraphNeighborsResponse, GraphPathsResponse
from services.graph_service import GraphService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get(
    "/paths",
    response_model=GraphPathsResponse,
    summary="Reasoning paths between two entities (Cypher via PGPRGraphRepository)",
)
async def get_graph_paths(
    source_type: str = Query(..., description="project | expert | funder | enterprise"),
    source_id: str = Query(...),
    target_type: str = Query(...),
    target_id: str = Query(...),
    max_length: int | None = Query(None, ge=1, le=12),
    limit: int = Query(10, ge=1, le=50),
    mode: str = Query("public", pattern="^(public|personal|admin_debug)$"),
    current_user: dict | None = Depends(get_optional_current_user),
    service: GraphService = Depends(get_graph_service),
) -> GraphPathsResponse:
    try:
        paths = await service.get_reasoning_paths(
            source_type=source_type,
            source_id=source_id,
            target_type=target_type,
            target_id=target_id,
            max_length=max_length,
            limit=limit,
            mode=mode,
            current_user_id=(current_user or {}).get("id"),
        )
        return GraphPathsResponse(status="success", data=paths, count=len(paths))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("get_graph_paths failed")
        raise HTTPException(status_code=500, detail="Internal error") from exc


@router.get(
    "/entities/{entity_type}/{entity_id}/neighbors",
    response_model=GraphNeighborsResponse,
    summary="Neighbor graph around one entity for visualization",
)
async def get_entity_neighbors(
    entity_type: str,
    entity_id: str,
    depth: int = Query(1, ge=1, le=3),
    limit: int = Query(80, ge=1, le=200),
    mode: str = Query("public", pattern="^(public|personal|admin_debug)$"),
    current_user: dict | None = Depends(get_optional_current_user),
    service: GraphService = Depends(get_graph_service),
) -> GraphNeighborsResponse:
    try:
        graph = await service.get_entity_neighbors(
            entity_type=entity_type,
            entity_id=entity_id,
            depth=depth,
            limit=limit,
            mode=mode,
            current_user_id=(current_user or {}).get("id"),
        )
        node_count = len(graph.get("nodes") or [])
        return GraphNeighborsResponse(status="success", data=graph, count=node_count)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("get_entity_neighbors failed")
        raise HTTPException(status_code=500, detail="Internal error") from exc
