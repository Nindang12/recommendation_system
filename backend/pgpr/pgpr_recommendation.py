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

from typing import List, Dict, Any, Tuple, Optional, Set
import os
import logging
import numpy as np
from collections import defaultdict, deque
import random
from functools import lru_cache
import time

from core.env import load_project_env

load_project_env()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
        data_dir: Optional[str] = None,
        enable_cache: bool = True,
        graph_repo: Optional[Any] = None,
        driver: Optional[Any] = None,
    ):
        try:
            from repositories.pgpr_graph_repo import PGPRGraphRepository
        except ImportError:
            from ..repositories.pgpr_graph_repo import PGPRGraphRepository

        self.graph_repo = graph_repo or PGPRGraphRepository(driver=driver)
        self.driver = self.graph_repo.driver
        self._owns_driver = getattr(self.graph_repo, "_owns_driver", False)
        self.max_path_length = max_path_length
        self.gamma = gamma
        self.top_k_paths = top_k_paths
        self.path_penalty = path_penalty
        self.data_dir = data_dir or os.path.join(os.path.dirname(__file__), "pgpr_data")
        self.policy_path = policy_path or os.path.join(self.data_dir, "policy.pt")
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
            try:
                from .pgpr_kg import KG
                from .pgpr_env import KGEnv
                from .pgpr_policy import load_policy as load_policy_net
            except ImportError:
                from pgpr_kg import KG
                from pgpr_env import KGEnv
                from pgpr_policy import load_policy as load_policy_net
        except ImportError as e:
            logger.error(f"PyTorch or pgpr modules not available: {e}; policy-only mode requires RL policy.")
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
        """Close connections and cleanup.

        KGEnv.close() does not close an injected graph_repo driver (see KGEnv._owns_driver).
        graph_repo.close() runs only when this recommender owns the repository/driver.
        """
        if getattr(self, "_env", None):
            try:
                self._env.close()
            except Exception:
                pass
        if getattr(self, "_owns_driver", False) and getattr(self, "graph_repo", None):
            self.graph_repo.close()
        
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

        return self.find_reasoning_paths_cypher(
            source_id=source_id,
            source_type=source_type,
            target_id=target_id,
            target_type=target_type,
            max_length=max_length,
            timeout=timeout,
        )

    def find_reasoning_paths_cypher(
        self,
        source_id: str,
        source_type: str,
        target_id: str,
        target_type: str,
        max_length: Optional[int] = None,
        timeout: float = DEFAULT_QUERY_TIMEOUT,
        limit: Optional[int] = None,
        mode: str = "public",
        current_user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Cypher-based reasoning paths via PGPRGraphRepository (for Graph API)."""
        effective_max_length = max_length if max_length is not None else self.max_path_length
        top_k = limit if limit is not None else self.top_k_paths

        cache_key = (
            source_id,
            source_type,
            target_id,
            target_type,
            effective_max_length,
            mode,
            current_user_id,
            "cypher",
        )
        if self.enable_cache and cache_key in self._path_cache:
            self._cache_hits += 1
            return self._path_cache[cache_key][:top_k]

        self._cache_misses += 1

        try:
            records = self.graph_repo.find_reasoning_paths(
                source_id=source_id,
                source_type=source_type,
                target_id=target_id,
                target_type=target_type,
                max_path_length=effective_max_length,
                limit=top_k * 2,
                timeout=timeout,
                mode=mode,
                current_user_id=current_user_id,
            )
        except Exception as e:
            logger.warning(f"Error finding paths {source_id} -> {target_id}: {e}")
            return []

        unique_paths = self._score_and_dedupe_path_records(records, top_k=top_k)

        if self.enable_cache:
            self._path_cache[cache_key] = unique_paths

        return unique_paths

    def _score_and_dedupe_path_records(
        self,
        records: List[Dict[str, Any]],
        top_k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        top_k = top_k if top_k is not None else self.top_k_paths
        paths: List[Dict[str, Any]] = []
        for record in records:
            entity_names = record.get("entity_names") or []
            node_types = record.get("node_types") or []
            path_info = self._score_path(
                record["relation_types"],
                node_types,
                record["path_length"],
                entity_names=entity_names,
            )
            paths.append({
                "relations": record["relation_types"],
                "nodes": node_types,
                "entity_names": entity_names,
                "entities": [
                    {
                        "name": str(name),
                        "type": node_types[idx] if idx < len(node_types) else "Node",
                    }
                    for idx, name in enumerate(entity_names)
                ],
                "length": record["path_length"],
                "score": path_info["score"],
                "explanation": path_info["explanation"],
            })

        paths.sort(key=lambda x: x["score"], reverse=True)
        unique_paths: List[Dict[str, Any]] = []
        seen_patterns: Set[tuple] = set()
        for p in paths:
            pattern = tuple(p["relations"])
            if pattern in seen_patterns:
                continue
            seen_patterns.add(pattern)
            unique_paths.append(p)
            if len(unique_paths) >= top_k:
                break
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
        if denom == 1:
            return 0.65
        rank_ratio = (idx - 1) / max(1, denom - 1)
        return round(max(0.2, 0.8 - rank_ratio * 0.5), 6)

    def _build_path_payload(self, path: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize an internal path into the API-facing shape.
        Keeps relation names for scoring/debugging and adds entity names for UI/XAI.
        """
        relations = path.get("relations") or path.get("path_relations") or []
        node_types = path.get("nodes") or path.get("node_types") or []
        entity_names = path.get("entity_names") or []
        entities = path.get("entities") or []

        if not entity_names and entities:
            entity_names = [
                str(entity.get("name") or entity.get("id") or entity)
                if isinstance(entity, dict)
                else str(entity)
                for entity in entities
            ]

        path_source = path.get("source") or "pgpr_policy"
        return {
            "path": path.get("explanation") or " -> ".join(relations),
            "relations": list(relations),
            "node_types": list(node_types),
            "entity_names": list(entity_names),
            "entities": list(entities),
            "score": round(float(path.get("score", path.get("path_score", 0.0))), 3),
            "length": int(path.get("length", len(relations))),
            "source": path_source,
        }

    def _resolve_policy_path_entities(self, entity_keys: List[str]) -> List[Dict[str, Any]]:
        """Resolve policy path entity keys through the graph repository adapter."""
        try:
            return self.graph_repo.resolve_entity_path_nodes(entity_keys)
        except Exception as exc:
            logger.debug("Could not resolve policy path entity names: %s", exc)
            out = []
            for key in entity_keys or []:
                if "::" in str(key):
                    label, entity_id = str(key).split("::", 1)
                    out.append({"id": entity_id, "type": label, "name": entity_id})
                else:
                    out.append({"id": str(key), "type": "Node", "name": str(key)})
            return out

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
        logger.debug(f"\n{'='*60}\n🔍 ĐANG CHẠY TÌM KIẾM ĐỒ THỊ (CYPHER FALLBACK)\n   Mục tiêu: {target_type} | Số lượng ứng viên: {len(candidates)}\n{'='*60}")
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
            reasoning_paths = self._fallback_reasoning_paths(c, target_type, id_field, t_id, name, score)
            rec = {
                f"{target_type.lower()}_id": t_id,
                "name": name,
                "score": round(score, 3),
                "reasoning_paths": reasoning_paths,
                "path_diversity": len(reasoning_paths),
                "scoring_method": "cypher_fallback",
                "metrics": {},
            }
            if not reasoning_paths:
                rec["fallback_reason"] = (
                    "Ket qua tu tim kiem heuristic/Cypher tren do thi. "
                    "Khong co duong ly do day du tren Knowledge Graph."
                )
                rec["score"] = min(rec["score"], 0.55)

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

    def _fallback_reasoning_paths(
        self,
        candidate: Dict[str, Any],
        target_type: str,
        id_field: str,
        target_id: str,
        target_name: str,
        score: float,
    ) -> List[Dict[str, Any]]:
        relations = candidate.get("path_relations") or []
        evidence_id = candidate.get("evidence_id")
        evidence_name = candidate.get("evidence_name") or evidence_id
        evidence_type = candidate.get("evidence_type") or "Evidence"
        source_id = candidate.get("source_id")
        source_type = candidate.get("source_type") or "Source"
        if not relations or not evidence_id or not source_id:
            return []

        entities = [
            {"id": source_id, "type": source_type, "name": source_id},
            {"id": evidence_id, "type": evidence_type, "name": evidence_name},
            {"id": target_id, "type": target_type, "name": target_name},
        ]
        return [
            {
                "path": " -> ".join(str(rel) for rel in relations),
                "relations": list(relations),
                "node_types": [source_type, evidence_type, target_type],
                "entity_names": [str(entity["name"]) for entity in entities],
                "entities": entities,
                "score": round(float(score), 3),
                "length": len(relations),
                "source": "cypher_fallback",
            }
        ]
    
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
        candidates = self.graph_repo.find_candidate_projects(expert_id, status_filter=status_filter)
        if include_funder_candidates:
            candidates2 = self.graph_repo.find_candidate_projects_by_shared_funder(
                expert_id, status_filter=status_filter, limit=max(80, limit * 5)
            )
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
        candidates = self.graph_repo.find_candidate_funders_for_expert(expert_id, limit=max(80, limit * 5))
        return self._recommend_generic_fallback_from_candidates(
            candidates=candidates,
            target_type="Funder",
            id_field="funder_id",
            limit=limit,
            min_score=0.0,
        )

    def _recommend_enterprises_for_expert_cypher(self, expert_id: str, limit: int) -> List[Dict[str, Any]]:
        candidates = self.graph_repo.find_candidate_enterprises_for_expert(expert_id, limit=max(80, limit * 5))
        return self._recommend_generic_fallback_from_candidates(
            candidates=candidates,
            target_type="Enterprise",
            id_field="enterprise_id",
            limit=limit,
            min_score=0.0,
        )

    def _recommend_experts_for_expert_cypher(self, expert_id: str, limit: int) -> List[Dict[str, Any]]:
        candidates = self.graph_repo.find_candidate_experts_for_expert(expert_id, limit=max(80, limit * 5))
        return self._recommend_generic_fallback_from_candidates(
            candidates=candidates,
            target_type="Expert",
            id_field="expert_id",
            limit=limit,
            min_score=0.0,
        )

    def _recommend_funders_for_project_cypher(self, project_id: str, limit: int) -> List[Dict[str, Any]]:
        candidates = self.graph_repo.find_candidate_funders(project_id)
        return self._recommend_generic_fallback_from_candidates(
            candidates=candidates,
            target_type="Funder",
            id_field="funder_id",
            limit=limit,
            min_score=0.0,
        )

    def _recommend_enterprises_for_project_cypher(self, project_id: str, limit: int) -> List[Dict[str, Any]]:
        candidates = self.graph_repo.find_candidate_enterprises_for_project(project_id, limit=max(80, limit * 5))
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
        candidates = self.graph_repo.find_candidate_projects_for_project(project_id, status_filter=status_filter, limit=max(80, limit * 5)
            )
        return self._recommend_generic_fallback_from_candidates(
            candidates=candidates,
            target_type="Project",
            id_field="project_id",
            limit=limit,
            min_score=0.0,
        )

    def _recommend_experts_for_enterprise_cypher(self, enterprise_id: str, limit: int) -> List[Dict[str, Any]]:
        candidates = self.graph_repo.find_candidate_experts_for_enterprise(enterprise_id, limit=max(80, limit * 5))
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
        candidates = self.graph_repo.find_candidate_projects_for_enterprise(enterprise_id, status_filter=status_filter, limit=max(80, limit * 5)
            )
        return self._recommend_generic_fallback_from_candidates(
            candidates=candidates,
            target_type="Project",
            id_field="project_id",
            limit=limit,
            min_score=0.0,
        )

    def _recommend_funders_for_enterprise_cypher(self, enterprise_id: str, limit: int) -> List[Dict[str, Any]]:
        candidates = self.graph_repo.find_candidate_funders_for_enterprise(enterprise_id, limit=max(80, limit * 5))
        return self._recommend_generic_fallback_from_candidates(
            candidates=candidates,
            target_type="Funder",
            id_field="funder_id",
            limit=limit,
            min_score=0.0,
        )

    def _recommend_enterprises_for_enterprise_cypher(self, enterprise_id: str, limit: int) -> List[Dict[str, Any]]:
        candidates = self.graph_repo.find_candidate_enterprises_for_enterprise(enterprise_id, limit=max(80, limit * 5))
        return self._recommend_generic_fallback_from_candidates(
            candidates=candidates,
            target_type="Enterprise",
            id_field="enterprise_id",
            limit=limit,
            min_score=0.0,
        )

    def _recommend_experts_for_funder_cypher(self, funder_id: str, limit: int) -> List[Dict[str, Any]]:
        candidates = self.graph_repo.find_candidate_experts_for_funder(funder_id, limit=max(80, limit * 5))
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
        candidates = self.graph_repo.find_candidate_projects_for_funder(funder_id, status_filter=status_filter, limit=max(80, limit * 5)
            )
        return self._recommend_generic_fallback_from_candidates(
            candidates=candidates,
            target_type="Project",
            id_field="project_id",
            limit=limit,
            min_score=0.0,
        )

    def _recommend_enterprises_for_funder_cypher(self, funder_id: str, limit: int) -> List[Dict[str, Any]]:
        candidates = self.graph_repo.find_candidate_enterprises_for_funder(funder_id, limit=max(80, limit * 5))
        return self._recommend_generic_fallback_from_candidates(
            candidates=candidates,
            target_type="Enterprise",
            id_field="enterprise_id",
            limit=limit,
            min_score=0.0,
        )
    
    def _calculate_expert_score(
        self,
        paths: List[Dict[str, Any]],
        expert_info: Dict[str, Any],
    ) -> float:
        """Score expert recommendation from paths and profile metrics."""
        if not paths:
            return 0.0

        path_scores = [p["score"] for p in paths]
        max_path_score = max(path_scores)
        avg_path_score = np.mean(path_scores)
        min_path_length = min(p["length"] for p in paths)
        path_diversity = len(set(tuple(p["relations"]) for p in paths))
        diversity_score = min(path_diversity / self.top_k_paths, 1.0)
        length_score = 1.0 / min_path_length

        h_index = expert_info.get("h_index", 0) or 0
        citations = expert_info.get("citations", 0) or 0
        h_index_normalized = min(h_index / 100.0, 1.0)
        citation_normalized = min(np.log10(citations + 1) / 6.0, 1.0)
        quality_score = (h_index_normalized + citation_normalized) / 2.0

        return (
            max_path_score * self.SCORE_WEIGHT_MAX_PATH
            + avg_path_score * self.SCORE_WEIGHT_AVG_PATH
            + length_score * self.SCORE_WEIGHT_MIN_LENGTH
            + diversity_score * self.SCORE_WEIGHT_DIVERSITY
            + quality_score * self.SCORE_WEIGHT_QUALITY
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

        candidates = self.graph_repo.find_all_reachable_experts_batch(
            project_id, max_depth=self.DEFAULT_HARD_LIMIT_DEPTH
        )

        if not candidates:
            logger.info(f"No candidate experts found for project {project_id}")
            return []

        candidates_by_depth = defaultdict(list)
        for candidate in candidates:
            depth = candidate.get("min_hops", 5)
            candidates_by_depth[depth].append(candidate)

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

                paths = self.find_reasoning_paths(
                    source_id=project_id,
                    source_type="Project",
                    target_id=expert_id,
                    target_type="Expert",
                    max_length=min(depth + 2, self.DEFAULT_HARD_LIMIT_DEPTH),
                )

                if not paths:
                    continue

                score = self._calculate_expert_score(paths, candidate)

                if score >= min_score:
                    recommendations.append({
                        "expert_id": expert_id,
                        "name": candidate.get("name"),
                        "location": candidate.get("location"),
                        "score": round(score, 3),
                        "reasoning_paths": [
                            self._build_path_payload(p)
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

        recommendations.sort(key=lambda x: x["score"], reverse=True)
        return recommendations[:limit]
    
    def _recommend_with_policy(
        self,
        project_id: str,
        limit: int,
        min_score: float,
    ) -> List[Dict[str, Any]]:
        """Use trained policy for recommendations."""
        exclude_keys = [
            f"Expert::{eid}" for eid in self.graph_repo.get_expert_participant_ids(project_id)
        ]

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
            for item in policy_paths[:limit * 2]:
                target_key = item["target_entity_key"]
                if "::" not in target_key:
                    continue
                _, expert_id = target_key.split("::", 1)
                expert_info = self.graph_repo.get_expert_info(
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
                    "reasoning_paths": [
                        self._build_path_payload(p)
                        for p in item.get("top_paths", [])[:3]
                    ],
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
                    entities = self._resolve_policy_path_entities(ents)
                    unique_top_paths.append({
                        "path_relations": rels,
                        "path_entities": ents,
                        "entities": entities,
                        "entity_names": [entity.get("name") for entity in entities],
                        "node_types": [entity.get("type") for entity in entities],
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

    def _get_exclude_keys(self, source_id: str, source_type: str, target_type: str) -> List[str]:
        """Tự động cắm biển cấm dựa trên cặp quan hệ Ground Truth"""
        ids = self.graph_repo.get_exclude_target_ids(source_id, source_type, target_type)
        return [f"{target_type}::{tid}" for tid in ids]

    def _generic_recommend_with_policy(
        self,
        source_id: str,
        source_type: str,
        target_type: str,
        limit: int = 10,
        min_score: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """Hàm duy nhất để chạy AI cho mọi luồng (Không có Cypher)"""
        logger.debug(f"\n{'='*60}\n🚀 ĐANG CHẠY MÔ HÌNH TRÍ TUỆ NHÂN TẠO (POLICY PGPR)\n   Luồng: {source_type} -> {target_type} | ID: {source_id}\n{'='*60}")
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
        for item in policy_paths[:limit * 2]:
            target_key = item["target_entity_key"]
            if "::" not in target_key:
                continue
            _, t_id = target_key.split("::", 1)

            info = self.graph_repo.get_generic_entity_info(t_id, target_type)
            if not info:
                continue

            reasoning_paths = [
                self._build_path_payload(p)
                for p in item["top_paths"]
            ]
            rec = {
                f"{target_type.lower()}_id": t_id,
                "name": info.get("name", info.get("title", "N/A")),
                "score": round(item["score"], 3),
                "reasoning_paths": reasoning_paths,
                "path_diversity": item["n_paths"],
                "scoring_method": "pgpr_policy",
                "metrics": {
                    "h_index": info.get("h_index"),
                    "budget": info.get("budget"),
                    "status": info.get("status"),
                },
            }
            if not reasoning_paths:
                rec["fallback_reason"] = (
                    "PGPR policy tim thay muc do phu hop nhung chua co duong ly do chi tiet."
                )
                rec["score"] = min(rec["score"], 0.55)
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

                # Chuẩn hóa về [0, 1] để đồng nhất với XAI formatter ({score:.1%})
                rec["score"] = round(final_percentage / 100.0, 3)

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
