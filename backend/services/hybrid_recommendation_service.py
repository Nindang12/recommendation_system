"""Hybrid recommendation pipeline: multi-source candidates, mask, score, rerank."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from repositories.auth_repo import AuthRepository
from services import provisional_status as st
from services.candidate_mask_service import CandidateMaskService
from services.embedding_candidate_service import EmbeddingCandidateService

logger = logging.getLogger(__name__)

SCORE_CAP_PATH_SUPPORTED = 1.0
SCORE_CAP_EMBEDDING_ONLY = 0.65
SCORE_CAP_FALLBACK_ONLY = 0.55
SCORE_CAP_EMBEDDING_UNVERIFIED = 0.50
SCORE_CAP_FALLBACK_UNVERIFIED = 0.45
SCORE_CAP_NO_SIGNAL = 0.40

WEIGHT_PGPR = 0.62
WEIGHT_PATH = 0.18
WEIGHT_EMBEDDING = 0.12
WEIGHT_TOPIC = 0.08


class HybridRecommendationService:
    """Stage 1–4 hybrid ranking; mask/trust applied by RecommendationService after."""

    def __init__(
        self,
        auth_repo: Optional[AuthRepository] = None,
        mask_service: Optional[CandidateMaskService] = None,
        embedding_candidates: Optional[EmbeddingCandidateService] = None,
    ) -> None:
        self.auth_repo = auth_repo or AuthRepository()
        self.mask_service = mask_service or CandidateMaskService(self.auth_repo)
        self.embedding_candidates = embedding_candidates or EmbeddingCandidateService()

    def source_recommendation_context(self, source_type: str, source_id: str) -> Dict[str, Any]:
        entity = self.auth_repo.find_entity_by_id(source_type, source_id) or {}
        embedding = entity.get("embedding") or {}
        status = str(
            embedding.get("status")
            or entity.get("embedding_status")
            or st.EMBEDDING_PENDING
        )
        signal = embedding.get("signal")
        ready = self._embedding_usable(embedding)
        cold_start = not ready or status in {
            st.EMBEDDING_PENDING,
            st.EMBEDDING_QUEUED,
            st.EMBEDDING_PROCESSING,
            st.EMBEDDING_STALE,
            st.EMBEDDING_FAILED,
        }
        if status == st.EMBEDDING_STALE:
            mode = "fallback_until_embedding_recomputed"
            message = "Ho so vua thay doi, he thong dang cap nhat du lieu goi y."
        elif ready:
            mode = "hybrid_ready"
            message = None
        elif status == st.EMBEDDING_FAILED:
            mode = "fallback_until_embedding_ready"
            message = "Embedding that bai; he thong dang dung PGPR/Cypher fallback."
        elif status in {st.EMBEDDING_QUEUED, st.EMBEDDING_PROCESSING}:
            mode = "fallback_until_embedding_ready"
            message = f"Embedding dang o trang thai {status}; he thong dang dung PGPR/Cypher fallback."
        else:
            mode = "fallback_until_embedding_ready"
            message = "Embedding chua san sang; he thong dang dung PGPR/Cypher fallback."

        readiness = "not_ready"
        if ready:
            if (
                entity.get("entity_verification_status") == st.ENTITY_VERIFIED
                and entity.get("participation_scope") == st.SCOPE_PUBLIC
            ):
                readiness = "public_hybrid_ready"
            else:
                readiness = "personal_hybrid_ready"

        return {
            "embedding_status": status,
            "embedding_signal": signal,
            "cold_start": cold_start,
            "recommendation_mode": mode,
            "recommendation_readiness": readiness,
            "recommendation_message": message,
            "source_entity": entity,
        }

    async def build_hybrid_candidates(
        self,
        pgpr_candidates: List[Dict[str, Any]],
        *,
        source_type: str,
        source_id: str,
        target_type: str,
        limit: int,
        mode: str = "public",
        current_user_id: Optional[str] = None,
        source_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        src_ctx = source_context or self.source_recommendation_context(source_type, source_id)
        source_entity = src_ctx.get("source_entity") or {}
        pool_limit = max(limit * 4, 40)

        merged: Dict[str, Dict[str, Any]] = {}
        for rec in pgpr_candidates:
            cid = self._candidate_id(rec, target_type)
            if not cid:
                continue
            item = dict(rec)
            item["id"] = cid
            item.setdefault("candidate_sources", [])
            if "pgpr" not in item["candidate_sources"]:
                item["candidate_sources"].append("pgpr")
            item["pgpr_score"] = float(item.get("score", 0.0) or 0.0)
            merged[cid] = item

        if src_ctx.get("recommendation_mode") == "hybrid_ready":
            embedding_hits = self.embedding_candidates.nearest_candidates(
                source_type,
                source_id,
                target_type,
                limit=pool_limit,
                mode=mode,
                current_user_id=current_user_id,
                candidate_pool_limit=500,
            )
            for hit in embedding_hits:
                cid = str(hit.get("id") or "")
                if not cid:
                    continue
                if cid in merged:
                    merged[cid]["embedding_similarity"] = hit.get("embedding_similarity")
                    if "embedding" not in merged[cid].get("candidate_sources", []):
                        merged[cid].setdefault("candidate_sources", []).append("embedding")
                else:
                    item = dict(hit)
                    item.setdefault("candidate_sources", ["embedding"])
                    item["pgpr_score"] = 0.0
                    item.setdefault("reasoning_paths", [])
                    merged[cid] = item

        topic_hits = self._topic_skill_candidates(
            source_entity,
            target_type,
            exclude_ids=set(merged.keys()),
            limit=pool_limit,
        )
        for hit in topic_hits:
            cid = str(hit.get("id") or "")
            if not cid or cid in merged:
                if cid in merged:
                    merged[cid]["topic_overlap"] = max(
                        float(merged[cid].get("topic_overlap", 0.0) or 0.0),
                        float(hit.get("topic_overlap", 0.0) or 0.0),
                    )
                    if "topic_skill" not in merged[cid].get("candidate_sources", []):
                        merged[cid].setdefault("candidate_sources", []).append("topic_skill")
                continue
            item = dict(hit)
            item.setdefault("candidate_sources", ["topic_skill"])
            item["pgpr_score"] = 0.0
            item.setdefault("reasoning_paths", [])
            merged[cid] = item

        scored = [
            self._score_candidate(item, source_entity=source_entity, src_ctx=src_ctx)
            for item in merged.values()
        ]
        scored = self._rerank_and_cap(scored, limit=limit)
        for item in scored:
            item["embedding_status"] = src_ctx.get("embedding_status")
            item["cold_start"] = src_ctx.get("cold_start", False)
            item["recommendation_mode"] = src_ctx.get("recommendation_mode")
            item["recommendation_readiness"] = item.get("recommendation_readiness") or src_ctx.get(
                "recommendation_readiness"
            )
            if src_ctx.get("recommendation_message") and not item.get("recommendation_message"):
                item["recommendation_message"] = src_ctx.get("recommendation_message")

        return scored, src_ctx

    def _score_candidate(
        self,
        item: Dict[str, Any],
        *,
        source_entity: Dict[str, Any],
        src_ctx: Dict[str, Any],
    ) -> Dict[str, Any]:
        out = dict(item)
        target_type = str(out.get("type") or "").lower()
        target_id = str(out.get("id") or "")
        target_entity = self.auth_repo.find_entity_by_id(target_type, target_id) if target_id else {}

        paths = out.get("reasoning_paths") or []
        has_pgpr_paths = bool(paths) and not all(
            isinstance(p, dict) and p.get("source") == "cypher_fallback" for p in paths
        )
        pgpr_score = float(out.get("pgpr_score", out.get("score", 0.0)) or 0.0)
        emb_sim = float(out.get("embedding_similarity", 0.0) or 0.0)
        if emb_sim <= 0.0 and target_entity:
            emb_sim = self._pair_embedding_similarity(source_entity, target_entity)

        topic_overlap = float(out.get("topic_overlap", 0.0) or 0.0)
        if topic_overlap <= 0.0 and target_entity:
            topic_overlap = self.topic_overlap_score(source_entity, target_entity)
        out["topic_overlap"] = round(topic_overlap, 6)

        path_boost = min(0.18, len(paths) * 0.04) if paths else 0.0
        pgpr_part = pgpr_score * WEIGHT_PGPR
        path_part = path_boost * (WEIGHT_PATH / 0.18) if path_boost else 0.0
        emb_part = emb_sim * WEIGHT_EMBEDDING
        topic_part = topic_overlap * WEIGHT_TOPIC

        if has_pgpr_paths or (paths and pgpr_score > 0):
            combined = pgpr_part + path_part + emb_part + topic_part
            evidence = "path_supported"
            if emb_part > 0:
                method = "hybrid_embedding_path"
            else:
                method = str(out.get("scoring_method") or "pgpr_policy")
        elif emb_part > 0 and src_ctx.get("recommendation_mode") == "hybrid_ready":
            combined = emb_part + topic_part + pgpr_part * 0.35
            evidence = "embedding_only"
            method = "hybrid_embedding"
        else:
            combined = pgpr_part + topic_part + path_part
            evidence = "fallback_only"
            method = str(out.get("scoring_method") or "cypher_fallback")

        out["raw_score"] = round(combined, 6)
        out["score"] = out["raw_score"]
        out["evidence_level"] = evidence
        out["scoring_method"] = method
        out["hybrid_score_breakdown"] = {
            "pgpr": round(pgpr_part, 6),
            "path": round(path_part, 6),
            "embedding": round(emb_part, 6),
            "topic_overlap": round(topic_part, 6),
        }
        if evidence == "embedding_only" and not paths:
            out.setdefault(
                "fallback_reason",
                "Goi y dua tren embedding similarity; chua co reasoning path day du tren KG.",
            )
        return out

    def _rerank_and_cap(self, candidates: List[Dict[str, Any]], *, limit: int) -> List[Dict[str, Any]]:
        seen_names: Set[str] = set()
        out: List[Dict[str, Any]] = []
        sorted_items = sorted(
            candidates,
            key=lambda c: float(c.get("score", 0.0) or 0.0),
            reverse=True,
        )
        for item in sorted_items:
            name_key = str(item.get("name") or "").strip().lower()[:48]
            diversity_penalty = 0.02 if name_key and name_key in seen_names else 0.0
            if name_key:
                seen_names.add(name_key)
            score = float(item.get("score", 0.0) or 0.0) - diversity_penalty
            item = self._apply_evidence_cap(dict(item), score=score)
            out.append(item)
            if len(out) >= limit:
                break
        return out

    def _apply_evidence_cap(self, item: Dict[str, Any], *, score: float) -> Dict[str, Any]:
        evidence = str(item.get("evidence_level") or "fallback_only")
        provisional = bool(item.get("uses_provisional_data"))
        signal = item.get("embedding_signal")

        cap = SCORE_CAP_PATH_SUPPORTED
        if signal == st.EMBEDDING_SIGNAL_NONE:
            cap = min(cap, SCORE_CAP_NO_SIGNAL)
        elif evidence == "embedding_only":
            cap = SCORE_CAP_EMBEDDING_UNVERIFIED if provisional else SCORE_CAP_EMBEDDING_ONLY
        elif evidence == "fallback_only":
            cap = SCORE_CAP_FALLBACK_UNVERIFIED if provisional else SCORE_CAP_FALLBACK_ONLY

        if not (item.get("reasoning_paths") or []):
            cap = min(cap, SCORE_CAP_EMBEDDING_ONLY if evidence == "embedding_only" else SCORE_CAP_FALLBACK_ONLY)

        final = round(min(max(score, 0.0), cap), 6)
        item["score"] = final
        item["final_score"] = final
        return item

    def _topic_skill_candidates(
        self,
        source_entity: Dict[str, Any],
        target_type: str,
        *,
        exclude_ids: Set[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        if not source_entity:
            return []
        collection = self.auth_repo.get_entity_collection(target_type)
        if collection is None:
            return []
        id_field = self.auth_repo.entity_id_field(target_type)
        cursor = collection.find(
            {
                id_field: {"$nin": list(exclude_ids)},
                "embedding.status": st.EMBEDDING_READY,
            }
        ).limit(max(limit, 20))
        hits: List[Dict[str, Any]] = []
        for doc in cursor:
            overlap = self.topic_overlap_score(source_entity, doc)
            if overlap < 0.08:
                continue
            cid = str(doc.get(id_field) or doc.get("_id") or "")
            if not cid:
                continue
            name = self._display_name(target_type, doc)
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

    @staticmethod
    def topic_overlap_score(source: Dict[str, Any], target: Dict[str, Any]) -> float:
        left = HybridRecommendationService._token_set(source)
        right = HybridRecommendationService._token_set(target)
        if not left or not right:
            return 0.0
        inter = len(left & right)
        union = len(left | right)
        return inter / union if union else 0.0

    @staticmethod
    def _token_set(entity: Dict[str, Any]) -> Set[str]:
        tokens: Set[str] = set()
        for raw in HybridRecommendationService._extract_topics_skills(entity):
            norm = HybridRecommendationService._normalize_token(raw)
            if norm:
                tokens.add(norm)
        return tokens

    @staticmethod
    def _extract_topics_skills(entity: Dict[str, Any]) -> List[str]:
        out: List[str] = []
        paths = [
            entity.get("skills"),
            entity.get("technology"),
            entity.get("research_interests"),
            entity.get("research_topics"),
            entity.get("focus_topics"),
            (entity.get("basic_info") or {}).get("research_topics"),
            (entity.get("research_capacity") or {}).get("research_topics"),
            (entity.get("research_capacity") or {}).get("technology"),
            (entity.get("requirements_and_timeline") or {}).get("required_skills"),
            (entity.get("rd_profile") or {}).get("rd_focus_topics"),
            (entity.get("funding_strategy") or {}).get("funding_topics"),
        ]
        for value in paths:
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        out.append(
                            str(item.get("name") or item.get("id") or item.get("topic") or item.get("skill") or "")
                        )
                    else:
                        out.append(str(item))
            elif value:
                out.append(str(value))
        return [x for x in out if x]

    @staticmethod
    def _normalize_token(value: str) -> str:
        return "".join(ch.lower() for ch in str(value or "").strip() if ch.isalnum() or ch.isspace()).strip()

    @staticmethod
    def _display_name(entity_type: str, entity: Dict[str, Any]) -> str:
        if entity_type == "project":
            return str(
                entity.get("title")
                or entity.get("name")
                or (entity.get("basic_info") or {}).get("title")
                or ""
            )
        return str(entity.get("name") or (entity.get("basic_info") or {}).get("name") or entity.get("title") or "")

    @staticmethod
    def _candidate_id(rec: Dict[str, Any], target_type: str) -> str:
        return str(
            rec.get("id")
            or rec.get(f"{target_type}_id")
            or rec.get("expert_id")
            or rec.get("project_id")
            or rec.get("funder_id")
            or rec.get("enterprise_id")
            or ""
        )

    @staticmethod
    def _embedding_usable(embedding: Dict[str, Any]) -> bool:
        vector = embedding.get("vector")
        dimension = int(embedding.get("dimension") or 0)
        return (
            embedding.get("status") == st.EMBEDDING_READY
            and embedding.get("signal") != st.EMBEDDING_SIGNAL_NONE
            and bool(embedding.get("normalized"))
            and dimension == st.EMBEDDING_DIMENSION
            and isinstance(vector, list)
            and len(vector) == st.EMBEDDING_DIMENSION
            and any(float(v or 0.0) != 0.0 for v in vector)
        )

    def _pair_embedding_similarity(
        self,
        source_entity: Dict[str, Any],
        target_entity: Dict[str, Any],
    ) -> float:
        src_emb = source_entity.get("embedding") or {}
        tgt_emb = target_entity.get("embedding") or {}
        if not self._embedding_usable(src_emb) or not self._embedding_usable(tgt_emb):
            return 0.0
        return EmbeddingCandidateService.cosine_similarity(
            src_emb.get("vector") or [],
            tgt_emb.get("vector") or [],
        )
