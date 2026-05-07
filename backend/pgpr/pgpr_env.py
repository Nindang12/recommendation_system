"""
PGPR RL Environment: state = current path, actions = valid (relation, next_entity) from Neo4j.
Step-by-step policy-guided walk on the knowledge graph.

Reference: PGPR (Xian et al., SIGIR 2019).
"""

import os
import logging
from typing import List, Any, Tuple, Optional

from neo4j import GraphDatabase
from dotenv import load_dotenv

try:
    from .pgpr_kg import KG
except ImportError:
    from pgpr_kg import KG

load_dotenv()
logger = logging.getLogger(__name__)

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")


class KGEnv:
    """
    RL environment for PGPR: start at source entity, at each step choose (relation, next_entity).
    State = (current_entity_id, path_history). Valid actions = neighbors from Neo4j.
    """

    def __init__(self, kg: KG, driver=None, max_path_length: int = 5):
        self.kg = kg
        self.driver = driver or GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        self.max_path_length = max_path_length
        self._current_entity_key: Optional[str] = None
        self._path: List[Tuple[int, int, int]] = []  # [(h, r, t), ...]
        self._source_entity_key: Optional[str] = None
        self._target_entity_key: Optional[str] = None
        self._target_type: Optional[str] = None  # e.g. "Expert"; for reward
        self._exclude_keys: set = set()

    def get_neighbors(self, entity_key: str) -> List[Tuple[str, str]]:
        """
        Get all (relation_type, next_entity_key) reachable from entity_key in one step.
        Fast path: read neighbors directly from in-memory adjacency list.
        """
        h_id = self.kg.entity_key_to_id(entity_key)
        if h_id is None:
            return []

        out: List[Tuple[str, str]] = []
        for r_id, t_id in self.kg.adj_list.get(h_id, []):
            rel_type = self.kg.id2relation.get(r_id)
            next_key = self.kg.id2entity.get(t_id)
            if rel_type is None or next_key is None:
                continue
            if next_key in self._exclude_keys:
                continue
            # Prevent direct one-hop answer exposure from source to known target during training.
            if (
                self._target_entity_key
                and entity_key == self._source_entity_key
                and next_key == self._target_entity_key
            ):
                continue
            out.append((rel_type, next_key))

        return out

    def reset(
        self,
        source_entity_key: str,
        target_entity_key: Optional[str] = None,
        target_type: Optional[str] = None,
        exclude_keys: Optional[List[str]] = None,
    ) -> Tuple[Any, List[Tuple[int, int, int]]]:
        """
        Reset env to start at source_entity_key.
        Returns: state_embedding (for policy), list of valid actions as (relation_id, entity_id).
        """
        self._source_entity_key = source_entity_key
        self._target_entity_key = target_entity_key
        self._target_type = target_type
        self._exclude_keys = set(exclude_keys) if exclude_keys else set()
        self._current_entity_key = source_entity_key
        self._path = []

        h = self.kg.get_entity_id(*source_entity_key.split("::", 1))
        neighbors = self.get_neighbors(source_entity_key)
        valid_actions = []
        for rel_type, next_key in neighbors:
            r = self.kg.get_relation_id(rel_type)
            t = self.kg.get_entity_id(*next_key.split("::", 1))
            valid_actions.append((r, t))

        return (h, self._path), valid_actions

    def step(self, action: Tuple[int, int]) -> Tuple[Any, List[Tuple[int, int, int]], float, bool]:
        """
        action = (relation_id, next_entity_id).
        Returns: (next_state, valid_actions, reward, done).
        """
        r, next_ent = action
        current_ent = self.kg.entity_key_to_id(self._current_entity_key)
        if current_ent is None:
            current_ent = self.kg.get_entity_id(*self._current_entity_key.split("::", 1))
        self._path.append((current_ent, r, next_ent))
        self._current_entity_key = self.kg.id2entity[next_ent]

        done = False
        reward = 0.0

        # Training mode: a concrete target entity is provided.
        if self._target_entity_key:
            if self._current_entity_key == self._target_entity_key:
                done = True
                reward = 1.0
            # Reached correct type but wrong entity -> terminate early, no positive reward.
            elif self._target_type and self._current_entity_key.startswith(self._target_type + "::"):
                done = True
                reward = 0.0
        # Inference mode: only target type is provided.
        elif self._target_type:
            if self._current_entity_key.startswith(self._target_type + "::"):
                done = True
                reward = 1.0
        if len(self._path) >= self.max_path_length:
            done = True
            if reward == 0.0:
                reward = -0.1  # small penalty for not reaching target

        neighbors = self.get_neighbors(self._current_entity_key)
        valid_actions = []
        for rel_type, next_key in neighbors:
            r_id = self.kg.get_relation_id(rel_type)
            t_id = self.kg.get_entity_id(*next_key.split("::", 1))
            valid_actions.append((r_id, t_id))

        next_state = (next_ent, self._path)
        return next_state, valid_actions, reward, done

    def get_path_entity_keys(self) -> List[str]:
        """Return path as list of entity keys (including start)."""
        keys = []
        if not self._path:
            if self._current_entity_key:
                keys.append(self._current_entity_key)
            return keys
        h = self._path[0][0]
        keys.append(self.kg.id2entity[h])
        for _, _, t in self._path:
            keys.append(self.kg.id2entity[t])
        return keys

    def get_path_relation_types(self) -> List[str]:
        """Return path as list of relation type names."""
        return [self.kg.id2relation[r] for _, r, _ in self._path]

    def close(self) -> None:
        if self.driver:
            self.driver.close()
