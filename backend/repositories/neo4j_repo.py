from __future__ import annotations

import os
from typing import Any, Dict, List

from neo4j import GraphDatabase

from core.env import load_project_env

load_project_env()


class Neo4jRepository:
    """
    Repository layer that encapsulates Neo4j access.
    """

    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ) -> None:
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = user or os.getenv("NEO4J_USER", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "password")
        self.driver = GraphDatabase.driver(
            self.uri,
            auth=(self.user, self.password),
        )

    def close(self) -> None:
        self.driver.close()

    def check_db_health(self) -> bool:
        with self.driver.session() as session:
            result = session.run("RETURN 1 AS num")
            record = result.single()
            return bool(record and record.get("num") == 1)

    async def count_active_projects(self, expert_id: str) -> int:
        query = """
        MATCH (e:Expert {expert_id: $expert_id})-[:PARTICIPATES_IN]->(p:Project)
        WHERE p.status IN ['ongoing', 'recruiting']
        RETURN count(p) AS count
        """
        with self.driver.session() as session:
            result = session.run(query, expert_id=expert_id)
            record = result.single()
            return int(record["count"]) if record else 0

    async def get_expert_network(self, expert_id: str) -> List[Dict[str, Any]]:
        query = """
        MATCH (e:Expert {expert_id: $expert_id})-[:COLLABORATES_WITH]-(colleague:Expert)
        RETURN colleague.expert_id AS id, colleague.name AS name
        LIMIT 10
        """
        with self.driver.session() as session:
            result = session.run(query, expert_id=expert_id)
            return [dict(record) for record in result]

