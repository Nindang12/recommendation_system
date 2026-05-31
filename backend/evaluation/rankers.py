"""Recommendation rankers for offline evaluation."""
from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Optional, Tuple

from evaluation.pgpr_session import get_evaluation_recommender
from repositories.auth_repo import AuthRepository
from services.candidate_mask_service import CandidateMaskService
from services.embedding_candidate_service import EmbeddingCandidateService
from services.hybrid_recommendation_service import HybridRecommendationService
from services import provisional_status as st
from services.recommendation_service import RecommendationService


METHODS = (
    "random",
    "topic_overlap",
    "graph_heuristic",
    "pgpr_only",
    "embedding_only",
    "hybrid",
)


class EvaluationRankers:
    def __init__(
        self,
        *,
        auth_repo: Optional[AuthRepository] = None,
        recommendation_service: Optional[RecommendationService] = None,
        hybrid: Optional[HybridRecommendationService] = None,
        embedding: Optional[EmbeddingCandidateService] = None,
        seed: int = 42,
    ) -> None:
        self.repo = auth_repo or AuthRepository()
        self.rs = recommendation_service or RecommendationService(recommender=get_evaluation_recommender())
        self.hybrid = hybrid or HybridRecommendationService(self.repo)
        self.embedding = embedding or EmbeddingCandidateService()
        self.mask = CandidateMaskService(self.repo)
        self.rng = random.Random(seed)

    async def rank(
        self,
        method: str,
        *,
        source_type: str,
        source_id: str,
        target_type: str,
        limit: int,
        mode: str = "public",
        current_user_id: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], float]:
        started = time.perf_counter()
        method = str(method).lower()
        if method == "random":
            items = await self._rank_random(
                source_type=source_type,
                source_id=source_id,
                target_type=target_type,
                limit=limit,
                mode=mode,
                current_user_id=current_user_id,
            )
        elif method == "topic_overlap":
            items = await self._rank_topic_overlap(
                source_type=source_type,
                source_id=source_id,
                target_type=target_type,
                limit=limit,
                mode=mode,
                current_user_id=current_user_id,
            )
        elif method == "graph_heuristic":
            items = await self._rank_graph_heuristic(
                source_type=source_type,
                source_id=source_id,
                target_type=target_type,
                limit=limit,
                mode=mode,
                current_user_id=current_user_id,
            )
        elif method == "pgpr_only":
            items = await self._rank_pgpr_only(
                source_type=source_type,
                source_id=source_id,
                target_type=target_type,
                limit=limit,
                mode=mode,
                current_user_id=current_user_id,
            )
        elif method == "embedding_only":
            items = await self._rank_embedding_only(
                source_type=source_type,
                source_id=source_id,
                target_type=target_type,
                limit=limit,
                mode=mode,
                current_user_id=current_user_id,
            )
        elif method == "hybrid":
            items = await self._rank_hybrid(
                source_type=source_type,
                source_id=source_id,
                target_type=target_type,
                limit=limit,
                mode=mode,
                current_user_id=current_user_id,
            )
        else:
            raise ValueError(f"Unsupported evaluation method: {method}")

        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return items, elapsed_ms

    async def _candidate_universe(
        self,
        *,
        source_type: str,
        source_id: str,
        target_type: str,
        pool_limit: int,
        mode: str,
        current_user_id: Optional[str],
    ) -> List[Dict[str, Any]]:
        source_label = self.rs._to_policy_label(source_type)
        target_label = self.rs._to_policy_label(target_type)
        pgpr_pool = await self.rs._run_pgpr_dispatch(
            source_id=source_id,
            source_label=source_label,
            target_label=target_label,
            limit=max(pool_limit, 30),
        )
        src_ctx = self.hybrid.source_recommendation_context(source_type, source_id)
        source_entity = src_ctx.get("source_entity") or {}

        merged: Dict[str, Dict[str, Any]] = {}
        for rec in pgpr_pool:
            cid = self.hybrid._candidate_id(rec, target_type)
            if not cid:
                continue
            item = dict(rec)
            item["id"] = cid
            merged[cid] = item

        if src_ctx.get("recommendation_mode") == "hybrid_ready":
            for hit in self.embedding.nearest_candidates(
                source_type,
                source_id,
                target_type,
                limit=pool_limit,
                mode=mode,
                current_user_id=current_user_id,
            ):
                cid = str(hit.get("id") or "")
                if cid and cid not in merged:
                    merged[cid] = dict(hit)

        for hit in self._topic_overlap_hits(
            source_entity,
            target_type,
            exclude_ids=set(),
            limit=pool_limit,
            require_embedding_ready=False,
        ):
            cid = str(hit.get("id") or "")
            if cid and cid not in merged:
                merged[cid] = dict(hit)

        items = list(merged.values())
        for item in items:
            item.setdefault("type", target_type)
            item.setdefault("id", self.hybrid._candidate_id(item, target_type))
        return self.mask.filter_candidates(
            items,
            target_type=target_type,
            mode=mode,
            current_user_id=current_user_id,
        )

    async def _rank_random(self, **kwargs: Any) -> List[Dict[str, Any]]:
        limit = int(kwargs["limit"])
        universe = await self._candidate_universe(
            source_type=kwargs["source_type"],
            source_id=kwargs["source_id"],
            target_type=kwargs["target_type"],
            pool_limit=max(limit * 4, 40),
            mode=kwargs.get("mode") or "public",
            current_user_id=kwargs.get("current_user_id"),
        )
        shuffled = list(universe)
        self.rng.shuffle(shuffled)
        return shuffled[:limit]

    def _topic_overlap_hits(
        self,
        source_entity: Dict[str, Any],
        target_type: str,
        *,
        exclude_ids: Optional[set] = None,
        limit: int = 40,
        require_embedding_ready: bool = False,
    ) -> List[Dict[str, Any]]:
        if not source_entity:
            return []
        collection = self.repo.get_entity_collection(target_type)
        if collection is None:
            return []
        id_field = self.repo.entity_id_field(target_type)
        query: Dict[str, Any] = {id_field: {"$nin": list(exclude_ids or set())}}
        if require_embedding_ready:
            query["embedding.status"] = st.EMBEDDING_READY
        cursor = collection.find(query).limit(max(limit, 20))
        hits: List[Dict[str, Any]] = []
        for doc in cursor:
            overlap = self.hybrid.topic_overlap_score(source_entity, doc)
            if overlap < 0.08:
                continue
            cid = str(doc.get(id_field) or doc.get("_id") or "")
            if not cid:
                continue
            name = self.hybrid._display_name(target_type, doc)
            hits.append(
                {
                    "id": cid,
                    "name": name or cid,
                    "type": target_type,
                    "topic_overlap": round(overlap, 6),
                    "score": round(overlap * 0.5, 6),
                    "scoring_method": "topic_overlap",
                    "evidence_level": "fallback_only",
                }
            )
        hits.sort(key=lambda row: float(row.get("topic_overlap", 0.0) or 0.0), reverse=True)
        return hits[:limit]

    async def _rank_topic_overlap(self, **kwargs: Any) -> List[Dict[str, Any]]:
        limit = int(kwargs["limit"])
        source_type = kwargs["source_type"]
        source_id = kwargs["source_id"]
        target_type = kwargs["target_type"]
        source_entity = self.repo.find_entity_by_id(source_type, source_id) or {}
        hits = self._topic_overlap_hits(
            source_entity,
            target_type,
            exclude_ids=set(),
            limit=max(limit * 4, 40),
            require_embedding_ready=False,
        )
        hits.sort(key=lambda row: float(row.get("topic_overlap", 0.0) or 0.0), reverse=True)
        filtered = self.mask.filter_candidates(
            hits,
            target_type=target_type,
            mode=kwargs.get("mode") or "public",
            current_user_id=kwargs.get("current_user_id"),
        )
        return filtered[:limit]

    async def _rank_graph_heuristic(self, **kwargs: Any) -> List[Dict[str, Any]]:
        limit = int(kwargs["limit"])
        universe = await self._candidate_universe(
            source_type=kwargs["source_type"],
            source_id=kwargs["source_id"],
            target_type=kwargs["target_type"],
            pool_limit=max(limit * 4, 40),
            mode=kwargs.get("mode") or "public",
            current_user_id=kwargs.get("current_user_id"),
        )

        def _key(item: Dict[str, Any]) -> Tuple[int, float]:
            paths = item.get("reasoning_paths") or []
            path_count = len(paths)
            score = float(item.get("pgpr_score", item.get("score", 0.0)) or 0.0)
            return (path_count, score)

        ranked = sorted(universe, key=_key, reverse=True)
        return ranked[:limit]

    async def _rank_pgpr_only(self, **kwargs: Any) -> List[Dict[str, Any]]:
        limit = int(kwargs["limit"])
        source_type = kwargs["source_type"]
        target_type = kwargs["target_type"]
        source_id = kwargs["source_id"]
        source_label = self.rs._to_policy_label(source_type)
        target_label = self.rs._to_policy_label(target_type)
        pgpr = await self.rs._run_pgpr_dispatch(
            source_id=source_id,
            source_label=source_label,
            target_label=target_label,
            limit=max(limit * 3, 30),
        )
        for item in pgpr:
            item["scoring_method"] = item.get("scoring_method") or "pgpr_policy"
            item["evidence_level"] = item.get("evidence_level") or "path_supported"
        pgpr.sort(key=lambda row: float(row.get("score", 0.0) or 0.0), reverse=True)
        masked = self.rs._apply_provisional_rules(
            recommendations=pgpr,
            source_id=source_id,
            source_label=source_label,
            target_label=target_label,
            mode=kwargs.get("mode") or "public",
            current_user_id=kwargs.get("current_user_id"),
        )
        normalized = self.rs._normalize_recommendations(masked, target_label=target_label)
        return normalized[:limit]

    async def _rank_embedding_only(self, **kwargs: Any) -> List[Dict[str, Any]]:
        limit = int(kwargs["limit"])
        hits = self.embedding.nearest_candidates(
            kwargs["source_type"],
            kwargs["source_id"],
            kwargs["target_type"],
            limit=max(limit * 3, 30),
            mode=kwargs.get("mode") or "public",
            current_user_id=kwargs.get("current_user_id"),
        )
        return hits[:limit]

    async def _rank_hybrid(self, **kwargs: Any) -> List[Dict[str, Any]]:
        limit = int(kwargs["limit"])
        source_type = kwargs["source_type"]
        target_type = kwargs["target_type"]
        source_id = kwargs["source_id"]
        source_label = self.rs._to_policy_label(source_type)
        target_label = self.rs._to_policy_label(target_type)
        pgpr_pool = await self.rs._run_pgpr_dispatch(
            source_id=source_id,
            source_label=source_label,
            target_label=target_label,
            limit=max(limit * 3, 30),
        )
        src_ctx = self.hybrid.source_recommendation_context(source_type, source_id)
        ranked, _ = await self.hybrid.build_hybrid_candidates(
            pgpr_pool,
            source_type=source_type,
            source_id=source_id,
            target_type=target_type,
            limit=limit,
            mode=kwargs.get("mode") or "public",
            current_user_id=kwargs.get("current_user_id"),
            source_context=src_ctx,
        )
        masked = self.rs._apply_provisional_rules(
            recommendations=ranked,
            source_id=source_id,
            source_label=source_label,
            target_label=target_label,
            mode=kwargs.get("mode") or "public",
            current_user_id=kwargs.get("current_user_id"),
        )
        normalized = self.rs._normalize_recommendations(masked, target_label=target_label)
        normalized = self.rs._apply_scoring_metadata(normalized, source_context=src_ctx)
        return normalized[:limit]
