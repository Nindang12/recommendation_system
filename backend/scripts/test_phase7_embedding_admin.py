"""Phase 7 embedding admin API smoke tests."""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402
from repositories.auth_repo import AuthRepository  # noqa: E402
from repositories.embedding_outbox_repo import EmbeddingOutboxRepository  # noqa: E402
from services import provisional_status as st  # noqa: E402
from services.auth_service import AuthService  # noqa: E402
from services.embedding_admin_service import EmbeddingAdminService  # noqa: E402

OUT = Path("scripts") / "phase7_embedding_admin_report.json"


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def unit_vector(first: float, second: float = 0.0, dimension: int = 128) -> List[float]:
    values = [0.0] * dimension
    values[0] = first
    values[1] = second
    norm = sum(v * v for v in values) ** 0.5
    return [v / norm for v in values] if norm else values


def embedding_doc(vector: List[float], status: str = st.EMBEDDING_READY) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "status": status,
        "model": "graphsage_lite_v1",
        "version": 1,
        "dimension": 128,
        "source_hash": "phase7_hash",
        "vector": vector,
        "normalized": True,
        "signal": st.EMBEDDING_SIGNAL_OK,
        "updated_at": now,
    }


def insert_entity(repo: AuthRepository, entity_type: str, doc: Dict[str, Any]) -> None:
    collection = repo.get_entity_collection(entity_type)
    assert_true(collection is not None, entity_type)
    id_field = repo.entity_id_field(entity_type)
    collection.delete_many({id_field: doc[id_field]})
    collection.insert_one(doc)


def auth_header(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def main() -> int:
    suffix = str(int(time.time() * 1000))
    repo = AuthRepository()
    outbox = EmbeddingOutboxRepository(repo)
    auth = AuthService(repo)
    admin_service = EmbeddingAdminService(repo, outbox)

    admin_email = f"phase7_admin_{suffix}@example.com"
    user_a_email = f"phase7_user_a_{suffix}@example.com"
    user_b_email = f"phase7_user_b_{suffix}@example.com"

    admin_user = auth.create_admin_user(
        {"email": admin_email, "password": "Phase7Admin!23", "full_name": "Phase7 Admin"},
        account_role="admin",
    )
    user_a = auth.register(
        {
            "email": user_a_email,
            "password": "Phase7UserA!23",
            "full_name": "Phase7 User A",
            "role": "expert",
        }
    )["user"]
    user_b = auth.register(
        {
            "email": user_b_email,
            "password": "Phase7UserB!23",
            "full_name": "Phase7 User B",
            "role": "expert",
        }
    )["user"]

    admin_token = auth.login(admin_email, "Phase7Admin!23")["token"]
    token_a = auth.login(user_a_email, "Phase7UserA!23")["token"]
    token_b = auth.login(user_b_email, "Phase7UserB!23")["token"]

    expert_a_id = str((user_a.get("linked_entity") or {}).get("id") or "")
    expert_b_id = str((user_b.get("linked_entity") or {}).get("id") or "")
    assert_true(bool(expert_a_id and expert_b_id), "missing linked experts")

    insert_entity(
        repo,
        "expert",
        {
            "expert_id": expert_a_id,
            "name": "Phase7 Expert A",
            "user_id": str(user_a["id"]),
            **st.verified_state(),
            "kg_sync_status": st.KG_SYNCED_VERIFIED,
            "embedding": embedding_doc(unit_vector(1.0), st.EMBEDDING_READY),
            "embedding_status": st.EMBEDDING_READY,
        },
    )

    report: Dict[str, Any] = {"status": "passed", "suffix": suffix}

    with TestClient(app) as client:
        pipeline = client.get("/api/v1/admin/embedding/pipeline-status", headers=auth_header(admin_token))
        assert_true(pipeline.status_code == 200, pipeline.text)
        assert_true("queues" in pipeline.json()["data"], pipeline.json())

        jobs = client.get("/api/v1/admin/embedding/jobs?limit=5", headers=auth_header(admin_token))
        assert_true(jobs.status_code == 200, jobs.text)

        own_status = client.get(
            f"/api/v1/entities/expert/{expert_a_id}/embedding-status",
            headers=auth_header(token_a),
        )
        assert_true(own_status.status_code == 200, own_status.text)
        assert_true("vector" not in json.dumps(own_status.json()), "vector leaked in status API")

        foreign_status = client.get(
            f"/api/v1/entities/expert/{expert_a_id}/embedding-status",
            headers=auth_header(token_b),
        )
        assert_true(foreign_status.status_code == 403, foreign_status.text)

        foreign_recompute = client.post(
            f"/api/v1/entities/expert/{expert_a_id}/embedding/recompute",
            headers=auth_header(token_b),
        )
        assert_true(foreign_recompute.status_code == 403, foreign_recompute.text)

        own_recompute = client.post(
            f"/api/v1/entities/expert/{expert_a_id}/embedding/recompute",
            headers=auth_header(token_a),
        )
        assert_true(own_recompute.status_code == 200, own_recompute.text)

        admin_recompute = client.post(
            f"/api/v1/admin/entities/expert/{expert_b_id}/embedding/recompute",
            headers=auth_header(admin_token),
            json={"reason": "profile_updated_by_admin"},
        )
        assert_true(admin_recompute.status_code == 200, admin_recompute.text)

        pipeline = client.get("/api/v1/admin/embedding/pipeline-status", headers=auth_header(admin_token))
        pipeline_data = pipeline.json()["data"]
        assert_true("worker_heartbeats" in pipeline_data, pipeline_data)
        assert_true("dlq" in pipeline_data, pipeline_data)

        def _failed_outbox_row(event_id: str, job_id: str, *, last_error: str, error_type: str) -> dict[str, Any]:
            payload = {
                "event_id": event_id,
                "job_id": job_id,
                "event_type": "kg.embedding.recompute",
                "entity_type": "expert",
                "entity_id": expert_a_id,
                "kg_sync_status": st.KG_SYNCED_VERIFIED,
                "entity_verification_status": st.ENTITY_VERIFIED,
                "embedding_source_hash": "phase7_hash",
            }
            return {
                "event_id": event_id,
                "job_id": job_id,
                "entity_type": "expert",
                "entity_id": expert_a_id,
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

        temp_event_id = f"evt_phase7_temp_{suffix}"
        validation_event_id = f"evt_phase7_validation_{suffix}"
        outbox.collection.insert_one(
            _failed_outbox_row(
                temp_event_id,
                f"job_phase7_temp_{suffix}",
                last_error="rabbitmq connection timeout",
                error_type="temporary",
            )
        )
        outbox.collection.insert_one(
            _failed_outbox_row(
                validation_event_id,
                f"job_phase7_validation_{suffix}",
                last_error="malformed event schema",
                error_type="validation",
            )
        )
        retry = client.post(
            "/api/v1/admin/embedding/retry-failed?limit=10&error_type=temporary",
            headers=auth_header(admin_token),
        )
        assert_true(retry.status_code == 200, retry.text)
        retry_data = retry.json()["data"]
        retried_ids = {row["event_id"] for row in retry_data.get("retried", [])}
        assert_true(temp_event_id in retried_ids, retry_data)
        assert_true(validation_event_id not in retried_ids, retry_data)
        assert_true(retry_data.get("skipped_count", 0) >= 0, retry_data)

        logs = client.get("/api/v1/admin/audit-logs?limit=30", headers=auth_header(admin_token))
        assert_true(logs.status_code == 200, logs.text)
        actions = {str(row.get("action")) for row in logs.json().get("data") or []}
        assert_true("embedding_recompute" in actions or "embedding_recompute_user" in actions, actions)
        assert_true("embedding_retry_failed" in actions, actions)

        audit_with_reason = [
            row
            for row in logs.json().get("data") or []
            if str(row.get("action")) == "embedding_recompute" and "profile_updated_by_admin" in str(row.get("reason") or "")
        ]
        assert_true(len(audit_with_reason) >= 1, "missing recompute audit reason")

    report["checks"] = {
        "pipeline_status": True,
        "foreign_recompute_403": True,
        "own_recompute_200": True,
        "admin_retry_failed": True,
        "retry_filters": True,
        "recompute_reason_audit": True,
        "worker_heartbeats_field": True,
        "dlq_field": True,
        "audit_actions": sorted(actions),
    }
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
