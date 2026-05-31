from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class RabbitMQPublishResult:
    ok: bool
    status: str
    error: Optional[str] = None


class RabbitMQClient:
    """Small optional RabbitMQ adapter.

    The client imports pika lazily so the API can still boot in environments
    where RabbitMQ support has not been installed yet.
    """

    def __init__(
        self,
        url: Optional[str] = None,
        exchange: Optional[str] = None,
        queue: Optional[str] = None,
        routing_key: Optional[str] = None,
        dlq: Optional[str] = None,
    ) -> None:
        self.url = url or os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
        self.exchange = exchange or os.getenv("RABBITMQ_EXCHANGE", "kg.events")
        self.queue = queue or os.getenv("RABBITMQ_EMBEDDING_QUEUE", "embedding.jobs")
        self.routing_key = routing_key or os.getenv("RABBITMQ_EMBEDDING_ROUTING_KEY", self.queue)
        self.dlq = dlq or os.getenv("RABBITMQ_EMBEDDING_DLQ", "embedding.jobs.dlq")

    def health(self) -> str:
        try:
            connection = self._connect()
            try:
                channel = connection.channel()
                self._declare(channel)
                return "connected"
            finally:
                connection.close()
        except Exception:
            return "unavailable_optional"

    def publish_json(self, payload: Dict[str, Any]) -> RabbitMQPublishResult:
        try:
            pika = self._pika()
            connection = self._connect()
            try:
                channel = connection.channel()
                self._declare(channel)
                body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
                channel.basic_publish(
                    exchange=self.exchange,
                    routing_key=self.routing_key,
                    body=body,
                    properties=pika.BasicProperties(
                        content_type="application/json",
                        delivery_mode=2,
                    ),
                )
                return RabbitMQPublishResult(ok=True, status="published")
            finally:
                connection.close()
        except Exception as exc:  # noqa: BLE001
            return RabbitMQPublishResult(ok=False, status="unavailable_optional", error=str(exc))

    def peek_dlq_sample(self) -> Dict[str, Any]:
        """Peek one DLQ message without removing it (requeue after read)."""
        try:
            connection = self._connect()
            try:
                channel = connection.channel()
                self._declare(channel)
                method, _props, body = channel.basic_get(queue=self.dlq, auto_ack=False)
                if not method:
                    return {"available": False}
                raw_size = len(body)
                try:
                    payload = json.loads(body.decode("utf-8"))
                except Exception as exc:  # noqa: BLE001
                    payload = {"raw_preview": body.decode("utf-8", errors="replace")[:240], "parse_error": str(exc)}
                channel.basic_nack(method.delivery_tag, requeue=True)
                return {
                    "available": True,
                    "sample": self._sanitize_dlq_sample(payload, raw_size_bytes=raw_size),
                }
            finally:
                connection.close()
        except Exception as exc:  # noqa: BLE001
            return {"available": False, "error": str(exc)}

    @staticmethod
    def _sanitize_dlq_sample(payload: Any, *, raw_size_bytes: int = 0) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return {
                "error_summary": str(payload)[:120],
                "raw_size_bytes": raw_size_bytes,
            }
        error_summary = None
        if payload.get("parse_error"):
            error_summary = f"malformed_json: {payload.get('parse_error')}"
        elif payload.get("raw_preview"):
            error_summary = "malformed_json"
        return {
            "event_type": payload.get("event_type"),
            "entity_type": payload.get("entity_type"),
            "entity_id": payload.get("entity_id"),
            "event_id": payload.get("event_id"),
            "job_id": payload.get("job_id"),
            "error_summary": error_summary,
            "raw_size_bytes": raw_size_bytes,
        }

    def _declare(self, channel: Any) -> None:
        channel.exchange_declare(exchange=self.exchange, exchange_type="direct", durable=True)
        channel.queue_declare(queue=self.dlq, durable=True)
        channel.queue_declare(
            queue=self.queue,
            durable=True,
            arguments={"x-dead-letter-exchange": "", "x-dead-letter-routing-key": self.dlq},
        )
        channel.queue_bind(exchange=self.exchange, queue=self.queue, routing_key=self.routing_key)

    def _connect(self) -> Any:
        pika = self._pika()
        parameters = pika.URLParameters(self.url)
        parameters.socket_timeout = 3
        parameters.blocked_connection_timeout = 3
        return pika.BlockingConnection(parameters)

    @staticmethod
    def _pika() -> Any:
        import pika  # type: ignore

        return pika
