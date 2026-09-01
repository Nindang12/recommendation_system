"""Capture current recommendation API responses before cold-start scale-up changes.

Run from backend/ after the FastAPI server is available:

    python scripts/baseline_recommendation_snapshot.py

The output is intentionally committed-friendly JSON so later phases can compare
response shape and avoid breaking the existing PGPR/frontend contract.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_OUTPUT = Path("scripts") / "baseline_recommendation_snapshot.json"
TIMEOUT_SECONDS = 180

REQUIRED_ITEM_FIELDS = ["id", "name", "score"]
LEGACY_COMPAT_FIELDS = [
    "id",
    "name",
    "score",
    "reasoning_paths",
    "explanation",
    "xai_explanation",
    "scoring_method",
]


def call_api(base_url: str, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    started_at = datetime.now(timezone.utc)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8")
            payload = json.loads(raw) if raw else None
            return {
                "ok": True,
                "status": response.status,
                "elapsed_ms": elapsed_ms(started_at),
                "body": payload,
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload: Any = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"raw": raw}
        return {
            "ok": False,
            "status": exc.code,
            "elapsed_ms": elapsed_ms(started_at),
            "body": payload,
        }
    except Exception as exc:  # noqa: BLE001 - snapshot should record failures.
        return {
            "ok": False,
            "status": None,
            "elapsed_ms": elapsed_ms(started_at),
            "error": str(exc),
        }


def elapsed_ms(started_at: datetime) -> int:
    return int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)


def first_entity_id(base_url: str, collection: str) -> str | None:
    response = call_api(base_url, "GET", f"/api/v1/entities/{collection}?limit=5")
    if not response.get("ok"):
        return None
    items = ((response.get("body") or {}).get("data") or [])
    if not items:
        return None
    return items[0].get("id")


def summarize_recommendation_item(item: dict[str, Any]) -> dict[str, Any]:
    keys = sorted(item.keys())
    return {
        "id": item.get("id") or item.get("expert_id") or item.get("project_id") or item.get("funder_id") or item.get("enterprise_id"),
        "name": item.get("name") or item.get("title"),
        "score": item.get("score"),
        "keys": keys,
        "missing_required_fields": [field for field in REQUIRED_ITEM_FIELDS if field not in keys],
        "legacy_field_presence": {
            field: field in keys and item.get(field) not in (None, "", [], {})
            for field in LEGACY_COMPAT_FIELDS
        },
        "reasoning_paths_count": len(item.get("reasoning_paths") or []),
        "scoring_method": item.get("scoring_method"),
        "uses_provisional_data": item.get("uses_provisional_data"),
        "data_quality_level": item.get("data_quality_level"),
    }


def summarize_recommendation_response(response: dict[str, Any]) -> dict[str, Any]:
    body = response.get("body") if isinstance(response.get("body"), dict) else {}
    items = body.get("data") or body.get("recommendations") or []
    sample = summarize_recommendation_item(items[0]) if items else None
    return {
        "ok": bool(response.get("ok")),
        "status": response.get("status"),
        "count": len(items),
        "api_count": body.get("count"),
        "sample": sample,
        "response_keys": sorted(body.keys()) if isinstance(body, dict) else [],
    }


def policy_case(base_url: str, name: str, source_id: str, source_type: str, target_type: str, limit: int) -> dict[str, Any]:
    request_body = {
        "source_id": source_id,
        "source_type": source_type,
        "target_type": target_type,
        "limit": limit,
        "language": "vi",
        "mode": "public",
    }
    response = call_api(base_url, "POST", "/api/v1/recommendations/policy", request_body)
    return {
        "name": name,
        "request": request_body,
        "summary": summarize_recommendation_response(response),
        "response": response,
    }


def build_snapshot(base_url: str, limit: int) -> dict[str, Any]:
    project_id = first_entity_id(base_url, "projects") or "prj_001"
    expert_id = first_entity_id(base_url, "experts")
    funder_id = first_entity_id(base_url, "funders")
    enterprise_id = first_entity_id(base_url, "enterprises")

    policy_cases: list[tuple[str, str, str, str]] = []
    if project_id:
        policy_cases.extend(
            [
                ("Project->Expert", project_id, "project", "expert"),
                ("Project->Funder", project_id, "project", "funder"),
                ("Project->Enterprise", project_id, "project", "enterprise"),
                ("Project->Project", project_id, "project", "project"),
            ]
        )
    if expert_id:
        policy_cases.extend(
            [
                ("Expert->Project", expert_id, "expert", "project"),
                ("Expert->Expert", expert_id, "expert", "expert"),
            ]
        )
    if enterprise_id:
        policy_cases.append(("Enterprise->Expert", enterprise_id, "enterprise", "expert"))
    if funder_id:
        policy_cases.append(("Funder->Project", funder_id, "funder", "project"))

    return {
        "snapshot_type": "recommendation_api_baseline",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "purpose": "Freeze current API response shape before cold-start hybrid recommendation scale-up.",
        "required_item_fields": REQUIRED_ITEM_FIELDS,
        "legacy_compat_fields": LEGACY_COMPAT_FIELDS,
        "sample_ids": {
            "project": project_id,
            "expert": expert_id,
            "funder": funder_id,
            "enterprise": enterprise_id,
        },
        "health": call_api(base_url, "GET", "/api/v1/health"),
        "policy_cases": [
            policy_case(base_url, name, source_id, source_type, target_type, limit)
            for name, source_id, source_type, target_type in policy_cases
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture baseline recommendation API responses.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()

    snapshot = build_snapshot(args.base_url, max(1, min(args.limit, 10)))
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    failed_cases = [
        case
        for case in snapshot["policy_cases"]
        if not case["summary"].get("ok") or case["summary"].get("status") != 200
    ]
    print(f"written {output_path}")
    print(f"policy_cases={len(snapshot['policy_cases'])} failed={len(failed_cases)}")
    if failed_cases:
        for case in failed_cases:
            print(f"FAIL {case['name']} status={case['summary'].get('status')}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
