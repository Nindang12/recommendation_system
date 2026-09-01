"""Generate leave-one-edge-out evaluation cases from the current data1 graph.

This protocol uses known graph links as held-out targets. During evaluation,
the runner allows the held-out target to pass through the production
existing-relationship exclude list, so the metric checks whether the ranking
pipeline can reconstruct a known link.
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
        "relation": "PARTICIPATES_IN",
        "query": """
        MATCH (t:Expert)-[:PARTICIPATES_IN]->(s:Project)
        WHERE s.project_id IS NOT NULL AND t.expert_id IS NOT NULL
        RETURN s.project_id AS source_id, collect(DISTINCT t.expert_id)[0..3] AS relevant_ids
        ORDER BY source_id
        LIMIT $limit
        """,
    },
    {
        "name": "expert_to_project",
        "source_type": "expert",
        "target_type": "project",
        "relation": "PARTICIPATES_IN",
        "query": """
        MATCH (s:Expert)-[:PARTICIPATES_IN]->(t:Project)
        WHERE s.expert_id IS NOT NULL AND t.project_id IS NOT NULL
        RETURN s.expert_id AS source_id, collect(DISTINCT t.project_id)[0..3] AS relevant_ids
        ORDER BY source_id
        LIMIT $limit
        """,
    },
    {
        "name": "project_to_funder",
        "source_type": "project",
        "target_type": "funder",
        "relation": "FUNDS",
        "query": """
        MATCH (t:Funder)-[:FUNDS]->(s:Project)
        WHERE s.project_id IS NOT NULL AND t.funder_id IS NOT NULL
        RETURN s.project_id AS source_id, collect(DISTINCT t.funder_id)[0..3] AS relevant_ids
        ORDER BY source_id
        LIMIT $limit
        """,
    },
    {
        "name": "funder_to_project",
        "source_type": "funder",
        "target_type": "project",
        "relation": "FUNDS",
        "query": """
        MATCH (s:Funder)-[:FUNDS]->(t:Project)
        WHERE s.funder_id IS NOT NULL AND t.project_id IS NOT NULL
        RETURN s.funder_id AS source_id, collect(DISTINCT t.project_id)[0..3] AS relevant_ids
        ORDER BY source_id
        LIMIT $limit
        """,
    },
    {
        "name": "expert_to_expert",
        "source_type": "expert",
        "target_type": "expert",
        "relation": "CO_AUTHORED",
        "query": """
        MATCH (s:Expert)-[:CO_AUTHORED]-(t:Expert)
        WHERE s.expert_id IS NOT NULL AND t.expert_id IS NOT NULL AND s.expert_id <> t.expert_id
        RETURN s.expert_id AS source_id, collect(DISTINCT t.expert_id)[0..3] AS relevant_ids
        ORDER BY source_id
        LIMIT $limit
        """,
    },
    {
        "name": "project_to_project",
        "source_type": "project",
        "target_type": "project",
        "relation": "SHARED_EXPERT_OR_FUNDER",
        "query": """
        MATCH (s:Project)
        WHERE s.project_id IS NOT NULL
        OPTIONAL MATCH (s)<-[:PARTICIPATES_IN]-(:Expert)-[:PARTICIPATES_IN]->(p_by_expert:Project)
        OPTIONAL MATCH (s)<-[:FUNDS]-(:Funder)-[:FUNDS]->(p_by_funder:Project)
        WITH s, collect(DISTINCT p_by_expert) + collect(DISTINCT p_by_funder) AS candidates
        UNWIND candidates AS t
        WITH s, t
        WHERE t IS NOT NULL AND t.project_id IS NOT NULL AND t.project_id <> s.project_id
        RETURN s.project_id AS source_id, collect(DISTINCT t.project_id)[0..3] AS relevant_ids
        ORDER BY source_id
        LIMIT $limit
        """,
    },
    {
        "name": "expert_to_enterprise",
        "source_type": "expert",
        "target_type": "enterprise",
        "relation": "HAS_APPLICATION_EXPERIENCE_IN/OPERATES_IN",
        "query": """
        MATCH (s:Expert)-[:HAS_APPLICATION_EXPERIENCE_IN]->(:Industry)<-[:OPERATES_IN]-(t:Enterprise)
        WHERE s.expert_id IS NOT NULL AND t.enterprise_id IS NOT NULL
        RETURN s.expert_id AS source_id, collect(DISTINCT t.enterprise_id)[0..3] AS relevant_ids
        ORDER BY source_id
        LIMIT $limit
        """,
    },
    {
        "name": "enterprise_to_expert",
        "source_type": "enterprise",
        "target_type": "expert",
        "relation": "OPERATES_IN/HAS_APPLICATION_EXPERIENCE_IN",
        "query": """
        MATCH (s:Enterprise)-[:OPERATES_IN]->(:Industry)<-[:HAS_APPLICATION_EXPERIENCE_IN]-(t:Expert)
        WHERE s.enterprise_id IS NOT NULL AND t.expert_id IS NOT NULL
        RETURN s.enterprise_id AS source_id, collect(DISTINCT t.expert_id)[0..3] AS relevant_ids
        ORDER BY source_id
        LIMIT $limit
        """,
    },
]


def _exists(repo: AuthRepository, entity_type: str, entity_id: str) -> bool:
    return repo.find_entity_by_id(entity_type, str(entity_id)) is not None


def _graded(relevant_ids: list[str]) -> dict[str, int]:
    return {rid: 3 for rid in relevant_ids}


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
                        rid
                        for rid in relevant_ids
                        if rid != source_id and _exists(repo, task["target_type"], rid)
                    ]
                    if not relevant_ids:
                        continue
                    cases.append(
                        {
                            "case_id": f"data1_loo_{task['name']}_{added + 1}",
                            "source_type": task["source_type"],
                            "source_id": source_id,
                            "target_type": task["target_type"],
                            "mode": "public",
                            "evaluation_protocol": "leave_one_edge_out",
                            "label_source": "graph_leave_one_edge_out_data1",
                            "heldout_relation": task["relation"],
                            "relevant_ids": relevant_ids[:3],
                            "graded_relevance": _graded(relevant_ids[:3]),
                            "tags": ["leave_one_edge_out", task["relation"]],
                            "notes": (
                                "Known graph target treated as held out; evaluation allows "
                                "this target through existing-relationship filtering."
                            ),
                        }
                    )
                    added += 1
                    if added >= per_task:
                        break
                stats[task["name"]] = added
    finally:
        driver.close()

    return {
        "version": 1,
        "description": "Leave-one-edge-out reconstruction cases generated from data1 Neo4j graph links.",
        "label_version": "data1_leave_one_edge_out_v1",
        "label_created_at": datetime.now(timezone.utc).date().isoformat(),
        "label_policy": "graph_leave_one_edge_out_data1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generation_stats": stats,
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate data1 leave-one-edge-out evaluation cases")
    parser.add_argument("--output", type=Path, default=Path("scripts") / "evaluation_cases_data1_leave_one_edge_out.json")
    parser.add_argument("--per-task", type=int, default=3)
    args = parser.parse_args()

    payload = generate(max(1, args.per_task))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {"output": str(args.output), "cases": len(payload["cases"]), "stats": payload["generation_stats"]},
            ensure_ascii=False,
        )
    )
    return 0 if payload["cases"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
