"""Smoke test for the admin-only Inductive PGPR shadow endpoint."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

import api.v1.endpoints.admin as admin_endpoint  # noqa: E402
from api.deps import get_current_user  # noqa: E402
from main import app  # noqa: E402


class _FakeShadowService:
    async def inspect(self, **kwargs):
        return {
            "status": "success",
            "prototype_only": True,
            "runtime_enabled": False,
            "warning": "fake shadow",
            "source": {
                "source_type": kwargs["source_type"],
                "source_id": kwargs["source_id"],
                "source_key": f"{kwargs['source_type'].capitalize()}::{kwargs['source_id']}",
            },
            "target_type": kwargs["target_type"],
            "hybrid": {"candidates": [{"id": "exp_001"}], "latency_ms": 1.0},
            "inductive_shadow": {
                "candidates": [{"id": "exp_001", "reasoning_path": []}],
                "blocked_action_count": 0,
                "blocked_action_counts": {},
                "latency_ms": 1.0,
            },
            "comparison": {
                "overlap_at_5": 1,
                "new_candidates_at_5": 0,
                "path_count": 1,
                "invalid_path_count": 0,
                "terminal_target_type_mismatch_count": 0,
            },
        }


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    original_service = admin_endpoint.InductivePGPRShadowService
    admin_endpoint.InductivePGPRShadowService = _FakeShadowService
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "admin_test",
        "account_role": "admin",
    }
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/admin/inductive-pgpr/shadow",
            json={
                "source_type": "project",
                "source_id": "prj_001",
                "target_type": "expert",
                "beam_width": 5,
                "max_hops": 3,
                "limit": 5,
                "mode": "admin_debug",
            },
        )
        _assert(response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}")
        payload = response.json()
        _assert(payload["prototype_only"] is True, "Endpoint must be marked prototype_only.")
        _assert(payload["runtime_enabled"] is False, "Endpoint must keep runtime disabled.")
        _assert(payload["data"]["runtime_enabled"] is False, "Data payload must keep runtime disabled.")
        _assert(payload["data"]["comparison"]["invalid_path_count"] == 0, "Comparison payload should expose path validity.")

        app.dependency_overrides[get_current_user] = lambda: {
            "id": "normal_user",
            "account_role": "user",
        }
        forbidden = client.post(
            "/api/v1/admin/inductive-pgpr/shadow",
            json={
                "source_type": "project",
                "source_id": "prj_001",
                "target_type": "expert",
            },
        )
        _assert(forbidden.status_code == 403, f"Expected 403 for normal user, got {forbidden.status_code}.")

        app.dependency_overrides.pop(get_current_user, None)
        unauthenticated = client.post(
            "/api/v1/admin/inductive-pgpr/shadow",
            json={
                "source_type": "project",
                "source_id": "prj_001",
                "target_type": "expert",
            },
        )
        _assert(
            unauthenticated.status_code == 401,
            f"Expected 401 for unauthenticated request, got {unauthenticated.status_code}.",
        )
    finally:
        admin_endpoint.InductivePGPRShadowService = original_service
        app.dependency_overrides.pop(get_current_user, None)

    output = ROOT / "scripts" / "inductive_pgpr_admin_shadow_endpoint_report.json"
    output.write_text(
        json.dumps(
            {
                "status": "passed",
                "endpoint": "POST /api/v1/admin/inductive-pgpr/shadow",
                "prototype_only": True,
                "runtime_enabled": False,
                "admin_status_code": 200,
                "normal_user_status_code": 403,
                "unauthenticated_status_code": 401,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps({"status": "passed", "output": str(output)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
