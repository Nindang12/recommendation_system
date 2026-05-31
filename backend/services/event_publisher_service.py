from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from infrastructure.rabbitmq_client import RabbitMQClient, RabbitMQPublishResult
from models.events import EmbeddingEvent, EmbeddingEventType
from repositories.auth_repo import AuthRepository
from services import provisional_status as st
from services.embedding_metadata_service import EmbeddingMetadataService

logger = logging.getLogger(__name__)


class EventPublisherService:
    """Publish embedding jobs after an entity is already present in Neo4j."""

    PUBLISHABLE_KG_STATUSES = {
        st.KG_SYNCED_UNVERIFIED,
        st.KG_SYNCED_VERIFIED,
    }

    def __init__(
        self,
        repo: Optional[AuthRepository] = None,
        rabbitmq: Optional[RabbitMQClient] = None,
    ) -> None:
        self.repo = repo or AuthRepository()
        self.rabbitmq = rabbitmq or RabbitMQClient()

    def build_embedding_event(
        self,
        entity_type: str,
        entity_id: str,
        *,
        event_type: EmbeddingEventType,
        source: str,
    ) -> tuple[Optional[EmbeddingEvent], Optional[RabbitMQPublishResult], Dict[str, Any], Dict[str, Any]]:
        entity_type = str(entity_type).lower()
        entity = self.repo.find_entity_by_id(entity_type, entity_id)
        if not entity:
            return None, RabbitMQPublishResult(ok=False, status="entity_not_found", error=f"{entity_type}/{entity_id}"), {}, {}

        kg_sync_status = str(entity.get("kg_sync_status") or st.KG_NOT_SYNCED)
        if kg_sync_status not in self.PUBLISHABLE_KG_STATUSES:
            return None, RabbitMQPublishResult(ok=False, status="kg_not_ready", error=kg_sync_status), entity, {}

        now = datetime.now(timezone.utc)
        embedding = dict(entity.get("embedding") or EmbeddingMetadataService.default_embedding(entity_type, entity, now=now))
        source_hash = EmbeddingMetadataService.compute_source_hash(entity_type, entity)
        if embedding.get("source_hash") != source_hash:
            embedding = EmbeddingMetadataService.refresh_after_source_change(entity_type, {**entity, "embedding": embedding}, now=now)

        event = EmbeddingEvent(
            event_id=f"evt_{uuid4().hex}",
            job_id=f"job_{uuid4().hex}",
            event_type=event_type,
            entity_type=entity_type,  # type: ignore[arg-type]
            entity_id=entity_id,
            user_id=entity.get("user_id") or entity.get("owner_user_id") or entity.get("owner_id"),
            source=source,
            kg_sync_status=kg_sync_status,
            entity_verification_status=str(entity.get("entity_verification_status") or st.ENTITY_UNVERIFIED),
            embedding_version=int(embedding.get("version") or 0),
            embedding_source_hash=source_hash,
            created_at=now,
        )
        return event, None, entity, embedding

    def publish_embedding_event(
        self,
        entity_type: str,
        entity_id: str,
        *,
        event_type: EmbeddingEventType,
        source: str,
    ) -> RabbitMQPublishResult:
        event, error_result, entity, embedding = self.build_embedding_event(
            entity_type,
            entity_id,
            event_type=event_type,
            source=source,
        )
        if error_result is not None:
            return error_result
        if event is None:
            return RabbitMQPublishResult(ok=False, status="event_not_created", error=f"{entity_type}/{entity_id}")
        return self.publish_prepared_embedding_event(event, entity=entity, embedding=embedding)

    def publish_prepared_embedding_event(
        self,
        event: EmbeddingEvent,
        *,
        entity: Optional[Dict[str, Any]] = None,
        embedding: Optional[Dict[str, Any]] = None,
    ) -> RabbitMQPublishResult:
        entity = entity or self.repo.find_entity_by_id(event.entity_type, event.entity_id) or {}
        embedding = dict(embedding or entity.get("embedding") or {})
        if not entity:
            return RabbitMQPublishResult(ok=False, status="entity_not_found", error=f"{event.entity_type}/{event.entity_id}")
        result = self.rabbitmq.publish_json(event.model_dump(mode="json"))
        now = datetime.now(timezone.utc)
        if result.ok:
            queued = {
                **embedding,
                "status": st.EMBEDDING_QUEUED,
                "job_id": event.job_id,
                "last_event_id": event.event_id,
                "last_queued_at": now,
                "updated_at": now,
                "source_hash": event.embedding_source_hash,
                "error": None,
                "error_type": None,
            }
            self.repo.update_entity_status(
                event.entity_type,
                event.entity_id,
                {
                    "embedding": queued,
                    "embedding_status": st.EMBEDDING_QUEUED,
                },
            )
            return result

        fallback_status = st.EMBEDDING_PENDING if embedding.get("status") != st.EMBEDDING_STALE else st.EMBEDDING_STALE
        failed_publish = {
            **embedding,
            "status": fallback_status,
            "job_id": event.job_id,
            "last_event_id": event.event_id,
            "updated_at": now,
            "source_hash": event.embedding_source_hash,
            "error": result.error,
            "error_type": st.EMBEDDING_ERROR_TEMPORARY,
        }
        self.repo.update_entity_status(
            event.entity_type,
            event.entity_id,
            {
                "embedding": failed_publish,
                "embedding_status": fallback_status,
            },
        )
        logger.warning("Could not publish embedding event %s: %s", event.event_id, result.error)
        return result
