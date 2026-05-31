from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field


EmbeddingEventType = Literal[
    "kg.entity.created",
    "kg.entity.updated",
    "kg.project.created",
    "kg.project.updated",
    "kg.embedding.recompute",
]


class EmbeddingEvent(BaseModel):
    """Versioned RabbitMQ event for cold-start embedding jobs."""

    event_id: str
    job_id: str
    event_type: EmbeddingEventType
    schema_version: int = 1
    entity_type: Literal["expert", "enterprise", "funder", "project"]
    entity_id: str
    user_id: Optional[str] = None
    source: str = "system"
    kg_sync_status: str
    entity_verification_status: str
    embedding_version: int = 0
    embedding_source_hash: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
