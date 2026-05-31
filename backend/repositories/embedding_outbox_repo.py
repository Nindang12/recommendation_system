from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from pymongo import ASCENDING

from repositories.auth_repo import AuthRepository


def classify_outbox_error(error: Optional[str]) -> str:
    text = str(error or "").lower()
    if not text:
        return "temporary"
    if any(token in text for token in ("validation", "invalid", "malformed", "parse", "schema")):
        return "validation"
    if any(token in text for token in ("permanent", "obsolete", "not found", "rejected", "kg not ready")):
        return "permanent"
    return "temporary"


class EmbeddingOutboxRepository:
    """MongoDB outbox for reliable embedding event publishing."""

    STATUS_PENDING = "pending"
    STATUS_PUBLISHED = "published"
    STATUS_FAILED = "failed"

    def __init__(self, auth_repo: Optional[AuthRepository] = None) -> None:
        self.auth_repo = auth_repo or AuthRepository()
        self.collection = self.auth_repo.db.embedding_event_outbox
        self.ensure_indexes()

    def ensure_indexes(self) -> None:
        try:
            self.collection.create_index([("event_id", ASCENDING)], unique=True)
            self.collection.create_index([("status", ASCENDING), ("next_attempt_at", ASCENDING)])
            self.collection.create_index([("entity_type", ASCENDING), ("entity_id", ASCENDING)])
        except Exception:
            pass

    def create_event(self, event_payload: Dict[str, Any], *, max_retry: int = 3) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        payload = {
            "event_id": event_payload["event_id"],
            "job_id": event_payload["job_id"],
            "entity_type": event_payload["entity_type"],
            "entity_id": event_payload["entity_id"],
            "event_type": event_payload["event_type"],
            "payload": event_payload,
            "status": self.STATUS_PENDING,
            "retry_count": 0,
            "max_retry": max_retry,
            "last_error": None,
            "error_type": None,
            "created_at": now,
            "updated_at": now,
            "next_attempt_at": now,
            "published_at": None,
        }
        result = self.collection.insert_one(payload)
        payload["_id"] = result.inserted_id
        return payload

    def get_by_event_id(self, event_id: str) -> Optional[Dict[str, Any]]:
        return self.collection.find_one({"event_id": event_id})

    def list_publishable(self, limit: int = 50) -> List[Dict[str, Any]]:
        now = datetime.now(timezone.utc)
        cursor = (
            self.collection.find(
                {
                    "status": self.STATUS_PENDING,
                    "next_attempt_at": {"$lte": now},
                }
            )
            .sort("created_at", ASCENDING)
            .limit(limit)
        )
        return list(cursor)

    def mark_published(self, event_id: str) -> Optional[Dict[str, Any]]:
        now = datetime.now(timezone.utc)
        self.collection.update_one(
            {"event_id": event_id},
            {
                "$set": {
                    "status": self.STATUS_PUBLISHED,
                    "published_at": now,
                    "updated_at": now,
                    "last_error": None,
                }
            },
        )
        return self.get_by_event_id(event_id)

    def mark_publish_failed(
        self,
        event_id: str,
        error: str,
        *,
        backoff_seconds: int,
    ) -> Optional[Dict[str, Any]]:
        current = self.get_by_event_id(event_id)
        if not current:
            return None
        now = datetime.now(timezone.utc)
        retry_count = int(current.get("retry_count") or 0) + 1
        max_retry = int(current.get("max_retry") or 3)
        status = self.STATUS_FAILED if retry_count >= max_retry else self.STATUS_PENDING
        error_type = classify_outbox_error(error)
        self.collection.update_one(
            {"event_id": event_id},
            {
                "$set": {
                    "status": status,
                    "retry_count": retry_count,
                    "last_error": error,
                    "error_type": error_type,
                    "updated_at": now,
                    "next_attempt_at": now + timedelta(seconds=backoff_seconds),
                }
            },
        )
        return self.get_by_event_id(event_id)

    def counts(self) -> Dict[str, int]:
        return {
            "pending": int(self.collection.count_documents({"status": self.STATUS_PENDING})),
            "published": int(self.collection.count_documents({"status": self.STATUS_PUBLISHED})),
            "failed": int(self.collection.count_documents({"status": self.STATUS_FAILED})),
        }

    def list_jobs(
        self,
        *,
        status: Optional[str] = None,
        entity_type: Optional[str] = None,
        limit: int = 50,
        page: int = 1,
    ) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {}
        if status:
            query["status"] = status
        if entity_type:
            query["entity_type"] = str(entity_type).lower()
        skip = max(page - 1, 0) * limit
        cursor = (
            self.collection.find(query)
            .sort("updated_at", -1)
            .skip(skip)
            .limit(max(1, min(limit, 200)))
        )
        return list(cursor)

    def list_failed(
        self,
        limit: int = 100,
        *,
        entity_type: Optional[str] = None,
        error_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {"status": self.STATUS_FAILED}
        if entity_type:
            query["entity_type"] = str(entity_type).lower()
        if error_type:
            query["error_type"] = error_type
        cursor = (
            self.collection.find(query)
            .sort("updated_at", -1)
            .limit(max(1, min(limit, 200)))
        )
        return list(cursor)

    def reset_for_retry(self, event_id: str) -> Optional[Dict[str, Any]]:
        now = datetime.now(timezone.utc)
        self.collection.update_one(
            {"event_id": event_id},
            {
                "$set": {
                    "status": self.STATUS_PENDING,
                    "retry_count": 0,
                    "last_error": None,
                    "error_type": None,
                    "next_attempt_at": now,
                    "updated_at": now,
                }
            },
        )
        return self.get_by_event_id(event_id)
