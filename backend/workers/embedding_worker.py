from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from infrastructure.rabbitmq_client import RabbitMQClient  # noqa: E402
from models.events import EmbeddingEvent  # noqa: E402
from repositories.auth_repo import AuthRepository  # noqa: E402
from repositories.embedding_repo import EmbeddingRepository  # noqa: E402
from repositories.pgpr_graph_repo import PGPRGraphRepository  # noqa: E402
from repositories.worker_heartbeat_repo import WorkerHeartbeatRepository  # noqa: E402
from services import provisional_status as st  # noqa: E402
from services.embedding_metadata_service import EmbeddingMetadataService  # noqa: E402
from services.embedding_service import EmbeddingService  # noqa: E402
from services.graph_feature_service import GraphFeatureService  # noqa: E402

logger = logging.getLogger("embedding_worker")


class EmbeddingWorker:
    def __init__(
        self,
        repo: Optional[AuthRepository] = None,
        graph_repo: Optional[PGPRGraphRepository] = None,
        rabbitmq: Optional[RabbitMQClient] = None,
    ) -> None:
        self.repo = repo or AuthRepository()
        self.graph_repo = graph_repo or PGPRGraphRepository()
        self.embedding_repo = EmbeddingRepository(self.repo, self.graph_repo)
        self.rabbitmq = rabbitmq or RabbitMQClient()
        self.features = GraphFeatureService(self.repo, self.graph_repo)
        self.embedding = EmbeddingService()
        self.worker_id = f"embedding-worker-{osafe_time()}"
        self.heartbeats = WorkerHeartbeatRepository(self.repo)
        self.heartbeats.upsert_heartbeat(self.worker_id, status="running")

    def run_once(self) -> int:
        self.heartbeats.upsert_heartbeat(self.worker_id, status="running")
        connection = self.rabbitmq._connect()
        try:
            channel = connection.channel()
            self.rabbitmq._declare(channel)
            method, props, body = channel.basic_get(queue=self.rabbitmq.queue, auto_ack=False)
            if not method:
                print("No embedding job available.")
                return 0
            try:
                event = self._parse_event(body)
            except Exception as exc:  # noqa: BLE001
                channel.basic_nack(method.delivery_tag, requeue=False)
                self.heartbeats.upsert_heartbeat(self.worker_id, status="running", failed_delta=1)
                print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2))
                return 1
            self.heartbeats.upsert_heartbeat(
                self.worker_id,
                status="running",
                current_job_id=event.job_id,
                current_event_id=event.event_id,
            )
            try:
                result = self.process_event(event)
                channel.basic_ack(method.delivery_tag)
                self.heartbeats.upsert_heartbeat(
                    self.worker_id,
                    status="running",
                    current_job_id=None,
                    current_event_id=None,
                    processed_delta=1,
                )
                print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
                return 0
            except ValueError as exc:
                channel.basic_ack(method.delivery_tag)
                self.heartbeats.upsert_heartbeat(
                    self.worker_id,
                    status="running",
                    current_job_id=None,
                    current_event_id=None,
                    failed_delta=1,
                )
                print(json.dumps({"status": "skipped", "error": str(exc)}, ensure_ascii=False, indent=2))
                return 0
            except Exception as exc:  # noqa: BLE001
                channel.basic_nack(method.delivery_tag, requeue=False)
                self.heartbeats.upsert_heartbeat(
                    self.worker_id,
                    status="running",
                    current_job_id=None,
                    current_event_id=None,
                    failed_delta=1,
                )
                print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2))
                return 1
        finally:
            connection.close()

    def run_forever(self, poll_seconds: float = 1.0) -> None:
        while True:
            self.heartbeats.upsert_heartbeat(self.worker_id, status="running")
            self.run_once()
            time.sleep(poll_seconds)

    def process_event(self, event: EmbeddingEvent) -> Dict[str, Any]:
        entity = self.embedding_repo.find_entity(event.entity_type, event.entity_id)
        if not entity:
            raise ValueError(f"Entity not found: {event.entity_type}/{event.entity_id}")
        self._skip_if_invalid_entity(event, entity)
        self._skip_if_obsolete(event, entity)
        self._mark_processing(event, entity)

        try:
            entity = self.embedding_repo.find_entity(event.entity_type, event.entity_id) or entity
            features = self.features.extract(event.entity_type, event.entity_id)
            result = self.embedding.build_graphsage_lite(features)
            now = datetime.now(timezone.utc)
            ready_embedding = {
                **(entity.get("embedding") or {}),
                "status": st.EMBEDDING_READY,
                "job_id": event.job_id,
                "last_event_id": event.event_id,
                "retry_count": int((entity.get("embedding") or {}).get("retry_count") or 0),
                "model": result.model,
                "version": result.version,
                "dimension": result.dimension,
                "source_hash": event.embedding_source_hash,
                "last_processed_at": now,
                "updated_at": now,
                "error": None,
                "error_type": None,
                "vector": result.vector,
                "normalized": result.normalized,
                "signal": result.signal,
                "locked_by": None,
                "locked_at": None,
                "evidence_counts": result.evidence_counts,
            }
            self.embedding_repo.update_embedding(event.entity_type, event.entity_id, ready_embedding)
            self.embedding_repo.update_neo4j_embedding(event.entity_type, event.entity_id, ready_embedding)
            return {
                "status": "ready",
                "entity_type": event.entity_type,
                "entity_id": event.entity_id,
                "job_id": event.job_id,
                "event_id": event.event_id,
                "signal": result.signal,
                "dimension": result.dimension,
                "normalized": result.normalized,
                "evidence_counts": result.evidence_counts,
            }
        except ValueError as exc:
            self._mark_skipped(event, str(exc))
            raise
        except Exception as exc:  # noqa: BLE001
            self._mark_failed(event, str(exc), st.EMBEDDING_ERROR_TEMPORARY)
            raise

    def _parse_event(self, body: bytes) -> EmbeddingEvent:
        payload = json.loads(body.decode("utf-8"))
        return EmbeddingEvent.model_validate(payload)

    def _skip_if_invalid_entity(self, event: EmbeddingEvent, entity: Dict[str, Any]) -> None:
        if entity.get("entity_verification_status") == st.ENTITY_REJECTED:
            self._mark_skipped(event, "entity rejected")
            raise ValueError("entity rejected")
        if entity.get("kg_sync_status") not in {st.KG_SYNCED_UNVERIFIED, st.KG_SYNCED_VERIFIED}:
            self._mark_skipped(event, f"kg not ready: {entity.get('kg_sync_status')}")
            raise ValueError(f"kg not ready: {entity.get('kg_sync_status')}")
        if entity.get("visibility") in {st.VISIBILITY_HIDDEN, st.VISIBILITY_DISABLED}:
            self._mark_skipped(event, f"entity visibility blocked: {entity.get('visibility')}")
            raise ValueError(f"entity visibility blocked: {entity.get('visibility')}")

    def _skip_if_obsolete(self, event: EmbeddingEvent, entity: Dict[str, Any]) -> None:
        current_hash = EmbeddingMetadataService.compute_source_hash(event.entity_type, entity)
        if current_hash != event.embedding_source_hash:
            raise ValueError("obsolete embedding event: source_hash changed")
        embedding = entity.get("embedding") or {}
        if embedding.get("job_id") and embedding.get("job_id") != event.job_id:
            raise ValueError("obsolete embedding event: job_id changed")
        if embedding.get("last_event_id") and embedding.get("last_event_id") != event.event_id:
            raise ValueError("obsolete embedding event: event_id changed")
        if embedding.get("status") == st.EMBEDDING_READY and embedding.get("source_hash") == event.embedding_source_hash:
            raise ValueError("embedding already ready")

    def _mark_processing(self, event: EmbeddingEvent, entity: Dict[str, Any]) -> None:
        now = datetime.now(timezone.utc)
        embedding = {
            **(entity.get("embedding") or EmbeddingMetadataService.default_embedding(event.entity_type, entity, now=now)),
            "status": st.EMBEDDING_PROCESSING,
            "job_id": event.job_id,
            "last_event_id": event.event_id,
            "source_hash": event.embedding_source_hash,
            "updated_at": now,
            "locked_by": self.worker_id,
            "locked_at": now,
            "error": None,
            "error_type": None,
        }
        self.embedding_repo.update_embedding(event.entity_type, event.entity_id, embedding)

    def _mark_skipped(self, event: EmbeddingEvent, reason: str) -> None:
        entity = self.embedding_repo.find_entity(event.entity_type, event.entity_id)
        now = datetime.now(timezone.utc)
        embedding = {
            **((entity or {}).get("embedding") or {}),
            "status": st.EMBEDDING_SKIPPED,
            "job_id": event.job_id,
            "last_event_id": event.event_id,
            "updated_at": now,
            "last_processed_at": now,
            "error": reason,
            "error_type": st.EMBEDDING_ERROR_VALIDATION,
            "locked_by": None,
            "locked_at": None,
        }
        self.embedding_repo.update_embedding(event.entity_type, event.entity_id, embedding)

    def _mark_failed(self, event: EmbeddingEvent, error: str, error_type: str) -> None:
        entity = self.embedding_repo.find_entity(event.entity_type, event.entity_id) or {}
        now = datetime.now(timezone.utc)
        previous = entity.get("embedding") or {}
        embedding = {
            **previous,
            "status": st.EMBEDDING_FAILED,
            "job_id": event.job_id,
            "last_event_id": event.event_id,
            "retry_count": int(previous.get("retry_count") or 0) + 1,
            "updated_at": now,
            "last_processed_at": now,
            "error": error,
            "error_type": error_type,
            "locked_by": None,
            "locked_at": None,
        }
        self.embedding_repo.update_embedding(event.entity_type, event.entity_id, embedding)


def osafe_time() -> int:
    return int(time.time())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Process one message and exit.")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    logging.getLogger("pika").setLevel(logging.WARNING)
    worker = EmbeddingWorker()
    if args.once:
        return worker.run_once()
    worker.run_forever(poll_seconds=args.poll_seconds)
    return 0


if __name__ == "__main__":
    sys.exit(main())
