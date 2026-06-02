from __future__ import annotations

import hashlib
import json
import math
import pickle
from pathlib import Path
from typing import Any, Dict, List

from .constants import DEFAULT_DIMENSION


class NodeFeatureEncoder:
    """Deterministic feature encoder for GraphSAGE candidate training."""

    def __init__(self, *, dimension: int = DEFAULT_DIMENSION, version: int = 1) -> None:
        self.dimension = int(dimension)
        self.version = int(version)

    def encode_node(self, node: Dict[str, Any]) -> List[float]:
        vector = [0.0] * self.dimension
        labels = [str(label) for label in node.get("labels") or []]
        props = node.get("properties") or {}
        weighted_tokens: List[tuple[str, float]] = []
        weighted_tokens.extend((f"label:{label}", 1.0) for label in labels)
        for key in ("name", "title", "label"):
            value = props.get(key)
            if value not in (None, "", [], {}):
                weighted_tokens.append((f"text:{value}", 0.7))
        for key in ("status", "entity_verification_status", "kg_sync_status", "visibility", "participation_scope"):
            value = props.get(key)
            if value not in (None, "", [], {}):
                weighted_tokens.append((f"{key}:{value}", 0.5))
        trust = _safe_float(props.get("trust_weight"), default=1.0)
        weighted_tokens.append((f"trust_bucket:{round(trust, 1):.1f}", 0.3))

        for token, weight in weighted_tokens:
            token_vector = self._text_vector(token)
            vector = [current + weight * item for current, item in zip(vector, token_vector)]
        return _l2_normalize(vector)

    def encode_snapshot(self, snapshot: Dict[str, Any]) -> Dict[str, List[float]]:
        return {node["element_id"]: self.encode_node(node) for node in snapshot.get("nodes") or []}

    def to_metadata(self) -> Dict[str, Any]:
        return {
            "encoder": "deterministic_hash_node_feature_encoder",
            "version": self.version,
            "dimension": self.dimension,
            "normalized": True,
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix.lower() == ".pkl":
            with path.open("wb") as f:
                pickle.dump(self.to_metadata(), f)
        else:
            path.write_text(json.dumps(self.to_metadata(), ensure_ascii=False, indent=2), encoding="utf-8")

    def _text_vector(self, text: str) -> List[float]:
        values: List[float] = []
        seed = text.strip().lower()
        counter = 0
        while len(values) < self.dimension:
            digest = hashlib.sha256(f"{seed}:{counter}".encode("utf-8")).digest()
            for byte in digest:
                values.append((byte / 127.5) - 1.0)
                if len(values) >= self.dimension:
                    break
            counter += 1
        return _l2_normalize(values)


def _safe_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _l2_normalize(vector: List[float]) -> List[float]:
    norm = math.sqrt(sum(item * item for item in vector))
    if norm <= 0:
        return vector
    return [item / norm for item in vector]

