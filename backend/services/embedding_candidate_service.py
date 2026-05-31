from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from repositories.embedding_repo import EmbeddingRepository
from services import provisional_status as st
from services.candidate_mask_service import CandidateMaskService


class EmbeddingCandidateService:
    """Find candidate entities by embedding cosine similarity for cold-start MVP."""

    def __init__(
        self,
        embedding_repo: Optional[EmbeddingRepository] = None,
        mask_service: Optional[CandidateMaskService] = None,
    ) -> None:
        self.embedding_repo = embedding_repo or EmbeddingRepository()
        self.mask_service = mask_service or CandidateMaskService(self.embedding_repo.auth_repo)

    def nearest_candidates(
        self,
        source_type: str,
        source_id: str,
        target_type: str,
        *,
        limit: int = 10,
        mode: str = "public",
        current_user_id: Optional[str] = None,
        candidate_pool_limit: int = 500,
        admin_debug: bool = False,
    ) -> List[Dict[str, Any]]:
        source = self.embedding_repo.find_entity(source_type, source_id) or {}
        source_embedding = source.get("embedding") or {}
        source_vector = source_embedding.get("vector")
        if not self._usable_embedding(source_embedding):
            return []

        raw_candidates = self.embedding_repo.list_ready_embeddings(
            target_type,
            model=source_embedding.get("model"),
            limit=candidate_pool_limit,
        )
        scored: List[Dict[str, Any]] = []
        for row in raw_candidates:
            candidate_id = str(row.get("entity_id") or "")
            if not candidate_id or candidate_id == str(source_id):
                continue
            candidate_vector = row.get("vector")
            if not self._usable_embedding(row):
                continue
            similarity = self.cosine_similarity(source_vector, candidate_vector)
            candidate = self.embedding_repo.find_entity(target_type, candidate_id) or {}
            name = self._display_name(target_type, candidate)
            scored.append(
                {
                    "id": candidate_id,
                    "name": name or candidate_id,
                    "type": str(target_type).lower(),
                    "score": round(max(0.0, similarity), 6),
                    "embedding_similarity": round(similarity, 6),
                    "scoring_method": "embedding_candidate",
                    "evidence_level": "embedding_only",
                    "cold_start": True,
                    "embedding_status": row.get("status") or st.EMBEDDING_READY,
                    "embedding_signal": row.get("signal"),
                    "recommendation_readiness": self._readiness(candidate),
                }
            )

        filtered = self.mask_service.filter_candidates(
            scored,
            target_type=str(target_type).lower(),
            mode=mode,
            current_user_id=current_user_id,
            admin_debug=admin_debug,
        )
        filtered.sort(key=lambda item: float(item.get("embedding_similarity", 0.0) or 0.0), reverse=True)
        return filtered[: max(1, limit)]

    @staticmethod
    def cosine_similarity(left: List[float], right: List[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        dot = sum(float(a) * float(b) for a, b in zip(left, right))
        left_norm = math.sqrt(sum(float(a) * float(a) for a in left))
        right_norm = math.sqrt(sum(float(b) * float(b) for b in right))
        if left_norm == 0.0 or right_norm == 0.0:
            return 0.0
        return dot / (left_norm * right_norm)

    @staticmethod
    def _usable_embedding(embedding: Dict[str, Any]) -> bool:
        vector = embedding.get("vector")
        dimension = int(embedding.get("dimension") or 0)
        return (
            embedding.get("status") == st.EMBEDDING_READY
            and embedding.get("signal") != st.EMBEDDING_SIGNAL_NONE
            and bool(embedding.get("normalized"))
            and dimension == st.EMBEDDING_DIMENSION
            and isinstance(vector, list)
            and len(vector) == st.EMBEDDING_DIMENSION
            and any(float(item or 0.0) != 0.0 for item in vector)
        )

    @staticmethod
    def _display_name(entity_type: str, entity: Dict[str, Any]) -> str:
        if not entity:
            return ""
        if entity_type == "project":
            return str(entity.get("title") or entity.get("name") or (entity.get("basic_info") or {}).get("title") or "")
        return str(entity.get("name") or (entity.get("basic_info") or {}).get("name") or entity.get("title") or "")

    @staticmethod
    def _readiness(entity: Dict[str, Any]) -> str:
        if not entity:
            return "not_ready"
        embedding = entity.get("embedding") or {}
        if embedding.get("status") != st.EMBEDDING_READY:
            return "fallback_only"
        if entity.get("entity_verification_status") == st.ENTITY_VERIFIED and entity.get("participation_scope") == st.SCOPE_PUBLIC:
            return "public_hybrid_ready"
        return "personal_hybrid_ready"
