from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pymongo import ASCENDING

from repositories.auth_repo import AuthRepository


class WorkerHeartbeatRepository:
    """Persist embedding worker liveness for admin monitoring."""

    def __init__(self, auth_repo: Optional[AuthRepository] = None) -> None:
        self.auth_repo = auth_repo or AuthRepository()
        self.collection = self.auth_repo.db.worker_heartbeats
        self.ensure_indexes()

    def ensure_indexes(self) -> None:
        try:
            self.collection.create_index([("worker_id", ASCENDING)], unique=True)
            self.collection.create_index([("last_seen_at", ASCENDING)])
        except Exception:
            pass

    WORKER_TYPE_EMBEDDING = "embedding_worker"

    def upsert_heartbeat(
        self,
        worker_id: str,
        *,
        worker_type: str = WORKER_TYPE_EMBEDDING,
        status: str = "running",
        current_job_id: Optional[str] = None,
        current_event_id: Optional[str] = None,
        processed_delta: int = 0,
        failed_delta: int = 0,
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        update: Dict[str, Any] = {
            "$set": {
                "worker_id": worker_id,
                "worker_type": worker_type,
                "status": status,
                "last_seen_at": now,
                "current_job_id": current_job_id,
                "current_event_id": current_event_id,
                "updated_at": now,
            },
            "$setOnInsert": {
                "started_at": now,
                "created_at": now,
            },
        }
        inc: Dict[str, int] = {}
        if processed_delta:
            inc["processed_count"] = processed_delta
        if failed_delta:
            inc["failed_count"] = failed_delta
        if inc:
            update["$inc"] = inc
        self.collection.update_one({"worker_id": worker_id}, update, upsert=True)
        return self.get(worker_id) or {}

    def get(self, worker_id: str) -> Optional[Dict[str, Any]]:
        return self.collection.find_one({"worker_id": worker_id})

    def list_workers(self, limit: int = 20) -> List[Dict[str, Any]]:
        cursor = self.collection.find({}).sort("last_seen_at", -1).limit(max(1, min(limit, 100)))
        return list(cursor)

    @staticmethod
    def stale_threshold_seconds() -> int:
        return int(os.getenv("WORKER_HEARTBEAT_STALE_SECONDS", "120"))

    def serialize_worker(self, row: Dict[str, Any]) -> Dict[str, Any]:
        last_seen = row.get("last_seen_at")
        stale_after = self.stale_threshold_seconds()
        liveness = "unknown"
        is_alive = False
        if isinstance(last_seen, datetime):
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - last_seen).total_seconds()
            is_alive = age <= stale_after
            liveness = "alive" if is_alive else "stale"
        return {
            "worker_id": row.get("worker_id"),
            "worker_type": row.get("worker_type") or self.WORKER_TYPE_EMBEDDING,
            "status": row.get("status"),
            "liveness": liveness,
            "last_seen_at": last_seen,
            "started_at": row.get("started_at"),
            "updated_at": row.get("updated_at"),
            "processed_count": int(row.get("processed_count") or 0),
            "failed_count": int(row.get("failed_count") or 0),
            "current_job_id": row.get("current_job_id"),
            "current_event_id": row.get("current_event_id"),
            "is_alive": is_alive,
            "stale_after_seconds": stale_after,
        }
