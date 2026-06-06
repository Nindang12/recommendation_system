"""Shadow-mode interface for the Inductive PGPR candidate.

This module is intentionally not wired into the live recommendation endpoint.
It gives tests/evaluation scripts a stable interface while keeping production
runtime protected until a future promote/rollback gate explicitly enables it.
"""
from __future__ import annotations

from dataclasses import asdict
from time import perf_counter
from pathlib import Path
from typing import Any

import torch

from .inductive_action_schema import DEFAULT_SHADOW_ENABLED
from .inductive_pgpr_env import InductiveAction, InductiveKGEnv, InductiveStep
from .inductive_pgpr_policy import InductivePolicyNetwork


class InductivePGPRShadowRunner:
    """Prototype-only runner for offline/shadow inference experiments."""

    def __init__(
        self,
        env: InductiveKGEnv,
        policy: InductivePolicyNetwork | None = None,
        *,
        enabled: bool = DEFAULT_SHADOW_ENABLED,
        device: torch.device | None = None,
    ) -> None:
        self.env = env
        self.policy = policy or InductivePolicyNetwork(embedding_dim=env.encoder.dimension)
        self.enabled = bool(enabled)
        self.device = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.policy.to(self.device)
        self.policy.eval()

    @classmethod
    def from_snapshot_path(cls, snapshot_path: str | Path, **kwargs: Any) -> "InductivePGPRShadowRunner":
        env_kwargs = dict(kwargs.pop("env_kwargs", {}) or {})
        return cls(InductiveKGEnv.from_snapshot_path(snapshot_path, **env_kwargs), **kwargs)

    def recommend_shadow(
        self,
        *,
        source_key: str,
        target_type: str,
        limit: int = 5,
        max_steps: int | None = None,
    ) -> dict[str, Any]:
        state, actions = self.env.reset(source_key, target_type=target_type)
        max_depth = int(max_steps or self.env.max_path_length)
        candidates: list[dict[str, Any]] = []
        trace: list[dict[str, Any]] = []
        path_payload: list[dict[str, Any]] = []

        for depth in range(max_depth):
            current_key, _ = state
            if not actions:
                break
            action_payloads = self.env.action_payloads(actions)
            current_embedding = self.env.encode_node(current_key)
            with torch.no_grad():
                log_probs, entropy = self.policy(current_embedding, path_payload, action_payloads, device=self.device)
            if log_probs.numel() == 0:
                break
            order = torch.argsort(log_probs, descending=True).tolist()
            chosen_idx = int(order[0])
            chosen = actions[chosen_idx]
            trace.append(
                {
                    "depth": depth,
                    "current_key": current_key,
                    "chosen_action": asdict(chosen),
                    "log_prob": float(log_probs[chosen_idx].item()),
                    "entropy": float(entropy.item()) if entropy.numel() else 0.0,
                    "action_count": len(actions),
                }
            )
            path_payload.append(
                {
                    "token": chosen.token,
                    "next_embedding": self.env.encode_node(chosen.next_key),
                }
            )
            state, actions, reward, done = self.env.step(chosen)
            next_key, _ = state
            if next_key.startswith(f"{target_type}::"):
                candidates.append(
                    {
                        "entity_key": next_key,
                        "score": float(torch.exp(log_probs[chosen_idx]).item()),
                        "reward": reward,
                        "path_entities": self.env.path_entity_keys(),
                        "path_relations": self.env.path_relation_tokens(),
                        "path_validity": self.env.validate_path(),
                    }
                )
            if done or len(candidates) >= limit:
                break

        return {
            "status": "shadow_disabled" if not self.enabled else "shadow_enabled",
            "runtime_enabled": False,
            "prototype_only": True,
            "source_key": source_key,
            "target_type": target_type,
            "candidate_count": len(candidates),
            "candidates": candidates[:limit],
            "trace": trace,
        }

    def recommend_beam_shadow(
        self,
        *,
        source_key: str,
        target_type: str,
        beam_width: int = 5,
        max_hops: int = 3,
        limit: int = 5,
    ) -> dict[str, Any]:
        started = perf_counter()
        if source_key not in self.env.key_to_element_id:
            return {
                "status": "source_not_found",
                "runtime_enabled": False,
                "prototype_only": True,
                "source_key": source_key,
                "target_type": target_type,
                "candidate_count": 0,
                "candidates": [],
                "blocked_action_count": 0,
                "latency_ms": round((perf_counter() - started) * 1000, 3),
            }

        self.env.reset(source_key, target_type=target_type)
        beams = [
            {
                "current_key": source_key,
                "path": [],
                "path_payload": [],
                "score": 0.0,
                "visited": {source_key},
            }
        ]
        candidates: list[dict[str, Any]] = []
        expansion_trace: list[dict[str, Any]] = []

        for depth in range(int(max_hops)):
            next_beams: list[dict[str, Any]] = []
            for beam in beams:
                current_key = str(beam["current_key"])
                path = list(beam["path"])
                actions = self.env.filtered_actions(
                    current_key,
                    source_key=source_key,
                    target_type=target_type,
                    visited_keys=beam["visited"],
                    count_blocks=True,
                )
                expansion_trace.append(
                    {
                        "depth": depth,
                        "current_key": current_key,
                        "valid_action_count": len(actions),
                    }
                )
                if not actions:
                    continue
                action_payloads = self.env.action_payloads(actions)
                with torch.no_grad():
                    log_probs, _entropy = self.policy(
                        self.env.encode_node(current_key),
                        beam["path_payload"],
                        action_payloads,
                        device=self.device,
                    )
                if log_probs.numel() == 0:
                    continue
                for idx, action in enumerate(actions):
                    step = InductiveStep(
                        head_key=current_key,
                        relation=action.relation,
                        tail_key=action.next_key,
                        direction=action.direction,
                    )
                    next_score = float(beam["score"]) + float(log_probs[idx].item())
                    next_path = path + [step]
                    next_payload = list(beam["path_payload"]) + [
                        {
                            "token": action.token,
                            "next_embedding": self.env.encode_node(action.next_key),
                        }
                    ]
                    next_visited = set(beam["visited"])
                    next_visited.add(action.next_key)
                    path_validity = self.env.validate_path(next_path)
                    if action.next_key.startswith(f"{target_type}::") and path_validity["valid"]:
                        candidates.append(
                            {
                                "entity_key": action.next_key,
                                "score": round(next_score, 6),
                                "path_score_prototype": round(float(torch.exp(torch.tensor(next_score)).item()), 6),
                                "reasoning_path": _path_to_report(source_key, next_path),
                                "path_validity": path_validity,
                                "hops": len(next_path),
                            }
                        )
                    else:
                        next_beams.append(
                            {
                                "current_key": action.next_key,
                                "path": next_path,
                                "path_payload": next_payload,
                                "score": next_score,
                                "visited": next_visited,
                            }
                        )
            next_beams.sort(key=lambda item: float(item["score"]), reverse=True)
            beams = next_beams[: int(beam_width)]
            if len(candidates) >= limit:
                break

        unique_candidates = _dedupe_candidates(candidates)
        latency_ms = round((perf_counter() - started) * 1000, 3)
        return {
            "status": "shadow_disabled" if not self.enabled else "shadow_enabled",
            "runtime_enabled": False,
            "prototype_only": True,
            "source_key": source_key,
            "target_type": target_type,
            "beam_width": beam_width,
            "max_hops": max_hops,
            "candidate_count": len(unique_candidates[:limit]),
            "candidates": unique_candidates[:limit],
            "blocked_action_count": sum(self.env.blocked_action_counts.values()),
            "blocked_action_counts": self.env.blocked_action_counts,
            "blocked_node_counts": self.env.blocked_node_counts,
            "latency_ms": latency_ms,
            "expansion_trace": expansion_trace,
        }


def action_to_dict(action: InductiveAction) -> dict[str, str]:
    return asdict(action)


def _path_to_report(source_key: str, path: list[InductiveStep]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    current = source_key
    for step in path:
        rows.append(
            {
                "source": current,
                "relation": step.token,
                "target": step.tail_key,
            }
        )
        current = step.tail_key
    return rows


def _dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        key = str(candidate["entity_key"])
        if key not in best or float(candidate["score"]) > float(best[key]["score"]):
            best[key] = candidate
    return sorted(best.values(), key=lambda item: float(item["score"]), reverse=True)
