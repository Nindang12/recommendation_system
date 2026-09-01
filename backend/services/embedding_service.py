from __future__ import annotations

import hashlib
import math
import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

from services import provisional_status as st


@dataclass(frozen=True)
class EmbeddingResult:
    vector: List[float]
    normalized: bool
    signal: str
    model: str
    version: int
    dimension: int
    evidence_counts: Dict[str, int]


class EmbeddingService:
    """GraphSAGE-lite deterministic embedding builder.

    This is an inductive placeholder for Phase 3: it aggregates deterministic
    text vectors from source features and graph neighborhood context.
    """

    WEIGHTS = {
        "topics": 0.40,
        "skills": 0.30,
        "industries": 0.15,
        "location": 0.05,
        "graph": 0.10,
    }

    def __init__(self, dimension: int | None = None, model_name: str | None = None, version: int | None = None) -> None:
        self.dimension = dimension or int(os.getenv("EMBEDDING_DIMENSION", st.EMBEDDING_DIMENSION))
        self.model_name = model_name or os.getenv("EMBEDDING_MODEL_NAME", "graphsage_lite_v1")
        self.version = version if version is not None else int(os.getenv("EMBEDDING_VERSION", "1"))

    def build_graphsage_lite(self, features: Dict[str, Any]) -> EmbeddingResult:
        buckets = {
            "topics": self._texts(features.get("topics")),
            "skills": self._texts(features.get("skills")),
            "industries": self._texts(features.get("industries")),
            "location": self._texts(features.get("location")),
            "graph": self._texts(features.get("graph_relations")) + self._texts(features.get("graph_neighbor_labels")),
        }
        evidence_counts = {key: len(value) for key, value in buckets.items()}
        weighted_sum = [0.0] * self.dimension
        total_weight = 0.0

        for bucket, texts in buckets.items():
            if not texts:
                continue
            bucket_vector = self._mean_vectors([self._text_vector(text) for text in texts])
            weight = self.WEIGHTS[bucket]
            weighted_sum = [current + weight * item for current, item in zip(weighted_sum, bucket_vector)]
            total_weight += weight

        if total_weight <= 0:
            return EmbeddingResult(
                vector=[0.0] * self.dimension,
                normalized=False,
                signal=st.EMBEDDING_SIGNAL_NONE,
                model=self.model_name,
                version=self.version,
                dimension=self.dimension,
                evidence_counts=evidence_counts,
            )

        vector = [item / total_weight for item in weighted_sum]
        normalized = self._l2_normalize(vector)
        signal = st.EMBEDDING_SIGNAL_OK if sum(evidence_counts.values()) >= 2 else st.EMBEDDING_SIGNAL_LOW
        return EmbeddingResult(
            vector=normalized,
            normalized=True,
            signal=signal,
            model=self.model_name,
            version=self.version,
            dimension=self.dimension,
            evidence_counts=evidence_counts,
        )

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
        return self._l2_normalize(values)

    @staticmethod
    def _texts(values: Any) -> List[str]:
        if values in (None, "", [], {}):
            return []
        if not isinstance(values, list):
            values = [values]
        texts: List[str] = []
        for item in values:
            if item in (None, "", [], {}):
                continue
            if isinstance(item, dict):
                value = item.get("id") or item.get("name") or item.get("label") or item.get("title")
            else:
                value = item
            if value not in (None, "", [], {}) and str(value) not in texts:
                texts.append(str(value))
        return texts

    def _mean_vectors(self, vectors: Iterable[List[float]]) -> List[float]:
        vectors = list(vectors)
        if not vectors:
            return [0.0] * self.dimension
        out = [0.0] * self.dimension
        for vector in vectors:
            out = [current + item for current, item in zip(out, vector)]
        return [item / len(vectors) for item in out]

    @staticmethod
    def _l2_normalize(vector: List[float]) -> List[float]:
        norm = math.sqrt(sum(item * item for item in vector))
        if norm <= 0:
            return vector
        return [item / norm for item in vector]
