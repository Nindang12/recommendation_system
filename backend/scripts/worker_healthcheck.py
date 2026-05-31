"""Docker healthcheck helper for background workers."""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from infrastructure.rabbitmq_client import RabbitMQClient  # noqa: E402
from repositories.auth_repo import AuthRepository  # noqa: E402
from repositories.mongodb_repo import MongoDBRepository  # noqa: E402


def _check_mongo() -> bool:
    try:
        return bool(MongoDBRepository().check_db_health())
    except Exception:
        return False


def _check_rabbitmq() -> bool:
    try:
        return RabbitMQClient().health() == "connected"
    except Exception:
        return False


def _check_embedding_worker() -> bool:
    stale_seconds = int(os.getenv("WORKER_HEARTBEAT_STALE_SECONDS", "120"))
    repo = AuthRepository()
    rows = list(
        repo.db["worker_heartbeats"]
        .find({"worker_type": "embedding_worker"})
        .sort("last_seen_at", -1)
        .limit(5)
    )
    if not rows:
        # Worker may still be starting; allow if mongo+rabbitmq are up.
        return _check_mongo() and _check_rabbitmq()
    now = datetime.now(timezone.utc)
    for row in rows:
        seen = row.get("last_seen_at")
        if seen is None:
            continue
        if getattr(seen, "tzinfo", None) is None:
            seen = seen.replace(tzinfo=timezone.utc)
        age = (now - seen).total_seconds()
        if age <= stale_seconds:
            return True
    return False


def _check_outbox_publisher() -> bool:
    # Outbox publisher has no heartbeat collection; verify dependencies only.
    return _check_mongo() and _check_rabbitmq()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker-type", choices=["embedding", "outbox"], required=True)
    args = parser.parse_args()

    if not _check_mongo():
        return 1
    if not _check_rabbitmq():
        return 1
    if args.worker_type == "embedding" and not _check_embedding_worker():
        return 1
    if args.worker_type == "outbox" and not _check_outbox_publisher():
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
