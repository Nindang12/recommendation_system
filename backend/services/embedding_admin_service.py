"""Admin and user operations for the embedding pipeline."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from infrastructure.rabbitmq_client import RabbitMQClient, RabbitMQPublishResult
from models.events import EmbeddingEventType
from repositories.auth_repo import AuthRepository
from repositories.embedding_outbox_repo import EmbeddingOutboxRepository
from repositories.worker_heartbeat_repo import WorkerHeartbeatRepository
from services import provisional_status as st
from services.admin_audit_log_service import AdminAuditLogService
from services.embedding_metadata_service import EmbeddingMetadataService
from services.outbox_publisher_service import OutboxPublisherService

ENTITY_TYPES = ("expert", "enterprise", "funder", "project")


class EmbeddingAdminService:
    RECOMPUTE_COOLDOWN_SECONDS = int(os.getenv("EMBEDDING_RECOMPUTE_COOLDOWN_SECONDS", "300"))

    def __init__(
        self,
        repo: Optional[AuthRepository] = None,
        outbox: Optional[EmbeddingOutboxRepository] = None,
        publisher: Optional[OutboxPublisherService] = None,
        audit: Optional[AdminAuditLogService] = None,
    ) -> None:
        self.repo = repo or AuthRepository()
        self.outbox = outbox or EmbeddingOutboxRepository(self.repo)
        self.publisher = publisher or OutboxPublisherService(self.repo, self.outbox)
        self.audit = audit or AdminAuditLogService(self.repo)
        self.rabbitmq = RabbitMQClient()
        self.heartbeats = WorkerHeartbeatRepository(self.repo)

    def get_embedding_status(
        self,
        entity_type: str,
        entity_id: str,
        *,
        actor_user_id: Optional[str] = None,
        is_admin: bool = False,
    ) -> Dict[str, Any]:
        entity_type = str(entity_type).lower()
        entity = self.repo.find_entity_by_id(entity_type, entity_id)
        if not entity:
            raise ValueError("Entity not found")
        if actor_user_id and not is_admin:
            self._assert_user_owns_entity(actor_user_id, entity_type, entity, entity_id)
        embedding = entity.get("embedding") or {}
        return {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "embedding_status": embedding.get("status") or entity.get("embedding_status") or st.EMBEDDING_PENDING,
            "embedding": self._public_embedding_metadata(embedding),
            "kg_sync_status": entity.get("kg_sync_status"),
            "entity_verification_status": entity.get("entity_verification_status"),
            "recommendation_mode": self._recommendation_mode(embedding),
            "can_recompute": self._can_recompute_now(embedding),
            "next_recompute_at": self._next_recompute_at(embedding),
        }

    def list_jobs(
        self,
        *,
        status: Optional[str] = None,
        entity_type: Optional[str] = None,
        limit: int = 50,
        page: int = 1,
    ) -> Dict[str, Any]:
        rows = self.outbox.list_jobs(status=status, entity_type=entity_type, limit=limit, page=page)
        return {
            "jobs": [self._serialize_job(row) for row in rows],
            "count": len(rows),
            "outbox_counts": self.outbox.counts(),
        }

    def pipeline_status(self) -> Dict[str, Any]:
        queue_report = self._queue_lengths()
        dlq_name = self.rabbitmq.dlq
        dlq_info = queue_report.get(dlq_name) if isinstance(queue_report, dict) else {}
        dlq_count = int(dlq_info.get("messages", 0) or 0) if isinstance(dlq_info, dict) else 0
        workers = [self.heartbeats.serialize_worker(row) for row in self.heartbeats.list_workers(limit=20)]
        any_alive = any(row.get("liveness") == "alive" for row in workers)
        alive_count = sum(1 for row in workers if row.get("liveness") == "alive")
        stale_count = sum(1 for row in workers if row.get("liveness") == "stale")
        return {
            "model": "graphsage_lite_v1",
            "embedding_dimension": st.EMBEDDING_DIMENSION,
            "rabbitmq": self.rabbitmq.health(),
            "queues": queue_report,
            "outbox": self.outbox.counts(),
            "entity_embedding_status": self._entity_embedding_status_counts(),
            "worker_heartbeats": workers,
            "worker_summary": {
                "count": len(workers),
                "any_alive": any_alive,
                "alive_count": alive_count,
                "stale_count": stale_count,
                "stale_after_seconds": self.heartbeats.stale_threshold_seconds(),
            },
            "dlq": {
                "queue": dlq_name,
                "messages": dlq_count,
                "alert": dlq_count > 0,
                "sample": self.rabbitmq.peek_dlq_sample() if dlq_count > 0 else {"available": False},
            },
        }

    def recompute_entity(
        self,
        entity_type: str,
        entity_id: str,
        *,
        actor_user_id: str,
        is_admin: bool = False,
        reason: str = "",
        source: str = "api.recompute",
    ) -> Dict[str, Any]:
        entity_type = str(entity_type).lower()
        if entity_type not in ENTITY_TYPES:
            raise ValueError(f"Unsupported entity type: {entity_type}")

        entity = self.repo.find_entity_by_id(entity_type, entity_id)
        if not entity:
            raise ValueError("Entity not found")

        if not is_admin:
            self._assert_user_owns_entity(actor_user_id, entity_type, entity, entity_id)

        embedding = dict(entity.get("embedding") or EmbeddingMetadataService.default_embedding(entity_type, entity))
        self._assert_recompute_allowed(embedding, is_admin=is_admin)

        before = self.repo.find_entity_by_id(entity_type, entity_id) or {}
        now = datetime.now(timezone.utc)
        refreshed = EmbeddingMetadataService.refresh_after_source_change(entity_type, {**entity, "embedding": embedding}, now=now)
        if refreshed.get("status") != st.EMBEDDING_STALE:
            refreshed = {**refreshed, "status": st.EMBEDDING_STALE, "updated_at": now}

        self.repo.update_entity_status(
            entity_type,
            entity_id,
            {"embedding": refreshed, "embedding_status": st.EMBEDDING_STALE},
        )

        result = self.publisher.enqueue_embedding_event(
            entity_type,
            entity_id,
            event_type="kg.embedding.recompute",  # type: ignore[arg-type]
            source=source,
        )
        after = self.repo.find_entity_by_id(entity_type, entity_id) or {}

        audit_reason = self._normalize_recompute_reason(reason, is_admin=is_admin, source=source)
        action = "embedding_recompute" if is_admin else "embedding_recompute_user"
        self.audit.log(
            admin_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before=self._audit_snapshot(before),
            after=self._audit_snapshot(after),
            reason=audit_reason,
        )

        return {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "publish": {
                "ok": result.ok,
                "status": result.status,
                "error": result.error,
            },
            "embedding_status": after.get("embedding_status"),
            "embedding": self._public_embedding_metadata(after.get("embedding") or {}),
        }

    def retry_failed_jobs(
        self,
        *,
        admin_user_id: str,
        limit: int = 50,
        reason: str = "",
        entity_type: Optional[str] = None,
        error_type: Optional[str] = None,
        include_permanent: bool = False,
    ) -> Dict[str, Any]:
        if include_permanent and not str(reason or "").strip():
            raise ValueError("reason is required when include_permanent=true")
        if error_type is None and not include_permanent:
            error_type = st.EMBEDDING_ERROR_TEMPORARY

        failed_rows = self.outbox.list_failed(
            limit=limit,
            entity_type=entity_type,
            error_type=error_type,
        )
        skipped: List[Dict[str, Any]] = []
        retried: List[Dict[str, Any]] = []
        for row in failed_rows:
            if len(retried) >= limit:
                break
            event_id = str(row.get("event_id") or "")
            row_error_type = row.get("error_type") or "temporary"
            if not include_permanent and row_error_type in {
                st.EMBEDDING_ERROR_VALIDATION,
                st.EMBEDDING_ERROR_PERMANENT,
                "validation",
                "permanent",
            }:
                skipped.append(
                    {
                        "event_id": event_id,
                        "error_type": row_error_type,
                        "reason": "skipped_non_retryable_error_type",
                    }
                )
                continue
            if not event_id:
                continue
            reset = self.outbox.reset_for_retry(event_id)
            if reset:
                retried.append(
                    {
                        "event_id": event_id,
                        "entity_type": reset.get("entity_type"),
                        "entity_id": reset.get("entity_id"),
                        "error_type": row_error_type,
                    }
                )

        publish_summary = {"total": 0, "published": 0, "pending": 0, "failed": 0, "results": []}
        for item in retried:
            event_id = str(item.get("event_id") or "")
            record = self.outbox.get_by_event_id(event_id) if event_id else None
            if not record:
                continue
            publish_summary["total"] += 1
            try:
                result = self.publisher.publish_record(record)
            except Exception as exc:  # noqa: BLE001
                result = RabbitMQPublishResult(ok=False, status="validation_error", error=str(exc))
            if result.ok:
                publish_summary["published"] += 1
            elif (self.outbox.get_by_event_id(event_id) or {}).get("status") == self.outbox.STATUS_FAILED:
                publish_summary["failed"] += 1
            else:
                publish_summary["pending"] += 1
            publish_summary["results"].append(
                {"event_id": event_id, "status": result.status, "ok": result.ok, "error": result.error}
            )

        audit_reason = str(reason or "").strip() or "admin_retry_failed_batch"
        if entity_type:
            audit_reason = f"{audit_reason}; entity_type={entity_type}"
        if error_type:
            audit_reason = f"{audit_reason}; error_type={error_type}"

        self.audit.log(
            admin_user_id=admin_user_id,
            action="embedding_retry_failed",
            entity_type="system",
            entity_id="embedding_pipeline",
            before={"failed_count": len(failed_rows), "filters": {"entity_type": entity_type, "error_type": error_type}},
            after={"retried": len(retried), "skipped": len(skipped), "publish": publish_summary},
            reason=audit_reason,
        )

        return {
            "retried_count": len(retried),
            "skipped_count": len(skipped),
            "retried": retried,
            "skipped": skipped,
            "filters": {
                "entity_type": entity_type,
                "error_type": error_type,
                "include_permanent": include_permanent,
                "limit": limit,
            },
            "publish": publish_summary,
            "outbox_counts": self.outbox.counts(),
        }

    @staticmethod
    def _normalize_recompute_reason(reason: str, *, is_admin: bool, source: str) -> str:
        cleaned = str(reason or "").strip()
        if cleaned:
            return cleaned
        if is_admin:
            return "admin_requested_recompute"
        return "user_requested_recompute"

    def _assert_user_owns_entity(
        self,
        user_id: str,
        entity_type: str,
        entity: Dict[str, Any],
        entity_id: str,
    ) -> None:
        user = self.repo.find_user_by_id(user_id)
        if not user:
            raise PermissionError("User not found")
        linked = user.get("linked_entity") or {}
        if str(linked.get("type") or "").lower() == entity_type and str(linked.get("id") or "") == entity_id:
            return
        if entity_type == "project":
            owner_id = str(entity.get("owner_id") or entity.get("owner_user_id") or "")
            if owner_id and owner_id == str(user_id):
                return
        raise PermissionError("You can only recompute embeddings for your own linked entity or owned project")

    def _assert_recompute_allowed(self, embedding: Dict[str, Any], *, is_admin: bool) -> None:
        if not is_admin and not self._can_recompute_now(embedding):
            next_at = self._next_recompute_at(embedding)
            raise ValueError(f"Rate limit: try again after {next_at}")

    def _can_recompute_now(self, embedding: Dict[str, Any]) -> bool:
        last_queued = embedding.get("last_queued_at")
        if not last_queued:
            return True
        if isinstance(last_queued, str):
            try:
                last_queued = datetime.fromisoformat(last_queued.replace("Z", "+00:00"))
            except ValueError:
                return True
        if last_queued.tzinfo is None:
            last_queued = last_queued.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) >= last_queued + timedelta(seconds=self.RECOMPUTE_COOLDOWN_SECONDS)

    def _next_recompute_at(self, embedding: Dict[str, Any]) -> Optional[str]:
        last_queued = embedding.get("last_queued_at")
        if not last_queued:
            return None
        if isinstance(last_queued, str):
            try:
                last_queued = datetime.fromisoformat(last_queued.replace("Z", "+00:00"))
            except ValueError:
                return None
        if last_queued.tzinfo is None:
            last_queued = last_queued.replace(tzinfo=timezone.utc)
        next_at = last_queued + timedelta(seconds=self.RECOMPUTE_COOLDOWN_SECONDS)
        if datetime.now(timezone.utc) >= next_at:
            return None
        return next_at.isoformat()

    def _entity_embedding_status_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for entity_type in ENTITY_TYPES:
            collection = self.repo.get_entity_collection(entity_type)
            if collection is None:
                continue
            pipeline = [
                {
                    "$group": {
                        "_id": {
                            "$ifNull": ["$embedding.status", {"$ifNull": ["$embedding_status", "pending"]}]
                        },
                        "count": {"$sum": 1},
                    }
                }
            ]
            for row in collection.aggregate(pipeline):
                key = str(row.get("_id") or "unknown")
                counts[key] = counts.get(key, 0) + int(row.get("count") or 0)
        return counts

    def _queue_lengths(self) -> Dict[str, Any]:
        try:
            connection = self.rabbitmq._connect()
            try:
                channel = connection.channel()
                self.rabbitmq._declare(channel)
                report: Dict[str, Any] = {}
                for queue in (self.rabbitmq.queue, self.rabbitmq.dlq):
                    state = channel.queue_declare(queue=queue, durable=True, passive=True)
                    report[queue] = {
                        "messages": int(state.method.message_count),
                        "consumers": int(state.method.consumer_count),
                    }
                return report
            finally:
                connection.close()
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

    @staticmethod
    def _public_embedding_metadata(embedding: Dict[str, Any]) -> Dict[str, Any]:
        if not embedding:
            return {}
        return {
            "status": embedding.get("status"),
            "job_id": embedding.get("job_id"),
            "last_event_id": embedding.get("last_event_id"),
            "model": embedding.get("model"),
            "version": embedding.get("version"),
            "dimension": embedding.get("dimension"),
            "source_hash": embedding.get("source_hash"),
            "signal": embedding.get("signal"),
            "normalized": embedding.get("normalized"),
            "retry_count": embedding.get("retry_count"),
            "error": embedding.get("error"),
            "error_type": embedding.get("error_type"),
            "last_queued_at": embedding.get("last_queued_at"),
            "last_processed_at": embedding.get("last_processed_at"),
            "updated_at": embedding.get("updated_at"),
        }

    @staticmethod
    def _recommendation_mode(embedding: Dict[str, Any]) -> str:
        status = str(embedding.get("status") or st.EMBEDDING_PENDING)
        if status == st.EMBEDDING_STALE:
            return "fallback_until_embedding_recomputed"
        vector = embedding.get("vector")
        ready = (
            status == st.EMBEDDING_READY
            and embedding.get("signal") != st.EMBEDDING_SIGNAL_NONE
            and bool(embedding.get("normalized"))
            and isinstance(vector, list)
            and len(vector) == st.EMBEDDING_DIMENSION
        )
        return "hybrid_ready" if ready else "fallback_until_embedding_ready"

    @staticmethod
    def _serialize_job(row: Dict[str, Any]) -> Dict[str, Any]:
        payload = row.get("payload") or {}
        return {
            "event_id": row.get("event_id"),
            "job_id": row.get("job_id"),
            "entity_type": row.get("entity_type"),
            "entity_id": row.get("entity_id"),
            "event_type": row.get("event_type") or payload.get("event_type"),
            "status": row.get("status"),
            "retry_count": row.get("retry_count"),
            "max_retry": row.get("max_retry"),
            "last_error": row.get("last_error"),
            "error_type": row.get("error_type"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
            "next_attempt_at": row.get("next_attempt_at"),
            "published_at": row.get("published_at"),
        }

    @staticmethod
    def _audit_snapshot(entity: Dict[str, Any]) -> Dict[str, Any]:
        embedding = entity.get("embedding") or {}
        return {
            "embedding_status": embedding.get("status") or entity.get("embedding_status"),
            "job_id": embedding.get("job_id"),
            "last_event_id": embedding.get("last_event_id"),
            "kg_sync_status": entity.get("kg_sync_status"),
        }
