"""Verify Phase 3 worker output for the preflight seed jobs."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from infrastructure.rabbitmq_client import RabbitMQClient  # noqa: E402
from repositories.auth_repo import AuthRepository  # noqa: E402
from repositories.pgpr_graph_repo import PGPRGraphRepository  # noqa: E402
from models.events import EmbeddingEvent  # noqa: E402
from services.embedding_service import EmbeddingService  # noqa: E402
from workers.embedding_worker import EmbeddingWorker  # noqa: E402


SEED = Path("scripts") / "phase3_preflight_jobs.json"
OUT = Path("scripts") / "phase3_worker_result_check.json"


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def queue_state() -> dict[str, Any]:
    client = RabbitMQClient()
    connection = client._connect()
    try:
        channel = connection.channel()
        client._declare(channel)
        main = channel.queue_declare(queue=client.queue, durable=True, passive=True)
        dlq = channel.queue_declare(queue=client.dlq, durable=True, passive=True)
        return {
            client.queue: main.method.message_count,
            client.dlq: dlq.method.message_count,
        }
    finally:
        connection.close()


def entity_embedding_summary(repo: AuthRepository, entity_type: str, entity_id: str) -> dict[str, Any]:
    doc = repo.find_entity_by_id(entity_type, entity_id) or {}
    embedding = doc.get("embedding") or {}
    vector = embedding.get("vector") or []
    norm = math.sqrt(sum(float(item) * float(item) for item in vector)) if vector else 0.0
    return {
        "status": embedding.get("status"),
        "top_level": doc.get("embedding_status"),
        "model": embedding.get("model"),
        "version": embedding.get("version"),
        "dimension": embedding.get("dimension"),
        "signal": embedding.get("signal"),
        "normalized": embedding.get("normalized"),
        "vector_len": len(vector),
        "vector_norm": round(norm, 6),
        "last_processed_at": str(embedding.get("last_processed_at")),
        "evidence_counts": embedding.get("evidence_counts"),
    }


def neo4j_embedding_summary(graph: PGPRGraphRepository, entity_type: str, entity_id: str) -> dict[str, Any]:
    label = PGPRGraphRepository._safe_label(entity_type)
    id_prop = PGPRGraphRepository._id_prop(label)
    rows = graph.run_read(
        f"""
        MATCH (n:{label} {{{id_prop}: $entity_id}})
        RETURN n.embedding_status AS status,
               n.embedding_model AS model,
               n.embedding_version AS version,
               n.embedding_dimension AS dimension,
               n.embedding_signal AS signal,
               size(n.embedding_vector) AS vector_len
        LIMIT 1
        """,
        entity_id=entity_id,
    )
    return dict(rows[0]) if rows else {}


def main() -> int:
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    repo = AuthRepository()
    graph = PGPRGraphRepository()
    try:
        report: dict[str, Any] = {"queue": queue_state(), "entities": {}}
        targets = {
            "expert": seed["entity_id"],
            "project": seed["project_id"],
        }
        for entity_type, entity_id in targets.items():
            mongo = entity_embedding_summary(repo, entity_type, entity_id)
            neo4j = neo4j_embedding_summary(graph, entity_type, entity_id)
            report["entities"][entity_type] = {
                "entity_id": entity_id,
                "mongo": mongo,
                "neo4j": neo4j,
            }
            assert_true(mongo["status"] == "ready", f"{entity_type} Mongo embedding not ready: {mongo}")
            assert_true(mongo["top_level"] == "ready", f"{entity_type} top-level embedding_status mismatch: {mongo}")
            assert_true(mongo["dimension"] == 128, f"{entity_type} dimension mismatch: {mongo}")
            assert_true(mongo["vector_len"] == 128, f"{entity_type} vector length mismatch: {mongo}")
            assert_true(abs(float(mongo["vector_norm"]) - 1.0) < 0.001, f"{entity_type} vector not normalized: {mongo}")
            assert_true(neo4j.get("status") == "ready", f"{entity_type} Neo4j embedding not ready: {neo4j}")
            assert_true(neo4j.get("vector_len") == 128, f"{entity_type} Neo4j vector length mismatch: {neo4j}")

        no_signal = EmbeddingService().build_graphsage_lite({})
        assert_true(no_signal.signal == "no_signal", f"empty features should be no_signal: {no_signal}")
        assert_true(no_signal.vector == [0.0] * no_signal.dimension, "no_signal vector should be zero-vector")
        report["no_signal_direct_test"] = {
            "signal": no_signal.signal,
            "dimension": no_signal.dimension,
            "normalized": no_signal.normalized,
        }

        expert_before_obsolete = entity_embedding_summary(repo, "expert", seed["entity_id"])
        obsolete_event = EmbeddingEvent(
            event_id=seed["entity_embedding"]["last_event_id"],
            job_id=seed["entity_embedding"]["job_id"],
            event_type="kg.entity.created",
            entity_type="expert",
            entity_id=seed["entity_id"],
            user_id=seed["user_id"],
            source="phase3_obsolete_test",
            kg_sync_status="synced_unverified",
            entity_verification_status="unverified",
            embedding_version=0,
            embedding_source_hash=seed["entity_embedding"]["source_hash"],
        )
        try:
            EmbeddingWorker(repo=repo, graph_repo=graph).process_event(obsolete_event)
            raise AssertionError("obsolete ready event should be skipped")
        except ValueError as exc:
            assert_true("already ready" in str(exc), f"unexpected obsolete error: {exc}")
        expert_after_obsolete = entity_embedding_summary(repo, "expert", seed["entity_id"])
        assert_true(
            expert_after_obsolete["status"] == expert_before_obsolete["status"] == "ready",
            f"obsolete event changed status: before={expert_before_obsolete} after={expert_after_obsolete}",
        )
        report["obsolete_event_test"] = {
            "before": expert_before_obsolete,
            "after": expert_after_obsolete,
        }

        assert_true(report["queue"].get("embedding.jobs") == 0, f"embedding.jobs not empty: {report['queue']}")
        assert_true(report["queue"].get("embedding.jobs.dlq") == 0, f"embedding.jobs.dlq not empty: {report['queue']}")
        report["status"] = "passed"
        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"PASS written {OUT}")
        return 0
    finally:
        graph.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        OUT.write_text(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"FAIL {exc}")
        sys.exit(1)
