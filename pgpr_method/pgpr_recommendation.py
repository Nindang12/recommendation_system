"""
PGPR (Policy-Guided Path Reasoning) for R&D Knowledge Graph Recommendations - IMPROVED VERSION

Multi-Entity Explainable Recommendation Framework: Project, Expert, Funder, Enterprise
(see MULTI_ENTITY_PGPR_FRAMEWORK.md for meta-paths and rationale per source/target pair).

Improvements:
- Thread-safe: No instance variable modification
- Performance: Batch candidate queries, caching
- Reliability: Timeout protection, better error handling
- Quality: Improved scoring, path deduplication

Reference: Xian et al., SIGIR 2019 "Reinforcement Knowledge Graph Reasoning
for Explainable Recommendation"
"""

from neo4j import GraphDatabase
from typing import List, Dict, Any, Tuple, Optional, Set
import os
from dotenv import load_dotenv
import logging
import numpy as np
from collections import defaultdict, deque
import random
from functools import lru_cache
import time

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Neo4j connection
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

# Module-level shared driver (safe to reuse across recommender instances).
# IMPORTANT: Do not close this driver inside PGPRRecommender.close(), otherwise
# subsequent requests will fail with "neo4j.exceptions.DriverError: Driver closed".
_shared_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def _entity_key(label: str, id_val: str) -> str:
    return f"{label}::{id_val}"


class PGPRRecommender:
    """
    PGPR recommender with improvements:
    - Caching for repeated queries
    - Batch processing for candidates
    - Thread-safe operations
    - Better path scoring
    """
    
    # Configuration constants
    SCORE_WEIGHT_MAX_PATH = 0.4
    SCORE_WEIGHT_AVG_PATH = 0.2
    SCORE_WEIGHT_MIN_LENGTH = 0.1
    SCORE_WEIGHT_DIVERSITY = 0.1
    SCORE_WEIGHT_QUALITY = 0.2
    
    DEFAULT_INITIAL_DEPTH = 2
    DEFAULT_DEPTH_INCREMENT = 2
    DEFAULT_HARD_LIMIT_DEPTH = 12
    DEFAULT_QUERY_TIMEOUT = 10.0  # seconds
    POLICY_ONLY_MODE = True
    
    def __init__(
        self,
        max_path_length: int = 5,
        gamma: float = 0.99,
        top_k_paths: int = 10,
        path_penalty: float = 0.1,
        policy_path: Optional[str] = None,
        data_dir: str = "pgpr_data",
        enable_cache: bool = True,
        driver: Optional[Any] = None,
    ):
        # Use provided driver if any; otherwise reuse module shared driver.
        # The recommender does NOT own the shared driver.
        self.driver = driver or _shared_driver
        self._owns_driver = driver is not None and driver is not _shared_driver
        self.max_path_length = max_path_length
        self.gamma = gamma
        self.top_k_paths = top_k_paths
        self.path_penalty = path_penalty
        self.policy_path = policy_path or os.path.join(data_dir, "policy.pt")
        self.data_dir = data_dir
        self.enable_cache = enable_cache
        
        # Cache for path queries
        self._path_cache = {} if enable_cache else None
        self._cache_hits = 0
        self._cache_misses = 0
        
        # Policy-related attributes
        self.kg = None
        self.policy = None
        self.policies = {}
        self._policy_device = None
        self._env = None
        self._load_policy_if_available()
        
        # Heuristic relation weights (align with MULTI_ENTITY_PGPR_FRAMEWORK.md meta-paths)
        self.relation_weights = {
            'HAS_EXPERTISE_IN': 1.0,
            'HAS_SKILL': 0.9,
            'PARTICIPATES_IN': 0.85,
            'BELONGS_TO': 0.8,
            'SUB_FIELD_OF': 0.7,
            'OPERATES_IN': 0.75,
            'PARTNERS_WITH': 0.8,
            'FUNDS': 0.85,
            'SUPPORTS': 0.8,
            'PRODUCES': 0.7,
            'COMMERCIALIZES': 0.75,
            'HAS_APPLICATION_EXPERIENCE_IN': 0.85,
            'UNDER_FIELD': 0.7,   # MethodTechnique -> ResearchField
            'COLLABORATES_WITH': 0.85,
        }
    
    def _load_policy_if_available(self) -> None:
        """Load KG and all available trained policies from data_dir."""
        try:
            import torch
            from pgpr_kg import KG
            from pgpr_env import KGEnv
            from pgpr_policy import load_policy as load_policy_net
        except ImportError:
            logger.error("PyTorch or pgpr modules not available; policy-only mode requires RL policy.")
            return
        
        vocab_path = os.path.join(self.data_dir, "vocab.json")
        if not os.path.exists(vocab_path):
            logger.error("No vocab found at %s; policy-only mode cannot initialize KG.", vocab_path)
            return
        
        try:
            self.kg = KG(data_dir=self.data_dir)
            self.kg.load_vocab()
            self.kg.load_triples()
            if os.path.exists(os.path.join(self.data_dir, "entity_emb.npy")):
                self.kg.load_embeddings()
            self._policy_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            self._env = KGEnv(self.kg, driver=self.driver, max_path_length=self.max_path_length)
            self.policies = {}

            # Preferred multi-policy files: policy_<Source>_<Target>.pt
            for filename in os.listdir(self.data_dir):
                if not filename.startswith("policy_") or not filename.endswith(".pt"):
                    continue
                task_name = filename.replace("policy_", "").replace(".pt", "")
                model_path = os.path.join(self.data_dir, filename)
                try:
                    self.policies[task_name] = load_policy_net(self.kg, model_path, device=self._policy_device)
                except Exception as e:
                    logger.warning("Skip policy %s due to load error: %s", model_path, e)

            # Backward compatibility with legacy single policy file.
            if not self.policies and os.path.exists(self.policy_path):
                self.policies["Project_Expert"] = load_policy_net(self.kg, self.policy_path, device=self._policy_device)
                logger.info("Loaded legacy policy at %s as task Project_Expert.", self.policy_path)

            self.policy = self.policies.get("Project_Expert")
            logger.info("Loaded %d policy model(s): %s", len(self.policies), sorted(self.policies.keys()))
        except Exception as e:
            logger.error("Could not load PGPR policy: %s; policy-only mode cannot use heuristic fallback.", e)
            self.kg = None
            self.policy = None
            self.policies = {}
            self._env = None
    
    def close(self):
        """Close connections and cleanup."""
        if getattr(self, "_env", None):
            try:
                self._env.close()
            except Exception:
                pass
        if getattr(self, "_owns_driver", False):
            self.driver.close()
        
        # Print cache statistics
        if self.enable_cache and (self._cache_hits + self._cache_misses) > 0:
            total = self._cache_hits + self._cache_misses
            hit_rate = self._cache_hits / total * 100
            logger.info(f"Path cache statistics: {self._cache_hits} hits, "
                       f"{self._cache_misses} misses ({hit_rate:.1f}% hit rate)")
    
    def clear_cache(self):
        """Clear path cache (call when graph updates)."""
        if self._path_cache is not None:
            self._path_cache.clear()
            logger.info("Path cache cleared")
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        return {
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "size": len(self._path_cache) if self._path_cache else 0,
        }
    
    # ==========================================
    # IMPROVED PATH FINDING & REASONING
    # ==========================================
    
    def find_reasoning_paths(
        self,
        source_id: str,
        source_type: str,
        target_id: str,
        target_type: str,
        max_length: Optional[int] = None,
        timeout: float = DEFAULT_QUERY_TIMEOUT,
    ) -> List[Dict[str, Any]]:
        """
        Find all reasoning paths between source and target entities.
        
        IMPROVEMENTS:
        - Thread-safe: max_length as parameter instead of modifying self
        - Cached: Check cache before querying
        - Timeout: Prevent hanging on large graphs
        - Better deduplication: Use relation tuples
        
        Args:
            source_id: Source entity ID
            source_type: Source entity type
            target_id: Target entity ID  
            target_type: Target entity type
            max_length: Override default max_path_length (thread-safe)
            timeout: Query timeout in seconds
        
        Returns:
            List of paths with scores and explanations
        """
        if self.POLICY_ONLY_MODE:
            logger.debug("find_reasoning_paths is disabled in policy-only mode.")
            return []

        # Use provided max_length or fall back to instance default
        effective_max_length = max_length if max_length is not None else self.max_path_length
        
        # Check cache
        cache_key = (source_id, source_type, target_id, target_type, effective_max_length)
        if self.enable_cache and cache_key in self._path_cache:
            self._cache_hits += 1
            return self._path_cache[cache_key]
        
        self._cache_misses += 1
        
        # Find paths with timeout protection
        try:
            with self.driver.session() as session:
                # Use transaction timeout; extract entity names for readable paths
                result = session.run(f"""
                    MATCH path = (source:{source_type} {{
                        {source_type.lower()}_id: $source_id
                    }})-[*1..{effective_max_length}]-(target:{target_type} {{
                        {target_type.lower()}_id: $target_id
                    }})
                    WITH path, relationships(path) as rels, nodes(path) as nodes
                    RETURN path,
                           [r in rels | type(r)] as relation_types,
                           [n in nodes | labels(n)[0]] as node_types,
                           [n in nodes | coalesce(
                               n.name, n.title, n.label,
                               n.project_id, n.expert_id, n.funder_id, n.enterprise_id,
                               n.field_id, n.industry_name, n.tech_id,
                               elementId(n)
                           )] as entity_names,
                           length(path) as path_length
                    LIMIT {self.top_k_paths * 2}
                """, source_id=source_id, target_id=target_id, timeout=timeout)
                
                records = list(result)
        except Exception as e:
            logger.warning(f"Error finding paths {source_id} -> {target_id}: {e}")
            return []
        
        # Score and process paths
        paths = []
        for record in records:
            entity_names = record.get("entity_names") or []
            path_info = self._score_path(
                record["relation_types"],
                record["node_types"],
                record["path_length"],
                entity_names=entity_names,
            )
            
            paths.append({
                "relations": record["relation_types"],
                "nodes": record["node_types"],
                "entity_names": entity_names,
                "length": record["path_length"],
                "score": path_info["score"],
                "explanation": path_info["explanation"],
            })
        
        # Sort by score
        paths.sort(key=lambda x: x["score"], reverse=True)
        
        # IMPROVED: Deduplicate by relation pattern (more robust)
        unique_paths = []
        seen_patterns = set()
        
        for p in paths:
            pattern = tuple(p["relations"])
            if pattern not in seen_patterns:
                unique_paths.append(p)
                seen_patterns.add(pattern)
                
                if len(unique_paths) >= self.top_k_paths:
                    break
        
        # Cache result
        if self.enable_cache:
            self._path_cache[cache_key] = unique_paths
        
        return unique_paths
    
    def _score_path(
        self,
        relation_types: List[str],
        node_types: List[str],
        path_length: int,
        entity_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Score a reasoning path."""
        # Calculate base score from relation weights
        relation_score = 1.0
        for rel_type in relation_types:
            weight = self.relation_weights.get(rel_type, 0.5)
            relation_score *= weight
        
        # Apply discount factor
        discount = self.gamma ** path_length
        
        # Apply length penalty
        length_penalty = 1.0 - (self.path_penalty * path_length)
        length_penalty = max(0.1, length_penalty)
        
        # Final score
        final_score = relation_score * discount * length_penalty
        
        # Generate explanation (with entity names when available)
        explanation = self._generate_path_explanation(
            relation_types, node_types, entity_names=entity_names
        )
        
        return {
            "score": final_score,
            "explanation": explanation,
            "components": {
                "relation_score": relation_score,
                "discount": discount,
                "length_penalty": length_penalty
            }
        }
    
    def _generate_path_explanation(
        self,
        relation_types: List[str],
        node_types: List[str],
        entity_names: Optional[List[str]] = None,
    ) -> str:
        """
        Generate human-readable explanation for a reasoning path.
        Uses entity names (e.g. prj_001, Nguyen Van A) when available for clearer paths.
        """
        relation_descriptions = {
            # New schema v2 (ResearchTopic/ResearchDirection)
            'RESEARCHES': 'researches',
            'FOCUSES_ON': 'focuses on',
            'FOCUSES_ON_TOPIC': 'focuses on topic',

            'HAS_EXPERTISE_IN': 'has expertise in',
            'HAS_SKILL': 'has skill in',
            'PARTICIPATES_IN': 'participates in',
            'BELONGS_TO': 'belongs to field',
            'SUB_FIELD_OF': 'is sub-field of',
            'OPERATES_IN': 'operates in industry',
            'PARTNERS_WITH': 'partners with',
            'FUNDS': 'funds',
            'SUPPORTS': 'supports',
            'PRODUCES': 'produces',
            'COMMERCIALIZES': 'commercializes',
            'HAS_APPLICATION_EXPERIENCE_IN': 'has experience in',
            'UNDER_FIELD': 'is under field',  # MethodTechnique -> ResearchField
            'COLLABORATES_WITH': 'collaborates with',
        }
        
        steps = []
        for i, rel_type in enumerate(relation_types):
            desc = relation_descriptions.get(rel_type, rel_type.lower())
            if i < len(node_types) - 1:
                # Prefer entity name (e.g. "PRJ_0001", "Nguyen Van A") over node type
                target = (entity_names[i + 1] if entity_names and i + 1 < len(entity_names)
                          else node_types[i + 1])
                steps.append(f"{desc} {target}")
        
        # Use ASCII arrow to avoid Windows console encoding issues (cp1252).
        return " -> ".join(steps)
    
    # ==========================================
    # IMPROVED EXPERT RECOMMENDATIONS
    # ==========================================

    def _is_new_node_in_vocab(self, source_type: str, source_id: str) -> bool:
        """
        Hybrid step-1 helper:
        return True when the source node is NOT present in the trained vocab (vocab.json).
        """
        source_key = f"{source_type}::{source_id}"
        return (not self.kg) or (not getattr(self.kg, "entity2id", None)) or (source_key not in self.kg.entity2id)

    def _fallback_score_by_rank(self, idx: int, total: int) -> float:
        """Simple monotonic score for Cypher fallback results."""
        denom = max(1, int(total))
        return round((denom - idx) / denom, 6)

    def _recommend_generic_fallback_from_candidates(
        self,
        candidates: List[Dict[str, Any]],
        target_type: str,
        id_field: str,
        limit: int,
        min_score: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """
        Convert candidate rows (from Cypher) into the same response shape as AI recommendations.
        This fallback intentionally does NOT depend on PGPR reasoning paths.
        """
        out: List[Dict[str, Any]] = []
        total = len(candidates)
        for idx, c in enumerate(candidates[: max(0, int(limit))], start=1):
            t_id = c.get(id_field)
            if not t_id:
                continue

            score = float(c.get("score")) if isinstance(c.get("score"), (int, float)) else self._fallback_score_by_rank(idx, total)
            if score < float(min_score):
                continue

            name = c.get("name") or c.get("title") or "N/A"
            rec = {
                f"{target_type.lower()}_id": t_id,
                "name": name,
                "score": round(score, 3),
                "reasoning_paths": [],
                "path_diversity": 0,
                "metrics": {},
            }

            # Preserve any useful extra fields from candidate query
            metrics = {}
            for k in ("location", "status", "trl", "budget", "type", "h_index", "citations", "publications"):
                if k in c and c.get(k) is not None:
                    metrics[k] = c.get(k)
            if metrics:
                rec["metrics"] = metrics

            out.append(rec)

        out.sort(key=lambda x: x["score"], reverse=True)
        return out[:limit]
    
    def recommend_experts_for_project_pgpr(
        self,
        project_id: str,
        limit: int = 10,
        min_score: float = 0.0,
        use_policy: bool = True,
    ) -> List[Dict[str, Any]]:
        # BƯỚC 1: KIỂM TRA XEM ĐÂY CÓ PHẢI LÀ NODE MỚI KHÔNG?
        source_key = f"Project::{project_id}"
        is_new_node = False
        if not self.kg or not getattr(self.kg, "entity2id", None) or source_key not in self.kg.entity2id:
            logger.info(
                "Phát hiện NODE MỚI '%s' chưa có trong vocab. Kích hoạt Cypher/Heuristic ngay lập tức!",
                project_id,
            )
            is_new_node = True

        # BƯỚC 2: NẾU KHÔNG PHẢI NODE MỚI -> THỬ DÙNG AI (CHÍNH)
        if use_policy and not is_new_node:
            ai_results = self._generic_recommend_with_policy(
                source_id=project_id,
                source_type="Project",
                target_type="Expert",
                limit=limit,
                min_score=min_score,
            )
            if ai_results:
                return ai_results  # AI làm tốt, trả kết quả luôn!
            logger.info("AI không tìm thấy đường cho '%s'. Chuyển sang Cypher/Heuristic...", project_id)

        # BƯỚC 3: FALLBACK XUỐNG CYPHER/HEURISTIC (Cho Node mới hoặc AI thất bại)
        cypher_results = self._recommend_experts_heuristic_improved(
            project_id=project_id,
            limit=limit,
            min_score=min_score,
        )
        return cypher_results

    def _recommend_projects_for_expert_cypher(
        self,
        expert_id: str,
        limit: int,
        status_filter: Optional[List[str]] = None,
        include_funder_candidates: bool = True,
    ) -> List[Dict[str, Any]]:
        # In current Neo4j seed, Project.status is typically "ongoing".
        status_filter = status_filter or ["ongoing", "active", "completed", "proposed"]
        with self.driver.session() as session:
            candidates = self._find_candidate_projects(session, expert_id, status_filter=status_filter)
            if include_funder_candidates:
                candidates2 = self._find_candidate_projects_by_shared_funder(
                    session, expert_id, status_filter=status_filter, limit=max(80, limit * 5)
                )
                # Merge unique by project_id, keep first occurrence (already ordered by query)
                seen = {c.get("project_id") for c in candidates if c.get("project_id")}
                for c in candidates2:
                    pid = c.get("project_id")
                    if pid and pid not in seen:
                        candidates.append(c)
                        seen.add(pid)
        return self._recommend_generic_fallback_from_candidates(
            candidates=candidates,
            target_type="Project",
            id_field="project_id",
            limit=limit,
            min_score=0.0,
        )

    def _recommend_funders_for_expert_cypher(self, expert_id: str, limit: int) -> List[Dict[str, Any]]:
        with self.driver.session() as session:
            candidates = self._find_candidate_funders_for_expert(session, expert_id, limit=max(80, limit * 5))
        return self._recommend_generic_fallback_from_candidates(
            candidates=candidates,
            target_type="Funder",
            id_field="funder_id",
            limit=limit,
            min_score=0.0,
        )

    def _recommend_enterprises_for_expert_cypher(self, expert_id: str, limit: int) -> List[Dict[str, Any]]:
        with self.driver.session() as session:
            candidates = self._find_candidate_enterprises_for_expert(session, expert_id, limit=max(80, limit * 5))
        return self._recommend_generic_fallback_from_candidates(
            candidates=candidates,
            target_type="Enterprise",
            id_field="enterprise_id",
            limit=limit,
            min_score=0.0,
        )

    def _recommend_experts_for_expert_cypher(self, expert_id: str, limit: int) -> List[Dict[str, Any]]:
        with self.driver.session() as session:
            candidates = self._find_candidate_experts_for_expert(session, expert_id, limit=max(80, limit * 5))
        return self._recommend_generic_fallback_from_candidates(
            candidates=candidates,
            target_type="Expert",
            id_field="expert_id",
            limit=limit,
            min_score=0.0,
        )

    def _recommend_funders_for_project_cypher(self, project_id: str, limit: int) -> List[Dict[str, Any]]:
        with self.driver.session() as session:
            candidates = self._find_candidate_funders(session, project_id)
        return self._recommend_generic_fallback_from_candidates(
            candidates=candidates,
            target_type="Funder",
            id_field="funder_id",
            limit=limit,
            min_score=0.0,
        )

    def _recommend_enterprises_for_project_cypher(self, project_id: str, limit: int) -> List[Dict[str, Any]]:
        with self.driver.session() as session:
            candidates = self._find_candidate_enterprises_for_project(session, project_id, limit=max(80, limit * 5))
        return self._recommend_generic_fallback_from_candidates(
            candidates=candidates,
            target_type="Enterprise",
            id_field="enterprise_id",
            limit=limit,
            min_score=0.0,
        )

    def _recommend_projects_for_project_cypher(
        self,
        project_id: str,
        limit: int,
        status_filter: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        status_filter = status_filter or ["ongoing", "active", "completed", "proposed"]
        with self.driver.session() as session:
            candidates = self._find_candidate_projects_for_project(
                session, project_id, status_filter=status_filter, limit=max(80, limit * 5)
            )
        return self._recommend_generic_fallback_from_candidates(
            candidates=candidates,
            target_type="Project",
            id_field="project_id",
            limit=limit,
            min_score=0.0,
        )

    def _recommend_experts_for_enterprise_cypher(self, enterprise_id: str, limit: int) -> List[Dict[str, Any]]:
        with self.driver.session() as session:
            candidates = self._find_candidate_experts_for_enterprise(session, enterprise_id, limit=max(80, limit * 5))
        return self._recommend_generic_fallback_from_candidates(
            candidates=candidates,
            target_type="Expert",
            id_field="expert_id",
            limit=limit,
            min_score=0.0,
        )

    def _recommend_projects_for_enterprise_cypher(
        self,
        enterprise_id: str,
        limit: int,
        status_filter: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        status_filter = status_filter or ["ongoing", "active", "completed", "proposed"]
        with self.driver.session() as session:
            candidates = self._find_candidate_projects_for_enterprise(
                session, enterprise_id, status_filter=status_filter, limit=max(80, limit * 5)
            )
        return self._recommend_generic_fallback_from_candidates(
            candidates=candidates,
            target_type="Project",
            id_field="project_id",
            limit=limit,
            min_score=0.0,
        )

    def _recommend_funders_for_enterprise_cypher(self, enterprise_id: str, limit: int) -> List[Dict[str, Any]]:
        with self.driver.session() as session:
            candidates = self._find_candidate_funders_for_enterprise(session, enterprise_id, limit=max(80, limit * 5))
        return self._recommend_generic_fallback_from_candidates(
            candidates=candidates,
            target_type="Funder",
            id_field="funder_id",
            limit=limit,
            min_score=0.0,
        )

    def _recommend_enterprises_for_enterprise_cypher(self, enterprise_id: str, limit: int) -> List[Dict[str, Any]]:
        with self.driver.session() as session:
            candidates = self._find_candidate_enterprises_for_enterprise(session, enterprise_id, limit=max(80, limit * 5))
        return self._recommend_generic_fallback_from_candidates(
            candidates=candidates,
            target_type="Enterprise",
            id_field="enterprise_id",
            limit=limit,
            min_score=0.0,
        )

    def _recommend_experts_for_funder_cypher(self, funder_id: str, limit: int) -> List[Dict[str, Any]]:
        with self.driver.session() as session:
            candidates = self._find_candidate_experts_for_funder(session, funder_id, limit=max(80, limit * 5))
        return self._recommend_generic_fallback_from_candidates(
            candidates=candidates,
            target_type="Expert",
            id_field="expert_id",
            limit=limit,
            min_score=0.0,
        )

    def _recommend_projects_for_funder_cypher(
        self,
        funder_id: str,
        limit: int,
        status_filter: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        status_filter = status_filter or ["ongoing", "active", "completed", "proposed"]
        with self.driver.session() as session:
            candidates = self._find_candidate_projects_for_funder(
                session, funder_id, status_filter=status_filter, limit=max(80, limit * 5)
            )
        return self._recommend_generic_fallback_from_candidates(
            candidates=candidates,
            target_type="Project",
            id_field="project_id",
            limit=limit,
            min_score=0.0,
        )

    def _recommend_enterprises_for_funder_cypher(self, funder_id: str, limit: int) -> List[Dict[str, Any]]:
        with self.driver.session() as session:
            candidates = self._find_candidate_enterprises_for_funder(session, funder_id, limit=max(80, limit * 5))
        return self._recommend_generic_fallback_from_candidates(
            candidates=candidates,
            target_type="Enterprise",
            id_field="enterprise_id",
            limit=limit,
            min_score=0.0,
        )
    
    def _recommend_experts_heuristic_improved(
        self,
        project_id: str,
        limit: int,
        min_score: float,
    ) -> List[Dict[str, Any]]:
        """
        IMPROVED heuristic recommendation:
        - Batch query all reachable candidates
        - Process by depth order
        - Better scoring function
        """
        if self.POLICY_ONLY_MODE:
            logger.debug("Heuristic recommendation is disabled in policy-only mode.")
            return []

        with self.driver.session() as session:
            # IMPROVEMENT: Single batch query to get all reachable experts
            candidates = self._find_all_reachable_experts_batch(
                session, project_id, max_depth=self.DEFAULT_HARD_LIMIT_DEPTH
            )
            
            if not candidates:
                logger.info(f"No candidate experts found for project {project_id}")
                return []
            
            # Group candidates by minimum path length
            candidates_by_depth = defaultdict(list)
            for candidate in candidates:
                depth = candidate.get("min_hops", 5)
                candidates_by_depth[depth].append(candidate)
            
            # Process candidates in order of increasing depth
            recommendations = []
            seen_expert_ids = set()
            
            for depth in sorted(candidates_by_depth.keys()):
                if len(recommendations) >= limit:
                    break
                
                logger.debug(f"Processing {len(candidates_by_depth[depth])} candidates at depth {depth}")
                
                for candidate in candidates_by_depth[depth]:
                    if len(recommendations) >= limit:
                        break
                    
                    expert_id = candidate["expert_id"]
                    if expert_id in seen_expert_ids:
                        continue
                    
                    # Find reasoning paths with appropriate depth limit
                    paths = self.find_reasoning_paths(
                        source_id=project_id,
                        source_type="Project",
                        target_id=expert_id,
                        target_type="Expert",
                        max_length=min(depth + 2, self.DEFAULT_HARD_LIMIT_DEPTH),  # Thread-safe!
                    )
                    
                    if not paths:
                        continue
                    
                    # IMPROVEMENT: Better scoring with multiple features
                    score = self._calculate_expert_score(paths, candidate)
                    
                    if score >= min_score:
                        recommendations.append({
                            "expert_id": expert_id,
                            "name": candidate.get("name"),
                            "location": candidate.get("location"),
                            "score": round(score, 3),
                            "reasoning_paths": [
                                {
                                    "path": p["explanation"],
                                    "score": round(p["score"], 3),
                                    "length": p["length"]
                                }
                                for p in paths[:3]
                            ],
                            "path_diversity": len(set(tuple(p["relations"]) for p in paths)),
                            "metrics": {
                                "h_index": candidate.get("h_index"),
                                "citations": candidate.get("citations"),
                                "publications": candidate.get("publications"),
                            },
                        })
                        seen_expert_ids.add(expert_id)
            
            # Sort by score
            recommendations.sort(key=lambda x: x["score"], reverse=True)
            return recommendations[:limit]
    
    def _find_all_reachable_experts_batch(
        self,
        session,
        project_id: str,
        max_depth: int = 12,
    ) -> List[Dict[str, Any]]:
        """
        IMPROVED: Batch query to find all reachable experts with min path length.
        
        Single query instead of multiple queries at each depth level.
        """
        try:
            # Schema v2: Project -> ResearchTopic/ResearchDirection,
            # Expert -> ResearchTopic via HAS_EXPERIENCE_IN, Expert -> ResearchDirection via RESEARCHES.
            result = session.run(
                """
                MATCH (p:Project {project_id: $project_id})

                // Source A: shared topics
                OPTIONAL MATCH (p)-[:FOCUSES_ON_TOPIC]->(t:ResearchTopic)<-[:HAS_EXPERIENCE_IN]-(e1:Expert)
                WHERE NOT (e1)-[:PARTICIPATES_IN]->(p)

                // Source B: shared directions
                OPTIONAL MATCH (p)-[:FOCUSES_ON]->(d:ResearchDirection)<-[:RESEARCHES]-(e2:Expert)
                WHERE NOT (e2)-[:PARTICIPATES_IN]->(p)

                WITH collect(DISTINCT e1) + collect(DISTINCT e2) AS experts, p
                UNWIND experts AS e
                WITH e, p
                WHERE e IS NOT NULL

                OPTIONAL MATCH (e)-[:LOCATED_IN]->(l:Location)
                RETURN DISTINCT e.expert_id as expert_id,
                       e.name as name,
                       l.location_id as location,
                       e.h_index as h_index,
                       e.citation_count as citations,
                       e.publication_count as publications,
                       3 as min_hops
                LIMIT 200
                """,
                project_id=project_id,
                timeout=self.DEFAULT_QUERY_TIMEOUT,
            )
            out = [dict(record) for record in result]

            # If the graph doesn't follow the expected schema,
            # fall back to a generic traversal (more robust across datasets).
            if out:
                return out
            return self._find_candidate_experts_generic(session, project_id, max_depth=max_depth)
            
        except Exception as e:
            logger.warning(f"Error in batch candidate query: {e}")
            # Fallback to simpler query
            return self._find_candidate_experts_generic(session, project_id, max_depth=max_depth)
    
    def _find_candidate_experts_simple(
        self,
        session,
        project_id: str
    ) -> List[Dict[str, Any]]:
        """Fallback: Simple candidate query without depth calculation."""
        result = session.run(
            """
            MATCH (p:Project {project_id: $project_id})
            OPTIONAL MATCH (p)-[:FOCUSES_ON_TOPIC]->(t:ResearchTopic)<-[:HAS_EXPERIENCE_IN]-(e:Expert)
            WHERE NOT (e)-[:PARTICIPATES_IN]->(p)
            OPTIONAL MATCH (e)-[:LOCATED_IN]->(l:Location)
            RETURN DISTINCT e.expert_id as expert_id,
                   e.name as name,
                   l.location_id as location,
                   e.h_index as h_index,
                   e.citation_count as citations,
                   e.publication_count as publications,
                   3 as min_hops
            LIMIT 100
            """,
            project_id=project_id,
            timeout=self.DEFAULT_QUERY_TIMEOUT,
        )
        
        return [dict(record) for record in result]

    def _find_candidate_experts_generic(
        self,
        session,
        project_id: str,
        max_depth: int = 3,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """
        Generic candidate discovery:
        find Experts reachable from Project within max_depth hops by ANY relationship types.

        This matches how you debug in Neo4j Browser:
            MATCH (p:Project {project_id:$id})-[*1..3]-(e:Expert) RETURN DISTINCT e ...
        """
        depth = int(max(1, min(max_depth, 12)))
        lim = int(max(1, min(limit, 500)))

        # Cypher does not accept a parameter for variable-length patterns,
        # so we safely embed the bounded integer depth/limit.
        query = f"""
        MATCH (p:Project {{project_id: $project_id}})
        MATCH path = (p)-[*1..{depth}]-(e:Expert)
        WHERE NOT (e)-[:PARTICIPATES_IN]->(p)
        WITH e, MIN(length(path)) AS min_hops
        RETURN e.expert_id AS expert_id,
               e.name AS name,
               e.location AS location,
               e.h_index AS h_index,
               e.citation_count AS citations,
               e.publication_count AS publications,
               min_hops
        ORDER BY min_hops ASC
        LIMIT {lim}
        """
        result = session.run(query, project_id=project_id, timeout=self.DEFAULT_QUERY_TIMEOUT)
        return [dict(record) for record in result]
    
    def _calculate_expert_score(
        self,
        paths: List[Dict[str, Any]],
        expert_info: Dict[str, Any],
    ) -> float:
        """
        IMPROVED scoring function with multiple features.
        
        Features:
        - Max path score (best single path)
        - Average path score (overall quality)
        - Minimum path length (prefer direct connections)
        - Path diversity (multiple reasoning types)
        - Expert quality (h-index, citations)
        """
        if not paths:
            return 0.0
        
        # Path-based features
        path_scores = [p["score"] for p in paths]
        max_path_score = max(path_scores)
        avg_path_score = np.mean(path_scores)
        min_path_length = min(p["length"] for p in paths)
        path_diversity = len(set(tuple(p["relations"]) for p in paths))
        
        # Normalize path diversity
        diversity_score = min(path_diversity / self.top_k_paths, 1.0)
        
        # Length bonus (prefer shorter paths)
        length_score = 1.0 / min_path_length
        
        # Expert quality features
        h_index = expert_info.get("h_index", 0) or 0
        citations = expert_info.get("citations", 0) or 0
        
        h_index_normalized = min(h_index / 100.0, 1.0)
        citation_normalized = min(np.log10(citations + 1) / 6.0, 1.0)
        quality_score = (h_index_normalized + citation_normalized) / 2.0
        
        # Weighted combination
        final_score = (
            max_path_score * self.SCORE_WEIGHT_MAX_PATH +
            avg_path_score * self.SCORE_WEIGHT_AVG_PATH +
            length_score * self.SCORE_WEIGHT_MIN_LENGTH +
            diversity_score * self.SCORE_WEIGHT_DIVERSITY +
            quality_score * self.SCORE_WEIGHT_QUALITY
        )
        
        return final_score
    
    def _recommend_with_policy(
        self,
        project_id: str,
        limit: int,
        min_score: float,
    ) -> List[Dict[str, Any]]:
        """Use trained policy for recommendations."""
        exclude_keys = []
        with self.driver.session() as session:
            res = session.run(
                "MATCH (e:Expert)-[:PARTICIPATES_IN]->(p:Project {project_id: $pid}) "
                "RETURN e.expert_id as eid",
                pid=project_id,
            )
            exclude_keys = [f"Expert::{record['eid']}" for record in res]

        n_rollouts = 1000
        policy_paths = self.policy_guided_paths(
            source_id=project_id,
            source_type="Project",
            target_type="Expert",
            n_rollouts=n_rollouts,
            deterministic=False,
            exclude_keys=exclude_keys,
        )
        
        if not policy_paths:
            # Try deterministic
            policy_paths = self.policy_guided_paths(
                source_id=project_id,
                source_type="Project",
                target_type="Expert",
                n_rollouts=1000,
                deterministic=True,
                exclude_keys=exclude_keys,
            )
        
        if policy_paths:
            recommendations = []
            with self.driver.session() as session:
                for item in policy_paths[:limit * 2]:
                    target_key = item["target_entity_key"]
                    if "::" not in target_key:
                        continue
                    _, expert_id = target_key.split("::", 1)
                    expert_info = self._get_expert_info(
                        session,
                        expert_id,
                        exclude_project_id=project_id,
                    )
                    if not expert_info:
                        continue
                    
                    rec = {
                        "expert_id": expert_id,
                        "name": expert_info.get("name"),
                        "location": expert_info.get("location"),
                        "score": round(item["score"], 3),
                        "reasoning_paths": [{
                            # Use ASCII arrow to avoid Windows console encoding issues (cp1252).
                            "path": " -> ".join(item["path_relations"]),
                            "score": item["score"],
                            "length": len(item["path_relations"]),
                        }],
                        "path_diversity": item["n_paths"],
                        "metrics": {
                            "h_index": expert_info.get("h_index"),
                            "citations": expert_info.get("citations"),
                            "publications": expert_info.get("publications"),
                        },
                    }
                    if rec["score"] >= min_score:
                        recommendations.append(rec)
            
            recommendations.sort(key=lambda x: x["score"], reverse=True)
            if recommendations:
                return recommendations[:limit]
        
        logger.info("Policy-guided paths returned no experts.")
        return []
    
    def policy_guided_paths(
        self,
        source_id: str,
        source_type: str,
        target_type: str,
        n_rollouts: int = 20,
        deterministic: bool = False,
        exclude_keys: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Use trained policy to walk from source until reaching target type."""
        if self._env is None or self._policy_device is None:
            return []

        task_name = f"{source_type}_{target_type}"
        active_policy = self.policies.get(task_name)
        if active_policy is None:
            logger.warning("No policy loaded for task %s.", task_name)
            return []
        
        try:
            import torch
        except ImportError:
            return []
        
        source_key = _entity_key(source_type, source_id)
        if source_key not in self.kg.entity2id:
            logger.debug("Source %s not in KG vocab; policy-guided paths skipped.", source_key)
            return []
        
        results = defaultdict(lambda: {"paths": [], "scores": []})
        
        for _ in range(n_rollouts):
            state, valid_actions = self._env.reset(
                source_key,
                target_type=target_type,
                exclude_keys=exclude_keys,
            )
            current_ent, path = state
            path_log_prob = 0.0
            
            while valid_actions and len(path) < self.max_path_length - 1:
                action_idx, log_prob = active_policy.select_action(
                    current_ent, path, valid_actions, self._policy_device, deterministic=deterministic
                )
                if action_idx < 0:
                    break
                
                path_log_prob += log_prob.item()
                action = valid_actions[action_idx]
                next_state, valid_actions, reward, done = self._env.step(action)
                current_ent, path = next_state
                
                if done and reward > 0:
                    entity_keys = self._env.get_path_entity_keys()
                    rel_types = self._env.get_path_relation_types()
                    target_key = entity_keys[-1] if entity_keys else None
                    
                    if target_key and target_key.startswith(target_type + "::"):
                        results[target_key]["paths"].append((list(rel_types), list(entity_keys)))
                        results[target_key]["scores"].append(np.exp(path_log_prob) * reward)
                    break
        
        out = []
        for target_key, data in results.items():
            if not data["scores"]:
                continue
                
            # Gom cặp (đường đi, điểm số) và sắp xếp giảm dần theo điểm
            paths_with_scores = list(zip(data["paths"], data["scores"]))
            paths_with_scores.sort(key=lambda x: x[1], reverse=True)
            
            # Lọc ra Top 3 đường đi CÓ LOGIC KHÁC NHAU
            unique_top_paths = []
            seen_patterns = set()
            for (rels, ents), p_score in paths_with_scores:
                pattern = tuple(rels)
                if pattern not in seen_patterns:
                    seen_patterns.add(pattern)
                    unique_top_paths.append({
                        "path_relations": rels,
                        "path_entities": ents,
                        "path_score": float(p_score)
                    })
                if len(unique_top_paths) >= 3: # Lấy tối đa 3 đường
                    break
                    
            out.append({
                "target_entity_key": target_key,
                "score": float(np.mean(data["scores"])),
                "n_paths": len(data["paths"]),
                "top_paths": unique_top_paths # ĐÂY LÀ KEY CÒN THIẾU
            })
        
        out.sort(key=lambda x: x["score"], reverse=True)
        return out
    def _get_expert_info(
        self,
        session,
        expert_id: str,
        exclude_project_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Fetch expert info from Neo4j and optionally exclude existing project members."""
        query = "MATCH (e:Expert {expert_id: $expert_id}) "
        if exclude_project_id:
            query += "WHERE NOT (e)-[:PARTICIPATES_IN]->(:Project {project_id: $exclude_project_id}) "
        query += """
        OPTIONAL MATCH (e)-[:LOCATED_IN]->(l:Location)
        RETURN e.name AS name,
               l.location_id AS location,
               e.h_index AS h_index,
               e.citation_count AS citations,
               e.publication_count AS publications
        """
        result = session.run(
            query,
            expert_id=expert_id,
            exclude_project_id=exclude_project_id,
        )
        records = list(result)
        return dict(records[0]) if records else None
    
    # ==========================================
    # PROJECT & FUNDER RECOMMENDATIONS (similar improvements)
    # ==========================================
    
    def recommend_projects_for_expert_pgpr(
        self,
        expert_id: str,
        limit: int = 10,
        status_filter: List[str] = None,
        include_funder_candidates: bool = True,
    ) -> List[Dict[str, Any]]:
        is_new_node = self._is_new_node_in_vocab("Expert", expert_id)
        if not is_new_node:
            ai_results = self._generic_recommend_with_policy(
                source_id=expert_id,
                source_type="Expert",
                target_type="Project",
                limit=limit,
            )
            if ai_results:
                return ai_results
            logger.info("AI không tìm thấy đường cho '%s'. Chuyển sang Cypher/Heuristic...", expert_id)
        else:
            logger.info("NODE MỚI '%s' chưa có trong vocab. Chuyển sang Cypher/Heuristic...", expert_id)

        return self._recommend_projects_for_expert_cypher(
            expert_id=expert_id,
            limit=limit,
            status_filter=status_filter,
            include_funder_candidates=include_funder_candidates,
        )

    def recommend_funders_for_expert_pgpr(
        self,
        expert_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        is_new_node = self._is_new_node_in_vocab("Expert", expert_id)
        if not is_new_node:
            ai_results = self._generic_recommend_with_policy(
                source_id=expert_id,
                source_type="Expert",
                target_type="Funder",
                limit=limit,
            )
            if ai_results:
                return ai_results
            logger.info("AI không tìm thấy đường cho '%s'. Chuyển sang Cypher/Heuristic...", expert_id)
        else:
            logger.info("NODE MỚI '%s' chưa có trong vocab. Chuyển sang Cypher/Heuristic...", expert_id)

        return self._recommend_funders_for_expert_cypher(expert_id=expert_id, limit=limit)

    def recommend_enterprises_for_expert_pgpr(
        self,
        expert_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        is_new_node = self._is_new_node_in_vocab("Expert", expert_id)
        if not is_new_node:
            ai_results = self._generic_recommend_with_policy(
                source_id=expert_id,
                source_type="Expert",
                target_type="Enterprise",
                limit=limit,
            )
            if ai_results:
                return ai_results
            logger.info("AI không tìm thấy đường cho '%s'. Chuyển sang Cypher/Heuristic...", expert_id)
        else:
            logger.info("NODE MỚI '%s' chưa có trong vocab. Chuyển sang Cypher/Heuristic...", expert_id)

        return self._recommend_enterprises_for_expert_cypher(expert_id=expert_id, limit=limit)

    def recommend_experts_for_expert_pgpr(
        self,
        expert_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        is_new_node = self._is_new_node_in_vocab("Expert", expert_id)
        if not is_new_node:
            ai_results = self._generic_recommend_with_policy(
                source_id=expert_id,
                source_type="Expert",
                target_type="Expert",
                limit=limit,
            )
            if ai_results:
                return ai_results
            logger.info("AI không tìm thấy đường cho '%s'. Chuyển sang Cypher/Heuristic...", expert_id)
        else:
            logger.info("NODE MỚI '%s' chưa có trong vocab. Chuyển sang Cypher/Heuristic...", expert_id)

        return self._recommend_experts_for_expert_cypher(expert_id=expert_id, limit=limit)

    def _calculate_project_score(self, paths: List[Dict], project_info: Dict) -> float:
        """Calculate project recommendation score."""
        if not paths:
            return 0.0
        
        max_path_score = max(p["score"] for p in paths)
        avg_path_score = np.mean([p["score"] for p in paths])
        path_diversity = len(set(tuple(p["relations"]) for p in paths))
        
        return (
            max_path_score * 0.5 +
            avg_path_score * 0.3 +
            (path_diversity / self.top_k_paths) * 0.2
        )
    
    def _find_candidate_projects(
        self,
        session,
        expert_id: str,
        status_filter: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Find candidate projects.

        NOTE (schema v2):
        - Neo4j uses ResearchTopic/ResearchDirection (NOT ResearchField).
        - Expert connects to topics via HAS_EXPERIENCE_IN and to directions via RESEARCHES.
        - Project connects to topics via FOCUSES_ON_TOPIC and to directions via FOCUSES_ON.
        """
        result = session.run(
            """
            // Candidate source 1: Shared ResearchTopic
            MATCH (e:Expert {expert_id: $expert_id})
            MATCH (e)-[:HAS_EXPERIENCE_IN]->(t:ResearchTopic)<-[:FOCUSES_ON_TOPIC]-(p:Project)
            WHERE p.status IN $status_filter AND NOT (e)-[:PARTICIPATES_IN]->(p)
            OPTIONAL MATCH (p)-[:LOCATED_IN]->(l:Location)
            RETURN DISTINCT p.project_id as project_id,
                   p.title as title,
                   p.status as status,
                   l.location_id as location,
                   p.trl as trl,
                   p.budget as budget,
                   2 as rank_hint
            UNION
            // Candidate source 2: Shared ResearchDirection
            MATCH (e:Expert {expert_id: $expert_id})
            MATCH (e)-[:RESEARCHES]->(d:ResearchDirection)<-[:FOCUSES_ON]-(p:Project)
            WHERE p.status IN $status_filter AND NOT (e)-[:PARTICIPATES_IN]->(p)
            OPTIONAL MATCH (p)-[:LOCATED_IN]->(l:Location)
            RETURN DISTINCT p.project_id as project_id,
                   p.title as title,
                   p.status as status,
                   l.location_id as location,
                   p.trl as trl,
                   p.budget as budget,
                   3 as rank_hint
            LIMIT 120
            """,
            expert_id=expert_id,
            status_filter=status_filter,
            timeout=self.DEFAULT_QUERY_TIMEOUT,
        )
        
        return [dict(record) for record in result]

    def _find_candidate_projects_by_shared_funder(
        self,
        session,
        expert_id: str,
        status_filter: List[str],
        limit: int = 80,
    ) -> List[Dict[str, Any]]:
        """
        Candidate projects based on shared funder with expert's participated projects.
        
        Pattern:
          (Expert)-[:PARTICIPATES_IN]->(p0:Project)<-[:FUNDS]-(f:Funder)-[:FUNDS]->(p:Project)
        """
        try:
            result = session.run(
                f"""
                MATCH (e:Expert {{expert_id: $expert_id}})-[:PARTICIPATES_IN]->(p0:Project)<-[:FUNDS]-(f:Funder)-[:FUNDS]->(p:Project)
                WHERE p.status IN $status_filter
                  AND NOT (e)-[:PARTICIPATES_IN]->(p)
                
                WITH p, count(DISTINCT f) as common_funders
                OPTIONAL MATCH (p)-[:LOCATED_IN]->(l:Location)
                RETURN DISTINCT p.project_id as project_id,
                       p.title as title,
                       p.status as status,
                       l.location_id as location,
                       p.trl as trl,
                       p.budget as budget,
                       common_funders
                ORDER BY common_funders DESC
                LIMIT {limit}
                """,
                expert_id=expert_id,
                status_filter=status_filter,
                timeout=self.DEFAULT_QUERY_TIMEOUT,
            )
            return [dict(record) for record in result]
        except Exception as e:
            logger.debug(f"Shared-funder candidate query failed: {e}")
            return []
    
    def recommend_funders_for_project_pgpr(
        self,
        project_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        is_new_node = self._is_new_node_in_vocab("Project", project_id)
        if not is_new_node:
            ai_results = self._generic_recommend_with_policy(
                source_id=project_id,
                source_type="Project",
                target_type="Funder",
                limit=limit,
            )
            if ai_results:
                return ai_results
            logger.info("AI không tìm thấy đường cho '%s'. Chuyển sang Cypher/Heuristic...", project_id)
        else:
            logger.info("NODE MỚI '%s' chưa có trong vocab. Chuyển sang Cypher/Heuristic...", project_id)

        return self._recommend_funders_for_project_cypher(project_id=project_id, limit=limit)

    def recommend_enterprises_for_project_pgpr(
        self,
        project_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        is_new_node = self._is_new_node_in_vocab("Project", project_id)
        if not is_new_node:
            ai_results = self._generic_recommend_with_policy(
                source_id=project_id,
                source_type="Project",
                target_type="Enterprise",
                limit=limit,
            )
            if ai_results:
                return ai_results
            logger.info("AI không tìm thấy đường cho '%s'. Chuyển sang Cypher/Heuristic...", project_id)
        else:
            logger.info("NODE MỚI '%s' chưa có trong vocab. Chuyển sang Cypher/Heuristic...", project_id)

        return self._recommend_enterprises_for_project_cypher(project_id=project_id, limit=limit)

    def recommend_projects_for_project_pgpr(
        self,
        project_id: str,
        limit: int = 10,
        status_filter: List[str] = None,
    ) -> List[Dict[str, Any]]:
        is_new_node = self._is_new_node_in_vocab("Project", project_id)
        if not is_new_node:
            ai_results = self._generic_recommend_with_policy(
                source_id=project_id,
                source_type="Project",
                target_type="Project",
                limit=limit,
            )
            if ai_results:
                return ai_results
            logger.info("AI không tìm thấy đường cho '%s'. Chuyển sang Cypher/Heuristic...", project_id)
        else:
            logger.info("NODE MỚI '%s' chưa có trong vocab. Chuyển sang Cypher/Heuristic...", project_id)

        return self._recommend_projects_for_project_cypher(
            project_id=project_id,
            limit=limit,
            status_filter=status_filter,
        )
    
    def _calculate_funder_score(self, paths: List[Dict], funder_info: Dict) -> float:
        """Calculate funder recommendation score."""
        if not paths:
            return 0.0
        
        max_path_score = max(p["score"] for p in paths)
        avg_path_score = np.mean([p["score"] for p in paths])
        path_diversity = len(set(tuple(p["relations"]) for p in paths))
        
        return (
            max_path_score * 0.5 +
            avg_path_score * 0.3 +
            (path_diversity / self.top_k_paths) * 0.2
        )
    
    def _find_candidate_funders(
        self,
        session,
        project_id: str
    ) -> List[Dict[str, Any]]:
        """
        Find candidate funders.
        
        IMPROVEMENTS (consistent with other recommenders):
        - Expand field hierarchy in BOTH directions (parent/child/sibling) using undirected traversal
        - Add a robust fallback source based on funders that have funded other projects in related fields
        - Track candidate_sources for debugging and explainability
        
        Why this matters:
        - In realistic graphs, a funder may SUPPORT a parent/sibling field of the project's field.
        - Some datasets have sparse SUPPORTS edges but reliable FUNDS edges.
        """
        by_id: Dict[str, Dict[str, Any]] = {}
        
        # Source 1: Funders that SUPPORT project's topics/directions (schema v2)
        try:
            result = session.run(
                """
                MATCH (p:Project {project_id: $project_id})
                OPTIONAL MATCH (p)-[:FOCUSES_ON_TOPIC]->(t:ResearchTopic)<-[:SUPPORTS_TOPIC]-(f1:Funder)
                OPTIONAL MATCH (p)-[:FOCUSES_ON]->(d:ResearchDirection)<-[:SUPPORTS]-(f2:Funder)
                WITH p, collect(DISTINCT f1) + collect(DISTINCT f2) AS funders
                UNWIND funders AS f
                WITH p, f
                WHERE f IS NOT NULL AND NOT (f)-[:FUNDS]->(p)
                
                RETURN DISTINCT f.funder_id as funder_id,
                       f.name as name,
                       f.type as type,
                       f.location as location,
                       f.budget_capacity as budget_capacity
                LIMIT 80
                """,
                project_id=project_id,
                timeout=self.DEFAULT_QUERY_TIMEOUT,
            )
            for record in result:
                d = dict(record)
                d["candidate_sources"] = ["supports_field"]
                by_id[d["funder_id"]] = d
        except Exception as e:
            logger.debug("Candidate funders (SUPPORTS) query failed: %s", e)
        
        # Source 2: Funders that FUNDS other projects sharing topic/direction (portfolio-based)
        try:
            result2 = session.run(
                """
                MATCH (p:Project {project_id: $project_id})
                OPTIONAL MATCH (p)-[:FOCUSES_ON_TOPIC]->(t:ResearchTopic)<-[:FOCUSES_ON_TOPIC]-(p2:Project)
                OPTIONAL MATCH (p)-[:FOCUSES_ON]->(d:ResearchDirection)<-[:FOCUSES_ON]-(p3:Project)
                WITH p, collect(DISTINCT p2) + collect(DISTINCT p3) AS projects
                UNWIND projects AS px
                WITH p, px
                WHERE px IS NOT NULL AND px.project_id <> $project_id
                MATCH (f:Funder)-[:FUNDS]->(px)
                WHERE NOT (f)-[:FUNDS]->(p)
                
                RETURN DISTINCT f.funder_id as funder_id,
                       f.name as name,
                       f.type as type,
                       f.location as location,
                       f.budget_capacity as budget_capacity,
                       count(DISTINCT px) as funded_related_projects
                ORDER BY funded_related_projects DESC
                LIMIT 80
                """,
                project_id=project_id,
                timeout=self.DEFAULT_QUERY_TIMEOUT,
            )
            for record in result2:
                d = dict(record)
                fid = d["funder_id"]
                if fid in by_id:
                    src = set(by_id[fid].get("candidate_sources") or [])
                    src.add("funds_related_projects")
                    by_id[fid]["candidate_sources"] = sorted(src)
                    by_id[fid]["funded_related_projects"] = max(
                        by_id[fid].get("funded_related_projects", 0) or 0,
                        d.get("funded_related_projects", 0) or 0,
                    )
                else:
                    d["candidate_sources"] = ["funds_related_projects"]
                    by_id[fid] = d
        except Exception as e:
            logger.debug("Candidate funders (FUNDS portfolio) query failed: %s", e)
        
        return list(by_id.values())

    def _find_candidate_enterprises_for_project(
        self,
        session,
        project_id: str,
        limit: int = 80,
    ) -> List[Dict[str, Any]]:
        """
        Candidate enterprises: PARTNERS_WITH projects in same/related field;
        or OPERATES_IN industry linked via experts in project.
        """
        by_id: Dict[str, Dict[str, Any]] = {}
        try:
            result = session.run(
                """
                MATCH (p:Project {project_id: $project_id})
                OPTIONAL MATCH (p)-[:FOCUSES_ON_TOPIC]->(t:ResearchTopic)<-[:FOCUSES_ON_TOPIC]-(p2:Project)<-[:PARTNERS_WITH]-(en:Enterprise)
                OPTIONAL MATCH (p)-[:FOCUSES_ON]->(d:ResearchDirection)<-[:FOCUSES_ON]-(p3:Project)<-[:PARTNERS_WITH]-(en2:Enterprise)
                WITH p, collect(DISTINCT {en: en, px: p2}) + collect(DISTINCT {en: en2, px: p3}) AS rows
                UNWIND rows AS r
                WITH p, r.en AS en, r.px AS px
                WHERE en IS NOT NULL AND px IS NOT NULL AND px.project_id <> $project_id
                RETURN DISTINCT en.enterprise_id AS enterprise_id,
                       en.name AS name,
                       en.location AS location,
                       count(DISTINCT px) AS partner_projects
                ORDER BY partner_projects DESC
                LIMIT $limit
                """,
                project_id=project_id,
                limit=limit,
                timeout=self.DEFAULT_QUERY_TIMEOUT,
            )
            for record in result:
                d = dict(record)
                d["candidate_sources"] = ["related_partner_projects"]
                by_id[d["enterprise_id"]] = d
        except Exception as e:
            logger.debug("Candidate enterprises for project query failed: %s", e)
        try:
            result2 = session.run(
                """
                MATCH (p:Project {project_id: $project_id})<-[:PARTICIPATES_IN]-(e:Expert)
                MATCH (e)-[:HAS_APPLICATION_EXPERIENCE_IN]->(i:Industry)<-[:OPERATES_IN]-(en:Enterprise)
                RETURN DISTINCT en.enterprise_id AS enterprise_id,
                       en.name AS name,
                       en.location AS location,
                       count(DISTINCT i) AS matched_industries
                ORDER BY matched_industries DESC
                LIMIT $limit
                """,
                project_id=project_id,
                limit=limit,
                timeout=self.DEFAULT_QUERY_TIMEOUT,
            )
            for record in result2:
                d = dict(record)
                eid = d["enterprise_id"]
                if eid in by_id:
                    src = set(by_id[eid].get("candidate_sources") or [])
                    src.add("expert_industry")
                    by_id[eid]["candidate_sources"] = sorted(src)
                else:
                    d["candidate_sources"] = ["expert_industry"]
                    by_id[eid] = d
        except Exception as e:
            logger.debug("Candidate enterprises for project (expert industry) failed: %s", e)
        return list(by_id.values())

    def _find_candidate_projects_for_project(
        self,
        session,
        project_id: str,
        status_filter: List[str],
        limit: int = 80,
    ) -> List[Dict[str, Any]]:
        """Similar projects: same/related field; same funder; shared experts."""
        by_id: Dict[str, Dict[str, Any]] = {}
        try:
            result = session.run(
                """
                MATCH (p:Project {project_id: $project_id})
                OPTIONAL MATCH (p)-[:FOCUSES_ON_TOPIC]->(t:ResearchTopic)<-[:FOCUSES_ON_TOPIC]-(p2:Project)
                OPTIONAL MATCH (p)-[:FOCUSES_ON]->(d:ResearchDirection)<-[:FOCUSES_ON]-(p3:Project)
                WITH p, collect(DISTINCT p2) + collect(DISTINCT p3) AS ps
                UNWIND ps AS px
                WITH px
                WHERE px IS NOT NULL AND px.project_id <> $project_id AND px.status IN $status_filter
                OPTIONAL MATCH (px)-[:LOCATED_IN]->(l:Location)
                RETURN DISTINCT px.project_id AS project_id,
                       px.title AS title,
                       px.status AS status,
                       l.location_id AS location,
                       px.trl AS trl,
                       px.budget AS budget
                LIMIT $limit
                """,
                project_id=project_id,
                status_filter=status_filter,
                limit=limit,
                timeout=self.DEFAULT_QUERY_TIMEOUT,
            )
            for record in result:
                d = dict(record)
                d["candidate_sources"] = ["same_field"]
                by_id[d["project_id"]] = d
        except Exception as e:
            logger.debug("Candidate projects for project (field) failed: %s", e)
        try:
            result2 = session.run(
                """
                MATCH (p:Project {project_id: $project_id})<-[:FUNDS]-(f:Funder)-[:FUNDS]->(p2:Project)
                WHERE p2.project_id <> $project_id AND p2.status IN $status_filter
                OPTIONAL MATCH (p2)-[:LOCATED_IN]->(l:Location)
                RETURN DISTINCT p2.project_id AS project_id,
                       p2.title AS title,
                       p2.status AS status,
                       l.location_id AS location,
                       p2.trl AS trl,
                       p2.budget AS budget
                LIMIT $limit
                """,
                project_id=project_id,
                status_filter=status_filter,
                limit=limit,
                timeout=self.DEFAULT_QUERY_TIMEOUT,
            )
            for record in result2:
                d = dict(record)
                pid = d["project_id"]
                if pid in by_id:
                    src = set(by_id[pid].get("candidate_sources") or [])
                    src.add("same_funder")
                    by_id[pid]["candidate_sources"] = sorted(src)
                else:
                    d["candidate_sources"] = ["same_funder"]
                    by_id[pid] = d
        except Exception as e:
            logger.debug("Candidate projects for project (funder) failed: %s", e)
        return list(by_id.values())

    def _find_candidate_funders_for_expert(
        self,
        session,
        expert_id: str,
        limit: int = 80,
    ) -> List[Dict[str, Any]]:
        """
        Find candidate funders for an expert.

        Nguồn ứng viên:
        - Funders đã FUNDS các project mà expert đó tham gia.
        - Funders SUPPORT các lĩnh vực mà expert có HAS_EXPERTISE_IN.
        """
        by_id: Dict[str, Dict[str, Any]] = {}

        # Source 1: funders tài trợ các project mà expert tham gia
        try:
            result = session.run(
                f"""
                MATCH (e:Expert {{expert_id: $expert_id}})-[:PARTICIPATES_IN]->(p:Project)<-[:FUNDS]-(f:Funder)
                RETURN DISTINCT f.funder_id AS funder_id,
                       f.name AS name,
                       f.type AS type,
                       f.location AS location,
                       f.budget_capacity AS budget_capacity,
                       count(DISTINCT p) AS funded_related_projects
                ORDER BY funded_related_projects DESC
                LIMIT {limit}
                """,
                expert_id=expert_id,
                timeout=self.DEFAULT_QUERY_TIMEOUT,
            )
            for record in result:
                d = dict(record)
                d["candidate_sources"] = ["expert_projects"]
                by_id[d["funder_id"]] = d
        except Exception as e:
            logger.debug("Candidate funders for expert (projects) query failed: %s", e)

        # Source 2: funders SUPPORT các lĩnh vực mà expert có chuyên môn
        try:
            result2 = session.run(
                f"""
                MATCH (e:Expert {{expert_id: $expert_id}})
                OPTIONAL MATCH (e)-[:HAS_EXPERIENCE_IN]->(t:ResearchTopic)<-[:SUPPORTS_TOPIC]-(f1:Funder)
                OPTIONAL MATCH (e)-[:RESEARCHES]->(d:ResearchDirection)<-[:SUPPORTS]-(f2:Funder)
                WITH collect(DISTINCT f1) + collect(DISTINCT f2) AS funders
                UNWIND funders AS f
                WITH f
                WHERE f IS NOT NULL
                RETURN DISTINCT f.funder_id AS funder_id,
                       f.name AS name,
                       f.type AS type,
                       f.location AS location,
                       f.budget_capacity AS budget_capacity
                LIMIT {limit}
                """,
                expert_id=expert_id,
                timeout=self.DEFAULT_QUERY_TIMEOUT,
            )
            for record in result2:
                d = dict(record)
                fid = d["funder_id"]
                if fid in by_id:
                    src = set(by_id[fid].get("candidate_sources") or [])
                    src.add("supports_expert_field")
                    by_id[fid]["candidate_sources"] = sorted(src)
                else:
                    d["candidate_sources"] = ["supports_expert_field"]
                    by_id[fid] = d
        except Exception as e:
            logger.debug(
                "Candidate funders for expert (supports fields) query failed: %s", e
            )

        return list(by_id.values())

    def _find_candidate_enterprises_for_expert(
        self,
        session,
        expert_id: str,
        limit: int = 80,
    ) -> List[Dict[str, Any]]:
        """
        Find candidate enterprises for an expert.

        Nguồn ứng viên:
        - Enterprises hoạt động trong industry mà expert có HAS_APPLICATION_EXPERIENCE_IN.
        - Enterprises đang PARTNERS_WITH các project mà expert tham gia.
        """
        by_id: Dict[str, Dict[str, Any]] = {}

        # Source 1: Enterprises theo kinh nghiệm ứng dụng industry của expert
        try:
            result = session.run(
                f"""
                MATCH (e:Expert {{expert_id: $expert_id}})-[:HAS_APPLICATION_EXPERIENCE_IN]->(i:Industry)
                MATCH (en:Enterprise)-[:OPERATES_IN]->(i)
                RETURN DISTINCT en.enterprise_id AS enterprise_id,
                       en.name AS name,
                       en.location AS location,
                       count(DISTINCT i) AS matched_industries
                ORDER BY matched_industries DESC
                LIMIT {limit}
                """,
                expert_id=expert_id,
                timeout=self.DEFAULT_QUERY_TIMEOUT,
            )
            for record in result:
                d = dict(record)
                d["candidate_sources"] = ["industry_experience"]
                by_id[d["enterprise_id"]] = d
        except Exception as e:
            logger.debug(
                "Candidate enterprises for expert (industry) query failed: %s", e
            )

        # Source 2: Enterprises hợp tác với các project mà expert tham gia
        try:
            result2 = session.run(
                f"""
                MATCH (e:Expert {{expert_id: $expert_id}})-[:PARTICIPATES_IN]->(p:Project)<-[:PARTNERS_WITH]-(en:Enterprise)
                RETURN DISTINCT en.enterprise_id AS enterprise_id,
                       en.name AS name,
                       en.location AS location,
                       count(DISTINCT p) AS partner_projects
                ORDER BY partner_projects DESC
                LIMIT {limit}
                """,
                expert_id=expert_id,
                timeout=self.DEFAULT_QUERY_TIMEOUT,
            )
            for record in result2:
                d = dict(record)
                eid = d["enterprise_id"]
                if eid in by_id:
                    src = set(by_id[eid].get("candidate_sources") or [])
                    src.add("partner_projects")
                    by_id[eid]["candidate_sources"] = sorted(src)
                    by_id[eid]["partner_projects"] = max(
                        by_id[eid].get("partner_projects", 0) or 0,
                        d.get("partner_projects", 0) or 0,
                    )
                else:
                    d["candidate_sources"] = ["partner_projects"]
                    by_id[eid] = d
        except Exception as e:
            logger.debug(
                "Candidate enterprises for expert (partner projects) query failed: %s",
                e,
            )

        return list(by_id.values())

    def _find_candidate_experts_for_expert(
        self,
        session,
        expert_id: str,
        limit: int = 80,
    ) -> List[Dict[str, Any]]:
        """
        Candidate experts for collaboration: same HAS_EXPERTISE_IN field (incl. hierarchy);
        same PARTICIPATES_IN project; same HAS_SKILL MethodTechnique.
        """
        by_id: Dict[str, Dict[str, Any]] = {}
        try:
            result = session.run(
                """
                MATCH (e:Expert {expert_id: $expert_id})
                OPTIONAL MATCH (e)-[:HAS_EXPERIENCE_IN]->(t:ResearchTopic)<-[:HAS_EXPERIENCE_IN]-(e2:Expert)
                OPTIONAL MATCH (e)-[:RESEARCHES]->(d:ResearchDirection)<-[:RESEARCHES]-(e3:Expert)
                WITH e,
                     collect(DISTINCT e2) + collect(DISTINCT e3) AS experts
                UNWIND experts AS ex
                WITH ex
                WHERE ex IS NOT NULL AND ex.expert_id <> $expert_id
                OPTIONAL MATCH (ex)-[:LOCATED_IN]->(l:Location)
                RETURN DISTINCT ex.expert_id AS expert_id,
                       ex.name AS name,
                       l.location_id AS location,
                       ex.h_index AS h_index,
                       ex.citation_count AS citations,
                       ex.publication_count AS publications
                LIMIT $limit
                """,
                expert_id=expert_id,
                limit=limit,
                timeout=self.DEFAULT_QUERY_TIMEOUT,
            )
            for record in result:
                d = dict(record)
                d["candidate_sources"] = ["same_field"]
                by_id[d["expert_id"]] = d
        except Exception as e:
            logger.debug("Candidate experts for expert (field) query failed: %s", e)
        try:
            result2 = session.run(
                """
                MATCH (e:Expert {expert_id: $expert_id})-[:PARTICIPATES_IN]->(p:Project)<-[:PARTICIPATES_IN]-(e2:Expert)
                WHERE e2.expert_id <> $expert_id
                RETURN DISTINCT e2.expert_id AS expert_id,
                       e2.name AS name,
                       e2.location AS location,
                       e2.h_index AS h_index,
                       e2.citation_count AS citations,
                       e2.publication_count AS publications,
                       count(DISTINCT p) AS shared_projects
                ORDER BY shared_projects DESC
                LIMIT $limit
                """,
                expert_id=expert_id,
                limit=limit,
                timeout=self.DEFAULT_QUERY_TIMEOUT,
            )
            for record in result2:
                d = dict(record)
                eid = d["expert_id"]
                if eid in by_id:
                    src = set(by_id[eid].get("candidate_sources") or [])
                    src.add("shared_projects")
                    by_id[eid]["candidate_sources"] = sorted(src)
                else:
                    d["candidate_sources"] = ["shared_projects"]
                    by_id[eid] = d
        except Exception as e:
            logger.debug("Candidate experts for expert (shared projects) query failed: %s", e)
        return list(by_id.values())

    def recommend_experts_for_enterprise_pgpr(
        self,
        enterprise_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        is_new_node = self._is_new_node_in_vocab("Enterprise", enterprise_id)
        if not is_new_node:
            ai_results = self._generic_recommend_with_policy(
                source_id=enterprise_id,
                source_type="Enterprise",
                target_type="Expert",
                limit=limit,
            )
            if ai_results:
                return ai_results
            logger.info("AI không tìm thấy đường cho '%s'. Chuyển sang Cypher/Heuristic...", enterprise_id)
        else:
            logger.info("NODE MỚI '%s' chưa có trong vocab. Chuyển sang Cypher/Heuristic...", enterprise_id)

        return self._recommend_experts_for_enterprise_cypher(enterprise_id=enterprise_id, limit=limit)

    def recommend_projects_for_enterprise_pgpr(
        self,
        enterprise_id: str,
        limit: int = 10,
        status_filter: List[str] = None,
    ) -> List[Dict[str, Any]]:
        is_new_node = self._is_new_node_in_vocab("Enterprise", enterprise_id)
        if not is_new_node:
            ai_results = self._generic_recommend_with_policy(
                source_id=enterprise_id,
                source_type="Enterprise",
                target_type="Project",
                limit=limit,
            )
            if ai_results:
                return ai_results
            logger.info("AI không tìm thấy đường cho '%s'. Chuyển sang Cypher/Heuristic...", enterprise_id)
        else:
            logger.info("NODE MỚI '%s' chưa có trong vocab. Chuyển sang Cypher/Heuristic...", enterprise_id)

        return self._recommend_projects_for_enterprise_cypher(
            enterprise_id=enterprise_id,
            limit=limit,
            status_filter=status_filter,
        )

    def recommend_funders_for_enterprise_pgpr(
        self,
        enterprise_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        is_new_node = self._is_new_node_in_vocab("Enterprise", enterprise_id)
        if not is_new_node:
            ai_results = self._generic_recommend_with_policy(
                source_id=enterprise_id,
                source_type="Enterprise",
                target_type="Funder",
                limit=limit,
            )
            if ai_results:
                return ai_results
            logger.info("AI không tìm thấy đường cho '%s'. Chuyển sang Cypher/Heuristic...", enterprise_id)
        else:
            logger.info("NODE MỚI '%s' chưa có trong vocab. Chuyển sang Cypher/Heuristic...", enterprise_id)

        return self._recommend_funders_for_enterprise_cypher(enterprise_id=enterprise_id, limit=limit)

    def recommend_enterprises_for_enterprise_pgpr(
        self,
        enterprise_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        is_new_node = self._is_new_node_in_vocab("Enterprise", enterprise_id)
        if not is_new_node:
            ai_results = self._generic_recommend_with_policy(
                source_id=enterprise_id,
                source_type="Enterprise",
                target_type="Enterprise",
                limit=limit,
            )
            if ai_results:
                return ai_results
            logger.info("AI không tìm thấy đường cho '%s'. Chuyển sang Cypher/Heuristic...", enterprise_id)
        else:
            logger.info("NODE MỚI '%s' chưa có trong vocab. Chuyển sang Cypher/Heuristic...", enterprise_id)

        return self._recommend_enterprises_for_enterprise_cypher(enterprise_id=enterprise_id, limit=limit)

    def _find_candidate_experts_for_enterprise(
        self,
        session,
        enterprise_id: str,
        limit: int = 80,
    ) -> List[Dict[str, Any]]:
        """Experts: có HAS_APPLICATION_EXPERIENCE_IN industry mà enterprise OPERATES_IN; hoặc PARTICIPATES_IN project PARTNERS_WITH enterprise."""
        by_id: Dict[str, Dict[str, Any]] = {}

        try:
            result = session.run(
                """
                MATCH (en:Enterprise {enterprise_id: $enterprise_id})-[:OPERATES_IN]->(i:Industry)
                MATCH (e:Expert)-[:HAS_APPLICATION_EXPERIENCE_IN]->(i)
                RETURN DISTINCT e.expert_id AS expert_id,
                       e.name AS name,
                       e.location AS location,
                       e.h_index AS h_index,
                       e.citation_count AS citations,
                       e.publication_count AS publications,
                       count(DISTINCT i) AS matched_industries
                ORDER BY matched_industries DESC
                LIMIT $limit
                """,
                enterprise_id=enterprise_id,
                limit=limit,
                timeout=self.DEFAULT_QUERY_TIMEOUT,
            )
            for record in result:
                d = dict(record)
                d["candidate_sources"] = ["industry_match"]
                by_id[d["expert_id"]] = d
        except Exception as e:
            logger.debug("Candidate experts for enterprise (industry) query failed: %s", e)

        try:
            result2 = session.run(
                """
                MATCH (en:Enterprise {enterprise_id: $enterprise_id})-[:PARTNERS_WITH]->(p:Project)<-[:PARTICIPATES_IN]-(e:Expert)
                RETURN DISTINCT e.expert_id AS expert_id,
                       e.name AS name,
                       e.location AS location,
                       e.h_index AS h_index,
                       e.citation_count AS citations,
                       e.publication_count AS publications,
                       count(DISTINCT p) AS partner_projects
                ORDER BY partner_projects DESC
                LIMIT $limit
                """,
                enterprise_id=enterprise_id,
                limit=limit,
                timeout=self.DEFAULT_QUERY_TIMEOUT,
            )
            for record in result2:
                d = dict(record)
                eid = d["expert_id"]
                if eid in by_id:
                    src = set(by_id[eid].get("candidate_sources") or [])
                    src.add("partner_projects")
                    by_id[eid]["candidate_sources"] = sorted(src)
                else:
                    d["candidate_sources"] = ["partner_projects"]
                    by_id[eid] = d
        except Exception as e:
            logger.debug("Candidate experts for enterprise (partner projects) query failed: %s", e)

        return list(by_id.values())

    def _find_candidate_projects_for_enterprise(
        self,
        session,
        enterprise_id: str,
        status_filter: List[str],
        limit: int = 80,
    ) -> List[Dict[str, Any]]:
        """Projects: cùng industry (BELONGS_TO field -> Industry?) hoặc liên quan project đã PARTNERS_WITH enterprise. KG có thể Project-BELONGS_TO-ResearchField; Enterprise-OPERATES_IN-Industry. Nếu không có link Field-Industry, dùng project đã partner làm nguồn."""
        by_id: Dict[str, Dict[str, Any]] = {}

        try:
            result = session.run(
                """
                MATCH (en:Enterprise {enterprise_id: $enterprise_id})-[:PARTNERS_WITH]->(p0:Project)
                OPTIONAL MATCH (p0)-[:FOCUSES_ON_TOPIC]->(t:ResearchTopic)<-[:FOCUSES_ON_TOPIC]-(p:Project)
                OPTIONAL MATCH (p0)-[:FOCUSES_ON]->(d:ResearchDirection)<-[:FOCUSES_ON]-(p2:Project)
                WITH en, collect(DISTINCT p) + collect(DISTINCT p2) AS ps
                UNWIND ps AS px
                WITH en, px
                WHERE px IS NOT NULL
                  AND px.status IN $status_filter
                  AND NOT (en)-[:PARTNERS_WITH]->(px)
                OPTIONAL MATCH (px)-[:LOCATED_IN]->(l:Location)
                RETURN DISTINCT px.project_id AS project_id,
                       px.title AS title,
                       px.status AS status,
                       l.location_id AS location,
                       px.trl AS trl,
                       px.budget AS budget
                LIMIT $limit
                """,
                enterprise_id=enterprise_id,
                status_filter=status_filter,
                limit=limit,
                timeout=self.DEFAULT_QUERY_TIMEOUT,
            )
            for record in result:
                d = dict(record)
                d["candidate_sources"] = ["related_partner_projects"]
                by_id[d["project_id"]] = d
        except Exception as e:
            logger.debug("Candidate projects for enterprise query failed: %s", e)

        return list(by_id.values())

    def _find_candidate_funders_for_enterprise(
        self,
        session,
        enterprise_id: str,
        limit: int = 80,
    ) -> List[Dict[str, Any]]:
        """Funders: FUNDS projects that enterprise PARTNERS_WITH; or SUPPORTS field of those projects."""
        by_id: Dict[str, Dict[str, Any]] = {}
        try:
            result = session.run(
                """
                MATCH (en:Enterprise {enterprise_id: $enterprise_id})-[:PARTNERS_WITH]->(p:Project)<-[:FUNDS]-(f:Funder)
                RETURN DISTINCT f.funder_id AS funder_id,
                       f.name AS name,
                       f.type AS type,
                       f.location AS location,
                       f.budget_capacity AS budget_capacity,
                       count(DISTINCT p) AS funded_partner_projects
                ORDER BY funded_partner_projects DESC
                LIMIT $limit
                """,
                enterprise_id=enterprise_id,
                limit=limit,
                timeout=self.DEFAULT_QUERY_TIMEOUT,
            )
            for record in result:
                d = dict(record)
                d["candidate_sources"] = ["partner_project_funders"]
                by_id[d["funder_id"]] = d
        except Exception as e:
            logger.debug("Candidate funders for enterprise query failed: %s", e)
        try:
            result2 = session.run(
                """
                MATCH (en:Enterprise {enterprise_id: $enterprise_id})-[:PARTNERS_WITH]->(p:Project)
                OPTIONAL MATCH (p)-[:FOCUSES_ON_TOPIC]->(t:ResearchTopic)<-[:SUPPORTS_TOPIC]-(f1:Funder)
                OPTIONAL MATCH (p)-[:FOCUSES_ON]->(d:ResearchDirection)<-[:SUPPORTS]-(f2:Funder)
                WITH collect(DISTINCT f1) + collect(DISTINCT f2) AS funders
                UNWIND funders AS f
                WITH f
                WHERE f IS NOT NULL
                RETURN DISTINCT f.funder_id AS funder_id,
                       f.name AS name,
                       f.type AS type,
                       f.location AS location,
                       f.budget_capacity AS budget_capacity
                LIMIT $limit
                """,
                enterprise_id=enterprise_id,
                limit=limit,
                timeout=self.DEFAULT_QUERY_TIMEOUT,
            )
            for record in result2:
                d = dict(record)
                fid = d["funder_id"]
                if fid in by_id:
                    src = set(by_id[fid].get("candidate_sources") or [])
                    src.add("supports_partner_field")
                    by_id[fid]["candidate_sources"] = sorted(src)
                else:
                    d["candidate_sources"] = ["supports_partner_field"]
                    by_id[fid] = d
        except Exception as e:
            logger.debug("Candidate funders for enterprise (supports field) failed: %s", e)
        return list(by_id.values())

    def _find_candidate_enterprises_for_enterprise(
        self,
        session,
        enterprise_id: str,
        limit: int = 80,
    ) -> List[Dict[str, Any]]:
        """Other enterprises: same OPERATES_IN industry; or PARTNERS_WITH same project; or partner projects in same field."""
        by_id: Dict[str, Dict[str, Any]] = {}
        try:
            result = session.run(
                """
                MATCH (en:Enterprise {enterprise_id: $enterprise_id})-[:OPERATES_IN]->(i:Industry)<-[:OPERATES_IN]-(en2:Enterprise)
                WHERE en2.enterprise_id <> $enterprise_id
                RETURN DISTINCT en2.enterprise_id AS enterprise_id,
                       en2.name AS name,
                       en2.location AS location,
                       count(DISTINCT i) AS matched_industries
                ORDER BY matched_industries DESC
                LIMIT $limit
                """,
                enterprise_id=enterprise_id,
                limit=limit,
                timeout=self.DEFAULT_QUERY_TIMEOUT,
            )
            for record in result:
                d = dict(record)
                d["candidate_sources"] = ["same_industry"]
                by_id[d["enterprise_id"]] = d
        except Exception as e:
            logger.debug("Candidate enterprises for enterprise (industry) failed: %s", e)
        try:
            result2 = session.run(
                """
                MATCH (en:Enterprise {enterprise_id: $enterprise_id})-[:PARTNERS_WITH]->(p:Project)<-[:PARTNERS_WITH]-(en2:Enterprise)
                WHERE en2.enterprise_id <> $enterprise_id
                RETURN DISTINCT en2.enterprise_id AS enterprise_id,
                       en2.name AS name,
                       en2.location AS location,
                       count(DISTINCT p) AS shared_projects
                ORDER BY shared_projects DESC
                LIMIT $limit
                """,
                enterprise_id=enterprise_id,
                limit=limit,
                timeout=self.DEFAULT_QUERY_TIMEOUT,
            )
            for record in result2:
                d = dict(record)
                eid = d["enterprise_id"]
                if eid in by_id:
                    src = set(by_id[eid].get("candidate_sources") or [])
                    src.add("shared_projects")
                    by_id[eid]["candidate_sources"] = sorted(src)
                    by_id[eid]["shared_projects"] = max(
                        by_id[eid].get("shared_projects", 0) or 0,
                        d.get("shared_projects", 0) or 0,
                    )
                else:
                    d["candidate_sources"] = ["shared_projects"]
                    by_id[eid] = d
        except Exception as e:
            logger.debug("Candidate enterprises for enterprise (shared projects) failed: %s", e)
        return list(by_id.values())

    def recommend_experts_for_funder_pgpr(
        self,
        funder_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        is_new_node = self._is_new_node_in_vocab("Funder", funder_id)
        if not is_new_node:
            ai_results = self._generic_recommend_with_policy(
                source_id=funder_id,
                source_type="Funder",
                target_type="Expert",
                limit=limit,
            )
            if ai_results:
                return ai_results
            logger.info("AI không tìm thấy đường cho '%s'. Chuyển sang Cypher/Heuristic...", funder_id)
        else:
            logger.info("NODE MỚI '%s' chưa có trong vocab. Chuyển sang Cypher/Heuristic...", funder_id)

        return self._recommend_experts_for_funder_cypher(funder_id=funder_id, limit=limit)

    def recommend_projects_for_funder_pgpr(
        self,
        funder_id: str,
        limit: int = 10,
        status_filter: List[str] = None,
    ) -> List[Dict[str, Any]]:
        is_new_node = self._is_new_node_in_vocab("Funder", funder_id)
        if not is_new_node:
            ai_results = self._generic_recommend_with_policy(
                source_id=funder_id,
                source_type="Funder",
                target_type="Project",
                limit=limit,
            )
            if ai_results:
                return ai_results
            logger.info("AI không tìm thấy đường cho '%s'. Chuyển sang Cypher/Heuristic...", funder_id)
        else:
            logger.info("NODE MỚI '%s' chưa có trong vocab. Chuyển sang Cypher/Heuristic...", funder_id)

        return self._recommend_projects_for_funder_cypher(
            funder_id=funder_id,
            limit=limit,
            status_filter=status_filter,
        )

    def recommend_enterprises_for_funder_pgpr(
        self,
        funder_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        is_new_node = self._is_new_node_in_vocab("Funder", funder_id)
        if not is_new_node:
            ai_results = self._generic_recommend_with_policy(
                source_id=funder_id,
                source_type="Funder",
                target_type="Enterprise",
                limit=limit,
            )
            if ai_results:
                return ai_results
            logger.info("AI không tìm thấy đường cho '%s'. Chuyển sang Cypher/Heuristic...", funder_id)
        else:
            logger.info("NODE MỚI '%s' chưa có trong vocab. Chuyển sang Cypher/Heuristic...", funder_id)

        return self._recommend_enterprises_for_funder_cypher(funder_id=funder_id, limit=limit)

    def _find_candidate_experts_for_funder(
        self,
        session,
        funder_id: str,
        limit: int = 80,
    ) -> List[Dict[str, Any]]:
        """Experts: PARTICIPATES_IN project FUNDS by funder; hoặc HAS_EXPERTISE_IN field SUPPORTED by funder."""
        by_id: Dict[str, Dict[str, Any]] = {}

        try:
            result = session.run(
                """
                MATCH (f:Funder {funder_id: $funder_id})-[:FUNDS]->(p:Project)<-[:PARTICIPATES_IN]-(e:Expert)
                OPTIONAL MATCH (e)-[:LOCATED_IN]->(l:Location)
                RETURN DISTINCT e.expert_id AS expert_id,
                       e.name AS name,
                       l.location_id AS location,
                       e.h_index AS h_index,
                       e.citation_count AS citations,
                       e.publication_count AS publications,
                       count(DISTINCT p) AS funded_projects
                ORDER BY funded_projects DESC
                LIMIT $limit
                """,
                funder_id=funder_id,
                limit=limit,
                timeout=self.DEFAULT_QUERY_TIMEOUT,
            )
            for record in result:
                d = dict(record)
                d["candidate_sources"] = ["funded_projects"]
                by_id[d["expert_id"]] = d
        except Exception as e:
            logger.debug("Candidate experts for funder (funded projects) query failed: %s", e)

        try:
            result2 = session.run(
                """
                MATCH (f:Funder {funder_id: $funder_id})
                OPTIONAL MATCH (f)-[:SUPPORTS_TOPIC]->(t:ResearchTopic)<-[:HAS_EXPERIENCE_IN]-(e1:Expert)
                OPTIONAL MATCH (f)-[:SUPPORTS]->(d:ResearchDirection)<-[:RESEARCHES]-(e2:Expert)
                WITH collect(DISTINCT e1) + collect(DISTINCT e2) AS experts
                UNWIND experts AS e
                WITH e
                WHERE e IS NOT NULL
                OPTIONAL MATCH (e)-[:LOCATED_IN]->(l:Location)
                RETURN DISTINCT e.expert_id AS expert_id,
                       e.name AS name,
                       l.location_id AS location,
                       e.h_index AS h_index,
                       e.citation_count AS citations,
                       e.publication_count AS publications
                LIMIT $limit
                """,
                funder_id=funder_id,
                limit=limit,
                timeout=self.DEFAULT_QUERY_TIMEOUT,
            )
            for record in result2:
                d = dict(record)
                eid = d["expert_id"]
                if eid in by_id:
                    src = set(by_id[eid].get("candidate_sources") or [])
                    src.add("supports_field")
                    by_id[eid]["candidate_sources"] = sorted(src)
                else:
                    d["candidate_sources"] = ["supports_field"]
                    by_id[eid] = d
        except Exception as e:
            logger.debug("Candidate experts for funder (supports field) query failed: %s", e)

        return list(by_id.values())

    def _find_candidate_projects_for_funder(
        self,
        session,
        funder_id: str,
        status_filter: List[str],
        limit: int = 80,
    ) -> List[Dict[str, Any]]:
        """Projects: trong field funder SUPPORT; hoặc cùng field với project funder đã FUNDS (chưa tài trợ dự án này)."""
        by_id: Dict[str, Dict[str, Any]] = {}

        try:
            result = session.run(
                """
                MATCH (f:Funder {funder_id: $funder_id})
                OPTIONAL MATCH (f)-[:SUPPORTS_TOPIC]->(t:ResearchTopic)<-[:FOCUSES_ON_TOPIC]-(p:Project)
                OPTIONAL MATCH (f)-[:SUPPORTS]->(d:ResearchDirection)<-[:FOCUSES_ON]-(p2:Project)
                WITH f, collect(DISTINCT p) + collect(DISTINCT p2) AS ps
                UNWIND ps AS px
                WITH f, px
                WHERE px IS NOT NULL
                  AND px.status IN $status_filter
                  AND NOT (f)-[:FUNDS]->(px)
                OPTIONAL MATCH (px)-[:LOCATED_IN]->(l:Location)
                RETURN DISTINCT px.project_id AS project_id,
                       px.title AS title,
                       px.status AS status,
                       l.location_id AS location,
                       px.trl AS trl,
                       px.budget AS budget
                LIMIT $limit
                """,
                funder_id=funder_id,
                status_filter=status_filter,
                limit=limit,
                timeout=self.DEFAULT_QUERY_TIMEOUT,
            )
            for record in result:
                d = dict(record)
                d["candidate_sources"] = ["supports_field"]
                by_id[d["project_id"]] = d
        except Exception as e:
            logger.debug("Candidate projects for funder (supports) query failed: %s", e)

        try:
            result2 = session.run(
                """
                MATCH (f:Funder {funder_id: $funder_id})-[:FUNDS]->(p0:Project)
                OPTIONAL MATCH (p0)-[:FOCUSES_ON_TOPIC]->(t:ResearchTopic)<-[:FOCUSES_ON_TOPIC]-(p:Project)
                OPTIONAL MATCH (p0)-[:FOCUSES_ON]->(d:ResearchDirection)<-[:FOCUSES_ON]-(p2:Project)
                WITH f, p0, collect(DISTINCT p) + collect(DISTINCT p2) AS ps
                UNWIND ps AS px
                WITH f, p0, px
                WHERE px IS NOT NULL
                  AND px.status IN $status_filter
                  AND px.project_id <> p0.project_id
                  AND NOT (f)-[:FUNDS]->(px)
                OPTIONAL MATCH (px)-[:LOCATED_IN]->(l:Location)
                RETURN DISTINCT px.project_id AS project_id,
                       px.title AS title,
                       px.status AS status,
                       l.location_id AS location,
                       px.trl AS trl,
                       px.budget AS budget
                LIMIT $limit
                """,
                funder_id=funder_id,
                status_filter=status_filter,
                limit=limit,
                timeout=self.DEFAULT_QUERY_TIMEOUT,
            )
            for record in result2:
                d = dict(record)
                pid = d["project_id"]
                if pid in by_id:
                    src = set(by_id[pid].get("candidate_sources") or [])
                    src.add("funded_related")
                    by_id[pid]["candidate_sources"] = sorted(src)
                else:
                    d["candidate_sources"] = ["funded_related"]
                    by_id[pid] = d
        except Exception as e:
            logger.debug("Candidate projects for funder (funded related) query failed: %s", e)

        return list(by_id.values())

    def _find_candidate_enterprises_for_funder(
        self,
        session,
        funder_id: str,
        limit: int = 80,
    ) -> List[Dict[str, Any]]:
        """Enterprises: PARTNERS_WITH projects that funder FUNDS; or projects in field funder SUPPORTS."""
        by_id: Dict[str, Dict[str, Any]] = {}
        try:
            result = session.run(
                """
                MATCH (f:Funder {funder_id: $funder_id})-[:FUNDS]->(p:Project)<-[:PARTNERS_WITH]-(en:Enterprise)
                RETURN DISTINCT en.enterprise_id AS enterprise_id,
                       en.name AS name,
                       en.location AS location,
                       count(DISTINCT p) AS partner_projects
                ORDER BY partner_projects DESC
                LIMIT $limit
                """,
                funder_id=funder_id,
                limit=limit,
                timeout=self.DEFAULT_QUERY_TIMEOUT,
            )
            for record in result:
                d = dict(record)
                d["candidate_sources"] = ["funded_project_partners"]
                by_id[d["enterprise_id"]] = d
        except Exception as e:
            logger.debug("Candidate enterprises for funder query failed: %s", e)
        try:
            result2 = session.run(
                """
                MATCH (f:Funder {funder_id: $funder_id})
                OPTIONAL MATCH (f)-[:SUPPORTS_TOPIC]->(t:ResearchTopic)<-[:FOCUSES_ON_TOPIC]-(p:Project)<-[:PARTNERS_WITH]-(en:Enterprise)
                OPTIONAL MATCH (f)-[:SUPPORTS]->(d:ResearchDirection)<-[:FOCUSES_ON]-(p2:Project)<-[:PARTNERS_WITH]-(en2:Enterprise)
                WITH collect(DISTINCT {en: en, px: p}) + collect(DISTINCT {en: en2, px: p2}) AS rows
                UNWIND rows AS r
                WITH r.en AS en, r.px AS px
                WHERE en IS NOT NULL AND px IS NOT NULL
                RETURN DISTINCT en.enterprise_id AS enterprise_id,
                       en.name AS name,
                       en.location AS location,
                       count(DISTINCT px) AS partner_projects
                ORDER BY partner_projects DESC
                LIMIT $limit
                """,
                funder_id=funder_id,
                limit=limit,
                timeout=self.DEFAULT_QUERY_TIMEOUT,
            )
            for record in result2:
                d = dict(record)
                eid = d["enterprise_id"]
                if eid in by_id:
                    src = set(by_id[eid].get("candidate_sources") or [])
                    src.add("supports_field_partners")
                    by_id[eid]["candidate_sources"] = sorted(src)
                    by_id[eid]["partner_projects"] = max(
                        by_id[eid].get("partner_projects", 0) or 0,
                        d.get("partner_projects", 0) or 0,
                    )
                else:
                    d["candidate_sources"] = ["supports_field_partners"]
                    by_id[eid] = d
        except Exception as e:
            logger.debug("Candidate enterprises for funder (supports field) failed: %s", e)
        return list(by_id.values())
    
    # ==========================================
    # EXPLAINABILITY HELPERS
    # ==========================================
    
    def get_recommendation_explanation(
        self,
        source_id: str,
        source_type: str,
        target_id: str,
        target_type: str
    ) -> Dict[str, Any]:
        """Get detailed explanation for why a recommendation was made."""
        paths = self.find_reasoning_paths(
            source_id=source_id,
            source_type=source_type,
            target_id=target_id,
            target_type=target_type
        )
        
        analysis = self.analyze_path_patterns(
            source_id=source_id,
            source_type=source_type,
            target_id=target_id,
            target_type=target_type
        )
        
        if paths:
            top_path = paths[0]
            explanation_text = (
                f"Recommended because: {top_path['explanation']} "
                f"(confidence: {top_path['score']:.2%})"
            )
        else:
            explanation_text = "No direct reasoning path found."
        
        return {
            "summary": explanation_text,
            "top_paths": [
                {
                    "rank": i + 1,
                    "explanation": p["explanation"],
                    "score": p["score"],
                    "length": p["length"],
                    "confidence": f"{p['score']:.2%}"
                }
                for i, p in enumerate(paths[:5])
            ],
            "analysis": analysis
        }
    
    def analyze_path_patterns(
        self,
        source_id: str,
        source_type: str,
        target_id: str,
        target_type: str
    ) -> Dict[str, Any]:
        """Analyze common path patterns between source and target."""
        paths = self.find_reasoning_paths(
            source_id=source_id,
            source_type=source_type,
            target_id=target_id,
            target_type=target_type
        )
        
        if not paths:
            return {
                "total_paths": 0,
                "avg_length": 0,
                "common_patterns": [],
                "relation_frequency": {}
            }
        
        total_paths = len(paths)
        avg_length = np.mean([p["length"] for p in paths])
        
        # Find common patterns
        pattern_counts = defaultdict(int)
        for path in paths:
            pattern = tuple(path["relations"])
            pattern_counts[pattern] += 1
        
        common_patterns = sorted(
            [
                {
                    # Use ASCII arrow to avoid Windows console encoding issues (cp1252).
                    "pattern": " -> ".join(pattern),
                    "count": count,
                    "frequency": count / total_paths
                }
                for pattern, count in pattern_counts.items()
            ],
            key=lambda x: x["count"],
            reverse=True
        )[:5]
        
        # Relation frequency
        relation_freq = defaultdict(int)
        for path in paths:
            for rel in path["relations"]:
                relation_freq[rel] += 1
        
        return {
            "total_paths": total_paths,
            "avg_length": round(avg_length, 2),
            "avg_score": round(np.mean([p["score"] for p in paths]), 3),
            "max_score": round(max(p["score"] for p in paths), 3),
            "common_patterns": common_patterns,
            "relation_frequency": dict(relation_freq)
        }

    # ==========================================
    # SUPER AI WRAPPER (TEST PURE RL POLICY)
    # ==========================================

    def _get_generic_entity_info(self, session, entity_id: str, entity_type: str) -> Dict[str, Any]:
        """Tự động query lấy thông tin của bất kỳ Node nào (kèm theo Location nếu có)."""
        id_prop = f"{entity_type.lower()}_id"
        query = f"""
        MATCH (n:{entity_type} {{{id_prop}: $eid}})
        OPTIONAL MATCH (n)-[:LOCATED_IN]->(l:Location)
        RETURN properties(n) AS props, l.location_id AS location
        """
        res = list(session.run(query, eid=entity_id))
        if not res:
            return {}
        info = res[0]["props"] or {}
        info["location"] = res[0].get("location")
        return info

    def _get_exclude_keys(self, source_id: str, source_type: str, target_type: str) -> List[str]:
        """Tự động cắm biển cấm dựa trên cặp quan hệ Ground Truth"""
        queries = {
            "Expert_Project": "MATCH (s:Expert {expert_id: $sid})-[:PARTICIPATES_IN]->(t:Project) RETURN t.project_id AS tid",
            "Project_Expert": "MATCH (s:Project {project_id: $sid})<-[:PARTICIPATES_IN]-(t:Expert) RETURN t.expert_id AS tid",
            "Enterprise_Project": "MATCH (s:Enterprise {enterprise_id: $sid})-[:PARTNERS_WITH]->(t:Project) RETURN t.project_id AS tid",
            "Project_Enterprise": "MATCH (s:Project {project_id: $sid})<-[:PARTNERS_WITH]-(t:Enterprise) RETURN t.enterprise_id AS tid",
            "Funder_Project": "MATCH (s:Funder {funder_id: $sid})-[:FUNDS]->(t:Project) RETURN t.project_id AS tid",
            "Project_Funder": "MATCH (s:Project {project_id: $sid})<-[:FUNDS]-(t:Funder) RETURN t.funder_id AS tid",
            "Expert_Enterprise": "MATCH (s:Expert {expert_id: $sid})-[:HAS_APPLICATION_EXPERIENCE_IN]->(:Industry)<-[:OPERATES_IN]-(t:Enterprise) RETURN t.enterprise_id AS tid",
            "Enterprise_Expert": "MATCH (s:Enterprise {enterprise_id: $sid})-[:OPERATES_IN]->(:Industry)<-[:HAS_APPLICATION_EXPERIENCE_IN]-(t:Expert) RETURN t.expert_id AS tid",
            "Expert_Expert": "MATCH (s:Expert {expert_id: $sid})-[:PARTICIPATES_IN]->(:Project)<-[:PARTICIPATES_IN]-(t:Expert) RETURN t.expert_id AS tid",
        }
        task_name = f"{source_type}_{target_type}"
        if task_name not in queries:
            return []
            
        with self.driver.session() as session:
            res = session.run(queries[task_name], sid=source_id)
            return [f"{target_type}::{record['tid']}" for record in res]

    def _generic_recommend_with_policy(
        self,
        source_id: str,
        source_type: str,
        target_type: str,
        limit: int = 10,
        min_score: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """Hàm duy nhất để chạy AI cho mọi luồng (Không có Cypher)"""
        task_name = f"{source_type}_{target_type}"
        if task_name not in self.policies:
            logger.warning(f"Không tìm thấy bộ não AI cho {task_name}. Vui lòng train trước!")
            return []

        # 1. Tìm người nhà để cắm biển cấm
        exclude_keys = self._get_exclude_keys(source_id, source_type, target_type)

        # 2. Thả AI đi dạo 1000 vòng
        policy_paths = self.policy_guided_paths(
            source_id=source_id,
            source_type=source_type,
            target_type=target_type,
            n_rollouts=1000,
            deterministic=False,
            exclude_keys=exclude_keys,
        )

        if not policy_paths:
            logger.info(f"AI RL không tìm thấy kết quả nào cho {source_id} -> {target_type}.")
            return []

        # 3. Lắp ráp dữ liệu trả về
        recommendations = []
        with self.driver.session() as session:
            for item in policy_paths[:limit * 2]:
                target_key = item["target_entity_key"]
                if "::" not in target_key:
                    continue
                _, t_id = target_key.split("::", 1)

                # Lấy info tự động
                info = self._get_generic_entity_info(session, t_id, target_type)
                if not info:
                    continue

                # Map thành dictionary chuẩn
                rec = {
                    f"{target_type.lower()}_id": t_id,
                    "name": info.get("name", info.get("title", "N/A")),
                    "score": round(item["score"], 3),
                    
                    # MỚI: Lặp qua danh sách top_paths để lấy ra 3 đường
                    "reasoning_paths": [
                        {
                            "path": " -> ".join(p["path_relations"]),
                            "score": p["path_score"],
                            "length": len(p["path_relations"]),
                        }
                        for p in item["top_paths"]
                    ],
                    
                    "path_diversity": item["n_paths"],
                    "metrics": {
                        "h_index": info.get("h_index"),
                        "budget": info.get("budget"),
                        "status": info.get("status"),
                    },
                }
                if rec["score"] >= min_score:
                    recommendations.append(rec)

        # Sắp xếp từ cao xuống thấp
        recommendations.sort(key=lambda x: x["score"], reverse=True)

        # ==========================================
        # CHUẨN HÓA ĐỘ TƯƠNG THÍCH TUYỆT ĐỐI (ABSOLUTE COMPATIBILITY)
        # ==========================================
        if recommendations:
            # Định nghĩa điểm số của một "Perfect Match" (Gợi ý hoàn hảo)
            # Theo đồ thị của bạn, điểm ~0.1 là một đường đi 2 bước cực kỳ rõ ràng.
            IDEAL_MAX_SCORE = 0.1

            for rec in recommendations:
                raw_score = rec["score"] if rec["score"] > 0 else (
                    rec["reasoning_paths"][0]["score"] if rec.get("reasoning_paths") else 0
                )

                # Tính % dựa trên thang điểm tuyệt đối
                compatibility = (raw_score / IDEAL_MAX_SCORE) * 100

                # Cắt trần ở mức 99% (Để chừa lại 1% cho sự hoàn hảo tuyệt đối ngoài đời thực)
                # Và tạo mốc sàn (Bonus thêm 10-15% cho những người đã lọt được vào Top Recommend)
                final_percentage = min(99.0, compatibility + 15.0) if raw_score > 0 else 0.0

                rec["score"] = round(final_percentage, 1)  # VD: 85.5%, 42.0%

        return recommendations[:limit]


# ==========================================
# UTILITY FUNCTIONS
# ==========================================

def print_pgpr_recommendations(
    recommendations: List[Dict],
    title: str,
    show_paths: bool = True,
    show_detailed: bool = False
):
    """Pretty print PGPR recommendations with reasoning paths and detailed explanations."""
    # Avoid Windows console encoding issues (cp1252/cp936...). Force UTF-8 when possible.
    try:
        import sys
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    print("\n" + "="*80)
    print(f"{title}")
    print("="*80)
    
    if not recommendations:
        print("No recommendations found.")
        return
    
    for idx, rec in enumerate(recommendations, 1):
        print(f"\n{idx}. {rec.get('name', rec.get('title', 'N/A'))}")
        print(f"   Score: {rec['score']}")
        print(f"   Path Diversity: {rec.get('path_diversity', 'N/A')}")
        
        if show_paths and 'reasoning_paths' in rec:
            print(f"\n   Top Reasoning Paths:")
            for i, path in enumerate(rec['reasoning_paths'], 1):
                print(f"\n     Đường dẫn {i}: {path.get('path', 'N/A')}")
                print(f"        (Score: {path.get('score', 'N/A')}, Length: {path.get('length', 'N/A')})")
                
                # Print detailed explanation if available
                if show_detailed and 'detailed' in path and path['detailed']:
                    det = path['detailed']
                    print(f"\n        Đường dẫn \"{det.get('name', 'N/A')}\" ({det.get('category', 'N/A')})")
                    print(f"        Path: {det.get('path_string', 'N/A')}")
                    print(f"\n        {det.get('description', 'N/A')}")
                    
                    if det.get('steps'):
                        print(f"\n        Chi tiết từng bước:")
                        for step in det['steps']:
                            print(f"          Bước {step['step']}: {step['explanation']}")
                    
                    if det.get('conclusion'):
                        print(f"\n        Kết luận:")
                        print(f"        {det['conclusion']}")
                    
                    if det.get('practical_value'):
                        print(f"\n        Giá trị thực tiễn:")
                        print(f"        {det['practical_value']}")
        
        if 'metrics' in rec:
            print(f"\n   Metrics:")
            for key, value in rec['metrics'].items():
                if value is not None:
                    print(f"     - {key}: {value}")
    
    print("\n" + "="*80)


# ==========================================
# EXAMPLE USAGE
# ==========================================

if __name__ == "__main__":
    print("\n" + "="*80)
    print("PGPR RECOMMENDER - IMPROVED VERSION")
    print("="*80)
    
    pgpr = PGPRRecommender(
        max_path_length=5,
        gamma=0.99,
        top_k_paths=10,
        path_penalty=0.1,
        enable_cache=True,
    )
    
    try:
        # Test expert recommendations
        print("\n### Expert Recommendations (Improved) ###")
        experts = pgpr.recommend_experts_for_project_pgpr(
            project_id="prj_001",
            limit=5
        )
        print_pgpr_recommendations(experts, "Recommended Experts for prj_001")
        
        # Show cache statistics
        stats = pgpr.get_cache_stats()
        print(f"\nCache stats: {stats['hits']} hits, {stats['misses']} misses, {stats['size']} entries")
        
    finally:
        pgpr.close()