"""Rate limiting helpers.

This project used to implement rate limiting via Redis + Lua.
As part of the LangGraph rewrite, we keep a simple *in-process* limiter to avoid
extra infrastructure. This is best-effort and not cross-process.
"""

from __future__ import annotations

import asyncio
import time

from .config import settings


def _limits_for(api_type: str) -> tuple[int, int]:
    limits = {
        "gemini": (60, 60),
        "claude": (40, 60),
        "codex": (60, 60),
    }
    return limits.get(api_type, (10, 60))


# In-process counter: (api_type, bucket_start) -> count
_COUNTS: dict[tuple[str, int], int] = {}
_LOCK = asyncio.Lock()


async def acquire_rate_limit(api_type: str) -> bool:
    """Acquire a token for the API type. Returns True if allowed."""
    limit, window = _limits_for(api_type)
    bucket = int(time.time() // window) * window
    key = (api_type, bucket)
    async with _LOCK:
        used = _COUNTS.get(key, 0)
        if used >= limit:
            return False
        _COUNTS[key] = used + 1
        return True


async def wait_for_rate_limit(api_type: str) -> bool:
    """Wait until a rate limit token is available or timeout."""
    if not settings.redis_rate_limit_enabled:
        return True

    deadline = time.time() + settings.redis_rate_limit_wait_seconds
    while time.time() < deadline:
        if await acquire_rate_limit(api_type):
            return True

        await asyncio.sleep(1)

    return False
