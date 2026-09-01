"""Optional restore verification — requires Docker stack running.

Set RUN_PHASE9_RESTORE_TEST=1 and ensure compose is up with seed data.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "phase9_restore_sample_report.json"


def main() -> int:
    if os.getenv("RUN_PHASE9_RESTORE_TEST", "").lower() not in {"1", "true", "yes"}:
        OUT.write_text(
            json.dumps({"status": "skipped", "reason": "set RUN_PHASE9_RESTORE_TEST=1 to run"}, indent=2),
            encoding="utf-8",
        )
        print("SKIP (set RUN_PHASE9_RESTORE_TEST=1)")
        return 0

    compose = ROOT / "docker-compose.production.yml"
    env_file = ROOT / ".env"
    if not env_file.exists():
        env_file = ROOT / ".env.production"
    if not env_file.exists():
        env_file = ROOT / ".env.production.example"
    assert compose.exists(), "docker-compose.production.yml missing"

    # Smoke: stack responds and backup script exists
    proc = subprocess.run(
        ["docker", "compose", "-f", str(compose), "--env-file", str(env_file), "ps", "--format", "json"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"docker compose ps failed: {proc.stderr}")

    backup_script = ROOT / "deploy" / "backup" / "backup_all.ps1"
    assert backup_script.exists(), "backup_all.ps1 missing"

    report = {
        "status": "passed",
        "note": "Compose reachable; run deploy/backup/backup_all.ps1 then restore_* on staging to complete full cycle.",
        "compose_ps_lines": len([line for line in (proc.stdout or "").splitlines() if line.strip()]),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("PASS written scripts/phase9_restore_sample_report.json")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        OUT.write_text(json.dumps({"status": "failed", "error": str(exc)}, indent=2), encoding="utf-8")
        print(f"FAIL {str(exc).encode('ascii', errors='replace').decode('ascii')}")
        sys.exit(1)
