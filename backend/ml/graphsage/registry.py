from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from .constants import DEFAULT_ACTIVE_MODEL, MODEL_STATUS_ACTIVE, MODEL_STATUS_CANDIDATE, MODEL_STATUSES


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ModelRegistry:
    """File-based model registry for offline candidate lifecycle."""

    def __init__(self, root: Path | str = Path("artifacts") / "models") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.active_pointer = self.root / "active_embedding_model.json"

    def ensure_active_pointer(self) -> Dict[str, Any]:
        if self.active_pointer.exists():
            return json.loads(self.active_pointer.read_text(encoding="utf-8"))
        payload = {
            "active_model": DEFAULT_ACTIVE_MODEL,
            "active_version": 1,
            "model_status": MODEL_STATUS_ACTIVE,
            "promoted_at": None,
            "fallback_model": DEFAULT_ACTIVE_MODEL,
            "updated_at": utc_now_iso(),
        }
        self.active_pointer.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    def candidate_dir(self, model_name: str) -> Path:
        path = self.root / model_name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_metadata(self, model_name: str, metadata: Dict[str, Any]) -> Path:
        status = metadata.get("model_status", MODEL_STATUS_CANDIDATE)
        if status not in MODEL_STATUSES:
            raise ValueError(f"Invalid model_status: {status}")
        output = self.candidate_dir(model_name) / "metadata.json"
        payload = {
            **metadata,
            "model_name": model_name,
            "updated_at": utc_now_iso(),
        }
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return output

    def write_evaluation_report(self, model_name: str, report: Dict[str, Any]) -> Path:
        output = self.candidate_dir(model_name) / "evaluation_report.json"
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return output

