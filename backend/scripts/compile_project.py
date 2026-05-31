"""Compile active backend Python files while excluding archived recovery scripts.

`scripts/restored_middle.py` is an old recovery artifact and is intentionally
excluded so Phase checks can compile the active codebase without failing on
unused archived content.
"""
from __future__ import annotations

import py_compile
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIRS = ["api", "core", "middleware", "models", "repositories", "services", "pgpr", "scripts"]
EXCLUDED = {
    ROOT / "scripts" / "restored_middle.py",
}


def iter_python_files() -> list[Path]:
    files: list[Path] = []
    for folder in DEFAULT_DIRS:
        base = ROOT / folder
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if path in EXCLUDED:
                continue
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
    print("excluded archived files:")
    for path in sorted(EXCLUDED):
        print(f"- {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
