from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from bson import ObjectId
from dotenv import find_dotenv, load_dotenv
from pymongo import MongoClient

load_dotenv(find_dotenv())


ENTITY_COLLECTIONS = {
    "project": "projects",
    "projects": "projects",
    "expert": "experts",
    "experts": "experts",
    "funder": "funders",
    "funders": "funders",
    "enterprise": "enterprises",
    "enterprises": "enterprises",
}

ENTITY_ID_FIELDS = {
    "projects": ["project_id", "proj_id", "id"],
    "experts": ["expert_id", "id"],
    "funders": ["funder_id", "id"],
    "enterprises": ["enterprise_id", "id"],
}

ENTITY_NAME_FIELDS = {
    "projects": ["title", "name", "project_name", "basic_info.title", "basic_info.name"],
    "experts": ["name", "full_name", "expert_name", "basic_info.name"],
    "funders": ["name", "funder_name", "organization_name", "basic_info.name"],
    "enterprises": ["name", "enterprise_name", "company_name", "basic_info.name"],
}

ENTITY_SUMMARY_FIELDS = {
    "projects": ["summary", "description", "abstract", "objectives", "basic_info.description", "basic_info.abstract"],
    "experts": ["summary", "bio", "description", "affiliation", "academic_profile.current_affiliation.org_name"],
    "funders": ["summary", "description", "mission", "basic_info.type"],
    "enterprises": ["summary", "description", "business_description", "basic_info.description"],
}


class MongoDBRepository:
    """
    Repository layer that encapsulates MongoDB access.
    Service layer should depend on this interface, not raw Mongo client.
    """

    def __init__(
        self,
        uri: str | None = None,
        db_name: str | None = None,
    ) -> None:
        # Fail fast when MongoDB is not reachable (better dev experience).
        uri = uri or os.getenv("MONGO_URI", "mongodb://localhost:27017")
        db_name = db_name or os.getenv("MONGO_DB_NAME", "rd_knowledge_graph")
        self.client = MongoClient(uri, serverSelectionTimeoutMS=2000)
        self.db = self.client[db_name]

    def check_db_health(self) -> bool:
        self.client.admin.command("ping")
        return True

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

    async def list_entities(
        self,
        entity_type: str,
        search: Optional[str] = None,
        limit: int = 20,
        page: int = 1,
    ) -> List[Dict[str, Any]]:
        collection_name = self._collection_name(entity_type)
        collection = self.db[collection_name]
        query = self._build_search_query(collection_name, search)
        skip = max(page - 1, 0) * limit
        cursor = collection.find(query).skip(skip).limit(limit)
        return [
            self._normalize_entity(doc, collection_name)
            for doc in cursor
        ]

    async def count_entities(
        self,
        entity_type: str,
        search: Optional[str] = None,
    ) -> int:
        collection_name = self._collection_name(entity_type)
        query = self._build_search_query(collection_name, search)
        return int(self.db[collection_name].count_documents(query))

    async def get_entity(
        self,
        entity_type: str,
        entity_id: str,
    ) -> Optional[Dict[str, Any]]:
        collection_name = self._collection_name(entity_type)
        collection = self.db[collection_name]
        query = self._build_id_query(collection_name, entity_id)
        doc = collection.find_one(query)
        if doc is None:
            return None
        return self._normalize_entity(doc, collection_name, include_raw=True)

    def _collection_name(self, entity_type: str) -> str:
        key = (entity_type or "").strip().lower()
        if key not in ENTITY_COLLECTIONS:
            raise ValueError(f"Unsupported entity type: {entity_type}")
        return ENTITY_COLLECTIONS[key]

    def _build_id_query(self, collection_name: str, entity_id: str) -> Dict[str, Any]:
        clauses: List[Dict[str, Any]] = [
            {field: entity_id}
            for field in ENTITY_ID_FIELDS.get(collection_name, ["id"])
        ]
        if ObjectId.is_valid(entity_id):
            clauses.append({"_id": ObjectId(entity_id)})
        return {"$or": clauses}

    def _build_search_query(
        self,
        collection_name: str,
        search: Optional[str],
    ) -> Dict[str, Any]:
        if not search:
            return {}
        fields = (
            ENTITY_ID_FIELDS.get(collection_name, [])
            + ENTITY_NAME_FIELDS.get(collection_name, [])
            + ENTITY_SUMMARY_FIELDS.get(collection_name, [])
        )
        return {
            "$or": [
                {field: {"$regex": search, "$options": "i"}}
                for field in fields
            ]
        }

    def _normalize_entity(
        self,
        doc: Dict[str, Any],
        collection_name: str,
        include_raw: bool = False,
    ) -> Dict[str, Any]:
        data = self._json_safe(doc)
        entity_type = collection_name[:-1]
        entity_id = self._first_value(data, ENTITY_ID_FIELDS[collection_name]) or data.get("_id")
        name = self._first_value(data, ENTITY_NAME_FIELDS[collection_name]) or entity_id
        summary = self._first_value(data, ENTITY_SUMMARY_FIELDS[collection_name])
        normalized = {
            "id": str(entity_id or ""),
            "name": str(name or ""),
            "type": entity_type,
            "summary": summary or "",
            "metadata": self._extract_metadata(data, collection_name),
        }
        embedding_metadata = self._extract_embedding_metadata(data)
        if embedding_metadata:
            normalized["metadata"]["embedding"] = embedding_metadata
            normalized["metadata"]["embedding_status"] = embedding_metadata.get("status")
        if include_raw:
            normalized["raw"] = data
        return normalized

    def _extract_embedding_metadata(self, data: Dict[str, Any]) -> Dict[str, Any]:
        embedding = data.get("embedding")
        if not isinstance(embedding, dict):
            status = data.get("embedding_status")
            return {"status": status} if status else {}
        return {
            "status": embedding.get("status"),
            "job_id": embedding.get("job_id"),
            "last_event_id": embedding.get("last_event_id"),
            "retry_count": embedding.get("retry_count"),
            "max_retry": embedding.get("max_retry"),
            "model": embedding.get("model"),
            "version": embedding.get("version"),
            "dimension": embedding.get("dimension"),
            "source_hash": embedding.get("source_hash"),
            "last_queued_at": embedding.get("last_queued_at"),
            "last_processed_at": embedding.get("last_processed_at"),
            "updated_at": embedding.get("updated_at"),
            "error": embedding.get("error"),
            "error_type": embedding.get("error_type"),
            "normalized": embedding.get("normalized"),
            "signal": embedding.get("signal"),
        }

    def _extract_metadata(
        self,
        data: Dict[str, Any],
        collection_name: str,
    ) -> Dict[str, Any]:
        excluded = {
            "_id",
            *ENTITY_ID_FIELDS[collection_name],
            *ENTITY_NAME_FIELDS[collection_name],
            *ENTITY_SUMMARY_FIELDS[collection_name],
        }
        metadata: Dict[str, Any] = {}
        for key, value in data.items():
            if key in excluded or value in (None, "", [], {}):
                continue
            if key == "embedding":
                continue
            metadata[key] = value
            if len(metadata) >= 12:
                break
        return metadata

    def _first_value(
        self,
        data: Dict[str, Any],
        fields: List[str],
    ) -> Optional[Any]:
        for field in fields:
            value = self._get_path(data, field)
            if value not in (None, "", [], {}):
                return value
        return None

    def _get_path(self, data: Dict[str, Any], path: str) -> Any:
        current: Any = data
        for part in path.split("."):
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current

    def _json_safe(self, value: Any) -> Any:
        if isinstance(value, ObjectId):
            return str(value)
        if isinstance(value, list):
            return [self._json_safe(item) for item in value]
        if isinstance(value, dict):
            return {key: self._json_safe(item) for key, item in value.items()}
        return value
