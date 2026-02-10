"""
PGPR Policy Network: encodes path state and scores valid actions (relation, next_entity).
Trained with REINFORCE to maximize reward (reach target entity).

Reference: PGPR (Xian et al., SIGIR 2019).
"""

import os
import logging
from typing import List, Tuple, Optional

import torch
import torch.nn as nn
import numpy as np

from pgpr_kg import KG

logger = logging.getLogger(__name__)


class PolicyNetwork(nn.Module):
    """
    Policy π(a|s): state = path encoding, action = (relation_id, entity_id).
    State encoding: path_emb = entity_emb[current] + sum over path of (relation_emb[r] + entity_emb[t]).
    Action encoding: action_emb = relation_emb[r] + entity_emb[t].
    Score(s, a) = MLP(path_emb, action_emb) or bilinear(path_emb, action_emb).
    """

    def __init__(
        self,
        kg: KG,
        embedding_dim: int = 64,
        hidden_dim: int = 128,
    ):
        super().__init__()
        self.kg = kg
        n_ent = len(kg.entity2id)
        n_rel = len(kg.relation2id)
        self.n_ent = n_ent
        self.n_rel = n_rel
        self.embedding_dim = embedding_dim

        # Embeddings (trainable; can be initialized from TransE)
        self.entity_emb = nn.Embedding(n_ent, embedding_dim)
        self.relation_emb = nn.Embedding(n_rel, embedding_dim)
        self._init_embeddings(kg)

        # Scoring: path_emb and action_emb -> scalar
        self.mlp = nn.Sequential(
            nn.Linear(embedding_dim * 2, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
        )

    def _init_embeddings(self, kg: KG) -> None:
        if kg.entity_emb is not None and hasattr(kg.entity_emb, "shape"):
            arr = np.asarray(kg.entity_emb, dtype=np.float32)
            self.entity_emb.weight.data.copy_(torch.from_numpy(arr))
        else:
            nn.init.uniform_(self.entity_emb.weight, -0.1, 0.1)
        if kg.relation_emb is not None and hasattr(kg.relation_emb, "shape"):
            arr = np.asarray(kg.relation_emb, dtype=np.float32)
            self.relation_emb.weight.data.copy_(torch.from_numpy(arr))
        else:
            nn.init.uniform_(self.relation_emb.weight, -0.1, 0.1)

    def encode_path(
        self,
        current_entity_id: int,
        path: List[Tuple[int, int, int]],
        device: torch.device,
    ) -> torch.Tensor:
        """
        path = [(h, r, t), (h2, r2, t2), ...]. Current entity = last tail in path, or current_entity_id if path empty.
        path_emb = entity_emb[current] + sum(relation_emb[r] + entity_emb[t] for (h,r,t) in path).
        """
        current = torch.tensor([current_entity_id], dtype=torch.long, device=device)
        path_emb = self.entity_emb(current).squeeze(0)  # (dim,)
        for (h, r, t) in path:
            r_t = torch.tensor([r], dtype=torch.long, device=device)
            t_t = torch.tensor([t], dtype=torch.long, device=device)
            path_emb = path_emb + self.relation_emb(r_t).squeeze(0) + self.entity_emb(t_t).squeeze(0)
        return path_emb  # (dim,)

    def score_actions(
        self,
        path_emb: torch.Tensor,
        valid_actions: List[Tuple[int, int]],
        device: torch.device,
    ) -> torch.Tensor:
        """valid_actions = [(r, t), ...]. Return logits (scores) for each action, shape (len(valid_actions),)."""
        if not valid_actions:
            return torch.tensor([], device=device)
        rel_ids = torch.tensor([a[0] for a in valid_actions], dtype=torch.long, device=device)
        ent_ids = torch.tensor([a[1] for a in valid_actions], dtype=torch.long, device=device)
        action_emb = self.relation_emb(rel_ids) + self.entity_emb(ent_ids)  # (n_actions, dim)
        path_emb_exp = path_emb.unsqueeze(0).expand(len(valid_actions), -1)  # (n_actions, dim)
        pair = torch.cat([path_emb_exp, action_emb], dim=1)  # (n_actions, 2*dim)
        logits = self.mlp(pair).squeeze(1)  # (n_actions,)
        return logits

    def forward(
        self,
        current_entity_id: int,
        path: List[Tuple[int, int, int]],
        valid_actions: List[Tuple[int, int]],
        device: torch.device,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Returns: (log_probs, entropy) for sampling.
        log_probs = log_softmax(scores), shape (n_actions,).
        """
        path_emb = self.encode_path(current_entity_id, path, device)
        logits = self.score_actions(path_emb, valid_actions, device)
        if logits.numel() == 0:
            return logits, logits
        log_probs = nn.functional.log_softmax(logits, dim=0)
        probs = torch.exp(log_probs)
        entropy = -(probs * log_probs).sum()
        return log_probs, entropy

    def select_action(
        self,
        current_entity_id: int,
        path: List[Tuple[int, int, int]],
        valid_actions: List[Tuple[int, int]],
        device: torch.device,
        deterministic: bool = False,
    ) -> Tuple[int, torch.Tensor]:
        """
        Sample (or argmax) action from policy. Returns (action_index, log_prob of selected action).
        """
        path_emb = self.encode_path(current_entity_id, path, device)
        logits = self.score_actions(path_emb, valid_actions, device)
        if logits.numel() == 0:
            return -1, torch.tensor(0.0, device=device)
        if deterministic:
            action_idx = logits.argmax().item()
        else:
            probs = torch.softmax(logits, dim=0)
            action_idx = torch.multinomial(probs, 1).item()
        log_prob = nn.functional.log_softmax(logits, dim=0)[action_idx]
        return action_idx, log_prob


def load_policy(kg: KG, model_path: str, device: Optional[torch.device] = None) -> PolicyNetwork:
    """Load trained policy from checkpoint."""
    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    state = torch.load(model_path, map_location=device)
    emb_dim = state.get("embedding_dim", 64)
    model = PolicyNetwork(kg, embedding_dim=emb_dim)
    model.load_state_dict(state.get("model_state_dict", state), strict=False)
    model.to(device)
    model.eval()
    return model
