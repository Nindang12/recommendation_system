from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
REPORT_PATH = BACKEND / "scripts" / "phase12_security_config_report.json"


def _load_env_file(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _effective_env() -> Dict[str, str]:
    merged: Dict[str, str] = {}
    for path in [BACKEND / ".env.example", ROOT / ".env", BACKEND / ".env"]:
        merged.update(_load_env_file(path))
    for key, value in os.environ.items():
        if key.startswith(("APP_", "ROOT_ADMIN_", "MONGO", "NEO4J", "RABBITMQ", "CORS", "FRONTEND", "RATE_LIMIT")):
            merged[key] = value
    return merged


def _severity(issue: str) -> str:
    if issue in {
        "auth_secret_default",
        "root_admin_password_default",
        "root_admin_password_weak",
        "cors_all_origins",
    }:
        return "high"
    if issue in {"neo4j_default_password", "rabbitmq_guest_credentials", "rate_limit_disabled"}:
        return "medium"
    return "low"


def _add_issue(issues: List[Dict[str, Any]], code: str, message: str, recommendation: str) -> None:
    issues.append(
        {
            "code": code,
            "severity": _severity(code),
            "message": message,
            "recommendation": recommendation,
        }
    )


def main() -> int:
    env = _effective_env()
    issues: List[Dict[str, Any]] = []

    auth_secret = env.get("APP_AUTH_SECRET", "")
    if not auth_secret or auth_secret == "dev-change-me":
        _add_issue(
            issues,
            "auth_secret_default",
            "APP_AUTH_SECRET is missing or still uses the development default.",
            "Set APP_AUTH_SECRET to a random production secret with at least 32 characters.",
        )
    elif len(auth_secret) < 32:
        _add_issue(
            issues,
            "auth_secret_short",
            "APP_AUTH_SECRET is shorter than the recommended production length.",
            "Use a random APP_AUTH_SECRET with at least 32 characters.",
        )

    root_password = env.get("ROOT_ADMIN_PASSWORD", "")
    if root_password == "Admin@123456":
        _add_issue(
            issues,
            "root_admin_password_default",
            "ROOT_ADMIN_PASSWORD still uses the scaffold default.",
            "Rotate ROOT_ADMIN_PASSWORD before any shared demo or production deployment.",
        )
    elif root_password and len(root_password) < 12:
        _add_issue(
            issues,
            "root_admin_password_weak",
            "ROOT_ADMIN_PASSWORD is shorter than 12 characters.",
            "Use a long random password and store it outside source control.",
        )

    neo4j_password = env.get("NEO4J_PASSWORD", "")
    if neo4j_password in {"password", "your_password", "neo4j", ""}:
        _add_issue(
            issues,
            "neo4j_default_password",
            "NEO4J_PASSWORD appears to be empty or a placeholder/default value.",
            "Set a non-default Neo4j password in the root .env used by deploy.",
        )

    rabbitmq_url = env.get("RABBITMQ_URL", "")
    if "guest:guest@" in rabbitmq_url and os.getenv("ENVIRONMENT", "development") == "production":
        _add_issue(
            issues,
            "rabbitmq_guest_credentials",
            "Production environment is using RabbitMQ guest credentials.",
            "Create a dedicated RabbitMQ user/password for production.",
        )

    cors_origins = env.get("CORS_ORIGINS", "")
    if "*" in cors_origins.split(","):
        _add_issue(
            issues,
            "cors_all_origins",
            "CORS_ORIGINS allows all origins.",
            "Use explicit frontend origins only.",
        )

    if env.get("RATE_LIMIT_ENABLED", "true").strip().lower() in {"0", "false", "no", "off"}:
        _add_issue(
            issues,
            "rate_limit_disabled",
            "RATE_LIMIT_ENABLED is disabled.",
            "Keep RATE_LIMIT_ENABLED=true for shared demo and production environments.",
        )

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checked_files": [
            str(BACKEND / ".env.example"),
            str(ROOT / ".env"),
            str(BACKEND / ".env"),
        ],
        "issue_count": len(issues),
        "by_severity": {
            severity: sum(1 for issue in issues if issue["severity"] == severity)
            for severity in ["high", "medium", "low"]
        },
        "issues": issues,
        "secrets_redacted": True,
    }
    REPORT_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
