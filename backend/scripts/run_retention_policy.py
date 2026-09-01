from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_project_env() -> None:
    for env_path in (ROOT.parent / ".env", ROOT / ".env"):
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            if not line or line.lstrip().startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip().strip('"').strip("'")


_load_project_env()

from repositories.auth_repo import AuthRepository


def _count_and_apply(collection, query: Dict[str, Any], apply: bool) -> Dict[str, Any]:
    matched_count = int(collection.count_documents(query))
    applied_count = 0
    if apply and matched_count:
        result = collection.delete_many(query)
        applied_count = int(result.deleted_count)
    return {"matched_count": matched_count, "would_delete_count": matched_count, "applied_count": applied_count}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Retention policy dry-run/apply for governance collections.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Only report matched records. Default.")
    mode.add_argument("--apply", action="store_true", help="Apply deletes for matched records.")
    parser.add_argument(
        "--confirm-retention-delete",
        action="store_true",
        help="Required with --apply unless RETENTION_ALLOW_APPLY=true is set.",
    )
    parser.add_argument("--outbox-days", type=int, default=90)
    parser.add_argument("--dlq-days", type=int, default=90)
    parser.add_argument("--audit-days", type=int, default=365)
    parser.add_argument("--output", default=str(ROOT / "scripts" / "retention_policy_report.json"))
    args = parser.parse_args()

    apply = bool(args.apply)
    if apply and not args.confirm_retention_delete and os.getenv("RETENTION_ALLOW_APPLY", "").lower() != "true":
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "--apply requires --confirm-retention-delete or RETENTION_ALLOW_APPLY=true",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    now = datetime.now(timezone.utc)
    repo = AuthRepository()
    specs = [
        {
            "collection": "embedding_event_outbox",
            "cutoff_date": now - timedelta(days=args.outbox_days),
            "query": {"status": "published", "published_at": {"$lt": now - timedelta(days=args.outbox_days)}},
        },
        {
            "collection": "embedding_event_outbox",
            "label": "embedding_event_outbox_failed_old",
            "cutoff_date": now - timedelta(days=args.dlq_days),
            "query": {"status": "failed", "updated_at": {"$lt": now - timedelta(days=args.dlq_days)}},
        },
        {
            "collection": "admin_audit_logs",
            "cutoff_date": now - timedelta(days=args.audit_days),
            "query": {"created_at": {"$lt": now - timedelta(days=args.audit_days)}},
        },
    ]
    report = {
        "generated_at": now.isoformat(),
        "mode": "apply" if apply else "dry-run",
        "rules": [],
    }
    for spec in specs:
        collection_name = spec["collection"]
        collection = repo.db[collection_name]
        result = _count_and_apply(collection, spec["query"], apply)
        report["rules"].append(
            {
                "collection": collection_name,
                "label": spec.get("label", collection_name),
                "cutoff_date": spec["cutoff_date"].isoformat(),
                "query": spec["query"],
                **result,
            }
        )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(output), "mode": report["mode"], "rules": report["rules"]}, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
