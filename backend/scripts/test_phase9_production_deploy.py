"""Phase 9 production deployment artifact checks (no Docker required)."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
COMPOSE = ROOT / "docker-compose.production.yml"
ENV_EXAMPLE = ROOT / ".env.production.example"
OUT = BACKEND / "scripts" / "phase9_production_deploy_report.json"

REQUIRED_APP_SERVICES = {
    "backend",
    "frontend",
    "embedding_worker",
    "outbox_publisher",
}

OPTIONAL_INFRA_SERVICES = {"mongodb", "neo4j", "redis", "rabbitmq"}

REQUIRED_ENV_EXAMPLE_KEYS = {
    "MONGO_DB_NAME",
    "MONGO_USERNAME",
    "NEO4J_URI",
    "NEO4J_PASSWORD",
    "RABBITMQ_URL",
    "REDIS_URL",
    "EMBEDDING_MODEL_NAME",
    "APP_AUTH_SECRET",
    "NEXT_PUBLIC_API_BASE_URL",
    "CORS_ORIGINS",
}


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _parse_compose_services(text: str) -> set[str]:
    services: set[str] = set()
    in_services = False
    for line in text.splitlines():
        if line.strip() == "services:":
            in_services = True
            continue
        if in_services:
            if re.match(r"^[a-z]+\s*:", line) and not line.startswith(" "):
                break
            match = re.match(r"^  ([a-zA-Z0-9_-]+):\s*$", line)
            if match:
                services.add(match.group(1))
    return services


def _env_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        keys.add(line.split("=", 1)[0].strip())
    return keys


def main() -> int:
    report: dict = {"status": "passed", "checks": []}

    assert_true(COMPOSE.exists(), f"missing {COMPOSE}")
    compose_text = COMPOSE.read_text(encoding="utf-8")
    services = _parse_compose_services(compose_text)
    assert_true(REQUIRED_APP_SERVICES <= services, f"app services missing: {REQUIRED_APP_SERVICES - services}")
    assert_true("host.docker.internal" in compose_text or "INFRA_HOST" in compose_text, "external infra host mapping")
    assert_true("authSource=admin" in compose_text, "mongo authSource for admin user")
    assert_true("*app-volumes" in compose_text or "pgpr/pgpr_data" in compose_text, "pgpr_data mount on workers")
    assert_true('env_file:\n      - .env' in compose_text.replace("\r\n", "\n") or "env_file:" in compose_text and ".env" in compose_text, "uses root .env")
    assert_true("unless-stopped" in compose_text, "restart policy unless-stopped")
    assert_true("healthcheck:" in compose_text, "healthcheck blocks")
    infra_compose = ROOT / "docker-compose.infra.yml"
    assert_true(infra_compose.exists(), "optional docker-compose.infra.yml")
    infra_text = infra_compose.read_text(encoding="utf-8")
    infra_services = _parse_compose_services(infra_text)
    assert_true(OPTIONAL_INFRA_SERVICES <= infra_services, "infra compose services")
    assert_true("mongo_data:" in infra_text and "neo4j_data:" in infra_text, "infra volumes")
    report["checks"].append("docker_compose")

    assert_true((BACKEND / "Dockerfile").exists(), "backend Dockerfile")
    assert_true((ROOT / "frontend" / "Dockerfile").exists(), "frontend Dockerfile")
    assert_true((BACKEND / "scripts" / "worker_healthcheck.py").exists(), "worker healthcheck")
    assert_true((BACKEND / "scripts" / "system_inventory_check.py").exists(), "inventory script")
    report["checks"].append("dockerfiles")

    assert_true(ENV_EXAMPLE.exists(), ".env.production.example")
    env_keys = _env_keys(ENV_EXAMPLE)
    assert_true(REQUIRED_ENV_EXAMPLE_KEYS <= env_keys, f"env example keys missing: {REQUIRED_ENV_EXAMPLE_KEYS - env_keys}")
    root_env = ROOT / ".env"
    report["root_env_present"] = root_env.exists()
    report["checks"].append("env_example")

    assert_true((ROOT / "deploy" / "SYSTEM_INVENTORY.md").exists(), "system inventory doc")
    assert_true((ROOT / "deploy" / "backup" / "backup_all.ps1").exists(), "backup bundled")
    assert_true((ROOT / "deploy" / "backup" / "backup_external.ps1").exists(), "backup external")
    assert_true((ROOT / "deploy" / "backup" / "restore_mongo_sample.ps1").exists(), "mongo restore")
    assert_true((ROOT / "deploy" / "backup" / "restore_neo4j_sample.ps1").exists(), "neo4j restore")
    report["checks"].append("backup_scripts")

    next_cfg = (ROOT / "frontend" / "next.config.ts").read_text(encoding="utf-8")
    assert_true("standalone" in next_cfg, "next standalone output")
    report["checks"].append("frontend_standalone")

    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("PASS written scripts/phase9_production_deploy_report.json")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        OUT.write_text(json.dumps({"status": "failed", "error": str(exc)}, indent=2), encoding="utf-8")
        print(f"FAIL: {exc}")
        sys.exit(1)
