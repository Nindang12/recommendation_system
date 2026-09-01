"""Backend bridge to shared skill helpers in add_data."""
from __future__ import annotations

import sys
from pathlib import Path

_ADD_DATA = Path(__file__).resolve().parents[2] / "add_data"
if str(_ADD_DATA) not in sys.path:
    sys.path.insert(0, str(_ADD_DATA))

from skill_identity_utils import (  # noqa: E402
    build_skill_taxonomy_maps,
    canonical_skill_display,
    compact_skill_key,
    dedupe_skill_names,
    normalize_skill_dict,
    normalize_skill_key,
    resolve_skill_record,
    skill_id_from_name,
)

__all__ = [
    "build_skill_taxonomy_maps",
    "canonical_skill_display",
    "compact_skill_key",
    "dedupe_skill_names",
    "normalize_skill_dict",
    "normalize_skill_key",
    "resolve_skill_record",
    "skill_id_from_name",
]
