"""Compile active backend Python files."""
from __future__ import annotations

import py_compile
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIRS = ["api", "core", "middleware", "models", "repositories", "services", "pgpr", "ml", "scripts"]


def iter_python_files() -> list[Path]:
    files: list[Path] = []
    for folder in DEFAULT_DIRS:
        base = ROOT / folder
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            files.append(path)
    files.append(ROOT / "main.py")
    return sorted(set(files))


def main() -> int:
    failed: list[tuple[Path, str]] = []
    for path in iter_python_files():
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            failed.append((path, str(exc)))

    if failed:
        print(f"compile failed: {len(failed)} file(s)")
        for path, error in failed:
            print(f"- {path.relative_to(ROOT)}: {error}")
        return 1

    print(f"compile passed: {len(iter_python_files())} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
