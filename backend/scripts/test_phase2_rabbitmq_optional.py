"""Smoke test Phase 2 RabbitMQ optional publisher behavior.

Requires local FastAPI backend, MongoDB and Neo4j. RabbitMQ may be either up
or down; the test verifies user flows do not fail in either state.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from repositories.auth_repo import AuthRepository  # noqa: E402
from infrastructure.rabbitmq_client import RabbitMQClient  # noqa: E402
from services.event_publisher_service import EventPublisherService  # noqa: E402


BASE_URL = "http://127.0.0.1:8000"
OUT = Path("scripts") / "phase2_rabbitmq_optional_test.json"
TIMEOUT_SECONDS = 120


def call_api(method: str, path: str, body: dict[str, Any] | None = None, token: str | None = None) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(BASE_URL + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            raw = resp.read().decode("utf-8")
            return {"ok": True, "status": resp.status, "body": json.loads(raw) if raw else None}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload: Any = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"raw": raw}
        return {"ok": False, "status": exc.code, "body": payload}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status": None, "error": str(exc)}


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def embedding_summary(doc: dict[str, Any] | None) -> dict[str, Any]:
    embedding = (doc or {}).get("embedding") or {}
    return {
        "status": embedding.get("status"),
        "job_id": embedding.get("job_id"),
        "last_event_id": embedding.get("last_event_id"),
        "error_type": embedding.get("error_type"),
        "top_level_embedding_status": (doc or {}).get("embedding_status"),
        "kg_sync_status": (doc or {}).get("kg_sync_status"),
    }


def queue_count() -> int | None:
    try:
        client = RabbitMQClient()
        connection = client._connect()
        try:
            channel = connection.channel()
            client._declare(channel)
            state = channel.queue_declare(queue=client.queue, durable=True, passive=True)
            return int(state.method.message_count)
        finally:
            connection.close()
    except Exception:
        return None


def main() -> int:
    timestamp = int(time.time())
    repo = AuthRepository()
    report: dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "timestamp": timestamp,
        "steps": [],
    }

    health = call_api("GET", "/api/v1/health")
    assert_true(health.get("ok") and health.get("status") == 200, f"health failed: {health}")
    services = ((health.get("body") or {}).get("services") or {})
    rabbitmq_status = services.get("rabbitmq")
    assert_true(
        rabbitmq_status in {"connected", "unavailable_optional"},
        f"unexpected rabbitmq health: {rabbitmq_status}",
    )
    report["steps"].append({"name": "health", "rabbitmq": rabbitmq_status, "services": services})

    email = f"phase2_expert_{timestamp}@example.com"
    register_payload = {
        "email": email,
        "password": "Phase2@123456",
        "full_name": f"Phase2 Expert {timestamp}",
        "role": "expert",
        "organization": "Phase 2 RabbitMQ Lab",
        "country": "VN",
        "province": "Ho Chi Minh",
        "district": "Thu Duc",
        "skills": ["python"],
        "research_interests": ["computer-vision"],
    }
    register = call_api("POST", "/api/v1/auth/register", register_payload)
    assert_true(register.get("ok") and register.get("status") == 200, f"register failed: {register}")
    data = (register.get("body") or {}).get("data") or {}
    token = data.get("token")
    user = data.get("user") or {}
    linked_entity = user.get("linked_entity") or {}
    entity_id = linked_entity.get("id")
    assert_true(bool(token), "missing token")
    assert_true(bool(entity_id), "missing linked entity")
    entity_doc = repo.find_entity_by_id("expert", str(entity_id))
    entity_embedding = embedding_summary(entity_doc)
    assert_true(
        entity_embedding["top_level_embedding_status"] == entity_embedding["status"],
        f"entity embedding_status mismatch: {entity_embedding}",
    )
    expected_status = "queued" if rabbitmq_status == "connected" and entity_embedding["kg_sync_status"] == "synced_unverified" else entity_embedding["status"]
    assert_true(
        entity_embedding["status"] == expected_status,
        f"unexpected entity embedding status: {entity_embedding}, rabbitmq={rabbitmq_status}",
    )
    if rabbitmq_status == "connected" and entity_embedding["kg_sync_status"] == "synced_unverified":
        assert_true(bool(entity_embedding["job_id"]), f"queued entity missing job_id: {entity_embedding}")
        assert_true(bool(entity_embedding["last_event_id"]), f"queued entity missing event_id: {entity_embedding}")
    report["steps"].append({"name": "register_expert", "entity_id": entity_id, "embedding": entity_embedding})

    project_payload = {
        "title": f"Phase2 Project {timestamp}",
        "summary": "Project used to verify RabbitMQ optional publisher.",
        "description": "Phase 2 smoke test project.",
        "field": "computer-vision",
        "keywords": ["computer-vision"],
        "status": "draft",
        "budget": 1000000,
        "trl": 3,
        "location": "Ho Chi Minh",
    }
    project_response = call_api("POST", "/api/v1/users/me/projects", project_payload, token=token)
    assert_true(project_response.get("ok") and project_response.get("status") == 200, f"create project failed: {project_response}")
    project_id = ((project_response.get("body") or {}).get("data") or {}).get("id")
    assert_true(bool(project_id), "missing project id")
    project_doc = repo.find_entity_by_id("project", str(project_id))
    project_embedding = embedding_summary(project_doc)
    assert_true(
        project_embedding["top_level_embedding_status"] == project_embedding["status"],
        f"project embedding_status mismatch: {project_embedding}",
    )
    if rabbitmq_status == "connected" and project_embedding["kg_sync_status"] == "synced_unverified":
        assert_true(project_embedding["status"] == "queued", f"project not queued: {project_embedding}")
        assert_true(bool(project_embedding["job_id"]), f"queued project missing job_id: {project_embedding}")
        assert_true(bool(project_embedding["last_event_id"]), f"queued project missing event_id: {project_embedding}")
    report["steps"].append({"name": "create_project", "project_id": project_id, "embedding": project_embedding})

    if rabbitmq_status == "connected":
        before_non_source_queue = queue_count()
        before_non_source_entity = repo.find_entity_by_id("expert", str(entity_id)) or {}
        before_non_source_event = ((before_non_source_entity.get("embedding") or {}).get("last_event_id"))
        non_source_update = call_api(
            "PUT",
            "/api/v1/users/me",
            {"bio": "Phase 2 non-source update", "phone": "0900000000"},
            token=token,
        )
        assert_true(non_source_update.get("ok") and non_source_update.get("status") == 200, f"non-source update failed: {non_source_update}")
        after_non_source_queue = queue_count()
        after_non_source_entity = repo.find_entity_by_id("expert", str(entity_id)) or {}
        after_non_source_embedding = embedding_summary(after_non_source_entity)
        after_non_source_event = ((after_non_source_entity.get("embedding") or {}).get("last_event_id"))
        assert_true(
            before_non_source_queue == after_non_source_queue,
            f"non-source update published a queue message: before={before_non_source_queue} after={after_non_source_queue}",
        )
        assert_true(
            before_non_source_event == after_non_source_event,
            f"non-source update changed event id: before={before_non_source_event} after={after_non_source_event}",
        )
        report["steps"].append(
            {
                "name": "non_source_update_no_publish",
                "queue_before": before_non_source_queue,
                "queue_after": after_non_source_queue,
                "embedding": after_non_source_embedding,
            }
        )

        before_source_queue = queue_count()
        source_update = call_api(
            "PUT",
            "/api/v1/users/me",
            {"skills": ["python", "rabbitmq"], "research_interests": ["computer-vision", "knowledge-graph"]},
            token=token,
        )
        assert_true(source_update.get("ok") and source_update.get("status") == 200, f"source update failed: {source_update}")
        after_source_queue = queue_count()
        after_source_entity = repo.find_entity_by_id("expert", str(entity_id)) or {}
        after_source_embedding = embedding_summary(after_source_entity)
        assert_true(after_source_embedding["status"] == "queued", f"source update did not queue embedding: {after_source_embedding}")
        assert_true(
            after_source_queue is not None and before_source_queue is not None and after_source_queue >= before_source_queue + 1,
            f"source update did not publish a queue message: before={before_source_queue} after={after_source_queue}",
        )
        report["steps"].append(
            {
                "name": "source_update_publish",
                "queue_before": before_source_queue,
                "queue_after": after_source_queue,
                "embedding": after_source_embedding,
            }
        )

        failed_publish_before = queue_count()
        repo.update_entity_status("expert", str(entity_id), {"kg_sync_status": "sync_failed"})
        failed_publish_result = EventPublisherService(repo).publish_embedding_event(
            "expert",
            str(entity_id),
            event_type="kg.entity.updated",
            source="phase2_test_kg_failed",
        )
        failed_publish_after = queue_count()
        assert_true(not failed_publish_result.ok and failed_publish_result.status == "kg_not_ready", f"expected kg_not_ready, got {failed_publish_result}")
        assert_true(
            failed_publish_before == failed_publish_after,
            f"kg sync failed case published message: before={failed_publish_before} after={failed_publish_after}",
        )
        report["steps"].append(
            {
                "name": "kg_sync_failed_no_publish",
                "queue_before": failed_publish_before,
                "queue_after": failed_publish_after,
                "result": {
                    "ok": failed_publish_result.ok,
                    "status": failed_publish_result.status,
                    "error": failed_publish_result.error,
                },
            }
        )

    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["status"] = "passed"
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"PASS written {OUT}")
    print(f"rabbitmq={rabbitmq_status} entity={entity_id}:{entity_embedding['status']} project={project_id}:{project_embedding['status']}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        failure = {
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "status": "failed",
            "error": str(exc),
        }
        OUT.write_text(json.dumps(failure, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"FAIL {exc}")
        sys.exit(1)
