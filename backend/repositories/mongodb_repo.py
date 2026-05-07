from __future__ import annotations

from typing import Any, Dict, List, Optional

from pymongo import MongoClient


class MongoDBRepository:
    """
    Repository layer that encapsulates MongoDB access.
    Service layer should depend on this interface, not raw Mongo client.
    """

    def __init__(
        self,
        uri: str = "mongodb://localhost:27017",
        db_name: str = "rd_knowledge_graph",
    ) -> None:
        # Fail fast when MongoDB is not reachable (better dev experience).
        self.client = MongoClient(uri, serverSelectionTimeoutMS=2000)
        self.db = self.client[db_name]

    async def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        # Support common id field variants found in datasets.
        return self.db.projects.find_one(
            {"$or": [{"project_id": project_id}, {"proj_id": project_id}]}
        )

    async def get_expert(self, expert_id: str) -> Optional[Dict[str, Any]]:
        return self.db.experts.find_one({"expert_id": expert_id})

    async def search_projects(
        self,
        status: Optional[str] = None,
        location: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {}
        if status:
            query["status"] = status
        if location:
            query["location"] = location

        cursor = self.db.projects.find(query).limit(limit)
        return list(cursor)

