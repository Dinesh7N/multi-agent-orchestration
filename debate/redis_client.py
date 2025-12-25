"""Async Redis client for debate workflow."""

import os

from redis.asyncio import ConnectionPool, Redis

from .config import settings

REDIS_URL = os.getenv("REDIS_URL", settings.redis_url)

_pool = ConnectionPool.from_url(REDIS_URL, max_connections=20, decode_responses=True)


def get_redis_client() -> Redis:
    """Get an async Redis client from the shared pool."""
    return Redis(connection_pool=_pool)
