from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pymongo import ASCENDING
from repositories.auth_repo import AuthRepository
from repositories.pgpr_graph_repo import PGPRGraphRepository


class EmbeddingRepository:
    """Repository for embedding metadata/vector persistence."""

    def __init__(
        self,
        auth_repo: Optional[AuthRepository] = None,
        graph_repo: Optional[PGPRGraphRepository] = None,
    ) -> None:
        self.auth_repo = auth_repo or AuthRepository()
        self.graph_repo = graph_repo or PGPRGraphRepository()
        self.embedding_collection = self.auth_repo.db.entity_embeddings
        self.ensure_indexes()

    def ensure_indexes(self) -> None:
        try:
            self.embedding_collection.create_index(
                [("entity_type", ASCENDING), ("entity_id", ASCENDING), ("model", ASCENDING), ("version", ASCENDING)],
                unique=True,
            )
            self.embedding_collection.create_index([("entity_type", ASCENDING), ("status", ASCENDING)])
            self.embedding_collection.create_index([("source_hash", ASCENDING)], sparse=True)
        except Exception:
            pass

    def find_entity(self, entity_type: str, entity_id: str) -> Optional[Dict[str, Any]]:
        return self.auth_repo.find_entity_by_id(entity_type, entity_id)

    def update_embedding(
        self,
        entity_type: str,
        entity_id: str,
        embedding: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        payload = {
            "embedding": embedding,
            "embedding_status": embedding.get("status"),
            "updated_at": datetime.now(timezone.utc),
        }
        updated = self.auth_repo.update_entity_status(entity_type, entity_id, payload)
        if embedding.get("vector"):
            self.upsert_embedding_record(entity_type, entity_id, embedding)
        return updated

    def update_neo4j_embedding(
        self,
        entity_type: str,
        entity_id: str,
        embedding: Dict[str, Any],
    ) -> None:
        self.graph_repo.update_entity_embedding(entity_type, entity_id, embedding)

    def upsert_embedding_record(
        self,
        entity_type: str,
        entity_id: str,
        embedding: Dict[str, Any],
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        model = embedding.get("model") or "unknown"
        version = int(embedding.get("version") or 0)
        record = {
            "entity_type": str(entity_type).lower(),
            "entity_id": str(entity_id),
            "model": model,
            "version": version,
            "dimension": int(embedding.get("dimension") or 0),
            "vector": embedding.get("vector"),
            "normalized": bool(embedding.get("normalized", False)),
            "source_hash": embedding.get("source_hash"),
            "status": embedding.get("status"),
            "signal": embedding.get("signal"),
            "updated_at": now,
        }
        self.embedding_collection.update_one(
            {
                "entity_type": record["entity_type"],
                "entity_id": record["entity_id"],
                "model": model,
                "version": version,
            },
            {
                "$set": record,
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
        return self.get_embedding_record(entity_type, entity_id, model=model, version=version) or record

    def get_embedding_record(
        self,
        entity_type: str,
        entity_id: str,
        *,
        model: Optional[str] = None,
        version: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        query: Dict[str, Any] = {
            "entity_type": str(entity_type).lower(),
            "entity_id": str(entity_id),
        }
        if model is not None:
            query["model"] = model
        if version is not None:
            query["version"] = int(version)
        return self.embedding_collection.find_one(query, sort=[("version", -1), ("updated_at", -1)])

    def list_ready_embeddings(
        self,
        entity_type: str,
        *,
        model: Optional[str] = None,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {
            "entity_type": str(entity_type).lower(),
            "status": "ready",
            "vector": {"$type": "array"},
        }
        if model is not None:
            query["model"] = model
        rows = list(
            self.embedding_collection.find(query)
            .sort("updated_at", -1)
            .limit(max(1, min(limit, 5000)))
        )
        if rows:
            return rows
        return self._fallback_ready_embeddings_from_entities(entity_type, limit=limit)

    def sync_ready_embeddings_from_entities(self, entity_type: str, limit: int = 1000) -> int:
        count = 0
        for row in self._fallback_ready_embeddings_from_entities(entity_type, limit=limit):
            embedding = {
                "status": row.get("status"),
                "model": row.get("model"),
                "version": row.get("version"),
                "dimension": row.get("dimension"),
                "vector": row.get("vector"),
                "normalized": row.get("normalized"),
                "source_hash": row.get("source_hash"),
                "signal": row.get("signal"),
            }
            self.upsert_embedding_record(entity_type, str(row.get("entity_id")), embedding)
            count += 1
        return count

    def _fallback_ready_embeddings_from_entities(self, entity_type: str, limit: int = 500) -> List[Dict[str, Any]]:
        entity_type = str(entity_type).lower()
        collection = self.auth_repo.get_entity_collection(entity_type)
        if collection is None:
            return []
        id_field = self.auth_repo.entity_id_field(entity_type)
        cursor = (
            collection.find({"embedding.status": "ready", "embedding.vector": {"$type": "array"}})
            .sort("updated_at", -1)
            .limit(max(1, min(limit, 5000)))
        )
        rows: List[Dict[str, Any]] = []
        for doc in cursor:
            embedding = doc.get("embedding") or {}
            rows.append(
                {
                    "entity_type": entity_type,
                    "entity_id": str(doc.get(id_field) or doc.get("_id")),
                    "model": embedding.get("model"),
                    "version": int(embedding.get("version") or 0),
                    "dimension": int(embedding.get("dimension") or 0),
                    "vector": embedding.get("vector"),
                    "normalized": bool(embedding.get("normalized", False)),
                    "source_hash": embedding.get("source_hash"),
                    "status": embedding.get("status"),
                    "signal": embedding.get("signal"),
                    "updated_at": embedding.get("updated_at") or doc.get("updated_at"),
                }
            )
        return rows
