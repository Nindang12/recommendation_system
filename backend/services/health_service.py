from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from core.cache import cache
from infrastructure.rabbitmq_client import RabbitMQClient
from repositories.mongodb_repo import MongoDBRepository
from repositories.neo4j_repo import Neo4jRepository


class HealthService:
    """
    Business layer for system readiness checks.
    Redis is intentionally optional because recommendation can still run without cache.
    """

    def __init__(
        self,
        mongo_repo: Optional[MongoDBRepository] = None,
        neo4j_repo: Optional[Neo4jRepository] = None,
    ) -> None:
        self.mongo_repo = mongo_repo
        self.neo4j_repo = neo4j_repo

    async def get_health(self) -> Dict[str, Any]:
        services = {
            "mongodb": self._check_mongodb(),
            "neo4j": self._check_neo4j(),
            "redis": await self._check_redis_optional(),
            "rabbitmq": self._check_rabbitmq_optional(),
            "pgpr": self._check_pgpr_assets(),
        }
        is_core_ok = (
            services["mongodb"] == "connected"
            and services["neo4j"] == "connected"
            and services["pgpr"] == "ready"
        )
        return {
            "status": "ok" if is_core_ok else "degraded",
            "services": services,
        }

    def _check_mongodb(self) -> str:
        try:
            repo = self.mongo_repo or MongoDBRepository()
            return "connected" if repo.check_db_health() else "unavailable"
        except Exception:
            return "unavailable"

    def _check_neo4j(self) -> str:
        repo = self.neo4j_repo
        owns_repo = repo is None
        try:
            repo = repo or Neo4jRepository()
            return "connected" if repo.check_db_health() else "unavailable"
        except Exception:
            return "unavailable"
        finally:
            if owns_repo and repo is not None:
                try:
                    repo.close()
                except Exception:
                    pass

    async def _check_redis_optional(self) -> str:
        try:
            pong = await cache.redis.ping()
            return "connected" if pong else "optional"
        except Exception:
            return "optional"

    def _check_rabbitmq_optional(self) -> str:
        try:
            return RabbitMQClient().health()
        except Exception:
            return "unavailable_optional"

    def _check_pgpr_assets(self) -> str:
        default_dir = Path(__file__).parents[1] / "pgpr" / "pgpr_data"
        data_dir = Path(os.getenv("PGPR_DATA_DIR", default_dir))
        vocab_exists = (data_dir / "vocab.json").exists()
        has_policy = any(data_dir.glob("policy_*.pt")) or (data_dir / "policy.pt").exists()
        if vocab_exists and has_policy:
            return "ready"
        if vocab_exists:
            return "missing_policy"
        return "missing_data"
