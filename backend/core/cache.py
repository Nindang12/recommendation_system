from __future__ import annotations

from typing import Any, Optional

import json

import redis.asyncio as redis


class Cache:
    """
    Redis Cache Layer used by the Service layer (cache-aside).
    """

    def __init__(self, url: str = "redis://localhost:6379") -> None:
        self.redis = redis.from_url(url, decode_responses=True)

    async def get(self, key: str) -> Optional[Any]:
        try:
            value = await self.redis.get(key)
            if value is None:
                return None
            return json.loads(value)
        except Exception:
            # fail gracefully – service can continue without cache
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int = 3600,
    ) -> None:
        try:
            await self.redis.setex(key, ttl, json.dumps(value, ensure_ascii=False))
        except Exception:
            # swallow cache errors – do not break business flow
            return None


# Global cache instance (simple usage for now)
cache = Cache()

