"""Queue embedding jobs for existing KG-synced entities.

Dry-run by default:

    python scripts/requeue_embedding_backfill.py

Apply and publish immediately when RabbitMQ is available:

    python scripts/requeue_embedding_backfill.py --apply

Then drain jobs:

    python -m workers.embedding_worker --max-jobs 200
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from repositories.auth_repo import AuthRepository  # noqa: E402
from services import provisional_status as st  # noqa: E402
from services.outbox_publisher_service import OutboxPublisherService  # noqa: E402


ENTITY_TYPES = ("expert", "project", "funder", "enterprise")
PUBLISHABLE_KG_STATUSES = {st.KG_SYNCED_UNVERIFIED, st.KG_SYNCED_VERIFIED}
SKIP_STATUSES = {st.EMBEDDING_QUEUED, st.EMBEDDING_PROCESSING}


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value) if value.__class__.__name__ == "ObjectId" else value


def _entity_types(raw: str) -> List[str]:
    values = [item.strip().lower() for item in str(raw or "").split(",") if item.strip()]
    if not values or values == ["all"]:
        return list(ENTITY_TYPES)
    unknown = sorted(set(values) - set(ENTITY_TYPES))
    if unknown:
        raise ValueError(f"Unsupported entity type(s): {', '.join(unknown)}")
    return values


def _needs_embedding_job(doc: Dict[str, Any], *, force: bool) -> tuple[bool, str]:
    kg_status = str(doc.get("kg_sync_status") or st.KG_NOT_SYNCED)
    if kg_status not in PUBLISHABLE_KG_STATUSES:
        return False, f"kg_not_ready:{kg_status}"

    embedding = doc.get("embedding") or {}
    status = str(embedding.get("status") or doc.get("embedding_status") or st.EMBEDDING_PENDING)
    vector = embedding.get("vector")
    signal = embedding.get("signal")
    if force:
        if status in SKIP_STATUSES:
            return False, f"busy:{status}"
        return True, "force"
    if status == st.EMBEDDING_READY and isinstance(vector, list) and vector and signal != st.EMBEDDING_SIGNAL_NONE:
        return False, "ready"
    if status in SKIP_STATUSES:
        return False, f"busy:{status}"
    return True, f"not_ready:{status}"


def _iter_entities(repo: AuthRepository, entity_types: Iterable[str], limit: int) -> Iterable[tuple[str, Dict[str, Any]]]:
    remaining = max(1, int(limit))
    for entity_type in entity_types:
        collection = repo.get_entity_collection(entity_type)
        if collection is None:
            continue
        for doc in collection.find({}).sort("updated_at", -1).limit(remaining):
            yield entity_type, doc


def main() -> int:
    parser = argparse.ArgumentParser(description="Queue embedding recompute jobs for existing entities.")
    parser.add_argument("--apply", action="store_true", help="Create outbox/RabbitMQ jobs. Default is dry-run.")
    parser.add_argument("--force", action="store_true", help="Requeue even ready embeddings, except queued/processing.")
    parser.add_argument("--types", default="all", help="Comma-separated entity types: expert,project,funder,enterprise.")
    parser.add_argument("--limit", type=int, default=1000, help="Maximum documents to scan.")
    parser.add_argument(
        "--no-publish-now",
        action="store_true",
        help="Only create outbox records; publish later with scripts/run_outbox_publisher.py.",
    )
    parser.add_argument(
        "--output",
        default=str(Path("scripts") / "embedding_requeue_report.json"),
        help="Where to write the JSON report.",
    )
    args = parser.parse_args()

    repo = AuthRepository()
    publisher = OutboxPublisherService(repo)
    entity_types = _entity_types(args.types)
    report: Dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "apply": bool(args.apply),
        "force": bool(args.force),
        "entity_types": entity_types,
        "scanned": 0,
        "eligible": 0,
        "queued": 0,
        "skipped": {},
        "results": [],
    }

    for entity_type, doc in _iter_entities(repo, entity_types, args.limit):
        report["scanned"] += 1
        id_field = repo.entity_id_field(entity_type)
        entity_id = str(doc.get(id_field) or doc.get("_id"))
        ok, reason = _needs_embedding_job(doc, force=bool(args.force))
        if not ok:
            report["skipped"][reason] = int(report["skipped"].get(reason, 0)) + 1
            continue

        report["eligible"] += 1
        row: Dict[str, Any] = {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "reason": reason,
            "embedding_status": (doc.get("embedding") or {}).get("status") or doc.get("embedding_status"),
            "kg_sync_status": doc.get("kg_sync_status"),
        }
        if args.apply:
            result = publisher.enqueue_embedding_event(
                entity_type,
                entity_id,
                event_type="kg.embedding.recompute",  # type: ignore[arg-type]
                source="scripts.requeue_embedding_backfill",
                try_publish_now=not args.no_publish_now,
            )
            row.update({"publish_status": result.status, "ok": result.ok, "error": result.error})
            if result.ok:
                report["queued"] += 1
        report["results"].append(row)

    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(_json_safe(report), ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"written {output_path}")
    print(
        "apply={apply} scanned={scanned} eligible={eligible} queued={queued}".format(
            apply=report["apply"],
            scanned=report["scanned"],
            eligible=report["eligible"],
            queued=report["queued"],
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
