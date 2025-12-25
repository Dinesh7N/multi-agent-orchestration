"""State reconciliation for Redis queue."""

from __future__ import annotations

from sqlalchemy import select

from . import db
from .config import settings
from .queue import JobPayload, enqueue_job
from .role_config import Role, resolve_role
from .run_agent import AgentType, Phase


async def reconcile_running_rounds() -> None:
    """Re-queue in-progress rounds missing completed agent runs."""
    if not settings.redis_queue_enabled:
        return

    async with db.get_session() as session:
        from .models import Round

        result = await session.execute(select(Round).where(Round.status == "in_progress"))
        rounds = result.scalars().all()
        for round_ in rounds:
            task = await db.get_task_by_id(session, round_.task_id)
            if not task:
                continue

            agent_statuses = round_.agent_statuses or {}
            if not isinstance(agent_statuses, dict):
                agent_statuses = {}

            def agent_value_from_key(agent_key: str) -> str:
                return (
                    agent_key.replace("debate_", "", 1)
                    if agent_key.startswith("debate_")
                    else agent_key
                )

            for role in (Role.PLANNER_PRIMARY, Role.PLANNER_SECONDARY):
                role_cfg = await resolve_role(role, session)
                agent_key = role_cfg.get("agent_key")
                if not isinstance(agent_key, str) or not agent_key:
                    continue

                agent_value = agent_value_from_key(agent_key)
                if agent_value not in (AgentType.GEMINI.value, AgentType.CLAUDE.value):
                    continue

                role_status = agent_statuses.get(role.value)
                agent_status = agent_statuses.get(agent_value)
                status = role_status or agent_status

                if status in ("completed", "failed"):
                    continue

                await enqueue_job(
                    JobPayload(
                        task_id=task.id,
                        task_slug=task.slug,
                        round_number=round_.round_number,
                        agent=agent_value,
                        phase=Phase.ANALYSIS.value,
                        role=role.value,
                        job_type="analysis",
                    )
                )
