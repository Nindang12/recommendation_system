"""Print a quick inventory of implemented phases and key files."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"


def exists(rel: str) -> bool:
    return (ROOT / rel).exists() or (BACKEND / rel).exists()


def main() -> int:
    checks = {
        "phase0_baseline": exists("backend/scripts/baseline_recommendation_snapshot.py"),
        "phase1_embedding_metadata": exists("backend/services/embedding_metadata_service.py"),
        "phase2_rabbitmq": exists("backend/infrastructure/rabbitmq_client.py"),
        "phase3_worker": exists("backend/workers/embedding_worker.py"),
        "phase4_outbox": exists("backend/services/outbox_publisher_service.py"),
        "phase5_candidate_mask": exists("backend/services/candidate_mask_service.py"),
        "phase6_hybrid": exists("backend/services/hybrid_recommendation_service.py"),
        "phase7_admin": exists("backend/api/v1/endpoints/admin.py"),
        "phase8_evaluation": exists("backend/evaluation/runner.py"),
        "phase9_docker_compose": exists("docker-compose.production.yml"),
        "phase9_dockerfile_backend": exists("backend/Dockerfile"),
        "phase9_env_root": exists(".env"),
        "pgpr_data": exists("backend/pgpr/pgpr_data/vocab.json"),
    }
    api_endpoints = list((BACKEND / "api" / "v1" / "endpoints").glob("*.py"))
    report = {
        "status": "ok",
        "checks": checks,
        "api_endpoint_modules": sorted(p.stem for p in api_endpoints if p.name != "__init__.py"),
        "deploy_mode": "app-only + external Mongo/Neo4j/Redis/RabbitMQ (see deploy/SYSTEM_INVENTORY.md)",
    }
    out = BACKEND / "scripts" / "system_inventory_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"written {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
