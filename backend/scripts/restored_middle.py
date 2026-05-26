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
    
