from __future__ import annotations

import os
from typing import Any, Dict, Optional

from infrastructure.rabbitmq_client import RabbitMQPublishResult
from models.events import EmbeddingEventType, EmbeddingEvent
from repositories.auth_repo import AuthRepository
from repositories.embedding_outbox_repo import EmbeddingOutboxRepository
from services.event_publisher_service import EventPublisherService


class OutboxPublisherService:
    """Reliable outbox wrapper around RabbitMQ embedding event publishing."""

    def __init__(
        self,
        repo: Optional[AuthRepository] = None,
        outbox_repo: Optional[EmbeddingOutboxRepository] = None,
        publisher: Optional[EventPublisherService] = None,
    ) -> None:
        self.repo = repo or AuthRepository()
        self.outbox = outbox_repo or EmbeddingOutboxRepository(self.repo)
        self.publisher = publisher or EventPublisherService(self.repo)
        self.backoff_seconds = self._backoff_seconds()

    def enqueue_embedding_event(
        self,
        entity_type: str,
        entity_id: str,
        *,
        event_type: EmbeddingEventType,
        source: str,
        try_publish_now: bool = True,
    ) -> RabbitMQPublishResult:
        event, error_result, entity, embedding = self.publisher.build_embedding_event(
            entity_type,
            entity_id,
            event_type=event_type,
            source=source,
        )
        if error_result is not None:
            return error_result
        if event is None:
            return RabbitMQPublishResult(ok=False, status="event_not_created", error=f"{entity_type}/{entity_id}")

        record = self.outbox.create_event(event.model_dump(mode="json"), max_retry=self._max_retry())
        if not try_publish_now:
            return RabbitMQPublishResult(ok=True, status="outbox_pending")
        return self.publish_record(record, entity=entity, embedding=embedding)

    def publish_pending(self, limit: int = 50) -> Dict[str, Any]:
        rows = self.outbox.list_publishable(limit=limit)
        summary = {"total": len(rows), "published": 0, "pending": 0, "failed": 0, "results": []}
        for row in rows:
            try:
                result = self.publish_record(row)
            except Exception as exc:  # noqa: BLE001
                event_id = str(row.get("event_id") or "")
                if event_id:
                    self.outbox.mark_publish_failed(
                        event_id,
                        str(exc),
                        backoff_seconds=self._backoff_for_retry(int(row.get("retry_count") or 0)),
                    )
                result = RabbitMQPublishResult(ok=False, status="validation_error", error=str(exc))
            if result.ok:
                summary["published"] += 1
            elif (self.outbox.get_by_event_id(row["event_id"]) or {}).get("status") == self.outbox.STATUS_FAILED:
                summary["failed"] += 1
            else:
                summary["pending"] += 1
            summary["results"].append({"event_id": row["event_id"], "status": result.status, "ok": result.ok, "error": result.error})
        return summary

    def publish_record(
        self,
        record: Dict[str, Any],
        *,
        entity: Optional[Dict[str, Any]] = None,
        embedding: Optional[Dict[str, Any]] = None,
    ) -> RabbitMQPublishResult:
        event = EmbeddingEvent.model_validate(record["payload"])
        result = self.publisher.publish_prepared_embedding_event(event, entity=entity, embedding=embedding)
        if result.ok:
            self.outbox.mark_published(event.event_id)
            return result
        self.outbox.mark_publish_failed(
            event.event_id,
            result.error or result.status,
            backoff_seconds=self._backoff_for_retry(int(record.get("retry_count") or 0)),
        )
        return result

    def _backoff_for_retry(self, retry_count: int) -> int:
        if not self.backoff_seconds:
            return 30
        index = max(0, min(retry_count, len(self.backoff_seconds) - 1))
        return self.backoff_seconds[index]

    @staticmethod
    def _backoff_seconds() -> list[int]:
        raw = os.getenv("EMBEDDING_RETRY_BACKOFF_SECONDS", "30,120,600")
        out: list[int] = []
        for item in raw.split(","):
            try:
                out.append(max(1, int(item.strip())))
            except ValueError:
                continue
        return out or [30, 120, 600]

    @staticmethod
    def _max_retry() -> int:
        try:
            return max(1, int(os.getenv("EMBEDDING_MAX_RETRY", "3")))
        except ValueError:
            return 3
