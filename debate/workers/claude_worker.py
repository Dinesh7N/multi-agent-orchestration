"""Claude Redis worker."""

import asyncio

from ..role_config import Role
from ..run_agent import AgentType, Phase, run_agent, run_agent_by_role
from .base import RedisWorker


class ClaudeWorker(RedisWorker):
    async def process(self, payload: dict[str, str]) -> None:
        if payload.get("agent") != AgentType.CLAUDE.value:
            return
        task_slug = payload["task_slug"]
        round_number = int(payload["round"])
        phase = Phase(payload.get("phase", Phase.ANALYSIS.value))

        role_value = payload.get("role")
        if role_value:
            try:
                role = Role(role_value)
            except ValueError:
                await run_agent(task_slug, AgentType.CLAUDE, round_number=round_number, phase=phase)
                return
            await run_agent_by_role(task_slug, role, round_number=round_number, phase=phase)
            return

        await run_agent(task_slug, AgentType.CLAUDE, round_number=round_number, phase=phase)


def main() -> None:
    worker = ClaudeWorker(agent=AgentType.CLAUDE.value, group="claude-workers")
    asyncio.run(worker.run_forever())


if __name__ == "__main__":
    main()
