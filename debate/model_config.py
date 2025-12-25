from __future__ import annotations

import os
from typing import TYPE_CHECKING

from sqlalchemy import select

from .models import Guardrail

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_MODELS: dict[str, str] = {
    "orchestrator": "amazon-bedrock/anthropic.claude-sonnet-4-5-20250929-v1:0",
    "librarian": "opencode/big-pickle",
    "frontend-ui-ux-engineer": "google/gemini-3-pro-high",
    "document-writer": "google/gemini-3-flash",
    "multimodal-looker": "google/gemini-3-flash",
    "debate_gemini": "google/gemini-3-pro-high",
    "debate_claude": "amazon-bedrock/anthropic.claude-sonnet-4-5-20250929-v1:0",
    "debate_codex": "openai/gpt-5.1-codex-max-medium",
    "oracle": "openai/gpt-5.2-high",
    "explore": "google/gemini-3-flash",
    "general": "google/gemini-3-pro-high",
}

GUARDRAIL_KEY = "model_config"


def get_env_key(agent_name: str) -> str:
    return f"{agent_name.upper().replace('-', '_')}_MODEL"


def get_model_from_env(agent_name: str) -> str | None:
    return os.getenv(get_env_key(agent_name))


async def get_db_model_config(session: AsyncSession) -> dict[str, str]:
    result = await session.execute(select(Guardrail).where(Guardrail.key == GUARDRAIL_KEY))
    guardrail = result.scalar_one_or_none()

    if guardrail and isinstance(guardrail.value, dict):
        return {k: v for k, v in guardrail.value.items() if isinstance(v, str)}
    return {}


async def resolve_model(agent_name: str, session: AsyncSession | None = None) -> str:
    env_value = get_model_from_env(agent_name)
    if env_value:
        return env_value

    if session:
        db_config = await get_db_model_config(session)
        if agent_name in db_config:
            return db_config[agent_name]

    return DEFAULT_MODELS.get(agent_name, DEFAULT_MODELS["orchestrator"])


async def resolve_model_with_source(
    agent_name: str, session: AsyncSession | None = None
) -> tuple[str, str]:
    env_value = get_model_from_env(agent_name)
    if env_value:
        return env_value, "env"

    if session:
        db_config = await get_db_model_config(session)
        if agent_name in db_config:
            return db_config[agent_name], "db"

    default = DEFAULT_MODELS.get(agent_name, DEFAULT_MODELS["orchestrator"])
    return default, "default"


async def update_db_model(session: AsyncSession, agent_name: str, model: str) -> None:
    result = await session.execute(select(Guardrail).where(Guardrail.key == GUARDRAIL_KEY))
    guardrail = result.scalar_one_or_none()

    if guardrail:
        if not isinstance(guardrail.value, dict):
            guardrail.value = {}
        new_value = dict(guardrail.value)
        new_value[agent_name] = model
        guardrail.value = new_value
    else:
        guardrail = Guardrail(key=GUARDRAIL_KEY, value={agent_name: model})
        session.add(guardrail)

    await session.commit()


async def delete_db_model(session: AsyncSession, agent_name: str) -> bool:
    result = await session.execute(select(Guardrail).where(Guardrail.key == GUARDRAIL_KEY))
    guardrail = result.scalar_one_or_none()

    if guardrail and isinstance(guardrail.value, dict) and agent_name in guardrail.value:
        new_value = dict(guardrail.value)
        del new_value[agent_name]
        guardrail.value = new_value
        await session.commit()
        return True
    return False


async def get_all_configs(session: AsyncSession) -> dict[str, dict[str, str]]:
    db_config = await get_db_model_config(session)

    all_agents = set(DEFAULT_MODELS.keys()) | set(db_config.keys())

    result = {}
    for agent_name in sorted(all_agents):
        model, source = await resolve_model_with_source(agent_name, session)
        result[agent_name] = {"model": model, "source": source}

    return result
