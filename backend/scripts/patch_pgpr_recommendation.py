"""Patch pgpr_recommendation.py to use PGPRGraphRepository."""
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
PATH = BACKEND / "pgpr" / "pgpr_recommendation.py"

REPLACEMENTS = [
    (
        "from neo4j import GraphDatabase\nfrom typing import",
        "from typing import",
    ),
    (
        """# Neo4j connection
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

# Module-level shared driver (safe to reuse across recommender instances).
# IMPORTANT: Do not close this driver inside PGPRRecommender.close(), otherwise
# subsequent requests will fail with "neo4j.exceptions.DriverError: Driver closed".
_shared_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


""",
        "",
    ),
    (
        """        enable_cache: bool = True,
        driver: Optional[Any] = None,
    ):
        # Use provided driver if any; otherwise reuse module shared driver.
        # The recommender does NOT own the shared driver.
        self.driver = driver or _shared_driver
        self._owns_driver = driver is not None and driver is not _shared_driver
""",
        """        enable_cache: bool = True,
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
""",
    ),
    (
        """        if getattr(self, "_owns_driver", False):
            self.driver.close()
""",
        """        if getattr(self, "_owns_driver", False):
            self.graph_repo.close()
""",
    ),
]

SESSION_CALLS = [
    ("_find_candidate_projects(session, expert_id", "find_candidate_projects(expert_id"),
    ("_find_candidate_projects_by_shared_funder(\n                    session, expert_id", "find_candidate_projects_by_shared_funder(expert_id"),
    ("_find_candidate_funders_for_expert(session, expert_id", "find_candidate_funders_for_expert(expert_id"),
    ("_find_candidate_enterprises_for_expert(session, expert_id", "find_candidate_enterprises_for_expert(expert_id"),
    ("_find_candidate_experts_for_expert(session, expert_id", "find_candidate_experts_for_expert(expert_id"),
    ("_find_candidate_funders(session, project_id", "find_candidate_funders(project_id"),
    ("_find_candidate_enterprises_for_project(session, project_id", "find_candidate_enterprises_for_project(project_id"),
    ("_find_candidate_projects_for_project(\n                session, project_id", "find_candidate_projects_for_project(project_id"),
    ("_find_candidate_experts_for_enterprise(session, enterprise_id", "find_candidate_experts_for_enterprise(enterprise_id"),
    ("_find_candidate_projects_for_enterprise(\n                session, enterprise_id", "find_candidate_projects_for_enterprise(enterprise_id"),
    ("_find_candidate_funders_for_enterprise(session, enterprise_id", "find_candidate_funders_for_enterprise(enterprise_id"),
    ("_find_candidate_enterprises_for_enterprise(session, enterprise_id", "find_candidate_enterprises_for_enterprise(enterprise_id"),
    ("_find_candidate_experts_for_funder(session, funder_id", "find_candidate_experts_for_funder(funder_id"),
    ("_find_candidate_projects_for_funder(\n                session, funder_id", "find_candidate_projects_for_funder(funder_id"),
    ("_find_candidate_enterprises_for_funder(session, funder_id", "find_candidate_enterprises_for_funder(funder_id"),
    ("_find_all_reachable_experts_batch(\n                session, project_id", "find_all_reachable_experts_batch(project_id"),
    ("self._get_expert_info(\n                        session,\n                        expert_id", "self.graph_repo.get_expert_info(expert_id"),
    ("self._get_generic_entity_info(session, t_id, target_type)", "self.graph_repo.get_generic_entity_info(t_id, target_type)"),
]


def remove_query_methods(text: str) -> str:
    start = text.find("    def _find_all_reachable_experts_batch(")
    end = text.find("    # ==========================================\n    # EXPLAINABILITY HELPERS")
    if start == -1 or end == -1:
        raise ValueError("Could not find method block boundaries")
    return text[:start] + text[end:]


def patch_find_reasoning_paths(text: str) -> str:
    old = """        # Find paths with timeout protection
        try:
            with self.driver.session() as session:
                # Use transaction timeout; extract entity names for readable paths
                result = session.run(f\"\"\"
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
                \"\"\", source_id=source_id, target_id=target_id, timeout=timeout)
                
                records = list(result)
        except Exception as e:
            logger.warning(f"Error finding paths {source_id} -> {target_id}: {e}")
            return []
        
        # Score and process paths
        paths = []
        for record in records:"""

    new = """        try:
            records = self.graph_repo.find_reasoning_paths(
                source_id=source_id,
                source_type=source_type,
                target_id=target_id,
                target_type=target_type,
                max_path_length=effective_max_length,
                limit=self.top_k_paths * 2,
                timeout=timeout,
            )
        except Exception as e:
            logger.warning(f"Error finding paths {source_id} -> {target_id}: {e}")
            return []

        paths = []
        for record in records:"""
    if old not in text:
        raise ValueError("find_reasoning_paths block not found")
    return text.replace(old, new, 1)


def patch_exclude_keys(text: str) -> str:
    old = """        task_name = f"{source_type}_{target_type}"
        if task_name not in queries:
            return []
            
        with self.driver.session() as session:
            res = session.run(queries[task_name], sid=source_id)
            return [f"{target_type}::{record['tid']}" for record in res]"""
    new = """        ids = self.graph_repo.get_exclude_target_ids(source_id, source_type, target_type)
        return [f"{target_type}::{tid}" for tid in ids]"""
    # remove queries dict - need bigger replacement
    start = text.find("    def _get_exclude_keys(")
    end = text.find("    def _generic_recommend_with_policy(")
    block = text[start:end]
    new_block = '''    def _get_exclude_keys(self, source_id: str, source_type: str, target_type: str) -> List[str]:
        """Tự động cắm biển cấm dựa trên cặp quan hệ Ground Truth"""
        ids = self.graph_repo.get_exclude_target_ids(source_id, source_type, target_type)
        return [f"{target_type}::{tid}" for tid in ids]

'''
    return text[:start] + new_block + text[end:]


def patch_policy_recommend(text: str) -> str:
    text = text.replace(
        """        exclude_keys = []
        with self.driver.session() as session:
            res = session.run(
                "MATCH (e:Expert)-[:PARTICIPATES_IN]->(p:Project {project_id: $pid}) "
                "RETURN e.expert_id as eid",
                pid=project_id,
            )
            exclude_keys = [f"Expert::{record['eid']}" for record in res]
""",
        """        exclude_keys = [
            f"Expert::{eid}" for eid in self.graph_repo.get_expert_participant_ids(project_id)
        ]
""",
    )
    text = text.replace(
        """            recommendations = []
            with self.driver.session() as session:
                for item in policy_paths[:limit * 2]:
                    target_key = item["target_entity_key"]
                    if "::" not in target_key:
                        continue
                    _, expert_id = target_key.split("::", 1)
                    expert_info = self._get_expert_info(
                        expert_id,
                        exclude_project_id=project_id,
                    )
""",
        """            recommendations = []
            for item in policy_paths[:limit * 2]:
                target_key = item["target_entity_key"]
                if "::" not in target_key:
                    continue
                _, expert_id = target_key.split("::", 1)
                expert_info = self.graph_repo.get_expert_info(
                    expert_id,
                    exclude_project_id=project_id,
                )
""",
    )
    text = text.replace(
        """        recommendations = []
        with self.driver.session() as session:
            for item in policy_paths[:limit * 2]:
                target_key = item["target_entity_key"]
                if "::" not in target_key:
                    continue
                _, t_id = target_key.split("::", 1)

                # Lấy info tự động
                info = self.graph_repo.get_generic_entity_info(t_id, target_type)
""",
        """        recommendations = []
        for item in policy_paths[:limit * 2]:
            target_key = item["target_entity_key"]
            if "::" not in target_key:
                continue
            _, t_id = target_key.split("::", 1)

            info = self.graph_repo.get_generic_entity_info(t_id, target_type)
""",
    )
    return text


def strip_session_blocks(text: str) -> str:
    import re

    text = re.sub(
        r"        with self\.driver\.session\(\) as session:\n            ",
        "        ",
        text,
    )
    text = re.sub(
        r"        with self\.driver\.session\(\) as session:\n                ",
        "            ",
        text,
    )
    for old, new in SESSION_CALLS:
        text = text.replace(f"self.{old}", f"self.graph_repo.{new}")
    text = text.replace("self.self.graph_repo.", "self.graph_repo.")
    return text


def main() -> None:
    text = PATH.read_text(encoding="utf-8")
    for a, b in REPLACEMENTS:
        if a not in text:
            raise ValueError(f"Missing pattern: {a[:60]}...")
        text = text.replace(a, b, 1)
    text = patch_find_reasoning_paths(text)
    text = remove_query_methods(text)
    text = patch_exclude_keys(text)
    text = patch_policy_recommend(text)
    text = strip_session_blocks(text)
    PATH.write_text(text, encoding="utf-8")
    print("patched", PATH)


if __name__ == "__main__":
    main()
