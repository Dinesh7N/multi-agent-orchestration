"""Redis-backed rate limiting helpers."""

from __future__ import annotations

import time
import asyncio
from pathlib import Path
from typing import Final

from .config import settings
from .redis_client import get_redis_client

_RATE_LIMIT_LUA: str | None = None
_LUA_PATH: Final[Path] = Path(__file__).with_name("lua") / "rate_limit.lua"


def _load_lua() -> str:
    global _RATE_LIMIT_LUA
    if _RATE_LIMIT_LUA is None:
        _RATE_LIMIT_LUA = _LUA_PATH.read_text()
    return _RATE_LIMIT_LUA


def _limits_for(api_type: str) -> tuple[int, int]:
    limits = {
        "gemini": (60, 60),
        "claude": (40, 60),
        "codex": (60, 60),
    }
    return limits.get(api_type, (10, 60))


async def acquire_rate_limit(api_type: str) -> bool:
    """Acquire a token for the API type. Returns True if allowed."""
    limit, window = _limits_for(api_type)
    bucket = int(time.time() // window)
    key = f"ratelimit:{api_type}:{bucket}"

    redis = get_redis_client()
    lua = _load_lua()
    result = await redis.eval(lua, 1, key, limit, window)
    return result == 1


async def wait_for_rate_limit(api_type: str) -> bool:
    """Wait until a rate limit token is available or timeout."""
    if not settings.redis_rate_limit_enabled:
        return True

    deadline = time.time() + settings.redis_rate_limit_wait_seconds
    while time.time() < deadline:
        try:
            if await acquire_rate_limit(api_type):
                return True
        except Exception:
            # If Redis is unavailable, do not block agent execution.
            return True

        await asyncio.sleep(1)

    return False
