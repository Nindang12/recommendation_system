"""Policy forward-pass prototype for Inductive PGPR.

The current PGPR policy learns entity ids from vocab.json. This prototype scores
actions from GraphSAGE/node-feature embeddings, so it can run a forward pass for
nodes that were not present in the original PGPR vocabulary.
"""
from __future__ import annotations

from typing import Any, Sequence

import torch
import torch.nn as nn

from .inductive_action_schema import ALLOWED_ACTION_RELATIONS, relation_tokens
from .inductive_pgpr_env import InductiveStep


class InductivePolicyNetwork(nn.Module):
    """Score snapshot actions using node embeddings plus relation-direction tokens."""

    def __init__(
        self,
        *,
        embedding_dim: int = 128,
        hidden_dim: int = 128,
        relation_token_names: Sequence[str] | None = None,
    ) -> None:
        super().__init__()
        self.embedding_dim = int(embedding_dim)
        self.relation_token_names = tuple(relation_token_names or relation_tokens(ALLOWED_ACTION_RELATIONS))
        self.relation2id = {name: idx for idx, name in enumerate(self.relation_token_names)}
        self.unknown_relation_id = len(self.relation2id)

        self.relation_emb = nn.Embedding(len(self.relation2id) + 1, self.embedding_dim)
        self.path_gru = nn.GRUCell(self.embedding_dim * 2, self.embedding_dim)
        self.scorer = nn.Sequential(
            nn.Linear(self.embedding_dim * 2, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
        )
        self._init_weights()

    def _init_weights(self) -> None:
        nn.init.uniform_(self.relation_emb.weight, -0.05, 0.05)
        for module in self.scorer:
            if isinstance(module, nn.Linear):
                nn.init.xavier_uniform_(module.weight)
                nn.init.zeros_(module.bias)

    def encode_path(
        self,
        current_embedding: torch.Tensor,
        path: Sequence[InductiveStep | dict[str, Any]],
        *,
        device: torch.device,
    ) -> torch.Tensor:
        current = _as_vector(current_embedding, self.embedding_dim, device)
        state = current
        for step in path:
            token = _step_token(step)
            next_embedding = _step_next_embedding(step)
            if next_embedding is None:
                continue
            rel = self.relation_emb(_relation_id_tensor(self, token, device)).squeeze(0)
            nxt = _as_vector(next_embedding, self.embedding_dim, device)
            state = self.path_gru(torch.cat([rel, nxt], dim=0).unsqueeze(0), state.unsqueeze(0)).squeeze(0)
        return state

    def score_actions(
        self,
        path_embedding: torch.Tensor,
        valid_actions: Sequence[dict[str, Any]],
        *,
        device: torch.device,
    ) -> torch.Tensor:
        if not valid_actions:
            return torch.empty(0, device=device)
        action_embeddings: list[torch.Tensor] = []
        for action in valid_actions:
            token = str(action.get("token") or "")
            next_embedding = action.get("next_embedding")
            rel = self.relation_emb(_relation_id_tensor(self, token, device)).squeeze(0)
            nxt = _as_vector(next_embedding, self.embedding_dim, device)
            action_embeddings.append(rel + nxt)
        action_tensor = torch.stack(action_embeddings, dim=0)
        state = path_embedding.unsqueeze(0).expand(action_tensor.shape[0], -1)
        return self.scorer(torch.cat([state, action_tensor], dim=1)).squeeze(1)

    def forward(
        self,
        current_embedding: torch.Tensor | Sequence[float],
        path: Sequence[InductiveStep | dict[str, Any]],
        valid_actions: Sequence[dict[str, Any]],
        *,
        device: torch.device | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        device = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.to(device)
        path_embedding = self.encode_path(
            torch.as_tensor(current_embedding, dtype=torch.float32, device=device),
            path,
            device=device,
        )
        logits = self.score_actions(path_embedding, valid_actions, device=device)
        if logits.numel() == 0:
            return logits, logits
        log_probs = nn.functional.log_softmax(logits, dim=0)
        entropy = -(torch.exp(log_probs) * log_probs).sum()
        return log_probs, entropy


def _relation_id_tensor(model: InductivePolicyNetwork, token: str, device: torch.device) -> torch.Tensor:
    idx = model.relation2id.get(token, model.unknown_relation_id)
    return torch.tensor([idx], dtype=torch.long, device=device)


def _as_vector(value: Any, dimension: int, device: torch.device) -> torch.Tensor:
    vector = torch.as_tensor(value, dtype=torch.float32, device=device)
    if vector.ndim != 1:
        vector = vector.flatten()
    if vector.numel() != dimension:
        raise ValueError(f"Expected embedding dimension {dimension}, got {vector.numel()}")
    return vector


def _step_token(step: InductiveStep | dict[str, Any]) -> str:
    if isinstance(step, InductiveStep):
        return step.token
    return str(step.get("token") or "")


def _step_next_embedding(step: InductiveStep | dict[str, Any]) -> Any:
    if isinstance(step, dict):
        return step.get("next_embedding")
    return None
