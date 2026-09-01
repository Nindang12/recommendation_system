from __future__ import annotations

from typing import Any, Dict, Optional

from repositories.mongodb_repo import MongoDBRepository


class EntityService:
    """
    Business layer for browsing source/target entities.
    Routers should call this service instead of talking to MongoDB directly.
    """

    def __init__(self, mongo_repo: Optional[MongoDBRepository] = None) -> None:
        self.mongo_repo = mongo_repo or MongoDBRepository()

    async def list_entities(
        self,
        entity_type: str,
        search: Optional[str] = None,
        limit: int = 20,
        page: int = 1,
    ) -> Dict[str, Any]:
        data = await self.mongo_repo.list_entities(
            entity_type=entity_type,
            search=search,
            limit=limit,
            page=page,
        )
        total = await self.mongo_repo.count_entities(
            entity_type=entity_type,
            search=search,
        )
        return {
            "status": "success",
            "data": data,
            "count": len(data),
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
            },
        }

    async def get_entity(
        self,
        entity_type: str,
        entity_id: str,
    ) -> Optional[Dict[str, Any]]:
        return await self.mongo_repo.get_entity(
            entity_type=entity_type,
            entity_id=entity_id,
        )

