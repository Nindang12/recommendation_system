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

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


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
    
    def __init__(
        self,
        max_path_length: int = 5,
        gamma: float = 0.99,
        top_k_paths: int = 10,
        path_penalty: float = 0.1,
        policy_path: Optional[str] = None,
        data_dir: str = "pgpr_data",
        enable_cache: bool = True,
    ):
        self.driver = driver
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
        """Load KG and trained policy from data_dir if files exist."""
        try:
            import torch
            from pgpr_kg import KG
            from pgpr_env import KGEnv
            from pgpr_policy import load_policy as load_policy_net
        except ImportError:
            logger.debug("PyTorch or pgpr modules not available; using heuristic only.")
            return
        
        vocab_path = os.path.join(self.data_dir, "vocab.json")
        if not os.path.exists(vocab_path) or not os.path.exists(self.policy_path):
            logger.debug("No PGPR policy found at %s; using heuristic only.", self.policy_path)
            return
        
        try:
            self.kg = KG(data_dir=self.data_dir)
            self.kg.load_vocab()
            self.kg.load_triples()
            if os.path.exists(os.path.join(self.data_dir, "entity_emb.npy")):
                self.kg.load_embeddings()
            self.policy = load_policy_net(self.kg, self.policy_path)
            self._policy_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            self._env = KGEnv(self.kg, driver=self.driver, max_path_length=self.max_path_length)
            logger.info("PGPR policy loaded from %s (policy-guided mode).", self.policy_path)
        except Exception as e:
            logger.warning("Could not load PGPR policy: %s; using heuristic only.", e)
            self.kg = None
            self.policy = None
            self._env = None
    
    def close(self):
        """Close connections and cleanup."""
        if getattr(self, "_env", None):
            try:
                self._env.close()
            except Exception:
                pass
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
        Uses entity names (e.g. PRJ_0001, Nguyen Van A) when available for clearer paths.
        """
        relation_descriptions = {
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
    
    def recommend_experts_for_project_pgpr(
        self,
        project_id: str,
        limit: int = 10,
        min_score: float = 0.0,
        use_policy: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Recommend experts using PGPR with improvements.
        
        IMPROVEMENTS:
        - Batch candidate queries (faster)
        - Better scoring with multiple features
        - Validation and error handling
        - Performance monitoring
        """
        start_time = time.time()
        
        # Validate inputs
        if not project_id:
            raise ValueError("project_id cannot be empty")
        if limit <= 0:
            raise ValueError(f"limit must be positive, got {limit}")
        
        # Policy-guided mode (if available)
        if use_policy and self.policy is not None:
            return self._recommend_with_policy(project_id, limit, min_score)
        
        # Heuristic mode with improvements
        try:
            recommendations = self._recommend_experts_heuristic_improved(
                project_id, limit, min_score
            )
            
            elapsed = time.time() - start_time
            logger.info(f"Expert recommendation for {project_id}: {len(recommendations)} results in {elapsed:.2f}s")
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error in expert recommendation: {e}", exc_info=True)
            return []
    
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
            result = session.run("""
                MATCH (p:Project {project_id: $project_id})-[:BELONGS_TO]->(rf:ResearchField)
                
                // Find all related fields through hierarchy
                MATCH path = (rf)-[:SUB_FIELD_OF*0..10]-(related_rf:ResearchField)
                
                // Find experts with expertise in these fields
                MATCH (related_rf)<-[:HAS_EXPERTISE_IN]-(e:Expert)
                
                // Exclude experts already in project
                WHERE NOT (e)-[:PARTICIPATES_IN]->(p)
                
                // Calculate minimum hops
                WITH e, MIN(length(path) + 2) as min_hops
                WHERE min_hops <= $max_depth
                
                RETURN e.expert_id as expert_id,
                       e.name as name,
                       e.location as location,
                       e.h_index as h_index,
                       e.citation_count as citations,
                       e.publication_count as publications,
                       min_hops
                ORDER BY min_hops ASC
                LIMIT 100
            """, project_id=project_id, max_depth=max_depth, timeout=self.DEFAULT_QUERY_TIMEOUT)
            
            return [dict(record) for record in result]
            
        except Exception as e:
            logger.warning(f"Error in batch candidate query: {e}")
            # Fallback to simpler query
            return self._find_candidate_experts_simple(session, project_id)
    
    def _find_candidate_experts_simple(
        self,
        session,
        project_id: str
    ) -> List[Dict[str, Any]]:
        """Fallback: Simple candidate query without depth calculation."""
        result = session.run("""
            MATCH (p:Project {project_id: $project_id})-[:BELONGS_TO]->(rf:ResearchField)
            MATCH (rf)<-[:SUB_FIELD_OF*0..2]-(related_rf:ResearchField)
                <-[:HAS_EXPERTISE_IN]-(e:Expert)
            WHERE NOT (e)-[:PARTICIPATES_IN]->(p)
            
            RETURN DISTINCT e.expert_id as expert_id,
                   e.name as name,
                   e.location as location,
                   e.h_index as h_index,
                   e.citation_count as citations,
                   e.publication_count as publications,
                   5 as min_hops
            LIMIT 50
        """, project_id=project_id)
        
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
        n_rollouts = min(50, self.top_k_paths * 5)
        policy_paths = self.policy_guided_paths(
            source_id=project_id,
            source_type="Project",
            target_type="Expert",
            n_rollouts=n_rollouts,
            deterministic=False,
        )
        
        if not policy_paths:
            # Try deterministic
            policy_paths = self.policy_guided_paths(
                source_id=project_id,
                source_type="Project",
                target_type="Expert",
                n_rollouts=min(20, n_rollouts),
                deterministic=True,
            )
        
        if policy_paths:
            recommendations = []
            with self.driver.session() as session:
                for item in policy_paths[:limit * 2]:
                    target_key = item["target_entity_key"]
                    if "::" not in target_key:
                        continue
                    _, expert_id = target_key.split("::", 1)
                    expert_info = self._get_expert_info(session, expert_id)
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
        
        logger.info("Policy-guided paths returned no experts; using heuristic fallback.")
        return self._recommend_experts_heuristic_improved(project_id, limit, min_score)
    
    def policy_guided_paths(
        self,
        source_id: str,
        source_type: str,
        target_type: str,
        n_rollouts: int = 20,
        deterministic: bool = False,
    ) -> List[Dict[str, Any]]:
        """Use trained policy to walk from source until reaching target type."""
        if self.policy is None or self._env is None:
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
            state, valid_actions = self._env.reset(source_key, target_type=target_type)
            current_ent, path = state
            path_log_prob = 0.0
            
            while valid_actions and len(path) < self.max_path_length - 1:
                action_idx, log_prob = self.policy.select_action(
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
            best_idx = np.argmax(data["scores"])
            out.append({
                "target_entity_key": target_key,
                "path_relations": data["paths"][best_idx][0],
                "path_entities": data["paths"][best_idx][1],
                "score": float(np.mean(data["scores"])),
                "n_paths": len(data["paths"]),
            })
        
        out.sort(key=lambda x: x["score"], reverse=True)
        return out
    
    def _get_expert_info(self, session, expert_id: str) -> Optional[Dict[str, Any]]:
        """Fetch expert info from Neo4j."""
        result = session.run(
            "MATCH (e:Expert {expert_id: $expert_id}) "
            "RETURN e.name AS name, e.location AS location, "
            "e.h_index AS h_index, e.citation_count AS citations, "
            "e.publication_count AS publications",
            expert_id=expert_id,
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
        """
        Recommend projects with improvements.
        
        Note: by default we source candidates from:
        - field/hierarchy match (Expert HAS_EXPERTISE_IN ... Project BELONGS_TO)
        - (optional) shared funder portfolio:
          Expert PARTICIPATES_IN Project <-FUNDS- Funder -FUNDS-> Other Projects
          This enables suggestions like PRJ_0007 for EXP_0003 if they share FUN_0002.
        """
        if status_filter is None:
            status_filter = ['planning', 'recruiting', 'ongoing']
        
        with self.driver.session() as session:
            candidates = self._find_candidate_projects(session, expert_id, status_filter)
            if include_funder_candidates:
                funder_candidates = self._find_candidate_projects_by_shared_funder(
                    session, expert_id, status_filter
                )
                if funder_candidates:
                    by_id = {c["project_id"]: c for c in candidates}
                    for fc in funder_candidates:
                        pid = fc["project_id"]
                        if pid in by_id:
                            src = set(by_id[pid].get("candidate_sources") or ["field"])
                            src.add("funder")
                            by_id[pid]["candidate_sources"] = sorted(src)
                            if "common_funders" in fc:
                                by_id[pid]["common_funders"] = max(
                                    by_id[pid].get("common_funders", 0),
                                    fc.get("common_funders", 0),
                                )
                        else:
                            fc["candidate_sources"] = ["funder"]
                            by_id[pid] = fc
                    candidates = list(by_id.values())
            recommendations = []
            
            for candidate in candidates:
                project_id = candidate["project_id"]
                paths = self.find_reasoning_paths(
                    source_id=expert_id,
                    source_type="Expert",
                    target_id=project_id,
                    target_type="Project"
                )
                
                if not paths:
                    continue
                
                # Improved scoring
                score = self._calculate_project_score(paths, candidate)
                
                recommendations.append({
                    "project_id": project_id,
                    "title": candidate["title"],
                    "status": candidate["status"],
                    "location": candidate.get("location"),
                    "trl": candidate.get("trl"),
                    "budget": candidate.get("budget"),
                    "score": round(score, 3),
                    "reasoning_paths": [
                        {"path": p["explanation"], "score": round(p["score"], 3), "length": p["length"]}
                        for p in paths[:3]
                    ],
                    "path_diversity": len(set(tuple(p["relations"]) for p in paths)),
                    "candidate_sources": candidate.get("candidate_sources", ["field"]),
                    "common_funders": candidate.get("common_funders"),
                })
            
            recommendations.sort(key=lambda x: x["score"], reverse=True)
            return recommendations[:limit]

    def recommend_funders_for_expert_pgpr(
        self,
        expert_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Recommend funders/enterprises for an expert.

        Ý tưởng:
        - Ưu tiên các funder đã từng tài trợ các project mà expert tham gia.
        - Mở rộng thêm các funder đang SUPPORT các lĩnh vực mà expert có chuyên môn.
        """
        with self.driver.session() as session:
            candidates = self._find_candidate_funders_for_expert(session, expert_id)
            recommendations: List[Dict[str, Any]] = []

            for candidate in candidates:
                funder_id = candidate["funder_id"]
                paths = self.find_reasoning_paths(
                    source_id=expert_id,
                    source_type="Expert",
                    target_id=funder_id,
                    target_type="Funder",
                )

                if not paths:
                    continue

                score = self._calculate_funder_score(paths, candidate)

                recommendations.append(
                    {
                        "funder_id": funder_id,
                        "name": candidate["name"],
                        "type": candidate.get("type"),
                        "location": candidate.get("location"),
                        "budget_capacity": candidate.get("budget_capacity"),
                        "candidate_sources": candidate.get("candidate_sources", []),
                        "funded_related_projects": candidate.get(
                            "funded_related_projects"
                        ),
                        "score": round(score, 3),
                        "reasoning_paths": [
                            {
                                "path": p["explanation"],
                                "score": round(p["score"], 3),
                                "length": p["length"],
                            }
                            for p in paths[:3]
                        ],
                        "path_diversity": len(
                            set(tuple(p["relations"]) for p in paths)
                        ),
                    }
                )

            recommendations.sort(key=lambda x: x["score"], reverse=True)
            return recommendations[:limit]

    def recommend_enterprises_for_expert_pgpr(
        self,
        expert_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Recommend enterprises for an expert.

        Ý tưởng:
        - Doanh nghiệp hoạt động trong các industry mà expert có kinh nghiệm ứng dụng.
        - Doanh nghiệp đang hợp tác (PARTNERS_WITH) với các dự án mà expert tham gia.
        """
        with self.driver.session() as session:
            candidates = self._find_candidate_enterprises_for_expert(session, expert_id)
            recommendations: List[Dict[str, Any]] = []

            for candidate in candidates:
                enterprise_id = candidate["enterprise_id"]
                paths = self.find_reasoning_paths(
                    source_id=expert_id,
                    source_type="Expert",
                    target_id=enterprise_id,
                    target_type="Enterprise",
                )

                if not paths:
                    continue

                # Reuse funder scoring logic (dựa trên path score + diversity)
                score = self._calculate_funder_score(paths, candidate)

                recommendations.append(
                    {
                        "enterprise_id": enterprise_id,
                        "name": candidate["name"],
                        "location": candidate.get("location"),
                        "candidate_sources": candidate.get("candidate_sources", []),
                        "matched_industries": candidate.get("matched_industries"),
                        "partner_projects": candidate.get("partner_projects"),
                        "score": round(score, 3),
                        "reasoning_paths": [
                            {
                                "path": p["explanation"],
                                "score": round(p["score"], 3),
                                "length": p["length"],
                            }
                            for p in paths[:3]
                        ],
                        "path_diversity": len(
                            set(tuple(p["relations"]) for p in paths)
                        ),
                    }
                )

            recommendations.sort(key=lambda x: x["score"], reverse=True)
            return recommendations[:limit]

    def recommend_experts_for_expert_pgpr(
        self,
        expert_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Recommend experts for collaboration (chuyên gia tiềm năng hợp tác nghiên cứu).
        Meta-paths: same HAS_EXPERTISE_IN field; same PARTICIPATES_IN project; HAS_SKILL same MethodTechnique.
        """
        with self.driver.session() as session:
            candidates = self._find_candidate_experts_for_expert(session, expert_id)
            recommendations: List[Dict[str, Any]] = []
            for candidate in candidates:
                other_id = candidate["expert_id"]
                paths = self.find_reasoning_paths(
                    source_id=expert_id,
                    source_type="Expert",
                    target_id=other_id,
                    target_type="Expert",
                )
                if not paths:
                    continue
                score = self._calculate_expert_score(paths, candidate)
                recommendations.append({
                    "expert_id": other_id,
                    "name": candidate.get("name"),
                    "location": candidate.get("location"),
                    "score": round(score, 3),
                    "reasoning_paths": [
                        {"path": p["explanation"], "score": round(p["score"], 3), "length": p["length"]}
                        for p in paths[:3]
                    ],
                    "path_diversity": len(set(tuple(p["relations"]) for p in paths)),
                    "metrics": {
                        "h_index": candidate.get("h_index"),
                        "citations": candidate.get("citations"),
                        "publications": candidate.get("publications"),
                    },
                    "candidate_sources": candidate.get("candidate_sources", []),
                })
            recommendations.sort(key=lambda x: x["score"], reverse=True)
            return recommendations[:limit]

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
        
        Note:
        - We expand the expert's research field through the hierarchy in BOTH directions
          (parent/child/sibling via common parent), so experts can be matched to related
          fields like: AI_002 (Computer Vision) ↔ IOT_001 (IoT) through AI_001.
        """
        result = session.run("""
            MATCH (e:Expert {expert_id: $expert_id})-[:HAS_EXPERTISE_IN]->(rf:ResearchField)
            // Traverse hierarchy undirected to include parent/child and sibling fields
            MATCH (rf)-[:SUB_FIELD_OF*0..2]-(related_rf:ResearchField)
                <-[:BELONGS_TO]-(p:Project)
            WHERE p.status IN $status_filter
              AND NOT (e)-[:PARTICIPATES_IN]->(p)
            
            RETURN DISTINCT p.project_id as project_id,
                   p.title as title,
                   p.status as status,
                   p.location as location,
                   p.trl as trl,
                   p.budget as budget
            LIMIT 80
        """, expert_id=expert_id, status_filter=status_filter)
        
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
                RETURN DISTINCT p.project_id as project_id,
                       p.title as title,
                       p.status as status,
                       p.location as location,
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
        """Recommend funders with improvements."""
        with self.driver.session() as session:
            candidates = self._find_candidate_funders(session, project_id)
            recommendations = []
            
            for candidate in candidates:
                funder_id = candidate["funder_id"]
                paths = self.find_reasoning_paths(
                    source_id=project_id,
                    source_type="Project",
                    target_id=funder_id,
                    target_type="Funder"
                )
                
                if not paths:
                    continue
                
                score = self._calculate_funder_score(paths, candidate)
                
                recommendations.append({
                    "funder_id": funder_id,
                    "name": candidate["name"],
                    "type": candidate["type"],
                    "location": candidate.get("location"),
                    "budget_capacity": candidate.get("budget_capacity"),
                    "candidate_sources": candidate.get("candidate_sources", []),
                    "funded_related_projects": candidate.get("funded_related_projects"),
                    "score": round(score, 3),
                    "reasoning_paths": [
                        {"path": p["explanation"], "score": round(p["score"], 3), "length": p["length"]}
                        for p in paths[:3]
                    ],
                    "path_diversity": len(set(tuple(p["relations"]) for p in paths))
                })
            
            recommendations.sort(key=lambda x: x["score"], reverse=True)
            return recommendations[:limit]

    def recommend_enterprises_for_project_pgpr(
        self,
        project_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Recommend enterprises for a project (doanh nghiệp hợp tác/chuyển giao công nghệ).
        Meta-paths: Project->Field->RelatedProject<-PARTNERS_WITH-Enterprise;
                    Project->Expert->Industry<-OPERATES_IN-Enterprise.
        """
        with self.driver.session() as session:
            candidates = self._find_candidate_enterprises_for_project(session, project_id)
            recommendations = []
            for candidate in candidates:
                enterprise_id = candidate["enterprise_id"]
                paths = self.find_reasoning_paths(
                    source_id=project_id,
                    source_type="Project",
                    target_id=enterprise_id,
                    target_type="Enterprise",
                )
                if not paths:
                    continue
                score = self._calculate_funder_score(paths, candidate)  # path+diversity
                recommendations.append({
                    "enterprise_id": enterprise_id,
                    "name": candidate["name"],
                    "location": candidate.get("location"),
                    "candidate_sources": candidate.get("candidate_sources", []),
                    "partner_projects": candidate.get("partner_projects"),
                    "score": round(score, 3),
                    "reasoning_paths": [
                        {"path": p["explanation"], "score": round(p["score"], 3), "length": p["length"]}
                        for p in paths[:3]
                    ],
                    "path_diversity": len(set(tuple(p["relations"]) for p in paths)),
                })
            recommendations.sort(key=lambda x: x["score"], reverse=True)
            return recommendations[:limit]

    def recommend_projects_for_project_pgpr(
        self,
        project_id: str,
        limit: int = 10,
        status_filter: List[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Recommend similar projects (dự án tương tự để tham khảo/hợp tác).
        Meta-paths: same field, same funder, shared experts.
        """
        if status_filter is None:
            status_filter = ["planning", "recruiting", "ongoing"]
        with self.driver.session() as session:
            candidates = self._find_candidate_projects_for_project(session, project_id, status_filter)
            recommendations = []
            for candidate in candidates:
                other_id = candidate["project_id"]
                paths = self.find_reasoning_paths(
                    source_id=project_id,
                    source_type="Project",
                    target_id=other_id,
                    target_type="Project",
                )
                if not paths:
                    continue
                score = self._calculate_project_score(paths, candidate)
                recommendations.append({
                    "project_id": other_id,
                    "title": candidate["title"],
                    "status": candidate["status"],
                    "location": candidate.get("location"),
                    "trl": candidate.get("trl"),
                    "budget": candidate.get("budget"),
                    "score": round(score, 3),
                    "reasoning_paths": [
                        {"path": p["explanation"], "score": round(p["score"], 3), "length": p["length"]}
                        for p in paths[:3]
                    ],
                    "path_diversity": len(set(tuple(p["relations"]) for p in paths)),
                    "candidate_sources": candidate.get("candidate_sources", ["field"]),
                })
            recommendations.sort(key=lambda x: x["score"], reverse=True)
            return recommendations[:limit]
    
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
        
        # Source 1: Funders that SUPPORT the project's field or related fields (hierarchy-expanded)
        try:
            result = session.run(
                """
                MATCH (p:Project {project_id: $project_id})-[:BELONGS_TO]->(rf:ResearchField)
                MATCH (rf)-[:SUB_FIELD_OF*0..2]-(related_rf:ResearchField)
                    <-[:SUPPORTS]-(f:Funder)
                WHERE NOT (f)-[:FUNDS]->(p)
                
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
        
        # Source 2: Funders that FUNDS other projects in related fields (portfolio-based)
        # Pattern: p -> field ~ related_field <- p2 <- FUNDS - f
        try:
            result2 = session.run(
                """
                MATCH (p:Project {project_id: $project_id})-[:BELONGS_TO]->(rf:ResearchField)
                MATCH (rf)-[:SUB_FIELD_OF*0..2]-(related_rf:ResearchField)<-[:BELONGS_TO]-(p2:Project)
                MATCH (f:Funder)-[:FUNDS]->(p2)
                WHERE p2.project_id <> $project_id
                  AND NOT (f)-[:FUNDS]->(p)
                
                RETURN DISTINCT f.funder_id as funder_id,
                       f.name as name,
                       f.type as type,
                       f.location as location,
                       f.budget_capacity as budget_capacity,
                       count(DISTINCT p2) as funded_related_projects
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
                MATCH (p:Project {project_id: $project_id})-[:BELONGS_TO]->(rf:ResearchField)
                MATCH (rf)-[:SUB_FIELD_OF*0..2]-(related_rf:ResearchField)<-[:BELONGS_TO]-(p2:Project)
                MATCH (en:Enterprise)-[:PARTNERS_WITH]->(p2)
                WHERE p2.project_id <> $project_id
                RETURN DISTINCT en.enterprise_id AS enterprise_id,
                       en.name AS name,
                       en.location AS location,
                       count(DISTINCT p2) AS partner_projects
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
                MATCH (p:Project {project_id: $project_id})-[:BELONGS_TO]->(rf:ResearchField)
                MATCH (rf)-[:SUB_FIELD_OF*0..2]-(related_rf:ResearchField)<-[:BELONGS_TO]-(p2:Project)
                WHERE p2.project_id <> $project_id AND p2.status IN $status_filter
                RETURN DISTINCT p2.project_id AS project_id,
                       p2.title AS title,
                       p2.status AS status,
                       p2.location AS location,
                       p2.trl AS trl,
                       p2.budget AS budget
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
                RETURN DISTINCT p2.project_id AS project_id,
                       p2.title AS title,
                       p2.status AS status,
                       p2.location AS location,
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
                MATCH (e:Expert {{expert_id: $expert_id}})-[:HAS_EXPERTISE_IN]->(rf:ResearchField)
                MATCH (rf)-[:SUB_FIELD_OF*0..2]-(related_rf:ResearchField)
                    <-[:SUPPORTS]-(f:Funder)
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
                MATCH (e:Expert {expert_id: $expert_id})-[:HAS_EXPERTISE_IN]->(rf:ResearchField)
                MATCH (rf)-[:SUB_FIELD_OF*0..2]-(related_rf:ResearchField)<-[:HAS_EXPERTISE_IN]-(e2:Expert)
                WHERE e2.expert_id <> $expert_id
                RETURN DISTINCT e2.expert_id AS expert_id,
                       e2.name AS name,
                       e2.location AS location,
                       e2.h_index AS h_index,
                       e2.citation_count AS citations,
                       e2.publication_count AS publications
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
        """
        Recommend experts for an enterprise (doanh nghiệp cần chuyên gia phù hợp).
        - Chuyên gia có kinh nghiệm ứng dụng trong industry mà enterprise hoạt động.
        - Chuyên gia từng tham gia các dự án mà enterprise đang hợp tác.
        """
        with self.driver.session() as session:
            candidates = self._find_candidate_experts_for_enterprise(session, enterprise_id)
            recommendations: List[Dict[str, Any]] = []

            for candidate in candidates:
                expert_id = candidate["expert_id"]
                paths = self.find_reasoning_paths(
                    source_id=enterprise_id,
                    source_type="Enterprise",
                    target_id=expert_id,
                    target_type="Expert",
                )
                if not paths:
                    continue
                score = self._calculate_expert_score(paths, candidate)
                recommendations.append({
                    "expert_id": expert_id,
                    "name": candidate.get("name"),
                    "location": candidate.get("location"),
                    "score": round(score, 3),
                    "reasoning_paths": [
                        {"path": p["explanation"], "score": round(p["score"], 3), "length": p["length"]}
                        for p in paths[:3]
                    ],
                    "path_diversity": len(set(tuple(p["relations"]) for p in paths)),
                    "metrics": {
                        "h_index": candidate.get("h_index"),
                        "citations": candidate.get("citations"),
                        "publications": candidate.get("publications"),
                    },
                    "candidate_sources": candidate.get("candidate_sources", []),
                })
            recommendations.sort(key=lambda x: x["score"], reverse=True)
            return recommendations[:limit]

    def recommend_projects_for_enterprise_pgpr(
        self,
        enterprise_id: str,
        limit: int = 10,
        status_filter: List[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Recommend projects for an enterprise (dự án phù hợp để doanh nghiệp hợp tác).
        - Dự án cùng lĩnh vực/industry với enterprise.
        - Dự án liên quan đến các dự án enterprise đã hợp tác.
        """
        if status_filter is None:
            status_filter = ["planning", "recruiting", "ongoing"]
        with self.driver.session() as session:
            candidates = self._find_candidate_projects_for_enterprise(session, enterprise_id, status_filter)
            recommendations: List[Dict[str, Any]] = []

            for candidate in candidates:
                project_id = candidate["project_id"]
                paths = self.find_reasoning_paths(
                    source_id=enterprise_id,
                    source_type="Enterprise",
                    target_id=project_id,
                    target_type="Project",
                )
                if not paths:
                    continue
                score = self._calculate_project_score(paths, candidate)
                recommendations.append({
                    "project_id": project_id,
                    "title": candidate["title"],
                    "status": candidate["status"],
                    "location": candidate.get("location"),
                    "trl": candidate.get("trl"),
                    "budget": candidate.get("budget"),
                    "score": round(score, 3),
                    "reasoning_paths": [
                        {"path": p["explanation"], "score": round(p["score"], 3), "length": p["length"]}
                        for p in paths[:3]
                    ],
                    "path_diversity": len(set(tuple(p["relations"]) for p in paths)),
                    "candidate_sources": candidate.get("candidate_sources", ["field"]),
                })
            recommendations.sort(key=lambda x: x["score"], reverse=True)
            return recommendations[:limit]

    def recommend_funders_for_enterprise_pgpr(
        self,
        enterprise_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Recommend funders for an enterprise (quỹ tài trợ liên quan lĩnh vực doanh nghiệp).
        Meta-paths: Enterprise-PARTNERS_WITH-Project-FUNDS-Funder; Enterprise-PARTNERS_WITH-Project-BELONGS_TO-Field-SUPPORTS-Funder.
        """
        with self.driver.session() as session:
            candidates = self._find_candidate_funders_for_enterprise(session, enterprise_id)
            recommendations: List[Dict[str, Any]] = []
            for candidate in candidates:
                funder_id = candidate["funder_id"]
                paths = self.find_reasoning_paths(
                    source_id=enterprise_id,
                    source_type="Enterprise",
                    target_id=funder_id,
                    target_type="Funder",
                )
                if not paths:
                    continue
                score = self._calculate_funder_score(paths, candidate)
                recommendations.append({
                    "funder_id": funder_id,
                    "name": candidate["name"],
                    "type": candidate.get("type"),
                    "location": candidate.get("location"),
                    "budget_capacity": candidate.get("budget_capacity"),
                    "candidate_sources": candidate.get("candidate_sources", []),
                    "score": round(score, 3),
                    "reasoning_paths": [
                        {"path": p["explanation"], "score": round(p["score"], 3), "length": p["length"]}
                        for p in paths[:3]
                    ],
                    "path_diversity": len(set(tuple(p["relations"]) for p in paths)),
                })
            recommendations.sort(key=lambda x: x["score"], reverse=True)
            return recommendations[:limit]

    def recommend_enterprises_for_enterprise_pgpr(
        self,
        enterprise_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Recommend enterprises for collaboration (doanh nghiệp cùng lĩnh vực để hợp tác).
        Meta-paths: same OPERATES_IN industry; same PARTNERS_WITH project; related field via partner projects.
        """
        with self.driver.session() as session:
            candidates = self._find_candidate_enterprises_for_enterprise(session, enterprise_id)
            recommendations: List[Dict[str, Any]] = []
            for candidate in candidates:
                other_id = candidate["enterprise_id"]
                paths = self.find_reasoning_paths(
                    source_id=enterprise_id,
                    source_type="Enterprise",
                    target_id=other_id,
                    target_type="Enterprise",
                )
                if not paths:
                    continue
                score = self._calculate_funder_score(paths, candidate)
                recommendations.append({
                    "enterprise_id": other_id,
                    "name": candidate["name"],
                    "location": candidate.get("location"),
                    "candidate_sources": candidate.get("candidate_sources", []),
                    "shared_projects": candidate.get("shared_projects"),
                    "matched_industries": candidate.get("matched_industries"),
                    "score": round(score, 3),
                    "reasoning_paths": [
                        {"path": p["explanation"], "score": round(p["score"], 3), "length": p["length"]}
                        for p in paths[:3]
                    ],
                    "path_diversity": len(set(tuple(p["relations"]) for p in paths)),
                })
            recommendations.sort(key=lambda x: x["score"], reverse=True)
            return recommendations[:limit]

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
                MATCH (en:Enterprise {enterprise_id: $enterprise_id})-[:PARTNERS_WITH]->(p0:Project)-[:BELONGS_TO]->(rf:ResearchField)
                MATCH (rf)-[:SUB_FIELD_OF*0..2]-(related_rf:ResearchField)<-[:BELONGS_TO]-(p:Project)
                WHERE p.status IN $status_filter
                  AND NOT (en)-[:PARTNERS_WITH]->(p)
                RETURN DISTINCT p.project_id AS project_id,
                       p.title AS title,
                       p.status AS status,
                       p.location AS location,
                       p.trl AS trl,
                       p.budget AS budget
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
                MATCH (en:Enterprise {enterprise_id: $enterprise_id})-[:PARTNERS_WITH]->(p:Project)-[:BELONGS_TO]->(rf:ResearchField)
                MATCH (f:Funder)-[:SUPPORTS]->(rf)
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
        """
        Recommend experts for a funder (chuyên gia phù hợp với danh mục/quỹ).
        - Chuyên gia tham gia các dự án mà funder tài trợ.
        - Chuyên gia có chuyên môn trong lĩnh vực funder hỗ trợ.
        """
        with self.driver.session() as session:
            candidates = self._find_candidate_experts_for_funder(session, funder_id)
            recommendations: List[Dict[str, Any]] = []

            for candidate in candidates:
                expert_id = candidate["expert_id"]
                paths = self.find_reasoning_paths(
                    source_id=funder_id,
                    source_type="Funder",
                    target_id=expert_id,
                    target_type="Expert",
                )
                if not paths:
                    continue
                score = self._calculate_expert_score(paths, candidate)
                recommendations.append({
                    "expert_id": expert_id,
                    "name": candidate.get("name"),
                    "location": candidate.get("location"),
                    "score": round(score, 3),
                    "reasoning_paths": [
                        {"path": p["explanation"], "score": round(p["score"], 3), "length": p["length"]}
                        for p in paths[:3]
                    ],
                    "path_diversity": len(set(tuple(p["relations"]) for p in paths)),
                    "metrics": {
                        "h_index": candidate.get("h_index"),
                        "citations": candidate.get("citations"),
                        "publications": candidate.get("publications"),
                    },
                    "candidate_sources": candidate.get("candidate_sources", []),
                })
            recommendations.sort(key=lambda x: x["score"], reverse=True)
            return recommendations[:limit]

    def recommend_projects_for_funder_pgpr(
        self,
        funder_id: str,
        limit: int = 10,
        status_filter: List[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Recommend projects for a funder (dự án phù hợp để quỹ tài trợ).
        - Dự án thuộc lĩnh vực funder SUPPORT.
        - Dự án liên quan (cùng field) với các dự án funder đã FUNDS.
        """
        if status_filter is None:
            status_filter = ["planning", "recruiting", "ongoing"]
        with self.driver.session() as session:
            candidates = self._find_candidate_projects_for_funder(session, funder_id, status_filter)
            recommendations: List[Dict[str, Any]] = []

            for candidate in candidates:
                project_id = candidate["project_id"]
                paths = self.find_reasoning_paths(
                    source_id=funder_id,
                    source_type="Funder",
                    target_id=project_id,
                    target_type="Project",
                )
                if not paths:
                    continue
                score = self._calculate_project_score(paths, candidate)
                recommendations.append({
                    "project_id": project_id,
                    "title": candidate["title"],
                    "status": candidate["status"],
                    "location": candidate.get("location"),
                    "trl": candidate.get("trl"),
                    "budget": candidate.get("budget"),
                    "score": round(score, 3),
                    "reasoning_paths": [
                        {"path": p["explanation"], "score": round(p["score"], 3), "length": p["length"]}
                        for p in paths[:3]
                    ],
                    "path_diversity": len(set(tuple(p["relations"]) for p in paths)),
                    "candidate_sources": candidate.get("candidate_sources", ["field"]),
                })
            recommendations.sort(key=lambda x: x["score"], reverse=True)
            return recommendations[:limit]

    def recommend_enterprises_for_funder_pgpr(
        self,
        funder_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Recommend enterprises for a funder (doanh nghiệp chiến lược đồng hành cùng dự án).
        Meta-paths: Funder-FUNDS-Project-PARTNERS_WITH-Enterprise; Funder-SUPPORTS-Field-BELONGS_TO-Project-PARTNERS_WITH-Enterprise.
        """
        with self.driver.session() as session:
            candidates = self._find_candidate_enterprises_for_funder(session, funder_id)
            recommendations: List[Dict[str, Any]] = []
            for candidate in candidates:
                enterprise_id = candidate["enterprise_id"]
                paths = self.find_reasoning_paths(
                    source_id=funder_id,
                    source_type="Funder",
                    target_id=enterprise_id,
                    target_type="Enterprise",
                )
                if not paths:
                    continue
                score = self._calculate_funder_score(paths, candidate)
                recommendations.append({
                    "enterprise_id": enterprise_id,
                    "name": candidate["name"],
                    "location": candidate.get("location"),
                    "candidate_sources": candidate.get("candidate_sources", []),
                    "partner_projects": candidate.get("partner_projects"),
                    "score": round(score, 3),
                    "reasoning_paths": [
                        {"path": p["explanation"], "score": round(p["score"], 3), "length": p["length"]}
                        for p in paths[:3]
                    ],
                    "path_diversity": len(set(tuple(p["relations"]) for p in paths)),
                })
            recommendations.sort(key=lambda x: x["score"], reverse=True)
            return recommendations[:limit]

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
                RETURN DISTINCT e.expert_id AS expert_id,
                       e.name AS name,
                       e.location AS location,
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
                MATCH (f:Funder {funder_id: $funder_id})-[:SUPPORTS]->(rf:ResearchField)
                MATCH (e:Expert)-[:HAS_EXPERTISE_IN]->(rf)
                RETURN DISTINCT e.expert_id AS expert_id,
                       e.name AS name,
                       e.location AS location,
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
                MATCH (f:Funder {funder_id: $funder_id})-[:SUPPORTS]->(rf:ResearchField)
                MATCH (rf)-[:SUB_FIELD_OF*0..2]-(related_rf:ResearchField)<-[:BELONGS_TO]-(p:Project)
                WHERE p.status IN $status_filter
                  AND NOT (f)-[:FUNDS]->(p)
                RETURN DISTINCT p.project_id AS project_id,
                       p.title AS title,
                       p.status AS status,
                       p.location AS location,
                       p.trl AS trl,
                       p.budget AS budget
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
                MATCH (f:Funder {funder_id: $funder_id})-[:FUNDS]->(p0:Project)-[:BELONGS_TO]->(rf:ResearchField)
                MATCH (rf)-[:SUB_FIELD_OF*0..2]-(related_rf:ResearchField)<-[:BELONGS_TO]-(p:Project)
                WHERE p.status IN $status_filter
                  AND p.project_id <> p0.project_id
                  AND NOT (f)-[:FUNDS]->(p)
                RETURN DISTINCT p.project_id AS project_id,
                       p.title AS title,
                       p.status AS status,
                       p.location AS location,
                       p.trl AS trl,
                       p.budget AS budget
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
                MATCH (f:Funder {funder_id: $funder_id})-[:SUPPORTS]->(rf:ResearchField)
                MATCH (rf)-[:SUB_FIELD_OF*0..2]-(related_rf:ResearchField)<-[:BELONGS_TO]-(p:Project)
                MATCH (en:Enterprise)-[:PARTNERS_WITH]->(p)
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
# UTILITY FUNCTIONS
# ==========================================

def print_pgpr_recommendations(
    recommendations: List[Dict],
    title: str,
    show_paths: bool = True,
    show_detailed: bool = False
):
    """Pretty print PGPR recommendations with reasoning paths and detailed explanations."""
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
            project_id="PRJ_0001",
            limit=5
        )
        print_pgpr_recommendations(experts, "Recommended Experts for PRJ_0001")
        
        # Show cache statistics
        stats = pgpr.get_cache_stats()
        print(f"\nCache stats: {stats['hits']} hits, {stats['misses']} misses, {stats['size']} entries")
        
    finally:
        pgpr.close()