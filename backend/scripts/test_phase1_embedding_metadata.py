"""Smoke test Phase 1 embedding metadata behavior.

Requires local FastAPI backend, MongoDB and Neo4j to be running.

It verifies:
- register creates Expert/Enterprise/Funder entities with embedding.status=pending
- top-level embedding_status stays in sync with embedding.status
- create project creates project with embedding.status=pending
- updating source fields marks embedding.status=stale
- updating non-source fields does not mark embedding.status=stale
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


BASE_URL = "http://127.0.0.1:8000"
OUT = Path("scripts") / "phase1_embedding_metadata_test.json"
TIMEOUT_SECONDS = 120


def call_api(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    token: str | None = None,
) -> dict[str, Any]:
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
        "dimension": embedding.get("dimension"),
        "source_hash": embedding.get("source_hash"),
        "top_level_embedding_status": (doc or {}).get("embedding_status"),
    }


def assert_embedding(summary: dict[str, Any], expected_status: str, label: str) -> None:
    assert_true(summary["status"] == expected_status, f"{label}: expected {expected_status}, got {summary}")
    assert_true(
        summary["top_level_embedding_status"] == summary["status"],
        f"{label}: top-level embedding_status mismatch: {summary}",
    )
    assert_true(summary["dimension"] == 128, f"{label}: expected dimension 128, got {summary}")
    assert_true(bool(summary["source_hash"]), f"{label}: missing source_hash")


def register_user(role: str, timestamp: int, suffix: str) -> dict[str, Any]:
    email = f"phase1_{role}_{timestamp}_{suffix}@example.com"
    payload = {
        "email": email,
        "password": "Phase1@123456",
        "full_name": f"Phase1 {role.title()} {timestamp} {suffix}",
        "role": role,
        "organization": "Phase 1 Test Lab",
        "country": "VN",
        "province": "Ho Chi Minh",
        "district": "Thu Duc",
        "skills": ["python"],
        "research_interests": ["computer-vision"],
        "social_links": {"website": f"https://phase1.example.com/{role}/{suffix}"},
    }
    response = call_api("POST", "/api/v1/auth/register", payload)
    assert_true(response.get("ok") and response.get("status") == 200, f"register {role} failed: {response}")
    data = (response.get("body") or {}).get("data") or {}
    user = data.get("user") or {}
    linked_entity = user.get("linked_entity") or {}
    assert_true(bool(data.get("token")), f"{role}: missing token")
    assert_true(bool(linked_entity.get("id")), f"{role}: missing linked entity")
    return {
        "role": role,
        "email": email,
        "token": data.get("token"),
        "user": user,
        "entity_id": linked_entity.get("id"),
        "response": response,
    }


def main() -> int:
    timestamp = int(time.time())
    repo = AuthRepository()
    report: dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "timestamp": timestamp,
        "steps": [],
    }

    registrations = {
        role: register_user(role, timestamp, "role")
        for role in ("expert", "enterprise", "funder")
    }
    for role, info in registrations.items():
        entity = repo.find_entity_by_id(role, info["entity_id"])
        summary = embedding_summary(entity)
        assert_embedding(summary, "pending", f"{role} after register")
        report["steps"].append({"name": f"{role}_after_register", "entity_id": info["entity_id"], "embedding": summary})

    expert = registrations["expert"]
    project_payload = {
        "title": f"Phase1 Project {timestamp}",
        "summary": "Project used to verify embedding metadata.",
        "description": "Phase 1 smoke test project.",
        "field": "computer-vision",
        "keywords": ["computer-vision"],
        "status": "draft",
        "budget": 1000000,
        "trl": 3,
        "location": "Ho Chi Minh",
    }
    project_response = call_api("POST", "/api/v1/users/me/projects", project_payload, token=expert["token"])
    report["steps"].append({"name": "create_project", "response": project_response})
    assert_true(project_response.get("ok") and project_response.get("status") == 200, f"create project failed: {project_response}")
    project_id = ((project_response.get("body") or {}).get("data") or {}).get("id")
    assert_true(bool(project_id), "missing project id")
    project_doc = repo.find_entity_by_id("project", project_id)
    project_embedding = embedding_summary(project_doc)
    assert_embedding(project_embedding, "pending", "project after create")
    report["steps"].append({"name": "project_after_create", "project_id": project_id, "embedding": project_embedding})

    source_update = {
        "skills": ["python", "graph-neural-networks"],
        "custom_skills": ["rabbitmq"],
        "research_interests": ["computer-vision", "knowledge-graph"],
    }
    source_update_response = call_api("PUT", "/api/v1/users/me", source_update, token=expert["token"])
    report["steps"].append({"name": "expert_update_source_fields", "response": source_update_response})
    assert_true(source_update_response.get("ok") and source_update_response.get("status") == 200, "source update failed")
    expert_after_update = repo.find_entity_by_id("expert", expert["entity_id"])
    expert_stale = embedding_summary(expert_after_update)
    assert_embedding(expert_stale, "stale", "expert after source update")
    report["steps"].append({"name": "expert_after_source_update", "entity_id": expert["entity_id"], "embedding": expert_stale})

    enterprise = registrations["enterprise"]
    before_non_source = embedding_summary(repo.find_entity_by_id("enterprise", enterprise["entity_id"]))
    non_source_update = {
        "phone": "0900000000",
        "bio": "Updated non-source text only.",
        "social_links": {"website": "https://phase1.example.com/non-source"},
    }
    non_source_response = call_api("PUT", "/api/v1/users/me", non_source_update, token=enterprise["token"])
    report["steps"].append({"name": "enterprise_update_non_source_fields", "response": non_source_response})
    assert_true(non_source_response.get("ok") and non_source_response.get("status") == 200, "non-source update failed")
    after_non_source = embedding_summary(repo.find_entity_by_id("enterprise", enterprise["entity_id"]))
    assert_embedding(after_non_source, "pending", "enterprise after non-source update")
    assert_true(
        after_non_source["source_hash"] == before_non_source["source_hash"],
        f"non-source update changed source_hash: before={before_non_source} after={after_non_source}",
    )
    report["steps"].append(
        {
            "name": "enterprise_after_non_source_update",
            "entity_id": enterprise["entity_id"],
            "before": before_non_source,
            "after": after_non_source,
        }
    )

    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["status"] = "passed"
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"PASS written {OUT}")
    print(
        "entities="
        + ", ".join(f"{role}:{info['entity_id']}" for role, info in registrations.items())
        + f" project:{project_id}"
    )
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
