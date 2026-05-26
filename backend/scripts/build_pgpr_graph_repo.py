"""
One-off helper: extract Neo4j query methods from pgpr_recommendation.py into pgpr_graph_repo.py.
Run from backend/: python scripts/build_pgpr_graph_repo.py
"""
from __future__ import annotations

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
SRC = BACKEND / "pgpr" / "pgpr_recommendation.py"
OUT = BACKEND / "repositories" / "pgpr_graph_repo.py"

METHODS = [
    "find_reasoning_paths_raw",
    "_find_all_reachable_experts_batch",
    "_find_candidate_experts_simple",
    "_find_candidate_experts_generic",
    "_get_expert_info",
    "_get_generic_entity_info",
    "_find_candidate_projects",
    "_find_candidate_projects_by_shared_funder",
    "_find_candidate_funders",
    "_find_candidate_enterprises_for_project",
    "_find_candidate_projects_for_project",
    "_find_candidate_funders_for_expert",
    "_find_candidate_enterprises_for_expert",
    "_find_candidate_experts_for_expert",
    "_find_candidate_experts_for_enterprise",
    "_find_candidate_projects_for_enterprise",
    "_find_candidate_funders_for_enterprise",
    "_find_candidate_enterprises_for_enterprise",
    "_find_candidate_experts_for_funder",
    "_find_candidate_projects_for_funder",
    "_find_candidate_enterprises_for_funder",
]

HEADER = '''"""
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

'''


def extract_method(source: str, name: str) -> str:
    pattern = rf"(\n    def {re.escape(name)}\([^)]*\)[^:]*:)"
    m = re.search(pattern, source)
    if not m:
        raise ValueError(f"Method not found: {name}")
    start = m.start() + 1
    # find next method at same indent
    rest = source[start:]
    nxt = re.search(r"\n    def [a-zA-Z_]", rest[10:])
    body = rest[: nxt.start() + 10] if nxt else rest
    return body.rstrip()


def transform_method(body: str, old_name: str, new_name: str) -> str:
    body = body.replace(f"def {old_name}", f"def {new_name}", 1)
    # drop session parameter
    body = re.sub(r"\(\s*self,\s*session,\s*", "(self, ", body)
    body = re.sub(r"\(\s*self,\s*session\)", "(self)", body)
    body = body.replace("session.run(", "self.run_read(")
    body = body.replace("self.DEFAULT_QUERY_TIMEOUT", "PGPRGraphRepository.DEFAULT_QUERY_TIMEOUT")
    # list(result) where result is from run_read already returns list
    body = re.sub(
        r"result = self\.run_read\(([^)]+(?:\([^)]*\)[^)]*)*)\)\s*\n\s*out = \[dict\(record\) for record in result\]",
        r"out = self.run_read(\1)",
        body,
    )
    body = re.sub(
        r"return \[dict\(record\) for record in result\]",
        r"return result",
        body,
    )
    body = re.sub(
        r"for record in result:",
        r"for record in self.run_read(",
        body,
        count=0,
    )
    return body


def main() -> None:
    source = SRC.read_text(encoding="utf-8")
    parts = [HEADER]

    # find_reasoning_paths: extract query block manually
    parts.append(
        '''
    def find_reasoning_paths(
        self,
        source_id: str,
        source_type: str,
        target_id: str,
        target_type: str,
        max_path_length: int,
        limit: int,
        timeout: float = DEFAULT_QUERY_TIMEOUT,
    ) -> List[Dict[str, Any]]:
        """Raw path records from Neo4j (no scoring/dedup)."""
        query = f"""
            MATCH path = (source:{source_type} {{
                {source_type.lower()}_id: $source_id
            }})-[*1..{max_path_length}]-(target:{target_type} {{
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
            LIMIT {limit}
        """
        return self.run_read(
            query,
            source_id=source_id,
            target_id=target_id,
            timeout=timeout,
        )

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

'''
    )

    rename_map = {
        "_get_expert_info": "get_expert_info",
        "_get_generic_entity_info": "get_generic_entity_info",
    }

    for name in METHODS:
        if name == "find_reasoning_paths_raw":
            continue
        if name not in [m for m in METHODS if not m.startswith("find_reasoning")]:
            pass
        try:
            body = extract_method(source, name)
        except ValueError:
            print(f"SKIP {name}")
            continue
        new_name = rename_map.get(name, name.lstrip("_"))
        parts.append(transform_method(body, name, new_name))
        parts.append("\n")

    OUT.write_text("\n".join(parts), encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
