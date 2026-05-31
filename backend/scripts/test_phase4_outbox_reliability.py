"""Smoke test Phase 4 embedding outbox reliability.

Requires MongoDB, Neo4j and RabbitMQ. The test does not stop Docker services;
it simulates RabbitMQ downtime by constructing services with an invalid
RABBITMQ_URL.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from infrastructure.rabbitmq_client import RabbitMQClient  # noqa: E402
from repositories.auth_repo import AuthRepository  # noqa: E402
from repositories.embedding_outbox_repo import EmbeddingOutboxRepository  # noqa: E402
from services import provisional_status as st  # noqa: E402
from services.auth_service import AuthService  # noqa: E402
from services.outbox_publisher_service import OutboxPublisherService  # noqa: E402


OUT = Path("scripts") / "phase4_outbox_reliability_report.json"
VALID_RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
INVALID_RABBITMQ_URL = "amqp://guest:guest@127.0.0.1:59999/"


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def purge_queue() -> None:
    client = RabbitMQClient(url=VALID_RABBITMQ_URL)
    connection = client._connect()
    try:
        channel = connection.channel()
        client._declare(channel)
        channel.queue_purge(queue=client.queue)
        channel.queue_purge(queue=client.dlq)
    finally:
        connection.close()


def queue_count() -> dict[str, int]:
    client = RabbitMQClient(url=VALID_RABBITMQ_URL)
    connection = client._connect()
    try:
        channel = connection.channel()
        client._declare(channel)
        main = channel.queue_declare(queue=client.queue, durable=True, passive=True)
        dlq = channel.queue_declare(queue=client.dlq, durable=True, passive=True)
        return {
            client.queue: int(main.method.message_count),
            client.dlq: int(dlq.method.message_count),
        }
    finally:
        connection.close()


def register_expert(service: AuthService, suffix: str) -> tuple[dict[str, Any], str]:
    timestamp = int(time.time() * 1000)
    result = service.register(
        {
            "email": f"phase4_{suffix}_{timestamp}@example.com",
            "password": "Phase4@123456",
            "full_name": f"Phase4 Outbox {suffix} {timestamp}",
            "role": "expert",
            "organization": "Phase 4 Outbox Lab",
            "country": "VN",
            "province": "Ho Chi Minh",
            "district": "Thu Duc",
            "skills": ["python", "rabbitmq"],
            "research_interests": ["knowledge-graph"],
        }
    )
    user = result["user"]
    entity_id = user["linked_entity"]["id"]
    return result, entity_id


def latest_outbox_for(outbox: EmbeddingOutboxRepository, entity_type: str, entity_id: str) -> dict[str, Any] | None:
    return outbox.collection.find_one(
        {"entity_type": entity_type, "entity_id": entity_id},
        sort=[("created_at", -1)],
    )


def force_retry_now(outbox: EmbeddingOutboxRepository, event_id: str) -> None:
    outbox.collection.update_one(
        {"event_id": event_id},
        {"$set": {"next_attempt_at": datetime.now(timezone.utc), "status": outbox.STATUS_PENDING}},
    )


def set_rabbitmq_url(value: str) -> None:
    os.environ["RABBITMQ_URL"] = value


def main() -> int:
    repo = AuthRepository()
    outbox = EmbeddingOutboxRepository(repo)
    report: dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "steps": [],
    }

    set_rabbitmq_url(VALID_RABBITMQ_URL)
    purge_queue()
    start_counts = outbox.counts()
    report["steps"].append({"name": "start_clean_queue", "queue": queue_count(), "outbox_counts": start_counts})

    success_service = AuthService(repo)
    _, success_entity_id = register_expert(success_service, "success")
    success_record = latest_outbox_for(outbox, "expert", success_entity_id)
    success_entity = repo.find_entity_by_id("expert", success_entity_id) or {}
    success_embedding = success_entity.get("embedding") or {}
    assert_true(success_record is not None, "successful register did not create outbox record")
    assert_true(success_record["status"] == outbox.STATUS_PUBLISHED, f"success outbox not published: {success_record}")
    assert_true(success_embedding.get("status") == st.EMBEDDING_QUEUED, f"success embedding not queued: {success_embedding}")
    assert_true(queue_count()["embedding.jobs"] == 1, f"expected one queue message: {queue_count()}")
    report["steps"].append(
        {
            "name": "register_publish_now",
            "entity_id": success_entity_id,
            "outbox_status": success_record["status"],
            "embedding_status": success_embedding.get("status"),
            "queue": queue_count(),
        }
    )

    set_rabbitmq_url(INVALID_RABBITMQ_URL)
    down_service = AuthService(repo)
    _, pending_entity_id = register_expert(down_service, "rabbitmq_down")
    pending_record = latest_outbox_for(outbox, "expert", pending_entity_id)
    pending_entity = repo.find_entity_by_id("expert", pending_entity_id) or {}
    pending_embedding = pending_entity.get("embedding") or {}
    assert_true(pending_record is not None, "RabbitMQ-down register did not create outbox record")
    assert_true(pending_record["status"] == outbox.STATUS_PENDING, f"RabbitMQ-down outbox not pending: {pending_record}")
    assert_true(int(pending_record.get("retry_count") or 0) == 1, f"RabbitMQ-down retry_count unexpected: {pending_record}")
    assert_true(pending_embedding.get("status") == st.EMBEDDING_PENDING, f"RabbitMQ-down embedding not pending: {pending_embedding}")
    assert_true(pending_embedding.get("error_type") == st.EMBEDDING_ERROR_TEMPORARY, f"missing temporary error: {pending_embedding}")
    assert_true(queue_count()["embedding.jobs"] == 1, "RabbitMQ-down case should not add queue message")
    report["steps"].append(
        {
            "name": "rabbitmq_down_pending_outbox",
            "entity_id": pending_entity_id,
            "outbox_status": pending_record["status"],
            "retry_count": pending_record.get("retry_count"),
            "embedding_status": pending_embedding.get("status"),
            "error_type": pending_embedding.get("error_type"),
            "queue": queue_count(),
        }
    )

    set_rabbitmq_url(VALID_RABBITMQ_URL)
    force_retry_now(outbox, pending_record["event_id"])
    retry_summary = OutboxPublisherService(repo).publish_pending(limit=10)
    retried_record = outbox.get_by_event_id(pending_record["event_id"]) or {}
    retried_entity = repo.find_entity_by_id("expert", pending_entity_id) or {}
    retried_embedding = retried_entity.get("embedding") or {}
    assert_true(retried_record.get("status") == outbox.STATUS_PUBLISHED, f"retry did not publish: {retried_record}")
    assert_true(retried_embedding.get("status") == st.EMBEDDING_QUEUED, f"retry did not queue embedding: {retried_embedding}")
    assert_true(queue_count()["embedding.jobs"] == 2, f"retry should add second queue message: {queue_count()}")
    report["steps"].append(
        {
            "name": "outbox_retry_publish",
            "summary": retry_summary,
            "outbox_status": retried_record.get("status"),
            "embedding_status": retried_embedding.get("status"),
            "queue": queue_count(),
        }
    )

    no_duplicate_summary = OutboxPublisherService(repo).publish_pending(limit=10)
    assert_true(no_duplicate_summary["total"] == 0, f"unexpected publishable rows: {no_duplicate_summary}")
    assert_true(queue_count()["embedding.jobs"] == 2, "second outbox publisher run duplicated queue messages")
    report["steps"].append({"name": "no_duplicate_republish", "summary": no_duplicate_summary, "queue": queue_count()})

    before_kg_failed_count = outbox.collection.count_documents({})
    repo.update_entity_status("expert", success_entity_id, {"kg_sync_status": st.KG_SYNC_FAILED})
    kg_failed_result = OutboxPublisherService(repo).enqueue_embedding_event(
        "expert",
        success_entity_id,
        event_type="kg.entity.updated",
        source="phase4_kg_sync_failed",
    )
    after_kg_failed_count = outbox.collection.count_documents({})
    assert_true(not kg_failed_result.ok and kg_failed_result.status == "kg_not_ready", f"expected kg_not_ready: {kg_failed_result}")
    assert_true(before_kg_failed_count == after_kg_failed_count, "kg_sync_failed created an outbox event")
    repo.update_entity_status("expert", success_entity_id, {"kg_sync_status": st.KG_SYNCED_UNVERIFIED})
    report["steps"].append(
        {
            "name": "kg_sync_failed_no_outbox",
            "result": {"ok": kg_failed_result.ok, "status": kg_failed_result.status, "error": kg_failed_result.error},
            "outbox_count_before": before_kg_failed_count,
            "outbox_count_after": after_kg_failed_count,
        }
    )

    set_rabbitmq_url(INVALID_RABBITMQ_URL)
    max_retry_service = OutboxPublisherService(repo)
    max_retry_result = max_retry_service.enqueue_embedding_event(
        "expert",
        success_entity_id,
        event_type="kg.embedding.recompute",
        source="phase4_max_retry",
        try_publish_now=False,
    )
    assert_true(max_retry_result.ok, f"could not enqueue max retry test: {max_retry_result}")
    max_retry_record = latest_outbox_for(outbox, "expert", success_entity_id)
    assert_true(max_retry_record is not None, "missing max retry outbox record")
    for _ in range(int(max_retry_record.get("max_retry") or 3)):
        max_retry_service.publish_record(max_retry_record)
    failed_record = outbox.get_by_event_id(max_retry_record["event_id"]) or {}
    assert_true(failed_record.get("status") == outbox.STATUS_FAILED, f"max retry did not mark failed: {failed_record}")
    report["steps"].append(
        {
            "name": "max_retry_marks_failed",
            "event_id": max_retry_record["event_id"],
            "retry_count": failed_record.get("retry_count"),
            "max_retry": failed_record.get("max_retry"),
            "status": failed_record.get("status"),
        }
    )

    set_rabbitmq_url(VALID_RABBITMQ_URL)
    purge_queue()
    report["final_queue"] = queue_count()
    report["outbox_counts"] = outbox.counts()
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["status"] = "passed"
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"PASS written {OUT}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        set_rabbitmq_url(VALID_RABBITMQ_URL)
        OUT.write_text(
            json.dumps(
                {
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "status": "failed",
                    "error": str(exc),
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        print(f"FAIL {exc}")
        sys.exit(1)
