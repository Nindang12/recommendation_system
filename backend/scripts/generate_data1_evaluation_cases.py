"""Generate evaluation cases from the current data1 Knowledge Graph.

The original evaluation_cases.json uses small seed IDs. This script builds a
fresh smoke/benchmark case file from real Neo4j relationships after data1
import, while checking that source and target IDs still exist in MongoDB.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.env import load_project_env  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402
from repositories.auth_repo import AuthRepository  # noqa: E402

load_project_env()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

TASKS: list[dict[str, Any]] = [
    {
        "name": "project_to_expert",
        "source_type": "project",
        "target_type": "expert",
        "query": """
        MATCH (s:Project)-[:FOCUSES_ON]->(d:ResearchDirection)<-[:RESEARCHES]-(t:Expert)
        WHERE s.project_id IS NOT NULL AND t.expert_id IS NOT NULL
          AND NOT (t)-[:PARTICIPATES_IN]->(s)
        WITH s.project_id AS source_id, collect(DISTINCT t.expert_id)[0..3] AS relevant_ids
        WHERE size(relevant_ids) > 0
        RETURN source_id, relevant_ids
        ORDER BY source_id
        LIMIT $limit
        """,
    },
    {
        "name": "expert_to_project",
        "source_type": "expert",
        "target_type": "project",
        "query": """
        MATCH (s:Expert)-[:RESEARCHES]->(d:ResearchDirection)<-[:FOCUSES_ON]-(t:Project)
        WHERE s.expert_id IS NOT NULL AND t.project_id IS NOT NULL
          AND NOT (s)-[:PARTICIPATES_IN]->(t)
        WITH s.expert_id AS source_id, collect(DISTINCT t.project_id)[0..3] AS relevant_ids
        WHERE size(relevant_ids) > 0
        RETURN source_id, relevant_ids
        ORDER BY source_id
        LIMIT $limit
        """,
    },
    {
        "name": "project_to_funder",
        "source_type": "project",
        "target_type": "funder",
        "query": """
        MATCH (s:Project)<-[:PARTICIPATES_IN]-(:Expert)-[:PARTICIPATES_IN]->(:Project)<-[:FUNDS]-(t:Funder)
        WHERE s.project_id IS NOT NULL AND t.funder_id IS NOT NULL
          AND NOT (t)-[:FUNDS]->(s)
        WITH s.project_id AS source_id, collect(DISTINCT t.funder_id)[0..3] AS relevant_ids
        WHERE size(relevant_ids) > 0
        RETURN source_id, relevant_ids
        ORDER BY source_id
        LIMIT $limit
        """,
    },
    {
        "name": "funder_to_project",
        "source_type": "funder",
        "target_type": "project",
        "query": """
        MATCH (s:Funder)-[:FUNDS]->(:Project)<-[:PARTICIPATES_IN]-(:Expert)-[:PARTICIPATES_IN]->(t:Project)
        WHERE s.funder_id IS NOT NULL AND t.project_id IS NOT NULL
          AND NOT (s)-[:FUNDS]->(t)
        WITH s.funder_id AS source_id, collect(DISTINCT t.project_id)[0..3] AS relevant_ids
        WHERE size(relevant_ids) > 0
        RETURN source_id, relevant_ids
        ORDER BY source_id
        LIMIT $limit
        """,
    },
    {
        "name": "expert_to_expert",
        "source_type": "expert",
        "target_type": "expert",
        "query": """
        MATCH (s:Expert)-[:PARTICIPATES_IN]->(:Project)<-[:PARTICIPATES_IN]-(t:Expert)
        WHERE s.expert_id IS NOT NULL AND t.expert_id IS NOT NULL AND s.expert_id <> t.expert_id
          AND NOT (s)-[:CO_AUTHORED]-(t)
        WITH s.expert_id AS source_id, collect(DISTINCT t.expert_id)[0..3] AS relevant_ids
        WHERE size(relevant_ids) > 0
        RETURN source_id, relevant_ids
        ORDER BY source_id
        LIMIT $limit
        """,
    },
    {
        "name": "project_to_project",
        "source_type": "project",
        "target_type": "project",
        "query": """
        MATCH (s:Project)
        WHERE s.project_id IS NOT NULL
        OPTIONAL MATCH (s)<-[:FUNDS]-(:Funder)-[:FUNDS]->(tf:Project)
        WHERE tf.project_id IS NOT NULL AND tf.project_id <> s.project_id
        OPTIONAL MATCH (s)<-[:PARTICIPATES_IN]-(:Expert)-[:PARTICIPATES_IN]->(te:Project)
        WHERE te.project_id IS NOT NULL AND te.project_id <> s.project_id
        WITH s.project_id AS source_id, collect(DISTINCT tf.project_id) + collect(DISTINCT te.project_id) AS raw_ids
        WITH source_id, [x IN raw_ids WHERE x IS NOT NULL][0..3] AS relevant_ids
        WHERE size(relevant_ids) > 0
        RETURN source_id, relevant_ids
        ORDER BY source_id
        LIMIT $limit
        """,
    },
    {
        "name": "expert_to_enterprise",
        "source_type": "expert",
        "target_type": "enterprise",
        "query": """
        MATCH (s:Expert)-[:PARTICIPATES_IN]->(:Project)<-[:PARTICIPATES_IN]-(:Expert)-[:HAS_APPLICATION_EXPERIENCE_IN]->(:Industry)<-[:OPERATES_IN]-(t:Enterprise)
        WHERE s.expert_id IS NOT NULL AND t.enterprise_id IS NOT NULL
          AND NOT (s)-[:HAS_APPLICATION_EXPERIENCE_IN]->(:Industry)<-[:OPERATES_IN]-(t)
        WITH s.expert_id AS source_id, collect(DISTINCT t.enterprise_id)[0..3] AS relevant_ids
        WHERE size(relevant_ids) > 0
        RETURN source_id, relevant_ids
        ORDER BY source_id
        LIMIT $limit
        """,
    },
    {
        "name": "enterprise_to_expert",
        "source_type": "enterprise",
        "target_type": "expert",
        "query": """
        MATCH (s:Enterprise)-[:OPERATES_IN]->(:Industry)<-[:HAS_APPLICATION_EXPERIENCE_IN]-(:Expert)-[:PARTICIPATES_IN]->(:Project)<-[:PARTICIPATES_IN]-(t:Expert)
        WHERE s.enterprise_id IS NOT NULL AND t.expert_id IS NOT NULL
          AND NOT (s)-[:OPERATES_IN]->(:Industry)<-[:HAS_APPLICATION_EXPERIENCE_IN]-(t)
        WITH s.enterprise_id AS source_id, collect(DISTINCT t.expert_id)[0..3] AS relevant_ids
        WHERE size(relevant_ids) > 0
        RETURN source_id, relevant_ids
        ORDER BY source_id
        LIMIT $limit
        """,
    },
]


def _exists(repo: AuthRepository, entity_type: str, entity_id: str) -> bool:
    return repo.find_entity_by_id(entity_type, str(entity_id)) is not None


def _graded(relevant_ids: list[str]) -> dict[str, int]:
    grades = [3, 2, 1]
    return {rid: grades[idx] if idx < len(grades) else 1 for idx, rid in enumerate(relevant_ids)}


def generate(per_task: int) -> dict[str, Any]:
    repo = AuthRepository()
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    cases: list[dict[str, Any]] = []
    stats: dict[str, int] = {}
    try:
        with driver.session() as session:
            for task in TASKS:
                records = list(session.run(task["query"], limit=max(per_task * 4, per_task)))
                added = 0
                for record in records:
                    source_id = str(record["source_id"])
                    relevant_ids = [str(x) for x in (record["relevant_ids"] or [])]
                    if not _exists(repo, task["source_type"], source_id):
                        continue
                    relevant_ids = [
                        rid for rid in relevant_ids if _exists(repo, task["target_type"], rid) and rid != source_id
                    ]
                    if not relevant_ids:
                        continue
                    cases.append(
                        {
                            "case_id": f"data1_{task['name']}_{added + 1}",
                            "source_type": task["source_type"],
                            "source_id": source_id,
                            "target_type": task["target_type"],
                            "mode": "public",
                            "label_source": "graph_indirect_data1",
                            "relevant_ids": relevant_ids[:3],
                            "graded_relevance": _graded(relevant_ids[:3]),
                            "notes": "Generated from indirect data1 Neo4j evidence after excluding existing production relationships.",
                        }
                    )
                    added += 1
                    if added >= per_task:
                        break
                stats[task["name"]] = added
    finally:
        driver.close()

    return {
        "version": 3,
        "description": "Evaluation cases generated from indirect data1 Neo4j evidence after MongoDB/Neo4j import.",
        "label_version": "data1_graph_indirect_v1",
        "label_created_at": datetime.now(timezone.utc).date().isoformat(),
        "label_policy": "graph_indirect_data1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generation_stats": stats,
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate data1 evaluation cases")
    parser.add_argument("--output", type=Path, default=Path("scripts") / "evaluation_cases_data1.json")
    parser.add_argument("--per-task", type=int, default=3)
    args = parser.parse_args()

    payload = generate(max(1, args.per_task))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "cases": len(payload["cases"]), "stats": payload["generation_stats"]}, ensure_ascii=False))
    return 0 if payload["cases"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
