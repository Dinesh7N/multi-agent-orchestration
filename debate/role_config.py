from __future__ import annotations

import os
from enum import StrEnum
from typing import TYPE_CHECKING, TypedDict

from sqlalchemy import select

from .config import settings
from .model_config import resolve_model
from .models import Guardrail

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class Role(StrEnum):
    PLANNER_PRIMARY = "planner_primary"
    PLANNER_SECONDARY = "planner_secondary"
    IMPLEMENTER = "implementer"
    REVIEWER = "reviewer"
    EXPLORER = "explorer"


class RoleConfig(TypedDict, total=False):
    agent_key: str
    model: str | None
    prompt_template: str
    description: str
    capabilities: list[str]
    timeout_override: int | None
    job_type: str


DEFAULT_ROLE_CONFIG: dict[str, RoleConfig] = {
    "planner_primary": {
        "agent_key": "debate_gemini",
        "prompt_template": "templates/planner.md",
        "description": "Primary planning agent with large context for comprehensive analysis",
        "capabilities": ["large_context", "pattern_recognition", "data_flow_analysis"],
        "job_type": "analysis",
    },
    "planner_secondary": {
        "agent_key": "debate_claude",
        "prompt_template": "templates/planner.md",
        "description": "Secondary planning agent focused on security and edge cases",
        "capabilities": ["security_analysis", "architectural_reasoning", "compliance_review"],
        "job_type": "analysis",
    },
    "implementer": {
        "agent_key": "debate_codex",
        "prompt_template": "templates/implementer.md",
        "description": "Code implementation agent that executes approved plans",
        "capabilities": ["code_generation"],
        "job_type": "implement",
    },
    "reviewer": {
        "agent_key": "debate_claude",
        "prompt_template": "templates/reviewer.md",
        "description": "Code review and validation agent with security focus",
        "capabilities": ["security_analysis", "code_quality", "compliance_review"],
        "job_type": "analysis",
    },
    "explorer": {
        "agent_key": "debate_gemini",
        "prompt_template": "templates/explorer.md",
        "description": "Codebase exploration agent with large context window",
        "capabilities": ["large_context", "pattern_recognition"],
        "job_type": "analysis",
    },
}

GUARDRAIL_KEY = "role_config"


def get_env_keys(role: Role) -> dict[str, str]:
    role_upper = role.value.upper()
    return {
        "agent_key": f"ROLE_{role_upper}_AGENT",
        "model": f"ROLE_{role_upper}_MODEL",
        "prompt_template": f"ROLE_{role_upper}_PROMPT",
    }


def get_role_from_env(role: Role) -> dict[str, str]:
    env_keys = get_env_keys(role)
    result = {}

    for field, env_key in env_keys.items():
        value = os.getenv(env_key)
        if value:
            result[field] = value

    return result


async def get_db_role_config(session: AsyncSession) -> dict[str, dict]:
    result = await session.execute(select(Guardrail).where(Guardrail.key == GUARDRAIL_KEY))
    guardrail = result.scalar_one_or_none()

    if guardrail and isinstance(guardrail.value, dict):
        return {k: v for k, v in guardrail.value.items() if isinstance(v, dict)}
    return {}


async def resolve_role(role: Role, session: AsyncSession | None = None) -> RoleConfig:
    env_overrides = get_role_from_env(role)

    default_config = DEFAULT_ROLE_CONFIG.get(role.value, DEFAULT_ROLE_CONFIG["planner_primary"])
    merged_config = RoleConfig(**default_config)

    if session:
        db_config = await get_db_role_config(session)
        db_role_config = db_config.get(role.value)
        if isinstance(db_role_config, dict):
            for key in (
                "agent_key",
                "model",
                "prompt_template",
                "description",
                "capabilities",
                "timeout_override",
                "job_type",
            ):
                if key in db_role_config:
                    merged_config[key] = db_role_config[key]  # type: ignore

    if env_overrides:
        for key, value in env_overrides.items():
            merged_config[key] = value  # type: ignore

    if merged_config.get("model") is None and session:
        agent_key = merged_config.get("agent_key")
        if isinstance(agent_key, str) and agent_key:
            merged_config["model"] = await resolve_model(agent_key, session)

    return merged_config


async def resolve_role_with_source(
    role: Role, session: AsyncSession | None = None
) -> tuple[RoleConfig, str]:
    env_overrides = get_role_from_env(role)
    if env_overrides:
        config = await resolve_role(role, session)
        return config, "env"

    if session:
        db_config = await get_db_role_config(session)
        if role.value in db_config:
            config = await resolve_role(role, session)
            return config, "db"

    config = await resolve_role(role, session)
    return config, "default"


async def get_all_role_configs(session: AsyncSession) -> dict[str, dict]:
    db_config = await get_db_role_config(session)

    all_roles = set(r.value for r in Role) | set(db_config.keys())

    result = {}
    for role_name in sorted(all_roles):
        try:
            role = Role(role_name)
            config, source = await resolve_role_with_source(role, session)
            result[role_name] = {
                "config": config,
                "source": source,
            }
        except ValueError:
            continue

    return result


async def update_role_config(
    session: AsyncSession,
    role: Role,
    agent_key: str | None = None,
    model: str | None = None,
    prompt_template: str | None = None,
    description: str | None = None,
    capabilities: list[str] | None = None,
    timeout_override: int | None = None,
    job_type: str | None = None,
) -> None:
    result = await session.execute(select(Guardrail).where(Guardrail.key == GUARDRAIL_KEY))
    guardrail = result.scalar_one_or_none()

    if guardrail:
        if not isinstance(guardrail.value, dict):
            guardrail.value = {}
        new_value = dict(guardrail.value)
    else:
        guardrail = Guardrail(key=GUARDRAIL_KEY, value={})
        session.add(guardrail)
        new_value = {}

    existing_config = new_value.get(role.value, {})

    updated_config = dict(existing_config)
    if agent_key is not None:
        updated_config["agent_key"] = agent_key
    if model is not None:
        updated_config["model"] = model
    if prompt_template is not None:
        updated_config["prompt_template"] = prompt_template
    if description is not None:
        updated_config["description"] = description
    if capabilities is not None:
        updated_config["capabilities"] = capabilities
    if timeout_override is not None:
        updated_config["timeout_override"] = timeout_override
    if job_type is not None:
        updated_config["job_type"] = job_type

    new_value[role.value] = updated_config
    guardrail.value = new_value

    await session.commit()


async def delete_role_override(session: AsyncSession, role: Role) -> bool:
    result = await session.execute(select(Guardrail).where(Guardrail.key == GUARDRAIL_KEY))
    guardrail = result.scalar_one_or_none()

    if guardrail and isinstance(guardrail.value, dict) and role.value in guardrail.value:
        new_value = dict(guardrail.value)
        del new_value[role.value]
        guardrail.value = new_value
        await session.commit()
        return True
    return False


def validate_prompt_template(prompt_template: str) -> bool:
    agent_dir = settings.agent_dir.resolve()
    prompt_path = (settings.agent_dir / prompt_template).resolve()

    if not prompt_path.is_relative_to(agent_dir):
        return False

    return prompt_path.exists() and prompt_path.is_file()


def validate_role_agent_compatibility(role: Role, agent_key: str) -> list[str]:
    agent_capabilities: dict[str, set[str]] = {
        "debate_gemini": {"analysis", "exploration"},
        "debate_claude": {"analysis", "review", "security"},
        "debate_codex": {"implementation", "code_generation"},
    }

    role_requirements: dict[Role, set[str]] = {
        Role.PLANNER_PRIMARY: {"analysis"},
        Role.PLANNER_SECONDARY: {"analysis"},
        Role.EXPLORER: {"exploration"},
        Role.IMPLEMENTER: {"implementation"},
        Role.REVIEWER: {"review"},
    }

    available = agent_capabilities.get(agent_key)
    required = role_requirements.get(role)

    if not available or not required:
        return []

    missing = required - available
    if missing:
        required_list = sorted(required)
        available_list = sorted(available)
        return [
            f"Role '{role.value}' typically requires {required_list}, "
            f"but '{agent_key}' only has {available_list}"
        ]

    return []


async def validate_role_config(session: AsyncSession, role: Role) -> list[str]:
    errors = []

    try:
        config = await resolve_role(role, session)
    except Exception as e:
        errors.append(f"Failed to resolve role config: {e}")
        return errors

    agent_key = config.get("agent_key")
    if not isinstance(agent_key, str) or not agent_key:
        errors.append("Missing required field: agent_key")
        return errors

    from .model_config import DEFAULT_MODELS, get_db_model_config

    db_models = await get_db_model_config(session)
    known_agent_keys = set(DEFAULT_MODELS.keys()) | set(db_models.keys())
    if agent_key not in known_agent_keys:
        errors.append(f"Unknown agent_key: {agent_key}")

    prompt_template = config.get("prompt_template")
    if not isinstance(prompt_template, str) or not prompt_template:
        errors.append("Missing required field: prompt_template")
        return errors

    if not validate_prompt_template(prompt_template):
        errors.append(f"Prompt template not found: {prompt_template}")

    return errors
