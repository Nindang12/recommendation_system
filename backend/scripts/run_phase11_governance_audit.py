from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def _load_project_env() -> None:
    # python-dotenv may preserve a UTF-8 BOM as part of the first key on Windows.
    # Parse with utf-8-sig first, then let dotenv handle ordinary files.
    for env_path in (ROOT.parent / ".env", ROOT / ".env"):
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            if not line or line.lstrip().startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip().strip('"').strip("'")
        load_dotenv(env_path, override=True)


_load_project_env()

from services.governance_audit_service import GovernanceAuditService


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Run read-only Phase 11 data governance audit.")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--max-age-days", type=int, default=30)
    parser.add_argument(
        "--output",
        default=str(ROOT / "scripts" / "phase11_governance_audit_report.json"),
    )
    args = parser.parse_args()

    report = GovernanceAuditService().full_audit(limit=args.limit, max_age_days=args.max_age_days)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(output_path), "summary": report["entities"]["summary"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
