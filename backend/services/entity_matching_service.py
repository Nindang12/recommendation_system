from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

from repositories.auth_repo import AuthRepository


class EntityMatchingService:
    """Lightweight duplicate detection before provisional KG sync."""

    def __init__(self, repo: Optional[AuthRepository] = None) -> None:
        self.repo = repo or AuthRepository()

    def match_user_entity(self, role: str, user: Dict[str, Any]) -> Dict[str, Any]:
        role = str(role or "").lower()
        if role not in {"expert", "enterprise", "funder"}:
            return {"match_status": "none", "candidates": []}

        strong = self.repo.find_strong_entity_match(role, user)
        if strong:
            return {
                "match_status": "matched_existing",
                "match_strength": "strong",
                "matched_entity": strong,
                "candidates": [self._candidate(role, strong, "strong")],
            }

        weak_candidates = self._weak_candidates(role, user)
        if weak_candidates:
            return {
                "match_status": "merge_required",
                "match_strength": "weak",
                "matched_entity": None,
                "candidates": weak_candidates,
            }

        return {
            "match_status": "created_new",
            "match_strength": "none",
            "matched_entity": None,
            "candidates": [],
        }

    def _weak_candidates(self, role: str, user: Dict[str, Any]) -> List[Dict[str, Any]]:
        name = str(user.get("full_name") or "").strip()
        organization = str(user.get("organization") or "").strip().lower()
        if not name:
            return []

        candidates = self.repo.find_entity_candidates_by_name(role, name, limit=10)
        out: List[Dict[str, Any]] = []
        for entity in candidates:
            entity_name = str(entity.get("name") or entity.get("title") or "")
            similarity = SequenceMatcher(None, name.lower(), entity_name.lower()).ratio()
            same_org = organization and organization == str(entity.get("organization") or "").strip().lower()
            if similarity >= 0.86 or (similarity >= 0.72 and same_org):
                out.append(
                    {
                        **self._candidate(role, entity, "weak"),
                        "similarity": round(similarity, 3),
                        "same_organization": bool(same_org),
                    }
                )
        return out

    def _candidate(self, role: str, entity: Dict[str, Any], strength: str) -> Dict[str, Any]:
        id_key = {
            "expert": "expert_id",
            "enterprise": "enterprise_id",
            "funder": "funder_id",
        }.get(role, "id")
        return {
            "id": str(entity.get(id_key) or entity.get("_id") or ""),
            "type": role,
            "name": entity.get("name") or entity.get("title") or "",
            "match_strength": strength,
        }
