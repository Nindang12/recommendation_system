"""Action schema for the Inductive PGPR candidate.

This module freezes which graph relations the candidate policy may traverse.
Runtime governance still has to apply candidate masks before any future
promotion; this schema only defines the offline/prototype action space.
"""
from __future__ import annotations

from typing import Iterable, Sequence


ALLOWED_ACTION_RELATIONS: tuple[str, ...] = (
    "FOCUSES_ON_TOPIC",
    "HAS_EXPERIENCE_IN",
    "INTERESTED_IN",
    "RESEARCHES",
    "FOCUSES_ON",
    "HAS_SKILL",
    "REQUIRES_SKILL",
    "USES_SKILL",
    "SUPPORTS_SKILL",
    "LOCATED_IN",
    "OPERATES_IN",
    "FOCUSES_ON_SECTORS",
    "FUNDS",
    "PARTNERS_WITH",
    "PARTICIPATES_IN",
    "RELATED_TO",
    "CO_AUTHOR_WITH",
)

REVERSIBLE_RELATIONS: tuple[str, ...] = (
    "FOCUSES_ON_TOPIC",
    "HAS_EXPERIENCE_IN",
    "INTERESTED_IN",
    "RESEARCHES",
    "FOCUSES_ON",
    "HAS_SKILL",
    "REQUIRES_SKILL",
    "USES_SKILL",
    "SUPPORTS_SKILL",
    "LOCATED_IN",
    "OPERATES_IN",
    "FOCUSES_ON_SECTORS",
    "PARTNERS_WITH",
    "RELATED_TO",
    "CO_AUTHOR_WITH",
)

FORWARD_ONLY_RELATIONS: tuple[str, ...] = (
    "FUNDS",
    "PARTICIPATES_IN",
)

POSITIVE_LABEL_RELATIONS: tuple[str, ...] = (
    "PARTICIPATES_IN",
    "FUNDS",
    "PARTNERS_WITH",
    "RELATED_TO",
    "CO_AUTHOR_WITH",
)

EVIDENCE_ONLY_RELATIONS: tuple[str, ...] = (
    "BELONGS_TO",
    "COLLABORATES_WITH",
    "CREATES",
    "DEVELOPS",
    "FOCUSES_ON_REGION",
    "HAS_ACCESS_TO",
    "HAS_APPLICATION_EXPERIENCE_IN",
    "OWNS_DATA",
    "REQUIRES_DATA",
    "SUPPORTS",
    "SUPPORTS_TOPIC",
    "TARGETS",
    "WORK_FOR",
)

DEFAULT_MAX_PATH_LENGTH = 4
DEFAULT_SHADOW_ENABLED = False

_ALLOWED = frozenset(ALLOWED_ACTION_RELATIONS)
_REVERSIBLE = frozenset(REVERSIBLE_RELATIONS)
_FORWARD_ONLY = frozenset(FORWARD_ONLY_RELATIONS)


def is_allowed_action_relation(relation: str | None) -> bool:
    """Return True when a relation is part of the frozen action space."""
    return bool(relation) and str(relation) in _ALLOWED


def is_reversible_relation(relation: str | None) -> bool:
    """Return True when the prototype may traverse the relation in both directions."""
    return bool(relation) and str(relation) in _REVERSIBLE


def is_forward_only_relation(relation: str | None) -> bool:
    """Return True when only the stored edge direction may be traversed."""
    return bool(relation) and str(relation) in _FORWARD_ONLY


def validate_action_schema(relations: Iterable[str]) -> dict[str, object]:
    """Summarize allowed/blocked relation coverage for a snapshot."""
    counts: dict[str, int] = {}
    for relation in relations:
        relation_key = str(relation or "")
        counts[relation_key] = counts.get(relation_key, 0) + 1

    total = sum(counts.values())
    allowed = {rel: count for rel, count in counts.items() if is_allowed_action_relation(rel)}
    blocked = {rel: count for rel, count in counts.items() if rel and rel not in _ALLOWED}
    allowed_edges = sum(allowed.values())
    return {
        "allowed_action_relations": list(ALLOWED_ACTION_RELATIONS),
        "reversible_relations": list(REVERSIBLE_RELATIONS),
        "forward_only_relations": list(FORWARD_ONLY_RELATIONS),
        "positive_label_relations": list(POSITIVE_LABEL_RELATIONS),
        "evidence_only_relations": list(EVIDENCE_ONLY_RELATIONS),
        "total_edges": total,
        "allowed_edges": allowed_edges,
        "allowed_coverage": round(allowed_edges / max(1, total), 6),
        "blocked_relations": dict(sorted(blocked.items())),
    }


def relation_token(relation: str, direction: str) -> str:
    """Create the policy token for a directed traversal of a relation."""
    suffix = "OUT" if direction == "out" else "IN"
    return f"{relation}::{suffix}"


def relation_tokens(relations: Sequence[str] = ALLOWED_ACTION_RELATIONS) -> tuple[str, ...]:
    """Return relation-direction tokens used by the prototype policy."""
    tokens: list[str] = []
    for relation in relations:
        tokens.append(relation_token(relation, "out"))
        if is_reversible_relation(relation):
            tokens.append(relation_token(relation, "in"))
    return tuple(tokens)
