"""Gemini Redis worker."""

import asyncio

from ..role_config import Role
from ..run_agent import AgentType, Phase, run_agent, run_agent_by_role
from .base import RedisWorker


class GeminiWorker(RedisWorker):
    async def process(self, payload: dict[str, str]) -> None:
        if payload.get("agent") != AgentType.GEMINI.value:
            return
        task_slug = payload["task_slug"]
        round_number = int(payload["round"])
        phase = Phase(payload.get("phase", Phase.ANALYSIS.value))

        role_value = payload.get("role")
        if role_value:
            try:
                role = Role(role_value)
            except ValueError:
                await run_agent(task_slug, AgentType.GEMINI, round_number=round_number, phase=phase)
                return
            await run_agent_by_role(task_slug, role, round_number=round_number, phase=phase)
            return

        await run_agent(task_slug, AgentType.GEMINI, round_number=round_number, phase=phase)


def main() -> None:
    worker = GeminiWorker(agent=AgentType.GEMINI.value, group="gemini-workers")
    asyncio.run(worker.run_forever())


if __name__ == "__main__":
    main()
