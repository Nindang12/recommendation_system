"""Hardening tests for Phase 3 embedding worker."""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from infrastructure.rabbitmq_client import RabbitMQClient  # noqa: E402
from models.events import EmbeddingEvent  # noqa: E402
from repositories.auth_repo import AuthRepository  # noqa: E402
from services import provisional_status as st  # noqa: E402
from services.auth_service import AuthService  # noqa: E402
from workers.embedding_worker import EmbeddingWorker  # noqa: E402


OUT = Path("scripts") / "phase3_worker_hardening_report.json"
BASE_URL = "http://127.0.0.1:8000"


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
        return {
            client.queue: int(main.method.message_count),
            client.dlq: int(dlq.method.message_count),
        }
    finally:
        connection.close()


def publish(payload: dict[str, Any]) -> None:
    result = RabbitMQClient().publish_json(payload)
    assert_true(result.ok, f"publish failed: {result}")


def run_worker_once_subprocess() -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "-m", "workers.embedding_worker", "--once"],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        timeout=120,
    )
    return {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def call_api(path: str) -> dict[str, Any]:
    with urllib.request.urlopen(BASE_URL + path, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def make_event(entity_type: str, entity_id: str, source_hash: str, *, suffix: str, user_id: str | None = None) -> dict[str, Any]:
    return EmbeddingEvent(
        event_id=f"evt_hardening_{suffix}_{int(time.time() * 1000)}",
        job_id=f"job_hardening_{suffix}_{int(time.time() * 1000)}",
        event_type="kg.embedding.recompute",
        entity_type=entity_type,  # type: ignore[arg-type]
        entity_id=entity_id,
        user_id=user_id,
        source="phase3_hardening",
        kg_sync_status=st.KG_SYNCED_UNVERIFIED,
        entity_verification_status=st.ENTITY_UNVERIFIED,
        embedding_version=0,
        embedding_source_hash=source_hash,
    ).model_dump(mode="json")


def main() -> int:
    repo = AuthRepository()
    service = AuthService(repo)
    report: dict[str, Any] = {"steps": []}
    purge_queue()

    empty_run = run_worker_once_subprocess()
    assert_true(empty_run["returncode"] == 0, f"empty queue worker failed: {empty_run}")
    assert_true("No embedding job available" in empty_run["stdout"], f"empty queue output unexpected: {empty_run}")
    report["steps"].append({"name": "empty_queue_once", **empty_run})

    timestamp = int(time.time())
    registered = service.register(
        {
            "email": f"phase3_hardening_{timestamp}@example.com",
            "password": "Phase3@123456",
            "full_name": f"Phase3 Hardening {timestamp}",
            "role": "expert",
            "organization": "Phase 3 Hardening Lab",
            "country": "VN",
            "province": "Ho Chi Minh",
            "district": "Thu Duc",
            "skills": ["python"],
            "research_interests": ["computer-vision"],
        }
    )
    user = registered["user"]
    entity_id = user["linked_entity"]["id"]
    token = registered["token"]
    entity = repo.find_entity_by_id("expert", entity_id) or {}
    embedding = entity.get("embedding") or {}
    source_hash = embedding.get("source_hash")
    report["steps"].append({"name": "created_seed", "entity_id": entity_id, "status": embedding.get("status")})

    # Consume the register event first so later tests start from ready.
    ready_run = run_worker_once_subprocess()
    assert_true(ready_run["returncode"] == 0, f"ready worker run failed: {ready_run}")
    entity = repo.find_entity_by_id("expert", entity_id) or {}
    assert_true((entity.get("embedding") or {}).get("status") == st.EMBEDDING_READY, "seed not ready after worker")
    report["steps"].append({"name": "seed_ready", **ready_run})

    bad_id_event = make_event("expert", "missing_entity_for_phase3", source_hash, suffix="missing")
    publish(bad_id_event)
    missing_run = run_worker_once_subprocess()
    assert_true(missing_run["returncode"] == 0, f"missing entity should skip cleanly: {missing_run}")
    assert_true("Entity not found" in missing_run["stdout"], f"missing entity output unexpected: {missing_run}")
    report["steps"].append({"name": "missing_entity_skip", **missing_run})

    repo.update_entity_status("expert", entity_id, {"kg_sync_status": st.KG_SYNC_FAILED})
    failed_event = make_event("expert", entity_id, source_hash, suffix="sync_failed", user_id=user["id"])
    publish(failed_event)
    sync_failed_run = run_worker_once_subprocess()
    assert_true(sync_failed_run["returncode"] == 0, f"sync_failed should skip cleanly: {sync_failed_run}")
    assert_true("kg not ready" in sync_failed_run["stdout"], f"sync_failed output unexpected: {sync_failed_run}")
    report["steps"].append({"name": "kg_sync_failed_skip", **sync_failed_run})

    repo.update_entity_status(
        "expert",
        entity_id,
        {
            "kg_sync_status": st.KG_SYNCED_UNVERIFIED,
            "entity_verification_status": st.ENTITY_REJECTED,
        },
    )
    rejected_event = make_event("expert", entity_id, source_hash, suffix="rejected", user_id=user["id"])
    publish(rejected_event)
    rejected_run = run_worker_once_subprocess()
    assert_true(rejected_run["returncode"] == 0, f"rejected should skip cleanly: {rejected_run}")
    assert_true("entity rejected" in rejected_run["stdout"], f"rejected output unexpected: {rejected_run}")
    report["steps"].append({"name": "rejected_skip", **rejected_run})

    repo.update_entity_status(
        "expert",
        entity_id,
        {
            "entity_verification_status": st.ENTITY_UNVERIFIED,
            "kg_sync_status": st.KG_SYNCED_UNVERIFIED,
            "visibility": st.VISIBILITY_LIMITED,
        },
    )
    stale_response = service.update_profile(
        user["id"],
        {
            "skills": ["python", "rabbitmq", "graphsage-lite"],
            "research_interests": ["computer-vision", "knowledge-graph"],
        },
    )
    updated_entity = repo.find_entity_by_id("expert", entity_id) or {}
    queued_embedding = updated_entity.get("embedding") or {}
    assert_true(queued_embedding.get("status") == st.EMBEDDING_QUEUED, f"stale recompute not queued: {queued_embedding}")
    assert_true(queued_embedding.get("source_hash") != source_hash, "source_hash did not change after source update")
    recompute_run = run_worker_once_subprocess()
    assert_true(recompute_run["returncode"] == 0, f"recompute worker failed: {recompute_run}")
    recomputed = repo.find_entity_by_id("expert", entity_id) or {}
    recomputed_embedding = recomputed.get("embedding") or {}
    assert_true(recomputed_embedding.get("status") == st.EMBEDDING_READY, f"recompute not ready: {recomputed_embedding}")
    assert_true(recomputed_embedding.get("source_hash") == queued_embedding.get("source_hash"), "ready source_hash mismatch")
    report["steps"].append(
        {
            "name": "stale_recompute_ready",
            "source_hash_before": source_hash,
            "source_hash_after": recomputed_embedding.get("source_hash"),
            "worker": recompute_run,
        }
    )

    detail = call_api(f"/api/v1/entities/expert/{entity_id}")
    metadata_embedding = (((detail.get("data") or {}).get("metadata") or {}).get("embedding") or {})
    assert_true(metadata_embedding.get("status") == st.EMBEDDING_READY, f"API missing ready embedding metadata: {metadata_embedding}")
    assert_true("vector" not in metadata_embedding, f"API leaked embedding vector: {metadata_embedding.keys()}")
    report["steps"].append({"name": "entity_api_no_vector", "embedding_keys": sorted(metadata_embedding.keys())})

    malformed = {"event_id": "evt_bad_phase3", "event_type": "kg.embedding.recompute", "schema_version": 1}
    publish(malformed)
    malformed_run = run_worker_once_subprocess()
    assert_true(malformed_run["returncode"] == 1, f"malformed event should fail worker once: {malformed_run}")
    queues_after_malformed = queue_count()
    assert_true(queues_after_malformed.get("embedding.jobs.dlq") == 1, f"malformed event not routed to DLQ: {queues_after_malformed}")
    report["steps"].append({"name": "malformed_event_dlq", "worker": malformed_run, "queues": queues_after_malformed})

    purge_queue()
    report["final_queue"] = queue_count()
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
