from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Dict, List, Set, Tuple

from .constants import DEFAULT_RANDOM_SEED


@dataclass
class GraphDataset:
    node_ids: List[str]
    node_features: Dict[str, List[float]]
    positive_edges: List[Tuple[str, str, str]]
    negative_edges: List[Tuple[str, str, str]]
    splits: Dict[str, Dict[str, List[Tuple[str, str, str]]]]
    stats: Dict[str, Any]


class GraphDatasetBuilder:
    """Build reproducible link-prediction data from a sanitized snapshot."""

    def __init__(self, *, random_seed: int = DEFAULT_RANDOM_SEED) -> None:
        self.random_seed = int(random_seed)

    def build(self, snapshot: Dict[str, Any], node_features: Dict[str, List[float]]) -> GraphDataset:
        node_ids = [node["element_id"] for node in snapshot.get("nodes") or []]
        existing: Set[Tuple[str, str]] = set()
        positive_edges: List[Tuple[str, str, str]] = []
        for edge in snapshot.get("edges") or []:
            source = str(edge.get("source"))
            target = str(edge.get("target"))
            rel_type = str(edge.get("type") or "RELATED_TO")
            if source in node_features and target in node_features:
                positive_edges.append((source, target, rel_type))
                existing.add((source, target))

        negative_edges = self._negative_sample(node_ids, existing, max(1, len(positive_edges)))
        splits = self._split(positive_edges, negative_edges)
        stats = {
            "node_count": len(node_ids),
            "positive_edges": len(positive_edges),
            "negative_edges": len(negative_edges),
            "random_seed": self.random_seed,
            "split_counts": {
                split: {
                    "positive": len(rows.get("positive") or []),
                    "negative": len(rows.get("negative") or []),
                }
                for split, rows in splits.items()
            },
        }
        return GraphDataset(
            node_ids=node_ids,
            node_features=node_features,
            positive_edges=positive_edges,
            negative_edges=negative_edges,
            splits=splits,
            stats=stats,
        )

    def _negative_sample(
        self,
        node_ids: List[str],
        existing: Set[Tuple[str, str]],
        target_count: int,
    ) -> List[Tuple[str, str, str]]:
        rng = random.Random(self.random_seed)
        if len(node_ids) < 2:
            return []
        negatives: List[Tuple[str, str, str]] = []
        attempts = 0
        max_attempts = max(100, target_count * 20)
        seen: Set[Tuple[str, str]] = set()
        while len(negatives) < target_count and attempts < max_attempts:
            source, target = rng.sample(node_ids, 2)
            pair = (source, target)
            attempts += 1
            if pair in existing or pair in seen:
                continue
            seen.add(pair)
            negatives.append((source, target, "NEGATIVE_SAMPLE"))
        return negatives

    def _split(
        self,
        positive_edges: List[Tuple[str, str, str]],
        negative_edges: List[Tuple[str, str, str]],
    ) -> Dict[str, Dict[str, List[Tuple[str, str, str]]]]:
        rng = random.Random(self.random_seed)
        positives = list(positive_edges)
        negatives = list(negative_edges)
        rng.shuffle(positives)
        rng.shuffle(negatives)
        return {
            "train": {
                "positive": positives[: int(len(positives) * 0.7)],
                "negative": negatives[: int(len(negatives) * 0.7)],
            },
            "val": {
                "positive": positives[int(len(positives) * 0.7) : int(len(positives) * 0.85)],
                "negative": negatives[int(len(negatives) * 0.7) : int(len(negatives) * 0.85)],
            },
            "test": {
                "positive": positives[int(len(positives) * 0.85) :],
                "negative": negatives[int(len(negatives) * 0.85) :],
            },
        }

