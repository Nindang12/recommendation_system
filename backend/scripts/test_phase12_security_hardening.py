from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.deps import rate_limit, require_non_empty_reason, require_root_role
from services.rate_limit_service import rate_limiter


class FakeRequest:
    def __init__(self, host: str = "127.0.0.1") -> None:
        self.client = SimpleNamespace(host=host)


def _expect_http_error(func, status_code: int) -> None:
    try:
        func()
    except HTTPException as exc:
        assert exc.status_code == status_code
        return
    raise AssertionError(f"Expected HTTPException {status_code}")


def test_reason_guard() -> None:
    _expect_http_error(lambda: require_non_empty_reason("", action="reject_entity"), 400)
    require_non_empty_reason("duplicate profile", action="merge_entity")


def test_root_guard() -> None:
    _expect_http_error(lambda: require_root_role({"account_role": "admin"}, action="retry permanent"), 403)
    require_root_role({"account_role": "root_admin"}, action="retry permanent")


def test_rate_limit_dependency() -> None:
    os.environ["RATE_LIMIT_ENABLED"] = "true"
    rate_limiter.reset()
    dependency = rate_limit("phase12_test", limit=2, window_seconds=60)

    async def run() -> None:
        await dependency(FakeRequest("10.0.0.1"))
        await dependency(FakeRequest("10.0.0.1"))
        try:
            await dependency(FakeRequest("10.0.0.1"))
        except HTTPException as exc:
            assert exc.status_code == 429
            assert exc.headers and "Retry-After" in exc.headers
            return
        raise AssertionError("Expected rate limit to block third request")

    asyncio.run(run())
    rate_limiter.reset()


def main() -> int:
    test_reason_guard()
    test_root_guard()
    test_rate_limit_dependency()
    print("Phase 12 security hardening tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
