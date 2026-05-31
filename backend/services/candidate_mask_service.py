from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from repositories.auth_repo import AuthRepository
from services import provisional_status as st


@dataclass
class CandidateMaskDecision:
    allowed: bool
    reasons: List[str] = field(default_factory=list)
    status: Dict[str, Any] = field(default_factory=dict)


class CandidateMaskService:
    """Central safety rules for recommendation candidates and KG traversal."""

    VALID_MODES = {"public", "personal", "admin_debug"}

    def __init__(self, repo: Optional[AuthRepository] = None) -> None:
        self.repo = repo or AuthRepository()

    def get_entity_status(self, entity_type: str, entity_id: str) -> Dict[str, Any]:
        entity = self.repo.find_entity_by_id(entity_type, entity_id) or {}
        if not entity:
            return {}
        return self.status_from_entity(entity_type, entity)

    def status_from_entity(self, entity_type: str, entity: Dict[str, Any]) -> Dict[str, Any]:
        entity_type = str(entity_type).lower()
        entity_id = entity.get(self.repo.entity_id_field(entity_type)) or entity.get("id") or entity.get("_id")
        return {
            "entity_type": entity_type,
            "entity_id": str(entity_id or ""),
            "owner_user_id": str(entity.get("user_id") or entity.get("owner_user_id") or entity.get("owner_id") or ""),
            "entity_verification_status": entity.get("entity_verification_status") or st.ENTITY_VERIFIED,
            "kg_sync_status": entity.get("kg_sync_status") or st.KG_SYNCED_VERIFIED,
            "visibility": entity.get("visibility") or st.VISIBILITY_PUBLIC,
            "participation_scope": entity.get("participation_scope") or st.SCOPE_PUBLIC,
            "allow_as_source": bool(entity.get("allow_as_source", True)),
            "recommendable_as_target": bool(entity.get("recommendable_as_target", True)),
            "allow_as_intermediate_node": bool(entity.get("allow_as_intermediate_node", True)),
            "trust_weight": float(entity.get("trust_weight", 1.0) or 1.0),
        }

    def source_decision(
        self,
        entity_type: str,
        entity_id: str,
        *,
        mode: str = "public",
        current_user_id: Optional[str] = None,
    ) -> CandidateMaskDecision:
        status = self.get_entity_status(entity_type, entity_id)
        return self.evaluate_source_status(status, mode=mode, current_user_id=current_user_id)

    def target_decision(
        self,
        entity_type: str,
        entity_id: str,
        *,
        mode: str = "public",
        current_user_id: Optional[str] = None,
    ) -> CandidateMaskDecision:
        status = self.get_entity_status(entity_type, entity_id)
        return self.evaluate_target_status(status, mode=mode, current_user_id=current_user_id)

    def intermediate_decision(
        self,
        entity_type: str,
        entity_id: str,
        *,
        mode: str = "public",
        current_user_id: Optional[str] = None,
    ) -> CandidateMaskDecision:
        status = self.get_entity_status(entity_type, entity_id)
        return self.evaluate_intermediate_status(status, mode=mode, current_user_id=current_user_id)

    def evaluate_source_status(
        self,
        status: Dict[str, Any],
        *,
        mode: str = "public",
        current_user_id: Optional[str] = None,
    ) -> CandidateMaskDecision:
        reasons = self._base_block_reasons(status, mode=mode, current_user_id=current_user_id)
        if status and status.get("allow_as_source") is False:
            reasons.append("source_not_allowed")
        if self._owner_only_other_user(status, mode=mode, current_user_id=current_user_id):
            reasons.append("owner_only_other_user")
        return self._decision(status, reasons, mode)

    def evaluate_target_status(
        self,
        status: Dict[str, Any],
        *,
        mode: str = "public",
        current_user_id: Optional[str] = None,
    ) -> CandidateMaskDecision:
        reasons = self._base_block_reasons(status, mode=mode, current_user_id=current_user_id)
        if mode in {"public", "admin_debug"} and status and status.get("recommendable_as_target") is False:
            reasons.append("target_not_recommendable")
        if self._owner_only_other_user(status, mode=mode, current_user_id=current_user_id):
            reasons.append("owner_only_other_user")
        return self._decision(status, reasons, mode)

    def evaluate_intermediate_status(
        self,
        status: Dict[str, Any],
        *,
        mode: str = "public",
        current_user_id: Optional[str] = None,
    ) -> CandidateMaskDecision:
        reasons = self._base_block_reasons(status, mode=mode, current_user_id=current_user_id)
        if status and status.get("allow_as_intermediate_node") is False:
            reasons.append("intermediate_not_allowed")
        if (status.get("kg_sync_status") if status else None) == st.KG_MERGE_REQUIRED:
            reasons.append("merge_required_not_intermediate")
        if self._owner_only_other_user(status, mode=mode, current_user_id=current_user_id):
            reasons.append("owner_only_other_user")
        return self._decision(status, reasons, mode)

    def filter_candidates(
        self,
        candidates: Iterable[Dict[str, Any]],
        *,
        target_type: str,
        mode: str = "public",
        current_user_id: Optional[str] = None,
        admin_debug: bool = False,
    ) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for candidate in candidates:
            candidate_id = str(
                candidate.get("id")
                or candidate.get(f"{target_type}_id")
                or candidate.get("expert_id")
                or candidate.get("project_id")
                or candidate.get("funder_id")
                or candidate.get("enterprise_id")
                or ""
            )
            decision = self.target_decision(
                target_type,
                candidate_id,
                mode=mode,
                current_user_id=current_user_id,
            )
            if decision.allowed:
                item = dict(candidate)
                item["candidate_mask"] = {
                    "allowed": True,
                    "reasons": decision.reasons if (admin_debug or mode == "admin_debug") else [],
                    "status": decision.status if (admin_debug or mode == "admin_debug") else {},
                }
                out.append(item)
            elif admin_debug or mode == "admin_debug":
                item = dict(candidate)
                item["candidate_mask"] = {
                    "allowed": False,
                    "reasons": decision.reasons,
                    "status": decision.status,
                }
                out.append(item)
        return out

    def runtime_source_weight(
        self,
        status: Dict[str, Any],
        *,
        mode: str = "public",
        current_user_id: Optional[str] = None,
    ) -> tuple[float, Optional[str]]:
        stored = float((status or {}).get("trust_weight", 1.0) or 1.0)
        if (
            mode == "personal"
            and status.get("allow_as_source", True)
            and status.get("participation_scope") == st.SCOPE_OWNER_ONLY
            and current_user_id
            and str(status.get("owner_user_id") or "") == str(current_user_id)
        ):
            return 1.0, "current_user_personal_mode"
        return stored, None

    def data_quality_level(self, *statuses: Dict[str, Any]) -> str:
        if any((status or {}).get("kg_sync_status") == st.KG_MERGE_REQUIRED for status in statuses):
            return "low"
        provisional_count = sum(1 for status in statuses if self.is_provisional(status))
        if provisional_count == 0:
            return "high"
        if provisional_count == 1:
            return "medium"
        return "low"

    @staticmethod
    def is_provisional(status: Dict[str, Any]) -> bool:
        return bool(status) and (status.get("entity_verification_status") or st.ENTITY_VERIFIED) != st.ENTITY_VERIFIED

    def _base_block_reasons(
        self,
        status: Dict[str, Any],
        *,
        mode: str,
        current_user_id: Optional[str],
    ) -> List[str]:
        if not status:
            return []
        reasons: List[str] = []
        if mode not in self.VALID_MODES:
            mode = "public"
        if status.get("visibility") in {st.VISIBILITY_HIDDEN, st.VISIBILITY_DISABLED}:
            reasons.append(f"visibility_{status.get('visibility')}")
        if status.get("participation_scope") == st.SCOPE_DISABLED:
            reasons.append("scope_disabled")
        if status.get("participation_scope") == st.SCOPE_ADMIN_ONLY and mode != "admin_debug":
            reasons.append("admin_only")
        if status.get("entity_verification_status") == st.ENTITY_REJECTED:
            reasons.append("entity_rejected")
        if status.get("kg_sync_status") in {st.KG_DISABLED, st.KG_REJECTED}:
            reasons.append(f"kg_{status.get('kg_sync_status')}")
        return reasons

    @staticmethod
    def _owner_only_other_user(
        status: Dict[str, Any],
        *,
        mode: str,
        current_user_id: Optional[str],
    ) -> bool:
        if not status:
            return False
        if status.get("participation_scope") != st.SCOPE_OWNER_ONLY:
            return False
        if mode == "admin_debug":
            return False
        if mode == "public":
            return True
        return str(status.get("owner_user_id") or "") != str(current_user_id or "")

    @staticmethod
    def _decision(status: Dict[str, Any], reasons: List[str], mode: str) -> CandidateMaskDecision:
        if mode == "admin_debug":
            return CandidateMaskDecision(allowed=True, reasons=reasons, status=status)
        return CandidateMaskDecision(allowed=len(reasons) == 0, reasons=reasons, status=status)
