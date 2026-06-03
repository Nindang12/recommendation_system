from __future__ import annotations

import os
from pathlib import Path


def _load_env_file(env_path: Path, *, override: bool) -> None:
    try:
        text = env_path.read_text(encoding="utf-8-sig")
    except OSError:
        return

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        if override or key not in os.environ:
            os.environ[key] = value


def load_project_env() -> None:
    """Load backend env files from stable project paths.

    The app is often started from ``backend/`` while the shared ``.env`` lives
    one directory above it. Relying on python-dotenv auto-discovery can miss
    that file, so we load both known locations explicitly.
    """

    backend_dir = Path(__file__).resolve().parents[1]
    project_root = backend_dir.parent

    for env_path in (project_root / ".env",):
        if env_path.exists():
            _load_env_file(env_path, override=False)
    backend_env = backend_dir / ".env"
    if backend_env.exists():
        _load_env_file(backend_env, override=True)
