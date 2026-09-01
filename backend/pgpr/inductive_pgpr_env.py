"""Snapshot-backed environment for the Inductive PGPR candidate prototype.

Unlike the current PGPR env, this prototype does not require vocab.json. It
uses GraphSAGE-style node feature vectors and a frozen action schema so new
nodes can be represented by features instead of integer ids learned at export
time.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

try:
    from ml.graphsage.encoder import NodeFeatureEncoder
except ImportError:  # pragma: no cover - direct module execution fallback
    from ..ml.graphsage.encoder import NodeFeatureEncoder

from .inductive_mask_adapter import InductiveMaskAdapter
from .inductive_action_schema import (
    ALLOWED_ACTION_RELATIONS,
    DEFAULT_MAX_PATH_LENGTH,
    is_allowed_action_relation,
    is_reversible_relation,
    relation_token,
    validate_action_schema,
)


ID_FIELDS_BY_LABEL = {
    "Dataset": ("dataset_id", "id", "name"),
    "Enterprise": ("enterprise_id", "id", "name"),
    "Expert": ("expert_id", "id", "name"),
    "Funder": ("funder_id", "id", "name"),
    "Industry": ("industry_id", "id", "name"),
    "Location": ("location_id", "id", "name"),
    "Product": ("product_id", "id", "name"),
    "Project": ("project_id", "id", "title", "name"),
    "ResearchDirection": ("direction_id", "research_direction_id", "id", "name"),
    "ResearchTopic": ("topic_id", "research_topic_id", "id", "name"),
    "Skill": ("skill_id", "id", "name"),
}

TARGET_ENTITY_TYPES = frozenset({"Expert", "Project", "Funder", "Enterprise"})


@dataclass(frozen=True)
class InductiveAction:
    relation: str
    next_key: str
    direction: str = "out"
    mask_reasons: tuple[str, ...] = ()
    mask_mode: str = "public"

    @property
    def token(self) -> str:
        return relation_token(self.relation, self.direction)


@dataclass(frozen=True)
class InductiveStep:
    head_key: str
    relation: str
    tail_key: str
    direction: str

    @property
    def token(self) -> str:
        return relation_token(self.relation, self.direction)


class InductiveKGEnv:
    """Small RL-style environment backed by a sanitized graph snapshot."""

    def __init__(
        self,
        snapshot: dict[str, Any],
        *,
        encoder: NodeFeatureEncoder | None = None,
        allowed_relations: Sequence[str] = ALLOWED_ACTION_RELATIONS,
        max_path_length: int = DEFAULT_MAX_PATH_LENGTH,
        mode: str = "public",
        current_user_id: str | None = None,
        mask_adapter: InductiveMaskAdapter | None = None,
        target_type_pruning: bool = True,
    ) -> None:
        self.snapshot = snapshot
        self.encoder = encoder or NodeFeatureEncoder()
        self.allowed_relations = frozenset(str(rel) for rel in allowed_relations)
        self.max_path_length = int(max_path_length)
        self.mode = mode if mode in {"public", "personal", "admin_debug"} else "public"
        self.current_user_id = current_user_id
        self.mask_adapter = mask_adapter or InductiveMaskAdapter()
        self.target_type_pruning = bool(target_type_pruning)

        self.nodes_by_element_id: dict[str, dict[str, Any]] = {}
        self.nodes_by_key: dict[str, dict[str, Any]] = {}
        self.key_to_element_id: dict[str, str] = {}
        self.element_id_to_key: dict[str, str] = {}
        self.features_by_element_id = self.encoder.encode_snapshot(snapshot)
        self._features_by_key: dict[str, list[float]] = {}
        self._adjacency: dict[str, list[InductiveAction]] = {}
        self._blocked_node_reason_counts: dict[str, int] = {}
        self._blocked_action_counts: dict[str, int] = {}
        self._source_blocked = False

        self._current_key: str | None = None
        self._source_key: str | None = None
        self._target_key: str | None = None
        self._target_type: str | None = None
        self._exclude_keys: set[str] = set()
        self._path: list[InductiveStep] = []

        self._index_nodes()
        self._index_edges()

    @classmethod
    def from_snapshot_path(cls, path: str | Path, **kwargs: Any) -> "InductiveKGEnv":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(payload, **kwargs)

    @property
    def node_count(self) -> int:
        return len(self.key_to_element_id)

    @property
    def action_edge_count(self) -> int:
        return sum(len(actions) for actions in self._adjacency.values())

    @property
    def blocked_action_counts(self) -> dict[str, int]:
        return dict(sorted(self._blocked_action_counts.items()))

    @property
    def blocked_node_counts(self) -> dict[str, int]:
        return dict(sorted(self._blocked_node_reason_counts.items()))

    @property
    def path(self) -> list[InductiveStep]:
        return list(self._path)

    def reset(
        self,
        source_key: str,
        *,
        target_key: str | None = None,
        target_type: str | None = None,
        exclude_keys: Iterable[str] | None = None,
    ) -> tuple[tuple[str, list[InductiveStep]], list[InductiveAction]]:
        if source_key not in self.key_to_element_id:
            raise KeyError(f"Unknown source key: {source_key}")
        if target_key and target_key not in self.key_to_element_id:
            raise KeyError(f"Unknown target key: {target_key}")
        self._source_key = source_key
        self._target_key = target_key
        self._target_type = target_type
        self._exclude_keys = set(exclude_keys or [])
        self._current_key = source_key
        self._path = []
        self._blocked_action_counts = {}
        self._source_blocked = False
        source_decision = self.mask_adapter.evaluate_node(
            self.nodes_by_key.get(source_key),
            role="source",
            mode=self.mode,
            current_user_id=self.current_user_id,
        )
        if not source_decision.allowed:
            self._source_blocked = True
            for reason in source_decision.reasons:
                self._count_blocked_action(f"source_{reason}")
            return (source_key, []), []
        return (source_key, []), self.valid_actions(source_key)

    def valid_actions(self, entity_key: str | None = None) -> list[InductiveAction]:
        key = entity_key or self._current_key
        if not key or self._source_blocked:
            return []
        return self.filtered_actions(
            key,
            source_key=self._source_key,
            target_key=self._target_key,
            target_type=self._target_type,
            exclude_keys=self._exclude_keys,
            count_blocks=True,
        )

    def filtered_actions(
        self,
        entity_key: str,
        *,
        source_key: str | None = None,
        target_key: str | None = None,
        target_type: str | None = None,
        exclude_keys: Iterable[str] | None = None,
        visited_keys: Iterable[str] | None = None,
        count_blocks: bool = False,
    ) -> list[InductiveAction]:
        excluded = set(exclude_keys or [])
        visited = set(visited_keys or [])
        actions: list[InductiveAction] = []
        for action in self._adjacency.get(entity_key, []):
            if action.next_key in excluded:
                self._count_blocked_action("excluded_node", enabled=count_blocks)
                continue
            if action.next_key in visited:
                self._count_blocked_action("cycle_pruned", enabled=count_blocks)
                continue
            if target_key and entity_key == source_key and action.next_key == target_key:
                self._count_blocked_action("direct_target_exposure", enabled=count_blocks)
                continue
            if self._should_prune_for_target_type(entity_key, action.next_key, source_key=source_key, target_type=target_type):
                self._count_blocked_action("target_type_pruned", enabled=count_blocks)
                continue
            role = "target" if target_type and action.next_key.startswith(f"{target_type}::") else "intermediate"
            decision = self.mask_adapter.evaluate_node(
                self.nodes_by_key.get(action.next_key),
                role=role,
                mode=self.mode,
                current_user_id=self.current_user_id,
            )
            if not decision.allowed:
                for reason in decision.reasons:
                    self._count_blocked_action(f"{role}_{reason}", enabled=count_blocks)
                    self._count_blocked_node(reason, enabled=count_blocks)
                continue
            actions.append(
                InductiveAction(
                    action.relation,
                    action.next_key,
                    action.direction,
                    tuple(decision.reasons),
                    decision.mode,
                )
            )
        return actions

    def step(
        self,
        action: InductiveAction,
    ) -> tuple[tuple[str, list[InductiveStep]], list[InductiveAction], float, bool]:
        if not self._current_key:
            raise RuntimeError("Environment must be reset before step().")
        if action not in self.valid_actions(self._current_key):
            raise ValueError(f"Invalid action from {self._current_key}: {action}")

        step = InductiveStep(
            head_key=self._current_key,
            relation=action.relation,
            tail_key=action.next_key,
            direction=action.direction,
        )
        self._path.append(step)
        self._current_key = action.next_key

        reward = 0.0
        done = False
        if self._target_key and self._current_key == self._target_key:
            reward = 1.0
            done = True
        elif self._target_type and self._current_key.startswith(f"{self._target_type}::"):
            reward = 1.0
            done = True
        if len(self._path) >= self.max_path_length:
            done = True
            if reward == 0.0:
                reward = -0.1

        return (self._current_key, self.path), self.valid_actions(self._current_key), reward, done

    def encode_node(self, entity_key: str) -> list[float]:
        return list(self._features_by_key[entity_key])

    def action_payloads(self, actions: Sequence[InductiveAction]) -> list[dict[str, Any]]:
        return [
            {
                "relation": action.relation,
                "direction": action.direction,
                "token": action.token,
                "next_key": action.next_key,
                "next_embedding": self.encode_node(action.next_key),
                "mask_reasons": list(action.mask_reasons),
                "mask_mode": action.mask_mode,
            }
            for action in actions
        ]

    def path_entity_keys(self) -> list[str]:
        if not self._path:
            return [self._current_key] if self._current_key else []
        return [self._path[0].head_key] + [step.tail_key for step in self._path]

    def path_relation_tokens(self) -> list[str]:
        return [step.token for step in self._path]

    def validate_path(self, path: Sequence[InductiveStep] | None = None) -> dict[str, Any]:
        steps = list(path if path is not None else self._path)
        invalid_relations = [step.relation for step in steps if step.relation not in self.allowed_relations]
        invalid_directions = [
            step.token
            for step in steps
            if step.direction == "in" and not is_reversible_relation(step.relation)
        ]
        missing_nodes = [
            key
            for step in steps
            for key in (step.head_key, step.tail_key)
            if key not in self.key_to_element_id
        ]
        return {
            "valid": not invalid_relations and not invalid_directions and not missing_nodes,
            "invalid_relations": invalid_relations,
            "invalid_directions": invalid_directions,
            "missing_nodes": missing_nodes,
            "path_length": len(steps),
        }

    def action_schema_report(self) -> dict[str, object]:
        return validate_action_schema(edge.get("type") for edge in self.snapshot.get("edges") or [])

    def _index_nodes(self) -> None:
        for node in self.snapshot.get("nodes") or []:
            element_id = str(node.get("element_id") or node.get("id"))
            if not element_id:
                continue
            key = _node_key(node)
            self.nodes_by_element_id[element_id] = node
            self.nodes_by_key[key] = node
            self.key_to_element_id[key] = element_id
            self.element_id_to_key[element_id] = key
            self._features_by_key[key] = list(self.features_by_element_id.get(element_id) or self.encoder.encode_node(node))

    def _index_edges(self) -> None:
        for edge in self.snapshot.get("edges") or []:
            relation = str(edge.get("type") or "")
            if relation not in self.allowed_relations or not is_allowed_action_relation(relation):
                continue
            source = self.element_id_to_key.get(str(edge.get("source") or ""))
            target = self.element_id_to_key.get(str(edge.get("target") or ""))
            if not source or not target:
                continue
            self._adjacency.setdefault(source, []).append(InductiveAction(relation, target, "out"))
            if is_reversible_relation(relation):
                self._adjacency.setdefault(target, []).append(InductiveAction(relation, source, "in"))

    def _should_prune_for_target_type(
        self,
        current_key: str,
        next_key: str,
        *,
        source_key: str | None = None,
        target_type: str | None = None,
    ) -> bool:
        effective_target_type = target_type or self._target_type
        effective_source_key = source_key or self._source_key
        if not self.target_type_pruning or not effective_target_type:
            return False
        next_type = next_key.split("::", 1)[0]
        if next_key == effective_source_key:
            return True
        if next_type not in TARGET_ENTITY_TYPES:
            return False
        if next_type == effective_target_type:
            return False
        current_type = current_key.split("::", 1)[0]
        if current_type == next_type:
            return False
        return True

    def _count_blocked_action(self, reason: str, *, enabled: bool = True) -> None:
        if not enabled:
            return
        self._blocked_action_counts[reason] = self._blocked_action_counts.get(reason, 0) + 1

    def _count_blocked_node(self, reason: str, *, enabled: bool = True) -> None:
        if not enabled:
            return
        self._blocked_node_reason_counts[reason] = self._blocked_node_reason_counts.get(reason, 0) + 1


def _node_key(node: dict[str, Any]) -> str:
    label = str(node.get("primary_label") or (node.get("labels") or ["Node"])[0])
    props = node.get("properties") or {}
    for field in ID_FIELDS_BY_LABEL.get(label, ("id", "name", "title")):
        value = props.get(field)
        if value not in (None, "", [], {}):
            return f"{label}::{value}"
    raw_id = node.get("id")
    if raw_id not in (None, "", [], {}):
        return f"{label}::{raw_id}"
    return f"{label}::{node.get('element_id')}"
