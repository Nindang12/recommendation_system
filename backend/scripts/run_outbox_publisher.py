"""Publish pending embedding events from MongoDB outbox to RabbitMQ."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.outbox_publisher_service import OutboxPublisherService  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Publish one batch and exit.")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    args = parser.parse_args()

    service = OutboxPublisherService()
    while True:
        summary = service.publish_pending(limit=args.limit)
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
        if args.once:
            return 0
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    sys.exit(main())
