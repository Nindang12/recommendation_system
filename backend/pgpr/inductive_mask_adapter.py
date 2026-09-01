"""Mask adapter for Inductive PGPR snapshot nodes.

The production recommendation stack uses CandidateMaskService against Mongo
entities. Inductive PGPR works from sanitized graph snapshots, so this adapter
converts snapshot node properties into the same status shape and delegates the
decision to CandidateMaskService evaluate_*_status methods.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services import provisional_status as st
from services.candidate_mask_service import CandidateMaskDecision, CandidateMaskService


@dataclass(frozen=True)
class InductiveMaskDecision:
    allowed: bool
    reasons: list[str]
    status: dict[str, Any]
    mode: str
    role: str


class InductiveMaskAdapter:
    """Evaluate snapshot nodes with production-compatible candidate mask rules."""

    VALID_ROLES = {"source", "target", "intermediate"}

    def __init__(self, service: CandidateMaskService | None = None) -> None:
        self.service = service or CandidateMaskService.__new__(CandidateMaskService)

    def evaluate_node(
        self,
        node: dict[str, Any] | None,
        *,
        role: str,
        mode: str = "public",
        current_user_id: str | None = None,
    ) -> InductiveMaskDecision:
        role = role if role in self.VALID_ROLES else "intermediate"
        mode = mode if mode in CandidateMaskService.VALID_MODES else "public"
        status = status_from_snapshot_node(node)
        if role == "source":
            decision = self.service.evaluate_source_status(
                status,
                mode=mode,
                current_user_id=current_user_id,
            )
        elif role == "target":
            decision = self.service.evaluate_target_status(
                status,
                mode=mode,
                current_user_id=current_user_id,
            )
        else:
            decision = self.service.evaluate_intermediate_status(
                status,
                mode=mode,
                current_user_id=current_user_id,
            )
        return _convert(decision, mode=mode, role=role)


def status_from_snapshot_node(node: dict[str, Any] | None) -> dict[str, Any]:
    if not node:
        return {}
    props = node.get("properties") or {}
    label = str(node.get("primary_label") or (node.get("labels") or ["node"])[0]).lower()
    entity_id = _snapshot_entity_id(node)
    return {
        "entity_type": label,
        "entity_id": entity_id,
        "owner_user_id": str(props.get("user_id") or props.get("owner_user_id") or props.get("owner_id") or ""),
        "entity_verification_status": props.get("entity_verification_status") or st.ENTITY_VERIFIED,
        "kg_sync_status": props.get("kg_sync_status") or st.KG_SYNCED_VERIFIED,
        "visibility": props.get("visibility") or st.VISIBILITY_PUBLIC,
        "participation_scope": props.get("participation_scope") or st.SCOPE_PUBLIC,
        "allow_as_source": bool(props.get("allow_as_source", True)),
        "recommendable_as_target": bool(props.get("recommendable_as_target", True)),
        "allow_as_intermediate_node": bool(props.get("allow_as_intermediate_node", True)),
        "trust_weight": float(props.get("trust_weight", 1.0) or 1.0),
    }


def _snapshot_entity_id(node: dict[str, Any]) -> str:
    props = node.get("properties") or {}
    for key in (
        "expert_id",
        "project_id",
        "funder_id",
        "enterprise_id",
        "dataset_id",
        "product_id",
        "topic_id",
        "skill_id",
        "industry_id",
        "location_id",
        "direction_id",
        "id",
        "name",
        "title",
    ):
        value = props.get(key)
        if value not in (None, "", [], {}):
            return str(value)
    return str(node.get("id") or node.get("element_id") or "")


def _convert(decision: CandidateMaskDecision, *, mode: str, role: str) -> InductiveMaskDecision:
    return InductiveMaskDecision(
        allowed=bool(decision.allowed),
        reasons=list(decision.reasons or []),
        status=dict(decision.status or {}),
        mode=mode,
        role=role,
    )
