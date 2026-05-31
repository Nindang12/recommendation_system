"""Backfill embedding metadata for existing MongoDB entities.

Dry-run by default:

    python scripts/backfill_embedding_metadata.py

Apply changes:

    python scripts/backfill_embedding_metadata.py --apply

Refresh stale hashes as well:

    python scripts/backfill_embedding_metadata.py --apply --refresh-stale
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from repositories.auth_repo import AuthRepository  # noqa: E402
from services.embedding_metadata_service import EmbeddingMetadataService  # noqa: E402


ENTITY_COLLECTIONS = {
    "expert": ("experts", "expert_id"),
    "enterprise": ("enterprises", "enterprise_id"),
    "funder": ("funders", "funder_id"),
    "project": ("projects", "project_id"),
}


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value) if value.__class__.__name__ == "ObjectId" else value


def backfill_collection(
    repo: AuthRepository,
    entity_type: str,
    collection_name: str,
    id_field: str,
    *,
    apply: bool,
    refresh_stale: bool,
) -> Dict[str, Any]:
    collection = repo.db[collection_name]
    scanned = 0
    missing = 0
    stale = 0
    updated = 0
    examples = []
    now = datetime.now(timezone.utc)

    for doc in collection.find({}):
        scanned += 1
        current = dict(doc.get("embedding") or {})
        desired = EmbeddingMetadataService.default_embedding(entity_type, doc, now=now)
        reason = None
        embedding = desired
        if not current:
            missing += 1
            reason = "missing_embedding"
        else:
            current_hash = current.get("source_hash")
            desired_hash = desired.get("source_hash")
            if refresh_stale and current_hash != desired_hash:
                stale += 1
                reason = "source_hash_changed"
                embedding = EmbeddingMetadataService.refresh_after_source_change(entity_type, doc, now=now)

        if not reason:
            continue

        entity_id = str(doc.get(id_field) or doc.get("_id"))
        examples.append({"entity_type": entity_type, "entity_id": entity_id, "reason": reason})
        if apply:
            collection.update_one(
                {"_id": doc["_id"]},
                {
                    "$set": {
                        "embedding": embedding,
                        "embedding_status": embedding.get("status"),
                        "updated_at": now,
                    }
                },
            )
            updated += 1

    return {
        "entity_type": entity_type,
        "collection": collection_name,
        "scanned": scanned,
        "missing_embedding": missing,
        "stale_hash": stale,
        "updated": updated,
        "examples": examples[:10],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill embedding metadata for existing entities.")
    parser.add_argument("--apply", action="store_true", help="Apply updates. Default is dry-run.")
    parser.add_argument(
        "--refresh-stale",
        action="store_true",
        help="Also mark existing embeddings stale when source_hash differs.",
    )
    parser.add_argument(
        "--output",
        default=str(Path("scripts") / "embedding_backfill_report.json"),
        help="Where to write the JSON report.",
    )
    args = parser.parse_args()

    repo = AuthRepository()
    report = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "apply": bool(args.apply),
        "refresh_stale": bool(args.refresh_stale),
        "collections": [],
    }

    for entity_type, (collection_name, id_field) in ENTITY_COLLECTIONS.items():
        report["collections"].append(
            backfill_collection(
                repo,
                entity_type,
                collection_name,
                id_field,
                apply=bool(args.apply),
                refresh_stale=bool(args.refresh_stale),
            )
        )

    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(json_safe(report), ensure_ascii=False, indent=2), encoding="utf-8")

    total_updated = sum(item["updated"] for item in report["collections"])
    total_missing = sum(item["missing_embedding"] for item in report["collections"])
    total_stale = sum(item["stale_hash"] for item in report["collections"])
    print(f"written {output_path}")
    print(f"apply={args.apply} missing={total_missing} stale={total_stale} updated={total_updated}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
