"""Run recommendation API smoke tests against local server."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

BASE = "http://127.0.0.1:8000"
OUT = "scripts/api_test_results.json"
TIMEOUT = 180


def call(method: str, path: str, body: dict | None = None) -> dict:
    url = BASE + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    t0 = datetime.now(timezone.utc)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            return {
                "ok": True,
                "status": resp.status,
                "elapsed_ms": int((datetime.now(timezone.utc) - t0).total_seconds() * 1000),
                "body": payload,
            }
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"raw": raw}
        return {
            "ok": False,
            "status": e.code,
            "elapsed_ms": int((datetime.now(timezone.utc) - t0).total_seconds() * 1000),
            "body": payload,
        }
    except Exception as e:
        return {
            "ok": False,
            "status": None,
            "elapsed_ms": int((datetime.now(timezone.utc) - t0).total_seconds() * 1000),
            "error": str(e),
        }


def first_id(entity_path: str) -> str | None:
    r = call("GET", entity_path)
    if not r.get("ok"):
        return None
    items = r["body"].get("data") or []
    if not items:
        return None
    return items[0].get("id")


def summarize_item(item: dict) -> dict:
    return {
        "id": item.get("id") or item.get("expert_id") or item.get("project_id"),
        "name": item.get("name"),
        "score": item.get("score"),
        "has_reasoning_paths": bool(item.get("reasoning_paths")),
        "reasoning_paths_count": len(item.get("reasoning_paths") or []),
        "path_diversity": item.get("path_diversity"),
        "has_explanation": bool(item.get("explanation") or item.get("xai_explanation")),
        "has_metrics": bool(item.get("metrics")),
        "keys": sorted(item.keys()),
    }


def check_shape(items: List[dict]) -> dict:
    if not items:
        return {"empty": True}
    sample = summarize_item(items[0])
    required = ["id", "name", "score"]
    missing = [k for k in required if not sample.get(k) and k not in (sample.get("keys") or [])]
    return {
        "count": len(items),
        "sample": sample,
        "missing_required": missing,
    }


def policy_test(name: str, source_id: str, source_type: str, target_type: str, limit: int = 3) -> dict:
    r = call(
        "POST",
        "/api/v1/recommendations/policy",
        {
            "source_id": source_id,
            "source_type": source_type,
            "target_type": target_type,
            "limit": limit,
            "language": "vi",
        },
    )
    items = []
    if r.get("ok") and isinstance(r.get("body"), dict):
        items = r["body"].get("data") or []
    return {
        "name": name,
        "request": {
            "source_id": source_id,
            "source_type": source_type,
            "target_type": target_type,
        },
        "response": r,
        "shape": check_shape(items),
    }


def main() -> int:
    results: Dict[str, Any] = {
        "base_url": BASE,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "tests": {},
    }

    results["tests"]["root"] = call("GET", "/")
    results["tests"]["health"] = call("GET", "/api/v1/health")
    results["tests"]["openapi"] = call("GET", "/openapi.json")

    pid = first_id("/api/v1/entities/projects?limit=5") or "prj_001"
    eid = first_id("/api/v1/entities/experts?limit=5")
    fid = first_id("/api/v1/entities/funders?limit=5")
    enid = first_id("/api/v1/entities/enterprises?limit=5")

    results["sample_ids"] = {
        "project": pid,
        "expert": eid,
        "funder": fid,
        "enterprise": enid,
    }

    policy_cases = []
    if pid:
        policy_cases += [
            ("Project->Expert", pid, "project", "expert"),
            ("Project->Funder", pid, "project", "funder"),
            ("Project->Enterprise", pid, "project", "enterprise"),
            ("Project->Project", pid, "project", "project"),
        ]
    if eid:
        policy_cases += [
            ("Expert->Project", eid, "expert", "project"),
            ("Expert->Funder", eid, "expert", "funder"),
            ("Expert->Enterprise", eid, "expert", "enterprise"),
            ("Expert->Expert", eid, "expert", "expert"),
        ]
    if enid:
        policy_cases += [
            ("Enterprise->Expert", enid, "enterprise", "expert"),
            ("Enterprise->Project", enid, "enterprise", "project"),
            ("Enterprise->Funder", enid, "enterprise", "funder"),
            ("Enterprise->Enterprise", enid, "enterprise", "enterprise"),
        ]
    if fid:
        policy_cases += [
            ("Funder->Expert", fid, "funder", "expert"),
            ("Funder->Project", fid, "funder", "project"),
            ("Funder->Enterprise", fid, "funder", "enterprise"),
        ]

    results["tests"]["policy"] = [
        policy_test(name, sid, st, tt) for name, sid, st, tt in policy_cases
    ]

    if pid:
        results["tests"]["overview"] = call(
            "POST",
            f"/api/v1/recommendations/projects/{pid}/overview?limit=3",
        )
        results["tests"]["experts_legacy"] = call(
            "POST",
            "/api/v1/recommendations/experts",
            {"project_id": pid, "limit": 3, "language": "vi"},
        )

    results["finished_at"] = datetime.now(timezone.utc).isoformat()

    out_path = OUT
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # compact stdout for CI
    passed = 0
    failed = 0
    for t in results["tests"].get("policy", []):
        ok = t["response"].get("ok") and t["response"].get("status") == 200
        print(f"{t['name']}: {'PASS' if ok else 'FAIL'} status={t['response'].get('status')} count={t['shape'].get('count', 0)}")
        if ok:
            passed += 1
        else:
            failed += 1
    print(f"policy total: {passed} pass, {failed} fail")
    print(f"written {out_path}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
