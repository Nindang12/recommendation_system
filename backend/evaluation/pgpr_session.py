"""Shared PGPR recommender for offline evaluation (avoid repeated init per rank call)."""
from __future__ import annotations

from typing import Optional

from pgpr.pgpr_recommendation import PGPRRecommender
from repositories.pgpr_graph_repo import PGPRGraphRepository

_shared_recommender: Optional[PGPRRecommender] = None


def get_evaluation_recommender() -> PGPRRecommender:
    global _shared_recommender
    if _shared_recommender is None:
        _shared_recommender = PGPRRecommender(
            graph_repo=PGPRGraphRepository(),
            max_path_length=5,
            gamma=0.99,
            top_k_paths=10,
            enable_cache=True,
        )
    return _shared_recommender


def close_evaluation_recommender() -> None:
    global _shared_recommender
    if _shared_recommender is not None:
        try:
            _shared_recommender.close()
        except Exception:
            pass
        _shared_recommender = None
