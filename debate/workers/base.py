"""Redis stream worker base class."""

from __future__ import annotations

import asyncio
import signal
import time
from dataclasses import dataclass
from typing import Any

from ..queue import STREAM_PRIORITY, stream_for_agent
from ..redis_client import get_redis_client


@dataclass
class JobMessage:
    msg_id: str
    stream: str
    payload: dict[str, Any]


class RedisWorker:
    """Base worker consuming jobs from Redis Streams."""

    def __init__(self, *, agent: str, group: str) -> None:
        self.agent = agent
        self.group = group
        self.consumer = f"{agent}-{int(time.time())}"
        self.shutdown_requested = False

    async def setup(self) -> None:
        redis = get_redis_client()
        streams = {STREAM_PRIORITY: "$", stream_for_agent(self.agent): "$"}
        for stream in streams:
            try:
                await redis.xgroup_create(stream, self.group, id="$", mkstream=True)
            except Exception:
                pass

    def _install_signal_handlers(self) -> None:
        def _handle_signal(signum: int, frame: object) -> None:
            self.shutdown_requested = True

        signal.signal(signal.SIGTERM, _handle_signal)
        signal.signal(signal.SIGINT, _handle_signal)

    async def _next_job(self) -> JobMessage | None:
        redis = get_redis_client()
        streams = [STREAM_PRIORITY, stream_for_agent(self.agent)]
        for stream in streams:
            result = await redis.xreadgroup(
                groupname=self.group,
                consumername=self.consumer,
                streams={stream: ">"},
                count=1,
                block=1000,
            )
            if result:
                stream_name, messages = result[0]
                msg_id, payload = messages[0]
                return JobMessage(msg_id=msg_id, stream=stream_name, payload=payload)
        return None

    async def _ack(self, job: JobMessage) -> None:
        redis = get_redis_client()
        await redis.xack(job.stream, self.group, job.msg_id)

    async def _to_dlq(self, job: JobMessage, error: str) -> None:
        redis = get_redis_client()
        dlq = f"stream:dlq:{job.payload.get('job_type', 'analysis')}"
        payload = dict(job.payload)
        payload["error"] = error
        await redis.xadd(dlq, payload)
        await self._ack(job)

    async def _requeue(self, job: JobMessage, retry_count: int) -> None:
        redis = get_redis_client()
        payload = dict(job.payload)
        payload["retry_count"] = str(retry_count)
        await redis.xadd(job.stream, payload)
        await self._ack(job)

    async def _should_process(self, payload: dict[str, Any]) -> bool:
        task_id = payload.get("task_id")
        round_number = payload.get("round")
        agent = payload.get("agent")
        if not task_id or not round_number or not agent:
            return False

        redis = get_redis_client()
        idem_key = f"idempotency:{task_id}:{round_number}:{agent}"
        return await redis.set(idem_key, "1", nx=True, ex=3600) is True

    async def process(self, payload: dict[str, Any]) -> None:
        """Override in subclasses to execute a job."""
        raise NotImplementedError

    async def run_forever(self) -> None:
        await self.setup()
        self._install_signal_handlers()

        while not self.shutdown_requested:
            job = await self._next_job()
            if not job:
                continue

            if not await self._should_process(job.payload):
                await self._ack(job)
                continue

            try:
                await self.process(job.payload)
                await self._ack(job)
            except Exception as exc:
                retry_count = int(job.payload.get("retry_count", "0")) + 1
                if retry_count >= 3:
                    await self._to_dlq(job, str(exc))
                else:
                    await self._requeue(job, retry_count)

        # Drain any in-flight state if needed before exit.
        await asyncio.sleep(0.1)
