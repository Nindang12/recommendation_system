"""Smoke test Phase 4 embedding outbox reliability."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from infrastructure.rabbitmq_client import RabbitMQClient  # noqa: E402
from repositories.auth_repo import AuthRepository  # noqa: E402
from repositories.embedding_outbox_repo import EmbeddingOutboxRepository  # noqa: E402
from services.auth_service import AuthService  # noqa: E402
from services.outbox_publisher_service import OutboxPublisherService  # noqa: E402


OUT = Path("scripts") / "phase4_outbox_test.json"


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def purge_queue() -> None:
    client = RabbitMQClient()
    connection = client._connect()
    try:
        channel = connection.channel()
        client._declare(channel)
        channel.queue_purge(queue=client.queue)
        channel.queue_purge(queue=client.dlq)
    finally:
        connection.close()


def queue_count() -> dict[str, int]:
    client = RabbitMQClient()
    connection = client._connect()
    try:
        channel = connection.channel()
        client._declare(channel)
        main = channel.queue_declare(queue=client.queue, durable=True, passive=True)
        dlq = channel.queue_declare(queue=client.dlq, durable=True, passive=True)
        return {client.queue: int(main.method.message_count), client.dlq: int(dlq.method.message_count)}
    finally:
        connection.close()


def register_expert(service: AuthService, suffix: str) -> dict[str, Any]:
    ts = int(time.time() * 1000)
    return service.register(
        {
            "email": f"phase4_{suffix}_{ts}@example.com",
            "password": "Phase4@123456",
            "full_name": f"Phase4 {suffix} {ts}",
            "role": "expert",
            "organization": "Phase 4 Outbox Lab",
            "country": "VN",
            "province": "Ho Chi Minh",
            "district": "Thu Duc",
            "skills": ["python"],
            "research_interests": ["computer-vision"],
        }
    )


def latest_outbox_for(outbox: EmbeddingOutboxRepository, entity_id: str) -> dict[str, Any]:
    row = outbox.collection.find_one({"entity_id": entity_id}, sort=[("created_at", -1)])
    assert_true(bool(row), f"missing outbox row for {entity_id}")
    return row


def main() -> int:
    original_url = os.environ.get("RABBITMQ_URL")
    repo = AuthRepository()
    outbox = EmbeddingOutboxRepository(repo)
    report: dict[str, Any] = {"steps": []}

    purge_queue()
    service_up = AuthService(repo)
    up_result = register_expert(service_up, "rabbit_up")
    up_entity_id = up_result["user"]["linked_entity"]["id"]
    up_outbox = latest_outbox_for(outbox, up_entity_id)
    up_entity = repo.find_entity_by_id("expert", up_entity_id) or {}
    report["steps"].append(
        {
            "name": "rabbitmq_up_immediate_publish",
            "entity_id": up_entity_id,
            "outbox_status": up_outbox.get("status"),
            "embedding_status": (up_entity.get("embedding") or {}).get("status"),
            "queue": queue_count(),
        }
    )
    assert_true(up_outbox.get("status") == outbox.STATUS_PUBLISHED, f"RabbitMQ up outbox not published: {up_outbox}")
    assert_true((up_entity.get("embedding") or {}).get("status") == "queued", f"RabbitMQ up entity not queued: {up_entity.get('embedding')}")

    os.environ["RABBITMQ_URL"] = "amqp://guest:guest@127.0.0.1:59999/"
    service_down = AuthService(repo)
    down_result = register_expert(service_down, "rabbit_down")
    down_entity_id = down_result["user"]["linked_entity"]["id"]
    down_outbox = latest_outbox_for(outbox, down_entity_id)
    down_entity = repo.find_entity_by_id("expert", down_entity_id) or {}
    report["steps"].append(
        {
            "name": "rabbitmq_down_outbox_pending",
            "entity_id": down_entity_id,
            "outbox_status": down_outbox.get("status"),
            "retry_count": down_outbox.get("retry_count"),
            "embedding_status": (down_entity.get("embedding") or {}).get("status"),
            "embedding_error_type": (down_entity.get("embedding") or {}).get("error_type"),
        }
    )
    assert_true(down_outbox.get("status") == outbox.STATUS_PENDING, f"RabbitMQ down outbox not pending: {down_outbox}")
    assert_true((down_entity.get("embedding") or {}).get("status") == "pending", f"RabbitMQ down entity not pending: {down_entity.get('embedding')}")

    if original_url is None:
        os.environ.pop("RABBITMQ_URL", None)
    else:
        os.environ["RABBITMQ_URL"] = original_url

    pending_before = outbox.counts()
    retry_summary = OutboxPublisherService(repo).publish_pending(limit=10)
    retried_outbox = latest_outbox_for(outbox, down_entity_id)
    retried_entity = repo.find_entity_by_id("expert", down_entity_id) or {}
    report["steps"].append(
        {
            "name": "retry_pending_outbox",
            "pending_before": pending_before,
            "summary": retry_summary,
            "outbox_status": retried_outbox.get("status"),
            "embedding_status": (retried_entity.get("embedding") or {}).get("status"),
            "queue": queue_count(),
        }
    )
    assert_true(retried_outbox.get("status") == outbox.STATUS_PUBLISHED, f"retry did not publish outbox: {retried_outbox}")
    assert_true((retried_entity.get("embedding") or {}).get("status") == "queued", f"retry did not queue entity: {retried_entity.get('embedding')}")

    report["outbox_counts"] = outbox.counts()
    report["status"] = "passed"
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"PASS written {OUT}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        OUT.write_text(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"FAIL {exc}")
        sys.exit(1)
