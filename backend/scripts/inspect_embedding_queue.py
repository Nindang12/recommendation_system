"""Inspect RabbitMQ embedding queues before running workers.

Default behavior is non-destructive: it prints queue lengths and peeks one
message from embedding.jobs, then requeues it.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from infrastructure.rabbitmq_client import RabbitMQClient  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--purge", action="store_true", help="Purge embedding.jobs and embedding.jobs.dlq.")
    args = parser.parse_args()

    client = RabbitMQClient()
    connection = client._connect()
    try:
        channel = connection.channel()
        client._declare(channel)

        report: dict[str, Any] = {"queues": {}, "sample": None}
        for queue in (client.queue, client.dlq):
            state = channel.queue_declare(queue=queue, durable=True, passive=True)
            report["queues"][queue] = {
                "messages": state.method.message_count,
                "consumers": state.method.consumer_count,
            }

        method, props, body = channel.basic_get(queue=client.queue, auto_ack=False)
        if method:
            try:
                sample: Any = json.loads(body.decode("utf-8"))
            except Exception:
                sample = body.decode("utf-8", errors="replace")
            report["sample"] = sample
            channel.basic_nack(method.delivery_tag, requeue=True)

        if args.purge:
            report["purged"] = {}
            for queue in (client.queue, client.dlq):
                result = channel.queue_purge(queue=queue)
                report["purged"][queue] = result.method.message_count

        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    sys.exit(main())
