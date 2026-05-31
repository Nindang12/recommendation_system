"""
Neo4j graph access layer for PGPR (Policy-Guided Path Reasoning).

Single place for Cypher queries used by PGPRRecommender.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from dotenv import find_dotenv, load_dotenv
from neo4j import GraphDatabase

load_dotenv(find_dotenv())

logger = logging.getLogger(__name__)

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")


class PGPRGraphRepository:
    """Adapter for Neo4j queries serving PGPR recommendation."""

    DEFAULT_QUERY_TIMEOUT = 10.0

    def __init__(self, driver: Any = None) -> None:
        if driver is not None:
            self.driver = driver
            self._owns_driver = False
        else:
            self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            self._owns_driver = True

    def close(self) -> None:
        if self._owns_driver and self.driver is not None:
            self.driver.close()

    def check_health(self) -> bool:
        try:
            with self.driver.session() as session:
                record = session.run("RETURN 1 AS num").single()
                return bool(record and record.get("num") == 1)
        except Exception:
            return False

    def run_read(self, query: str, **params: Any) -> List[Dict[str, Any]]:
        timeout = params.pop("timeout", self.DEFAULT_QUERY_TIMEOUT)
        with self.driver.session() as session:
            result = session.run(query, **params, timeout=timeout)
            return [dict(record) for record in result]

    def run_write(self, query: str, **params: Any) -> List[Dict[str, Any]]:
        return self.run_read(query, **params)

    def ensure_constraints(self) -> None:
        constraints = [
            ("expert_id_unique", "Expert", "id"),
            ("expert_expert_id_unique", "Expert", "expert_id"),
            ("project_id_unique", "Project", "id"),
            ("project_project_id_unique", "Project", "project_id"),
            ("enterprise_id_unique", "Enterprise", "id"),
            ("enterprise_enterprise_id_unique", "Enterprise", "enterprise_id"),
            ("funder_id_unique", "Funder", "id"),
            ("funder_funder_id_unique", "Funder", "funder_id"),
            ("topic_id_unique", "ResearchTopic", "topic_id"),
            ("skill_id_unique", "Skill", "skill_id"),
            ("location_id_unique", "Location", "location_id"),
            ("industry_id_unique", "Industry", "industry_id"),
        ]
        for name, label, prop in constraints:
            try:
                self.run_write(
                    f"CREATE CONSTRAINT {name} IF NOT EXISTS "
                    f"FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE"
                )
            except Exception as exc:
                logger.debug("Could not create Neo4j constraint %s: %s", name, exc)

    def upsert_provisional_entity(
        self,
        entity_type: str,
        entity_id: str,
        properties: Dict[str, Any],
    ) -> None:
        label = self._safe_label(entity_type)
        id_prop = self._id_prop(label)
        props = dict(properties)
        props["id"] = entity_id
        props[id_prop] = entity_id
        query = f"""
        MERGE (n:{label} {{{id_prop}: $entity_id}})
        ON CREATE SET n.created_at = datetime()
        SET n += $props,
            n.updated_at = datetime()
        """
        self.run_write(query, entity_id=entity_id, props=props)

    def upsert_topic_relationships(
        self,
        entity_type: str,
        entity_id: str,
        topic_ids: List[str],
    ) -> None:
        label = self._safe_label(entity_type)
        id_prop = self._id_prop(label)
        relations = {
            # Keep INTERESTED_IN for the user-facing profile meaning, and add
            # HAS_EXPERIENCE_IN because the current PGPR Expert -> Project
            # candidate query relies on this schema edge.
            "Expert": ["INTERESTED_IN", "HAS_EXPERIENCE_IN"],
            "Enterprise": ["FOCUSES_ON_TOPIC"],
            "Funder": ["SUPPORTS_TOPIC"],
            "Project": ["FOCUSES_ON_TOPIC"],
        }.get(label, ["RELATED_TO"])
        for topic_id in topic_ids or []:
            if not topic_id:
                continue
            topic_name = str(topic_id).replace("-", " ").title()
            for relation in relations:
                query = f"""
                MATCH (n:{label} {{{id_prop}: $entity_id}})
                MERGE (t:ResearchTopic {{topic_id: $topic_id}})
                ON CREATE SET t.created_at = datetime(),
                              t.visibility = "public",
                              t.participation_scope = "public",
                              t.trust_weight = 1.0
                SET t.name = coalesce(t.name, $topic_name),
                    t.label = coalesce(t.label, $topic_name),
                    t.updated_at = datetime()
                MERGE (n)-[r:{relation}]->(t)
                SET r.provisional_sync_version = 1,
                    r.updated_at = datetime()
                """
                self.run_write(query, entity_id=entity_id, topic_id=topic_id, topic_name=topic_name)

    def upsert_skill_relationships(self, entity_type: str, entity_id: str, skills: List[str]) -> None:
        label = self._safe_label(entity_type)
        id_prop = self._id_prop(label)
        relations = {
            "Expert": "HAS_SKILL",
            "Enterprise": "USES_SKILL",
            "Funder": "SUPPORTS_SKILL",
            "Project": "REQUIRES_SKILL",
        }
        relation = relations.get(label, "HAS_SKILL")
        for skill in skills or []:
            skill_id = str(skill).strip()
            if not skill_id:
                continue
            skill_name = skill_id.replace("-", " ").title()
            query = f"""
            MATCH (n:{label} {{{id_prop}: $entity_id}})
            MERGE (s:Skill {{skill_id: $skill_id}})
            ON CREATE SET s.created_at = datetime(),
                          s.visibility = "public",
                          s.participation_scope = "public",
                          s.trust_weight = 1.0
            SET s.name = coalesce(s.name, $skill_name),
                s.label = coalesce(s.label, $skill_name),
                s.updated_at = datetime()
            MERGE (n)-[r:{relation}]->(s)
            SET r.provisional_sync_version = 1,
                r.updated_at = datetime()
            """
            self.run_write(query, entity_id=entity_id, skill_id=skill_id, skill_name=skill_name)

    def upsert_location_relationship(self, entity_type: str, entity_id: str, location: Dict[str, Any]) -> None:
        label = self._safe_label(entity_type)
        id_prop = self._id_prop(label)
        country = str(location.get("country") or "VN").strip()
        province = str(location.get("province") or "").strip()
        district = str(location.get("district") or "").strip()
        location_id = "::".join([item for item in [country, province, district] if item])
        if not location_id:
            return
        location_name = ", ".join([item for item in [district, province, country] if item])
        query = f"""
        MATCH (n:{label} {{{id_prop}: $entity_id}})
        MERGE (l:Location {{location_id: $location_id}})
        ON CREATE SET l.created_at = datetime(),
                      l.visibility = "public",
                      l.participation_scope = "public",
                      l.trust_weight = 1.0
        SET l.name = coalesce(l.name, $location_name),
            l.country = $country,
            l.province = $province,
            l.district = $district,
            l.updated_at = datetime()
        MERGE (n)-[r:LOCATED_IN]->(l)
        SET r.provisional_sync_version = 1,
            r.updated_at = datetime()
        """
        self.run_write(
            query,
            entity_id=entity_id,
            location_id=location_id,
            location_name=location_name,
            country=country,
            province=province,
            district=district,
        )

    def update_entity_verification_status(
        self,
        entity_type: str,
        entity_id: str,
        properties: Dict[str, Any],
    ) -> None:
        label = self._safe_label(entity_type)
        id_prop = self._id_prop(label)
        self.run_write(
            f"""
            MATCH (n:{label} {{{id_prop}: $entity_id}})
            SET n += $props,
                n.updated_at = datetime()
            """,
            entity_id=entity_id,
            props=properties,
        )

    def update_entity_embedding(
        self,
        entity_type: str,
        entity_id: str,
        embedding: Dict[str, Any],
    ) -> None:
        props = {
            "embedding_status": embedding.get("status"),
            "embedding_model": embedding.get("model"),
            "embedding_version": embedding.get("version"),
            "embedding_dimension": embedding.get("dimension"),
            "embedding_source_hash": embedding.get("source_hash"),
            "embedding_signal": embedding.get("signal"),
            "embedding_updated_at": str(embedding.get("updated_at")),
            "embedding_vector": embedding.get("vector"),
        }
        self.update_entity_verification_status(entity_type, entity_id, props)

    def disable_entity(self, entity_type: str, entity_id: str, merged_into: Optional[str] = None) -> None:
        props = {
            "kg_sync_status": "disabled",
            "visibility": "disabled",
            "participation_scope": "disabled",
            "active": False,
            "trust_weight": 0,
        }
        if merged_into:
            props["merged_into"] = merged_into
        self.update_entity_verification_status(entity_type, entity_id, props)

    @staticmethod
    def _safe_label(entity_type: str) -> str:
        mapping = {
            "expert": "Expert",
            "enterprise": "Enterprise",
            "funder": "Funder",
            "project": "Project",
            "Expert": "Expert",
            "Enterprise": "Enterprise",
            "Funder": "Funder",
            "Project": "Project",
        }
        label = mapping.get(str(entity_type))
        if not label:
            raise ValueError(f"Unsupported entity type: {entity_type}")
        return label

    @staticmethod
    def _id_prop(label: str) -> str:
        return {
            "Expert": "expert_id",
            "Enterprise": "enterprise_id",
            "Funder": "funder_id",
            "Project": "project_id",
        }[label]



    def find_reasoning_paths(
        self,
        source_id: str,
        source_type: str,
        target_id: str,
        target_type: str,
        max_path_length: int,
        limit: int,
        timeout: float = DEFAULT_QUERY_TIMEOUT,
        mode: str = "public",
        current_user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Raw path records from Neo4j (no scoring/dedup)."""
        query = f"""
            MATCH path = (source:{source_type} {{
                {source_type.lower()}_id: $source_id
            }})-[*1..{max_path_length}]-(target:{target_type} {{
                {target_type.lower()}_id: $target_id
            }})
            WITH path, relationships(path) as rels, nodes(path) as nodes
            WHERE $mode = "admin_debug"
               OR (
                    none(n IN nodes WHERE coalesce(n.participation_scope, "public") = "disabled"
                         OR coalesce(n.visibility, "public") IN ["hidden", "disabled"]
                         OR coalesce(n.entity_verification_status, "verified") = "rejected")
                    AND all(n IN nodes[1..(size(nodes)-1)] WHERE coalesce(n.allow_as_intermediate_node, true) = true)
                    AND (
                        $mode <> "public"
                        OR all(n IN nodes WHERE coalesce(n.participation_scope, "public") <> "owner_only")
                    )
                    AND (
                        $mode <> "personal"
                        OR all(n IN nodes WHERE coalesce(n.participation_scope, "public") <> "owner_only"
                             OR coalesce(n.user_id, n.owner_user_id, "") = coalesce($current_user_id, ""))
                    )
               )
            RETURN path,
                   [r in rels | type(r)] as relation_types,
                   [n in nodes | labels(n)[0]] as node_types,
                   [n in nodes | coalesce(
                       n.name, n.title, n.label,
                       n.project_id, n.expert_id, n.funder_id, n.enterprise_id,
                       n.topic_id, n.direction_id, n.field_id, n.industry_id,
                       n.location_id, elementId(n)
                   )] as entity_names,
                   length(path) as path_length
            LIMIT {limit}
        """
        return self.run_read(
            query,
            source_id=source_id,
            target_id=target_id,
            timeout=timeout,
            mode=mode,
            current_user_id=current_user_id,
        )

    def find_entity_neighbors(
        self,
        entity_type: str,
        entity_id: str,
        depth: int = 1,
        limit: int = 80,
        timeout: float = DEFAULT_QUERY_TIMEOUT,
        mode: str = "public",
        current_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return a bounded ego graph around an entity for frontend visualization."""
        label = str(entity_type)
        if label not in {"Project", "Expert", "Funder", "Enterprise"}:
            raise ValueError(f"Unsupported entity type: {entity_type}")

        id_prop = f"{label.lower()}_id"
        depth = int(max(1, min(depth, 3)))
        limit = int(max(1, min(limit, 200)))

        query = f"""
        MATCH (source:{label} {{{id_prop}: $entity_id}})
        MATCH path = (source)-[*1..{depth}]-(neighbor)
        WITH source, path, nodes(path) AS ns, relationships(path) AS rs
        WITH collect(path)[0..{limit}] AS paths
        UNWIND paths AS p
        WITH collect(DISTINCT nodes(p)) AS node_groups, collect(DISTINCT relationships(p)) AS rel_groups
        WITH
          reduce(nodes_acc = [], group IN node_groups | nodes_acc + group) AS all_nodes,
          reduce(rels_acc = [], group IN rel_groups | rels_acc + group) AS all_rels
        UNWIND all_nodes AS n
        WITH collect(DISTINCT n) AS raw_nodes, all_rels
        WITH [n IN raw_nodes WHERE
          $mode = "admin_debug"
          OR (
            NOT coalesce(n.visibility, "public") IN ["hidden", "disabled"]
            AND coalesce(n.participation_scope, "public") <> "disabled"
            AND coalesce(n.entity_verification_status, "verified") <> "rejected"
            AND (
              $mode <> "public"
              OR coalesce(n.participation_scope, "public") <> "owner_only"
            )
            AND (
              $mode <> "personal"
              OR coalesce(n.participation_scope, "public") <> "owner_only"
              OR coalesce(n.user_id, n.owner_user_id, "") = coalesce($current_user_id, "")
            )
          )
        ] AS nodes, all_rels
        UNWIND all_rels AS r
        WITH nodes, collect(DISTINCT r) AS raw_rels
        WITH nodes, [r IN raw_rels WHERE startNode(r) IN nodes AND endNode(r) IN nodes] AS rels
        RETURN
          [n IN nodes | {{
            id: coalesce(
              n.project_id, n.expert_id, n.funder_id, n.enterprise_id,
              n.topic_id, n.direction_id, n.industry_id,
              n.location_id, n.dataset_id, n.product_id,
              elementId(n)
            ),
            label: coalesce(
              n.name, n.title, n.label,
              n.project_id, n.expert_id, n.funder_id, n.enterprise_id,
              n.topic_id, n.direction_id, n.industry_id,
              n.location_id, elementId(n)
            ),
            type: labels(n)[0],
            properties: properties(n)
          }}] AS nodes,
          [r IN rels | {{
            id: elementId(r),
            source: coalesce(
              startNode(r).project_id, startNode(r).expert_id, startNode(r).funder_id, startNode(r).enterprise_id,
              startNode(r).topic_id, startNode(r).direction_id, startNode(r).industry_id,
              startNode(r).location_id, startNode(r).dataset_id, startNode(r).product_id,
              elementId(startNode(r))
            ),
            target: coalesce(
              endNode(r).project_id, endNode(r).expert_id, endNode(r).funder_id, endNode(r).enterprise_id,
              endNode(r).topic_id, endNode(r).direction_id, endNode(r).industry_id,
              endNode(r).location_id, endNode(r).dataset_id, endNode(r).product_id,
              elementId(endNode(r))
            ),
            type: type(r)
          }}] AS edges
        """
        rows = self.run_read(
            query,
            entity_id=entity_id,
            timeout=timeout,
            mode=mode,
            current_user_id=current_user_id,
        )
        if not rows:
            return {"nodes": [], "edges": []}
        return {
            "nodes": rows[0].get("nodes") or [],
            "edges": rows[0].get("edges") or [],
        }

    def get_entity_status(self, entity_type: str, entity_id: str) -> Dict[str, Any]:
        label = self._safe_label(entity_type)
        id_prop = self._id_prop(label)
        rows = self.run_read(
            f"""
            MATCH (n:{label} {{{id_prop}: $entity_id}})
            RETURN n.trust_weight AS trust_weight,
                   n.entity_verification_status AS entity_verification_status,
                   n.kg_sync_status AS kg_sync_status,
                   n.visibility AS visibility,
                   n.participation_scope AS participation_scope,
                   n.allow_as_source AS allow_as_source,
                   n.recommendable_as_target AS recommendable_as_target,
                   n.allow_as_intermediate_node AS allow_as_intermediate_node,
                   coalesce(n.user_id, n.owner_user_id, "") AS owner_user_id
            LIMIT 1
            """,
            entity_id=entity_id,
        )
        return dict(rows[0]) if rows else {}

    def get_expert_participant_ids(self, project_id: str) -> List[str]:
        rows = self.run_read(
            "MATCH (e:Expert)-[:PARTICIPATES_IN]->(p:Project {project_id: $pid}) "
            "RETURN e.expert_id as eid",
            pid=project_id,
        )
        return [r["eid"] for r in rows if r.get("eid")]

    def get_exclude_target_ids(
        self, source_id: str, source_type: str, target_type: str
    ) -> List[str]:
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
        rows = self.run_read(queries[task_name], sid=source_id)
        return [r["tid"] for r in rows if r.get("tid")]


    def find_all_reachable_experts_batch(self, project_id: str,
        max_depth: int = 12,
    ) -> List[Dict[str, Any]]:
        """
        IMPROVED: Batch query to find all reachable experts with min path length.
        
        Single query instead of multiple queries at each depth level.
        """
        try:
            # Schema v2: Project -> ResearchTopic/ResearchDirection,
            # Expert -> ResearchTopic via HAS_EXPERIENCE_IN, Expert -> ResearchDirection via RESEARCHES.
            out = self.run_read(
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
                timeout=PGPRGraphRepository.DEFAULT_QUERY_TIMEOUT,
            )

            # If the graph doesn't follow the expected schema,
            # fall back to a generic traversal (more robust across datasets).
            if out:
                return out
            return self.find_candidate_experts_generic(project_id, max_depth=max_depth)

        except Exception as e:
            logger.warning(f"Error in batch candidate query: {e}")
            return self.find_candidate_experts_generic(project_id, max_depth=max_depth)


    def find_candidate_experts_simple(self, project_id: str
    ) -> List[Dict[str, Any]]:
        """Fallback: Simple candidate query without depth calculation."""
        result = self.run_read(
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
            timeout=PGPRGraphRepository.DEFAULT_QUERY_TIMEOUT,
        )
        
        return result


    def find_candidate_experts_generic(self, project_id: str,
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
        result = self.run_read(query, project_id=project_id, timeout=PGPRGraphRepository.DEFAULT_QUERY_TIMEOUT)
        return result


    def get_expert_info(self, expert_id: str,
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
        result = self.run_read(
            query,
            expert_id=expert_id,
            exclude_project_id=exclude_project_id,
        )
        records = list(result)
        return dict(records[0]) if records else None
    
    # ==========================================
    # PROJECT & FUNDER RECOMMENDATIONS (similar improvements)
    # ==========================================


    def get_generic_entity_info(self, entity_id: str, entity_type: str) -> Dict[str, Any]:
        """Tự động query lấy thông tin của bất kỳ Node nào (kèm theo Location nếu có)."""
        id_prop = f"{entity_type.lower()}_id"
        query = f"""
        MATCH (n:{entity_type} {{{id_prop}: $eid}})
        OPTIONAL MATCH (n)-[:LOCATED_IN]->(l:Location)
        RETURN properties(n) AS props, l.location_id AS location
        """
        res = list(self.run_read(query, eid=entity_id))
        if not res:
            return {}
        info = res[0]["props"] or {}
        info["location"] = res[0].get("location")
        return info

    def resolve_entity_path_nodes(self, entity_keys: List[str]) -> List[Dict[str, Any]]:
        """
        Resolve PGPR vocab keys like "Project::prj_001" into displayable path nodes.
        This is used by recommendation output so XAI/reasoning paths can show
        actual node names instead of only relationship names.
        """
        label_props = {
            "Project": (["project_id"], ["title", "name", "project_id"]),
            "Expert": (["expert_id"], ["name", "expert_id"]),
            "Funder": (["funder_id"], ["name", "funder_id"]),
            "Enterprise": (["enterprise_id"], ["name", "enterprise_id"]),
            "ResearchTopic": (["topic_id"], ["name", "label", "topic_id"]),
            "ResearchDirection": (["direction_id"], ["name", "direction_id"]),
            "Industry": (["industry_id"], ["name", "label", "industry_id"]),
            "Location": (["location_id"], ["name", "label", "location_id"]),
            "Dataset": (["dataset_id"], ["name", "title", "label", "dataset_id"]),
            "Product": (["product_id"], ["name", "title", "label", "product_id"]),
            "Skill": (["skill_id"], ["name", "label", "skill_id"]),
        }
        resolved: List[Dict[str, Any]] = []
        for key in entity_keys or []:
            if "::" not in str(key):
                resolved.append({"id": str(key), "type": "Node", "name": str(key)})
                continue

            label, entity_id = str(key).split("::", 1)
            if not label.replace("_", "").isalnum() or label not in label_props:
                resolved.append({"id": entity_id, "type": label, "name": entity_id})
                continue

            id_props, name_props = label_props[label]
            id_expr = "coalesce(" + ", ".join(f"n.{prop}" for prop in id_props) + ")"
            name_expr = "coalesce(" + ", ".join([f"n.{prop}" for prop in name_props] + ["$entity_id"]) + ")"
            query = f"""
            MATCH (n:{label})
            WHERE {id_expr} = $entity_id
            RETURN {name_expr} AS name
            LIMIT 1
            """
            rows = self.run_read(query, entity_id=entity_id)
            name = rows[0].get("name") if rows else entity_id
            resolved.append({"id": entity_id, "type": label, "name": name or entity_id})
        return resolved


    def find_candidate_projects(self, expert_id: str,
        status_filter: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Find candidate projects.

        NOTE (schema v2):
        - Neo4j uses ResearchTopic/ResearchDirection (NOT ResearchField).
        - Expert connects to topics via HAS_EXPERIENCE_IN and to directions via RESEARCHES.
        - Project connects to topics via FOCUSES_ON_TOPIC and to directions via FOCUSES_ON.
        """
        result = self.run_read(
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
                   $expert_id as source_id,
                   "Expert" as source_type,
                   "Project" as target_type,
                   t.topic_id as evidence_id,
                   coalesce(t.name, t.label, t.topic_id) as evidence_name,
                   "ResearchTopic" as evidence_type,
                   ["HAS_EXPERIENCE_IN", "FOCUSES_ON_TOPIC"] as path_relations,
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
                   $expert_id as source_id,
                   "Expert" as source_type,
                   "Project" as target_type,
                   d.direction_id as evidence_id,
                   coalesce(d.name, d.direction_id) as evidence_name,
                   "ResearchDirection" as evidence_type,
                   ["RESEARCHES", "FOCUSES_ON"] as path_relations,
                   3 as rank_hint
            LIMIT 120
            """,
            expert_id=expert_id,
            status_filter=status_filter,
            timeout=PGPRGraphRepository.DEFAULT_QUERY_TIMEOUT,
        )
        
        return result


    def find_candidate_projects_by_shared_funder(self, expert_id: str,
        status_filter: List[str],
        limit: int = 80,
    ) -> List[Dict[str, Any]]:
        """
        Candidate projects based on shared funder with expert's participated projects.
        
        Pattern:
          (Expert)-[:PARTICIPATES_IN]->(p0:Project)<-[:FUNDS]-(f:Funder)-[:FUNDS]->(p:Project)
        """
        try:
            result = self.run_read(
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
                timeout=PGPRGraphRepository.DEFAULT_QUERY_TIMEOUT,
            )
            return result
        except Exception as e:
            logger.debug(f"Shared-funder candidate query failed: {e}")
            return []


    def find_candidate_funders(self, project_id: str
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
            result = self.run_read(
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
                timeout=PGPRGraphRepository.DEFAULT_QUERY_TIMEOUT,
            )
            for record in result:
                d = dict(record)
                d["candidate_sources"] = ["supports_field"]
                by_id[d["funder_id"]] = d
        except Exception as e:
            logger.debug("Candidate funders (SUPPORTS) query failed: %s", e)
        
        # Source 2: Funders that FUNDS other projects sharing topic/direction (portfolio-based)
        try:
            result2 = self.run_read(
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
                timeout=PGPRGraphRepository.DEFAULT_QUERY_TIMEOUT,
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


    def find_candidate_enterprises_for_project(self, project_id: str,
        limit: int = 80,
    ) -> List[Dict[str, Any]]:
        """
        Candidate enterprises: PARTNERS_WITH projects in same/related field;
        or OPERATES_IN industry linked via experts in project.
        """
        by_id: Dict[str, Dict[str, Any]] = {}
        try:
            result = self.run_read(
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
                timeout=PGPRGraphRepository.DEFAULT_QUERY_TIMEOUT,
            )
            for record in result:
                d = dict(record)
                d["candidate_sources"] = ["related_partner_projects"]
                by_id[d["enterprise_id"]] = d
        except Exception as e:
            logger.debug("Candidate enterprises for project query failed: %s", e)
        try:
            result2 = self.run_read(
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
                timeout=PGPRGraphRepository.DEFAULT_QUERY_TIMEOUT,
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


    def find_candidate_projects_for_project(self, project_id: str,
        status_filter: List[str],
        limit: int = 80,
    ) -> List[Dict[str, Any]]:
        """Similar projects: same/related field; same funder; shared experts."""
        by_id: Dict[str, Dict[str, Any]] = {}
        try:
            result = self.run_read(
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
                timeout=PGPRGraphRepository.DEFAULT_QUERY_TIMEOUT,
            )
            for record in result:
                d = dict(record)
                d["candidate_sources"] = ["same_field"]
                by_id[d["project_id"]] = d
        except Exception as e:
            logger.debug("Candidate projects for project (field) failed: %s", e)
        try:
            result2 = self.run_read(
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
                timeout=PGPRGraphRepository.DEFAULT_QUERY_TIMEOUT,
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


    def find_candidate_funders_for_expert(self, expert_id: str,
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
            result = self.run_read(
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
                timeout=PGPRGraphRepository.DEFAULT_QUERY_TIMEOUT,
            )
            for record in result:
                d = dict(record)
                d["candidate_sources"] = ["expert_projects"]
                by_id[d["funder_id"]] = d
        except Exception as e:
            logger.debug("Candidate funders for expert (projects) query failed: %s", e)

        # Source 2: funders SUPPORT các lĩnh vực mà expert có chuyên môn
        try:
            result2 = self.run_read(
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
                timeout=PGPRGraphRepository.DEFAULT_QUERY_TIMEOUT,
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


    def find_candidate_enterprises_for_expert(self, expert_id: str,
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
            result = self.run_read(
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
                timeout=PGPRGraphRepository.DEFAULT_QUERY_TIMEOUT,
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
            result2 = self.run_read(
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
                timeout=PGPRGraphRepository.DEFAULT_QUERY_TIMEOUT,
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


    def find_candidate_experts_for_expert(self, expert_id: str,
        limit: int = 80,
    ) -> List[Dict[str, Any]]:
        """
        Candidate experts for collaboration: same HAS_EXPERTISE_IN field (incl. hierarchy);
        same PARTICIPATES_IN project; same HAS_SKILL MethodTechnique.
        """
        by_id: Dict[str, Dict[str, Any]] = {}
        try:
            result = self.run_read(
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
                timeout=PGPRGraphRepository.DEFAULT_QUERY_TIMEOUT,
            )
            for record in result:
                d = dict(record)
                d["candidate_sources"] = ["same_field"]
                by_id[d["expert_id"]] = d
        except Exception as e:
            logger.debug("Candidate experts for expert (field) query failed: %s", e)
        try:
            result2 = self.run_read(
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
                timeout=PGPRGraphRepository.DEFAULT_QUERY_TIMEOUT,
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


    def find_candidate_experts_for_enterprise(self, enterprise_id: str,
        limit: int = 80,
    ) -> List[Dict[str, Any]]:
        """Experts: có HAS_APPLICATION_EXPERIENCE_IN industry mà enterprise OPERATES_IN; hoặc PARTICIPATES_IN project PARTNERS_WITH enterprise."""
        by_id: Dict[str, Dict[str, Any]] = {}

        try:
            result = self.run_read(
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
                timeout=PGPRGraphRepository.DEFAULT_QUERY_TIMEOUT,
            )
            for record in result:
                d = dict(record)
                d["candidate_sources"] = ["industry_match"]
                by_id[d["expert_id"]] = d
        except Exception as e:
            logger.debug("Candidate experts for enterprise (industry) query failed: %s", e)

        try:
            result2 = self.run_read(
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
                timeout=PGPRGraphRepository.DEFAULT_QUERY_TIMEOUT,
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


    def find_candidate_projects_for_enterprise(self, enterprise_id: str,
        status_filter: List[str],
        limit: int = 80,
    ) -> List[Dict[str, Any]]:
        """Projects: cùng industry (BELONGS_TO field -> Industry?) hoặc liên quan project đã PARTNERS_WITH enterprise. KG có thể Project-BELONGS_TO-ResearchField; Enterprise-OPERATES_IN-Industry. Nếu không có link Field-Industry, dùng project đã partner làm nguồn."""
        by_id: Dict[str, Dict[str, Any]] = {}

        try:
            result = self.run_read(
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
                timeout=PGPRGraphRepository.DEFAULT_QUERY_TIMEOUT,
            )
            for record in result:
                d = dict(record)
                d["candidate_sources"] = ["related_partner_projects"]
                by_id[d["project_id"]] = d
        except Exception as e:
            logger.debug("Candidate projects for enterprise query failed: %s", e)

        return list(by_id.values())


    def find_candidate_funders_for_enterprise(self, enterprise_id: str,
        limit: int = 80,
    ) -> List[Dict[str, Any]]:
        """Funders: FUNDS projects that enterprise PARTNERS_WITH; or SUPPORTS field of those projects."""
        by_id: Dict[str, Dict[str, Any]] = {}
        try:
            result = self.run_read(
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
                timeout=PGPRGraphRepository.DEFAULT_QUERY_TIMEOUT,
            )
            for record in result:
                d = dict(record)
                d["candidate_sources"] = ["partner_project_funders"]
                by_id[d["funder_id"]] = d
        except Exception as e:
            logger.debug("Candidate funders for enterprise query failed: %s", e)
        try:
            result2 = self.run_read(
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
                timeout=PGPRGraphRepository.DEFAULT_QUERY_TIMEOUT,
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


    def find_candidate_enterprises_for_enterprise(self, enterprise_id: str,
        limit: int = 80,
    ) -> List[Dict[str, Any]]:
        """Other enterprises: same OPERATES_IN industry; or PARTNERS_WITH same project; or partner projects in same field."""
        by_id: Dict[str, Dict[str, Any]] = {}
        try:
            result = self.run_read(
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
                timeout=PGPRGraphRepository.DEFAULT_QUERY_TIMEOUT,
            )
            for record in result:
                d = dict(record)
                d["candidate_sources"] = ["same_industry"]
                by_id[d["enterprise_id"]] = d
        except Exception as e:
            logger.debug("Candidate enterprises for enterprise (industry) failed: %s", e)
        try:
            result2 = self.run_read(
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
                timeout=PGPRGraphRepository.DEFAULT_QUERY_TIMEOUT,
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


    def find_candidate_experts_for_funder(self, funder_id: str,
        limit: int = 80,
    ) -> List[Dict[str, Any]]:
        """Experts: PARTICIPATES_IN project FUNDS by funder; hoặc HAS_EXPERTISE_IN field SUPPORTED by funder."""
        by_id: Dict[str, Dict[str, Any]] = {}

        try:
            result = self.run_read(
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
                timeout=PGPRGraphRepository.DEFAULT_QUERY_TIMEOUT,
            )
            for record in result:
                d = dict(record)
                d["candidate_sources"] = ["funded_projects"]
                by_id[d["expert_id"]] = d
        except Exception as e:
            logger.debug("Candidate experts for funder (funded projects) query failed: %s", e)

        try:
            result2 = self.run_read(
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
                timeout=PGPRGraphRepository.DEFAULT_QUERY_TIMEOUT,
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


    def find_candidate_projects_for_funder(self, funder_id: str,
        status_filter: List[str],
        limit: int = 80,
    ) -> List[Dict[str, Any]]:
        """Projects: trong field funder SUPPORT; hoặc cùng field với project funder đã FUNDS (chưa tài trợ dự án này)."""
        by_id: Dict[str, Dict[str, Any]] = {}

        try:
            result = self.run_read(
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
                timeout=PGPRGraphRepository.DEFAULT_QUERY_TIMEOUT,
            )
            for record in result:
                d = dict(record)
                d["candidate_sources"] = ["supports_field"]
                by_id[d["project_id"]] = d
        except Exception as e:
            logger.debug("Candidate projects for funder (supports) query failed: %s", e)

        try:
            result2 = self.run_read(
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
                timeout=PGPRGraphRepository.DEFAULT_QUERY_TIMEOUT,
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


    def find_candidate_enterprises_for_funder(self, funder_id: str,
        limit: int = 80,
    ) -> List[Dict[str, Any]]:
        """Enterprises: PARTNERS_WITH projects that funder FUNDS; or projects in field funder SUPPORTS."""
        by_id: Dict[str, Dict[str, Any]] = {}
        try:
            result = self.run_read(
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
                timeout=PGPRGraphRepository.DEFAULT_QUERY_TIMEOUT,
            )
            for record in result:
                d = dict(record)
                d["candidate_sources"] = ["funded_project_partners"]
                by_id[d["enterprise_id"]] = d
        except Exception as e:
            logger.debug("Candidate enterprises for funder query failed: %s", e)
        try:
            result2 = self.run_read(
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
                timeout=PGPRGraphRepository.DEFAULT_QUERY_TIMEOUT,
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

