"""Phase 7.1 production hardening tests (worker heartbeat, DLQ, reason, retry filters)."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402
from infrastructure.rabbitmq_client import RabbitMQClient  # noqa: E402
from repositories.auth_repo import AuthRepository  # noqa: E402
from repositories.embedding_outbox_repo import EmbeddingOutboxRepository  # noqa: E402
from repositories.worker_heartbeat_repo import WorkerHeartbeatRepository  # noqa: E402
from services import provisional_status as st  # noqa: E402
from services.auth_service import AuthService  # noqa: E402
from services.embedding_admin_service import EmbeddingAdminService  # noqa: E402
from workers.embedding_worker import EmbeddingWorker  # noqa: E402

OUT = Path("scripts") / "phase7_1_hardening_report.json"


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def auth_header(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def dlq_message_count(rabbit: RabbitMQClient) -> int:
    try:
        connection = rabbit._connect()
        try:
            channel = connection.channel()
            rabbit._declare(channel)
            state = channel.queue_declare(queue=rabbit.dlq, durable=True, passive=True)
            return int(state.method.message_count)
        finally:
            connection.close()
    except Exception:
        return -1


def publish_dlq_payload(rabbit: RabbitMQClient, body: bytes) -> None:
    connection = rabbit._connect()
    try:
        channel = connection.channel()
        rabbit._declare(channel)
        channel.basic_publish(exchange="", routing_key=rabbit.dlq, body=body)
    finally:
        connection.close()


def failed_outbox_row(
    outbox: EmbeddingOutboxRepository,
    *,
    event_id: str,
    job_id: str,
    entity_id: str,
    last_error: str,
    error_type: str,
) -> Dict[str, Any]:
    payload = {
        "event_id": event_id,
        "job_id": job_id,
        "event_type": "kg.embedding.recompute",
        "entity_type": "expert",
        "entity_id": entity_id,
        "kg_sync_status": st.KG_SYNCED_VERIFIED,
        "entity_verification_status": st.ENTITY_VERIFIED,
        "embedding_source_hash": "phase71_hash",
    }
    return {
        "event_id": event_id,
        "job_id": job_id,
        "entity_type": "expert",
        "entity_id": entity_id,
        "event_type": "kg.embedding.recompute",
        "payload": payload,
        "status": outbox.STATUS_FAILED,
        "retry_count": 3,
        "max_retry": 3,
        "last_error": last_error,
        "error_type": error_type,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "next_attempt_at": datetime.now(timezone.utc),
    }


def main() -> int:
    suffix = str(int(time.time() * 1000))
    repo = AuthRepository()
    outbox = EmbeddingOutboxRepository(repo)
    heartbeats = WorkerHeartbeatRepository(repo)
    admin_service = EmbeddingAdminService(repo, outbox)
    auth = AuthService(repo)
    rabbit = RabbitMQClient()
    rabbit_ok = rabbit.health() == "connected"

    admin_email = f"phase71_admin_{suffix}@example.com"
    user_email = f"phase71_user_{suffix}@example.com"
    auth.create_admin_user(
        {"email": admin_email, "password": "Phase71Admin!23", "full_name": "Phase71 Admin"},
        account_role="root_admin",
    )
    user = auth.register(
        {
            "email": user_email,
            "password": "Phase71User!23",
            "full_name": "Phase71 User",
            "role": "expert",
        }
    )["user"]
    admin_token = auth.login(admin_email, "Phase71Admin!23")["token"]
    user_token = auth.login(user_email, "Phase71User!23")["token"]
    expert_id = str((user.get("linked_entity") or {}).get("id") or "")
    assert_true(bool(expert_id), "missing linked expert")

    checks: Dict[str, Any] = {}
    worker_id = f"phase71-worker-{suffix}"

    collection = repo.get_entity_collection("expert")
    assert_true(collection is not None, "expert collection")
    collection.update_one(
        {"expert_id": expert_id},
        {
            "$set": {
                "name": "Phase71 Expert",
                "user_id": str(user["id"]),
                **st.verified_state(),
                "kg_sync_status": st.KG_SYNCED_VERIFIED,
                "embedding_status": st.EMBEDDING_READY,
                "embedding": {
                    "status": st.EMBEDDING_READY,
                    "model": "graphsage_lite_v1",
                    "version": 1,
                    "dimension": 128,
                    "source_hash": "phase71",
                    "updated_at": datetime.now(timezone.utc),
                },
            }
        },
        upsert=True,
    )

    # 1) Worker heartbeat recorded (--once path via direct worker touch)
    worker = EmbeddingWorker(repo)
    worker.worker_id = worker_id
    worker.heartbeats.upsert_heartbeat(worker_id, status="running", processed_delta=1)
    row = heartbeats.get(worker_id)
    assert_true(row is not None and row.get("worker_type") == "embedding_worker", row)
    checks["worker_heartbeat_written"] = True

    # Optional subprocess --once when RabbitMQ is up (best-effort)
    if rabbit_ok:
        proc = subprocess.run(
            [sys.executable, "-m", "workers.embedding_worker", "--once"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
        checks["worker_once_exit_code"] = proc.returncode

    # 2) Stale heartbeat surfaces in pipeline-status
    stale_at = datetime.now(timezone.utc) - timedelta(seconds=heartbeats.stale_threshold_seconds() + 30)
    heartbeats.collection.update_one(
        {"worker_id": worker_id},
        {"$set": {"last_seen_at": stale_at, "status": "running"}},
    )
    serialized = heartbeats.serialize_worker(heartbeats.get(worker_id) or {})
    assert_true(serialized.get("liveness") == "stale", serialized)
    pipeline = admin_service.pipeline_status()
    stale_workers = [w for w in pipeline.get("worker_heartbeats", []) if w.get("worker_id") == worker_id]
    assert_true(stale_workers and stale_workers[0].get("liveness") == "stale", stale_workers)
    checks["worker_stale_pipeline"] = True

    # Refresh heartbeat for later UI checks
    heartbeats.upsert_heartbeat(worker_id, status="running")

    # 3-4) DLQ visibility + peek does not consume
    if rabbit_ok:
        before_dlq = dlq_message_count(rabbit)
        publish_dlq_payload(rabbit, b"{not-json")
        after_publish = dlq_message_count(rabbit)
        assert_true(after_publish > before_dlq, f"dlq count before={before_dlq} after={after_publish}")
        pipe = admin_service.pipeline_status()
        assert_true(pipe["dlq"]["messages"] > 0, pipe["dlq"])
        assert_true(pipe["dlq"]["alert"] is True, pipe["dlq"])
        peek1 = rabbit.peek_dlq_sample()
        count_after_peek1 = dlq_message_count(rabbit)
        peek2 = rabbit.peek_dlq_sample()
        count_after_peek2 = dlq_message_count(rabbit)
        assert_true(peek1.get("available") and peek2.get("available"), (peek1, peek2))
        assert_true(count_after_peek1 == after_publish, f"peek consumed messages: {count_after_peek1}")
        assert_true(count_after_peek2 == after_publish, f"second peek changed count: {count_after_peek2}")
        sample = peek1.get("sample") or {}
        assert_true("raw_size_bytes" in sample, sample)
        checks["dlq_alert_and_peek"] = True
    else:
        checks["dlq_alert_and_peek"] = "skipped_rabbitmq_down"

    with TestClient(app) as client:
        # 5) Admin recompute reason in audit
        admin_recompute = client.post(
            f"/api/v1/admin/entities/expert/{expert_id}/embedding/recompute",
            headers=auth_header(admin_token),
            json={"reason": "profile_updated_by_admin"},
        )
        assert_true(admin_recompute.status_code == 200, admin_recompute.text)

        # 6) User recompute without reason -> default audit reason
        collection.update_one(
            {"expert_id": expert_id},
            {"$unset": {"embedding.last_queued_at": ""}},
        )
        user_recompute = client.post(
            f"/api/v1/entities/expert/{expert_id}/embedding/recompute",
            headers=auth_header(user_token),
        )
        assert_true(user_recompute.status_code == 200, user_recompute.text)

        logs = client.get("/api/v1/admin/audit-logs?limit=50", headers=auth_header(admin_token))
        assert_true(logs.status_code == 200, logs.text)
        rows = logs.json().get("data") or []
        admin_reason_rows = [
            r for r in rows if r.get("action") == "embedding_recompute" and "profile_updated_by_admin" in str(r.get("reason") or "")
        ]
        user_reason_rows = [
            r for r in rows if r.get("action") == "embedding_recompute_user" and "user_requested_recompute" in str(r.get("reason") or "")
        ]
        assert_true(len(admin_reason_rows) >= 1, rows)
        assert_true(len(user_reason_rows) >= 1, rows)
        checks["recompute_reason_audit"] = True

        # Seed failed jobs for retry tests
        temp_ids = [f"evt_phase71_temp_{suffix}_{i}" for i in range(5)]
        validation_id = f"evt_phase71_validation_{suffix}"
        permanent_id = f"evt_phase71_perm_{suffix}"
        for idx, event_id in enumerate(temp_ids):
            outbox.collection.insert_one(
                failed_outbox_row(
                    outbox,
                    event_id=event_id,
                    job_id=f"job_{event_id}",
                    entity_id=expert_id,
                    last_error="timeout",
                    error_type="temporary",
                )
            )
        outbox.collection.insert_one(
            failed_outbox_row(
                outbox,
                event_id=validation_id,
                job_id=f"job_{validation_id}",
                entity_id=expert_id,
                last_error="schema",
                error_type="validation",
            )
        )
        outbox.collection.insert_one(
            failed_outbox_row(
                outbox,
                event_id=permanent_id,
                job_id=f"job_{permanent_id}",
                entity_id=expert_id,
                last_error="bad entity",
                error_type="permanent",
            )
        )

        # 7) Default retry only temporary
        retry_default = client.post(
            "/api/v1/admin/embedding/retry-failed",
            headers=auth_header(admin_token),
        )
        assert_true(retry_default.status_code == 200, retry_default.text)
        default_data = retry_default.json()["data"]
        retried_default = {row["event_id"] for row in default_data.get("retried", [])}
        assert_true(any(eid in retried_default for eid in temp_ids), default_data)
        assert_true(validation_id not in retried_default, default_data)
        assert_true(permanent_id not in retried_default, default_data)
        checks["retry_default_temporary_only"] = True

        # Re-seed for limit / filter tests (upsert so retried rows can be failed again)
        for event_id in temp_ids[2:]:
            outbox.collection.replace_one(
                {"event_id": event_id},
                failed_outbox_row(
                    outbox,
                    event_id=event_id,
                    job_id=f"job_{event_id}",
                    entity_id=expert_id,
                    last_error="timeout",
                    error_type="temporary",
                ),
                upsert=True,
            )

        # 8) include_permanent=false skips validation/permanent (explicit filter)
        retry_filtered = client.post(
            "/api/v1/admin/embedding/retry-failed?error_type=temporary&include_permanent=false&limit=20",
            headers=auth_header(admin_token),
        )
        assert_true(retry_filtered.status_code == 200, retry_filtered.text)
        filtered_retried = {row["event_id"] for row in retry_filtered.json()["data"].get("retried", [])}
        assert_true(validation_id not in filtered_retried, filtered_retried)
        assert_true(permanent_id not in filtered_retried, filtered_retried)
        checks["retry_skips_non_temporary"] = True

        # 9) limit respected
        limit_retry = client.post(
            "/api/v1/admin/embedding/retry-failed?limit=2&error_type=temporary",
            headers=auth_header(admin_token),
        )
        assert_true(limit_retry.status_code == 200, limit_retry.text)
        limited = limit_retry.json()["data"]
        assert_true(limited.get("retried_count", 0) <= 2, limited)
        checks["retry_respects_limit"] = True

        # include_permanent requires reason
        bad_perm = client.post(
            "/api/v1/admin/embedding/retry-failed?include_permanent=true",
            headers=auth_header(admin_token),
        )
        assert_true(bad_perm.status_code == 400, bad_perm.text)
        checks["retry_include_permanent_requires_reason"] = True

        # 10) Regular user cannot call admin retry-failed
        user_retry = client.post(
            "/api/v1/admin/embedding/retry-failed",
            headers=auth_header(user_token),
        )
        assert_true(user_retry.status_code == 403, user_retry.text)
        checks["user_retry_forbidden"] = True

    report = {"status": "passed", "suffix": suffix, "checks": checks, "rabbitmq_ok": rabbit_ok}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"PASS written {OUT}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        OUT.write_text(
            json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"FAIL {exc}")
        sys.exit(1)
