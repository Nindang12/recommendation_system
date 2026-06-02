from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from models.canonical_taxonomy import (
    canonicalize_industry,
    canonicalize_skill,
    canonicalize_topic,
    normalize_text,
)
from services import provisional_status as st
from services.embedding_metadata_service import EmbeddingMetadataService


@dataclass
class DataQualityResult:
    score: float
    level: str
    missing_fields: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    signals: Dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": round(max(0.0, min(1.0, self.score)), 4),
            "level": self.level,
            "missing_fields": self.missing_fields,
            "warnings": self.warnings,
            "signals": self.signals,
            "updated_at": self.updated_at,
        }


class DataQualityService:
    """Compute a deterministic quality score for entity/project governance."""

    def __init__(self, taxonomy_aliases: Optional[Dict[str, Set[str]]] = None) -> None:
        self.taxonomy_aliases = taxonomy_aliases or {}

    def evaluate(self, entity_type: str, entity: Dict[str, Any]) -> Dict[str, Any]:
        entity_type = str(entity_type or "").lower()
        payload = EmbeddingMetadataService.source_payload(entity_type, entity)
        topics = self._as_list(payload.get("research_topics"))
        skills = self._as_list(payload.get("skills"))
        industries = self._as_list(payload.get("industry"))
        location = payload.get("location") if isinstance(payload.get("location"), dict) else {}
        relationships = self._as_list(payload.get("relevant_relationship_ids"))
        embedding = entity.get("embedding") if isinstance(entity.get("embedding"), dict) else {}

        missing: List[str] = []
        warnings: List[str] = []
        score = 0.1

        score += self._presence_score("research_topics", topics, 0.22, missing)
        score += self._presence_score("skills_or_technology", skills, 0.18, missing)
        score += self._presence_score("location", self._location_tokens(location), 0.12, missing)
        score += self._presence_score("industry_or_sector", industries, 0.12, missing)
        score += min(len(relationships), 3) * 0.03

        verification_status = entity.get("entity_verification_status") or st.ENTITY_VERIFIED
        kg_status = entity.get("kg_sync_status") or st.KG_SYNCED_VERIFIED
        scope = entity.get("participation_scope") or st.SCOPE_PUBLIC
        trust_weight = float(entity.get("trust_weight", 1.0) or 1.0)

        if verification_status == st.ENTITY_VERIFIED:
            score += 0.12
        elif verification_status == st.ENTITY_REJECTED:
            score -= 0.4
            warnings.append("entity_rejected")
        else:
            warnings.append("entity_unverified")

        if kg_status == st.KG_SYNCED_VERIFIED:
            score += 0.08
        elif kg_status == st.KG_SYNCED_UNVERIFIED:
            score += 0.03
            warnings.append("kg_synced_unverified")
        elif kg_status == st.KG_MERGE_REQUIRED:
            score -= 0.18
            warnings.append("merge_required")
        elif kg_status in {st.KG_SYNC_FAILED, st.KG_SYNC_PARTIAL, st.KG_NOT_SYNCED}:
            score -= 0.08
            warnings.append(f"kg_{kg_status}")
        elif kg_status in {st.KG_DISABLED, st.KG_REJECTED}:
            score -= 0.35
            warnings.append(f"kg_{kg_status}")

        if scope == st.SCOPE_OWNER_ONLY:
            score -= 0.05
            warnings.append("owner_only")
        elif scope == st.SCOPE_DISABLED:
            score -= 0.3
            warnings.append("scope_disabled")

        if trust_weight < 0.5:
            score -= 0.1
            warnings.append("low_trust_weight")
        elif trust_weight >= 1.0:
            score += 0.04

        embedding_status = embedding.get("status")
        embedding_signal = embedding.get("signal")
        if embedding_status == st.EMBEDDING_READY and embedding_signal != st.EMBEDDING_SIGNAL_NONE:
            score += 0.06
        elif embedding_status in {st.EMBEDDING_STALE, st.EMBEDDING_FAILED}:
            score -= 0.06
            warnings.append(f"embedding_{embedding_status}")
        elif embedding_signal == st.EMBEDDING_SIGNAL_NONE:
            score -= 0.08
            warnings.append("embedding_no_signal")

        duplicate_candidates = entity.get("duplicate_candidates") or []
        if duplicate_candidates:
            score -= 0.12
            warnings.append("duplicate_candidates")
        if entity.get("matched_existing_entity_id"):
            score += 0.03

        for category, values in (
            ("topic", topics),
            ("skill", skills),
            ("industry", industries),
        ):
            unmapped = self._unmapped_values(values, category)
            if unmapped:
                warnings.append(f"unmapped_{category}:{','.join(unmapped[:5])}")
                score -= min(0.08, 0.02 * len(unmapped))

        score = max(0.0, min(1.0, score))
        result = DataQualityResult(
            score=score,
            level=self._level(score),
            missing_fields=missing,
            warnings=self._dedupe(warnings),
            signals={
                "topic_count": len(topics),
                "skill_count": len(skills),
                "industry_count": len(industries),
                "relationship_count": len(relationships),
                "has_location": bool(self._location_tokens(location)),
                "entity_verification_status": verification_status,
                "kg_sync_status": kg_status,
                "participation_scope": scope,
                "trust_weight": trust_weight,
                "embedding_status": embedding_status,
                "embedding_signal": embedding_signal,
            },
        )
        return result.to_dict()

    def review_status(self, entity_type: str, entity: Dict[str, Any], quality: Dict[str, Any]) -> str:
        if entity.get("entity_verification_status") == st.ENTITY_REJECTED:
            return "rejected"
        if entity.get("kg_sync_status") == st.KG_MERGE_REQUIRED or entity.get("duplicate_candidates"):
            return "merge_required"
        if quality.get("score", 0.0) < 0.5 or quality.get("missing_fields"):
            return "needs_more_info"
        if entity.get("entity_verification_status") != st.ENTITY_VERIFIED:
            return "pending_review"
        return "verified"

    @staticmethod
    def _presence_score(name: str, value: List[Any], weight: float, missing: List[str]) -> float:
        if value:
            return weight
        missing.append(name)
        return 0.0

    @staticmethod
    def _location_tokens(location: Dict[str, Any]) -> List[str]:
        out: List[str] = []
        for key in ("country", "province", "district", "raw"):
            value = location.get(key)
            if value not in (None, "", [], {}) and str(value) not in out:
                out.append(str(value))
        return out

    @staticmethod
    def _as_list(value: Any) -> List[Any]:
        if value in (None, "", [], {}):
            return []
        if isinstance(value, list):
            return [item for item in value if item not in (None, "", [], {})]
        return [value]

    def _unmapped_values(self, values: List[Any], category: str) -> List[str]:
        out: List[str] = []
        dynamic_aliases = self.taxonomy_aliases.get(category, set())
        mapper = {
            "topic": canonicalize_topic,
            "skill": canonicalize_skill,
            "industry": canonicalize_industry,
        }[category]
        for value in values:
            if value in (None, "", [], {}):
                continue
            normalized = normalize_text(value)
            if not normalized:
                continue
            if normalized in dynamic_aliases:
                continue
            if mapper(value) is None and normalized not in out:
                out.append(normalized)
        return out

    @staticmethod
    def _level(score: float) -> str:
        if score >= 0.85:
            return "excellent"
        if score >= 0.7:
            return "good"
        if score >= 0.5:
            return "fair"
        return "poor"

    @staticmethod
    def _dedupe(values: List[str]) -> List[str]:
        out: List[str] = []
        for value in values:
            if value and value not in out:
                out.append(value)
        return out
