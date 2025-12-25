"""Redis Streams job queue helpers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, cast

from .config import settings
from .redis_client import get_redis_client

STREAM_ANALYSIS = "stream:jobs:analysis"
STREAM_IMPLEMENT = "stream:jobs:implement"
STREAM_PRIORITY = "stream:jobs:priority"


class QueueFullError(RuntimeError):
    """Raised when a Redis job stream reaches capacity."""


@dataclass(frozen=True)
class JobPayload:
    task_id: str
    task_slug: str
    round_number: int
    agent: str
    phase: str
    role: str | None = None
    schema_version: str = "1.1"
    job_type: str = "analysis"
    retry_count: int = 0

    def to_dict(self) -> dict[str, str]:
        payload: dict[str, str] = {
            "schema_version": str(self.schema_version),
            "job_type": str(self.job_type),
            "task_id": str(self.task_id),
            "task_slug": str(self.task_slug),
            "round": str(self.round_number),
            "agent": str(self.agent),
            "phase": str(self.phase),
            "retry_count": str(self.retry_count),
        }
        if self.role:
            payload["role"] = str(self.role)
        return payload


STREAM_MAP = {
    "analysis": STREAM_ANALYSIS,
    "implement": STREAM_IMPLEMENT,
}


def stream_for_agent(agent: str, *, role: str | None = None, job_type: str | None = None) -> str:
    if job_type:
        return STREAM_MAP.get(job_type, STREAM_ANALYSIS)

    if role == "implementer" or agent == "codex":
        return STREAM_IMPLEMENT

    return STREAM_ANALYSIS


async def _ensure_capacity(stream: str) -> None:
    redis = get_redis_client()
    length = await redis.xlen(stream)
    if length >= settings.redis_queue_max_depth:
        raise QueueFullError(f"Stream {stream} at capacity ({length})")


async def enqueue_job(payload: JobPayload, *, priority: bool = False) -> str:
    """Enqueue a job to Redis Streams."""
    stream = (
        STREAM_PRIORITY
        if priority
        else stream_for_agent(payload.agent, role=payload.role, job_type=payload.job_type)
    )
    await _ensure_capacity(stream)

    redis = get_redis_client()
    msg_id = await redis.xadd(stream, cast(dict[Any, Any], payload.to_dict()))
    return msg_id


async def wait_for_round_status(
    task_slug: str,
    round_number: int,
    *,
    timeout_seconds: int,
) -> bool:
    """Wait for round completion status in Postgres."""
    from . import db

    deadline = asyncio.get_event_loop().time() + timeout_seconds
    while asyncio.get_event_loop().time() < deadline:
        async with db.get_session() as session:
            task = await db.get_task_by_slug(session, task_slug)
            if not task:
                return False
            round_ = await db.get_or_create_round(session, task, round_number)
            if round_.status in ("completed", "failed"):
                return round_.status == "completed"
        await asyncio.sleep(2)
    return False
