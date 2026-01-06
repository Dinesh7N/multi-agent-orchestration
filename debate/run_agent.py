"""Agent runner - executes AI agents and captures their output."""

import asyncio
import json
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import UUID

import click
from rich.console import Console
from rich.panel import Panel

from . import db
from .config import settings
from .model_config import resolve_model
from .models import Analysis, Round, Task
from .role_config import Role, RoleConfig, resolve_role

console = Console()


class AgentType(StrEnum):
    """Supported agent types."""

    GEMINI = "gemini"
    CLAUDE = "claude"
    CODEX = "codex"


class Phase(StrEnum):
    """Workflow phases."""

    EXPLORATION = "exploration"
    ANALYSIS = "analysis"
    CONSENSUS = "consensus"
    IMPLEMENTATION = "implementation"
    REVIEW = "review"


@dataclass
class AgentResult:
    """Result from running an agent."""

    success: bool
    raw_output: str
    structured_output: dict[str, Any] | None = None
    error: str | None = None
    duration_seconds: int = 0
    session_id: str | None = None
    message_id: str | None = None
    response_json: dict[str, Any] | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    model_used: str | None = None


def load_agent_instructions(agent: AgentType) -> str:
    agent_file = settings.agent_dir / f"{agent.value}.md"
    if not agent_file.exists():
        raise FileNotFoundError(f"Agent file not found: {agent_file}")
    return agent_file.read_text()


def load_instructions_from_template(prompt_template: str) -> str:
    template_path = settings.agent_dir / prompt_template
    if not template_path.exists():
        raise FileNotFoundError(f"Prompt template not found: {template_path}")
    return template_path.read_text()


def build_prompt(
    instructions: str, context: dict[str, Any], task_slug: str, round_number: int, phase: Phase
) -> str:
    """Build the complete prompt from instructions and context."""
    context_block = f"""
=== TASK CONTEXT (from PostgreSQL) ===

TASK: {task_slug}
Title: {context["task"]["title"]}
Status: {context["task"]["status"]}
Complexity: {context["task"].get("complexity", "standard")}

ORCHESTRATOR-HUMAN CONVERSATIONS:
{_format_conversations(context.get("conversations", []))}

ANSWERED QUESTIONS:
{_format_questions(context.get("answered_questions", []))}

HUMAN DECISIONS:
{_format_decisions(context.get("decisions", []))}

EXPLORATION FINDINGS:
{_format_explorations(context.get("explorations", []))}

CONFLICT SUMMARY:
{_format_conflicts(context.get("conflict_summary", []))}

PREVIOUS ROUND ANALYSES:
{_format_analyses(context.get("previous_analyses", []))}

=== END CONTEXT ===

NOW EXECUTE YOUR ANALYSIS FOR: {task_slug} (Round {round_number}, Phase: {phase.value})
"""
    return f"{instructions}\n\n---\n\n{context_block}"


def _format_conversations(conversations: list[dict[str, Any]]) -> str:
    if not conversations:
        return "(none)"
    return "\n".join(
        f"  [{c['role']}]: {c['content'][:200]}..."
        if len(c["content"]) > 200
        else f"  [{c['role']}]: {c['content']}"
        for c in conversations
    )


def _format_questions(questions: list[dict[str, Any]]) -> str:
    if not questions:
        return "(none)"
    return "\n".join(
        f"  Q: {q['question']}\n  A: {q.get('answer', '(pending)')}" for q in questions
    )


def _format_decisions(decisions: list[dict[str, Any]]) -> str:
    if not decisions:
        return "(none)"
    return "\n".join(f"  {d['topic']}: {d['decision']} (source: {d['source']})" for d in decisions)


def _format_analyses(analyses: list[dict[str, Any]]) -> str:
    if not analyses:
        return "(none)"
    return "\n".join(f"  [{a['agent']}]: {a.get('summary', '(no summary)')}" for a in analyses)


def _format_explorations(explorations: list[dict[str, Any]]) -> str:
    if not explorations:
        return "(none)"
    formatted: list[str] = []
    for e in explorations:
        formatted.append(
            "  Agent: {agent}\n"
            "  Relevant files: {files}\n"
            "  Tech stack: {stack}\n"
            "  Patterns: {patterns}\n"
            "  Dependencies: {deps}\n"
            "  Schema: {schema}\n"
            "  Structure: {structure}".format(
                agent=e.get("agent"),
                files=e.get("relevant_files") or [],
                stack=e.get("tech_stack") or {},
                patterns=e.get("existing_patterns") or {},
                deps=e.get("dependencies") or {},
                schema=e.get("schema_summary") or "",
                structure=e.get("directory_structure") or "",
            )
        )
    return "\n".join(formatted)


def _format_conflicts(conflicts: list[dict[str, Any]]) -> str:
    if not conflicts:
        return "(none)"
    lines: list[str] = []
    for c in conflicts:
        positions = c.get("positions")
        if isinstance(positions, dict) and positions:
            positions_block = "\n".join(f"  - {k}: {v}" for k, v in sorted(positions.items()))
        else:
            positions_block = "  (none)"
        lines.append(
            "  Topic: {topic}\n  Positions:\n{positions}\n  Impact: {impact}".format(
                topic=c.get("topic"),
                positions=positions_block,
                impact=c.get("impact") or "",
            )
        )
    return "\n".join(lines)


def extract_structured_output(output: str) -> dict[str, Any] | None:
    """Extract JSON block from agent output."""
    # Look for ```json:structured_output ... ```
    pattern = r"```json:structured_output\s*(.*?)\s*```"
    match = re.search(pattern, output, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Fallback: look for any JSON block
    pattern = r"```json\s*(.*?)\s*```"
    match = re.search(pattern, output, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    return None


def _extract_token_usage(response_json: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(response_json, dict):
        return {}

    info = response_json.get("info") if isinstance(response_json.get("info"), dict) else {}
    usage = response_json.get("usage") if isinstance(response_json.get("usage"), dict) else {}
    model = info.get("model") or usage.get("model")

    input_tokens = usage.get("input_tokens") or usage.get("prompt_tokens")
    output_tokens = usage.get("output_tokens") or usage.get("completion_tokens")

    return {
        "input_tokens": int(input_tokens) if isinstance(input_tokens, (int, float)) else None,
        "output_tokens": int(output_tokens) if isinstance(output_tokens, (int, float)) else None,
        "model": model if isinstance(model, str) else None,
    }


async def run_agent_cli(
    agent: AgentType,
    prompt: str,
    timeout: int = 300,
    phase: Phase = Phase.ANALYSIS,
    *,
    session_id: str | None = None,
    task_id: str | None = None,
    round_number: int | None = None,
) -> AgentResult:
    """Run an agent via the local OpenCode server and capture output."""
    start_time = datetime.now(UTC)
    task_uuid = UUID(task_id) if task_id else None

    import importlib

    opencode_client_mod = importlib.import_module("debate.opencode_client")
    opencode_api_error = opencode_client_mod.OpencodeAPIError
    opencode_client_cls = opencode_client_mod.OpencodeClient

    client = opencode_client_cls(
        base_url=settings.opencode_api_url, directory=settings.opencode_directory
    )
    try:
        if settings.redis_rate_limit_enabled:
            from .rate_limit import wait_for_rate_limit

            allowed = await wait_for_rate_limit(agent.value)
            if not allowed:
                return AgentResult(
                    success=False,
                    raw_output="",
                    error="Rate limit timeout",
                    duration_seconds=int((datetime.now(UTC) - start_time).total_seconds()),
                    session_id=session_id,
                    response_json=None,
                )

        if task_uuid and round_number is not None:
            from .events import emit_agent_started

            await emit_agent_started(task_uuid, agent.value, round_number, phase.value)

        await client.health_check()

        if settings.opencode_directory is None:
            guessed = await client.guess_active_directory()
            if guessed:
                client.set_directory(guessed)

        if session_id is None:
            session_id = await client.create_session(
                title=f"debate:{agent.value}:{phase.value}:{id(prompt)}",
            )

        agent_config_key = f"debate_{agent.value}"
        resolved_model = await resolve_model(agent_config_key)

        result = await client.prompt(
            session_id=session_id,
            agent=agent.value,
            text=prompt,
            model={"id": resolved_model},
        )
        raw_output = result.raw_output
        if not raw_output:
            raw_output = await client.get_latest_assistant_text(session_id=session_id)
        if not raw_output:
            end_time = datetime.now(UTC)
            duration = int((end_time - start_time).total_seconds())
            return AgentResult(
                success=False,
                raw_output="",
                error="Empty response from OpenCode",
                duration_seconds=duration,
                session_id=session_id,
                response_json=result.response_json,
            )
        structured = extract_structured_output(raw_output)
        usage = _extract_token_usage(result.response_json)

        end_time = datetime.now(UTC)
        duration = int((end_time - start_time).total_seconds())

        if task_uuid and round_number is not None:
            from .events import emit_agent_completed

            await emit_agent_completed(
                task_uuid,
                agent.value,
                round_number,
                phase.value,
                duration_ms=duration * 1000,
            )

        return AgentResult(
            success=True,
            raw_output=raw_output,
            structured_output=structured,
            duration_seconds=duration,
            session_id=session_id,
            message_id=result.message_id,
            response_json=result.response_json,
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            model_used=usage.get("model"),
        )
    except opencode_api_error as e:
        end_time = datetime.now(UTC)
        duration = int((end_time - start_time).total_seconds())
        if task_uuid and round_number is not None:
            from .events import emit_agent_failed

            await emit_agent_failed(
                task_uuid,
                agent.value,
                round_number,
                phase.value,
                error=str(e),
                duration_ms=duration * 1000,
            )
        return AgentResult(
            success=False,
            raw_output="",
            error=str(e),
            duration_seconds=duration,
            session_id=session_id,
            response_json=None,
        )
    except Exception as e:
        end_time = datetime.now(UTC)
        duration = int((end_time - start_time).total_seconds())
        if task_uuid and round_number is not None:
            from .events import emit_agent_failed

            await emit_agent_failed(
                task_uuid,
                agent.value,
                round_number,
                phase.value,
                error=str(e),
                duration_ms=duration * 1000,
            )
        return AgentResult(
            success=False,
            raw_output="",
            error=str(e),
            duration_seconds=duration,
            session_id=session_id,
            response_json=None,
        )
    finally:
        await client.aclose()


async def process_agent_result(
    session: db.AsyncSession,
    task: Task,
    round_: Round,
    agent: AgentType,
    result: AgentResult,
    phase: Phase,
) -> Analysis:
    """Process agent result and store in database."""
    # Get or create analysis record
    analysis = await db.get_analysis(session, task, round_, agent.value)
    if analysis is None:
        analysis = await db.create_analysis(session, task, round_, agent.value)

    if result.success:
        await db.complete_analysis(
            session,
            analysis,
            summary=result.structured_output.get("summary") if result.structured_output else None,
            recommendations=result.structured_output.get("recommendations")
            if result.structured_output
            else None,
            concerns=result.structured_output.get("concerns") if result.structured_output else None,
            raw_output=result.raw_output,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            model_used=result.model_used,
        )

        # Insert findings and questions if we have structured output
        if result.structured_output and phase != Phase.EXPLORATION:
            findings = result.structured_output.get("findings", [])
            if findings:
                await db.add_findings(session, task, round_, analysis, agent.value, findings)
                console.print(f"[green]Inserted {len(findings)} findings[/green]")

            questions = result.structured_output.get("questions", [])
            if questions:
                await db.add_questions(session, task, round_, agent.value, questions)
                console.print(f"[green]Inserted {len(questions)} questions[/green]")
    else:
        await db.complete_analysis(
            session,
            analysis,
            raw_output=result.raw_output,
            error_message=result.error,
        )

    status = "completed" if result.success else "failed"
    agent_statuses = dict(getattr(round_, "agent_statuses", {}) or {})
    agent_statuses[agent.value] = status
    round_.agent_statuses = agent_statuses

    if agent in (AgentType.GEMINI, AgentType.CLAUDE):
        gemini = agent_statuses.get(AgentType.GEMINI.value)
        claude = agent_statuses.get(AgentType.CLAUDE.value)
        if gemini in ("completed", "failed") and claude in ("completed", "failed"):
            if gemini == "completed" and claude == "completed":
                round_.status = "completed"
            else:
                round_.status = "failed"

    if (
        result.input_tokens is not None
        and result.output_tokens is not None
        and result.model_used
        and result.success
    ):
        from .costs import TokenUsage, log_cost

        cost_log = await log_cost(
            session,
            task.id,
            agent.value,
            result.model_used,
            phase.value,
            TokenUsage(
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                model=result.model_used,
            ),
            analysis_id=analysis.id,
        )
        analysis.cost_estimate = cost_log.total_cost

    if phase == Phase.EXPLORATION and result.structured_output:
        await db.add_exploration(
            session,
            task,
            agent.value,
            result.structured_output,
            raw_output=result.raw_output,
        )

    # Log the event
    await db.log_event(
        session,
        task,
        Phase.ANALYSIS.value,
        "completed" if result.success else "failed",
        agent=agent.value,
        message=f"{agent.value} analysis {'completed' if result.success else 'failed'}",
        duration_ms=result.duration_seconds * 1000,
    )

    return analysis


async def run_agent(
    task_slug: str,
    agent: AgentType,
    round_number: int = 1,
    phase: Phase = Phase.ANALYSIS,
) -> bool:
    """Main function to run an agent for a task."""
    console.print(
        Panel(
            f"[bold]Agent Execution: {agent.value}[/bold]\n"
            f"Task: {task_slug} | Round: {round_number} | Phase: {phase.value}"
        )
    )

    async with db.get_session() as session:
        # Get task
        task = await db.get_task_by_slug(session, task_slug)
        if task is None:
            console.print(f"[red]Task not found: {task_slug}[/red]")
            return False

        # Get or create round
        round_ = await db.get_or_create_round(session, task, round_number)

        # Load agent instructions
        try:
            instructions = load_agent_instructions(agent)
        except FileNotFoundError as e:
            console.print(f"[red]{e}[/red]")
            return False

        # Build context from database
        context = await db.build_task_context(session, task, round_number)

        # Build complete prompt
        prompt = build_prompt(instructions, context, task_slug, round_number, phase)

        # Save prompt for debugging
        prompt_file = Path(f"/tmp/{agent.value}_{task_slug}_{round_number}_prompt.md")
        prompt_file.write_text(prompt)
        console.print(f"[dim]Prompt saved to: {prompt_file}[/dim]")

        # Run the agent
        result = await run_agent_cli(
            agent,
            prompt,
            timeout=settings.agent_timeout,
            phase=phase,
            task_id=task.id,
            round_number=round_number,
        )

        if result.success:
            console.print(f"[green]Agent completed in {result.duration_seconds}s[/green]")
            if result.structured_output:
                console.print("[green]Structured output extracted successfully[/green]")
            else:
                console.print("[yellow]No structured output found in response[/yellow]")
        else:
            console.print(f"[red]Agent failed: {result.error}[/red]")

        # Process and store results
        await process_agent_result(session, task, round_, agent, result, phase)

        # Save raw output
        output_file = Path(f"/tmp/{agent.value}_{task_slug}_{round_number}_output.md")
        output_file.write_text(result.raw_output)
        console.print(f"[dim]Output saved to: {output_file}[/dim]")

        return result.success


async def run_agent_by_role(
    task_slug: str,
    role: Role,
    round_number: int = 1,
    phase: Phase = Phase.ANALYSIS,
) -> bool:
    role_config: RoleConfig
    async with db.get_session() as session:
        role_config = await resolve_role(role, session)

    agent_key = role_config.get("agent_key", "")
    prompt_template = role_config.get("prompt_template", "")
    model_override = role_config.get("model")

    console.print(
        Panel(
            f"[bold]Role Execution: {role.value}[/bold]\n"
            f"Agent: {agent_key} | Model: {model_override or '(from model_config)'}\n"
            f"Task: {task_slug} | Round: {round_number} | Phase: {phase.value}"
        )
    )

    async with db.get_session() as session:
        task = await db.get_task_by_slug(session, task_slug)
        if task is None:
            console.print(f"[red]Task not found: {task_slug}[/red]")
            return False

        round_ = await db.get_or_create_round(session, task, round_number)

        try:
            instructions = load_instructions_from_template(prompt_template)
        except FileNotFoundError as e:
            console.print(f"[red]{e}[/red]")
            return False

        context = await db.build_task_context(session, task, round_number)
        prompt = build_prompt(instructions, context, task_slug, round_number, phase)

        prompt_file = Path(f"/tmp/{role.value}_{task_slug}_{round_number}_prompt.md")
        prompt_file.write_text(prompt)
        console.print(f"[dim]Prompt saved to: {prompt_file}[/dim]")

        result = await run_agent_cli_with_config(
            agent_key=agent_key,
            model=model_override,
            role=role,
            prompt=prompt,
            timeout=role_config.get("timeout_override") or settings.agent_timeout,
            phase=phase,
            task_id=task.id,
            round_number=round_number,
        )

        if result.success:
            console.print(
                f"[green]Role {role.value} completed in {result.duration_seconds}s[/green]"
            )
            if result.structured_output:
                console.print("[green]Structured output extracted successfully[/green]")
            else:
                console.print("[yellow]No structured output found in response[/yellow]")
        else:
            console.print(f"[red]Role {role.value} failed: {result.error}[/red]")

        await process_role_result(session, task, round_, role, agent_key, result, phase)

        output_file = Path(f"/tmp/{role.value}_{task_slug}_{round_number}_output.md")
        output_file.write_text(result.raw_output)
        console.print(f"[dim]Output saved to: {output_file}[/dim]")

        return result.success


async def run_agent_cli_with_config(
    agent_key: str,
    model: str | None,
    role: Role,
    prompt: str,
    timeout: int = 300,
    phase: Phase = Phase.ANALYSIS,
    *,
    session_id: str | None = None,
    task_id: str | None = None,
    round_number: int | None = None,
) -> AgentResult:
    start_time = datetime.now(UTC)
    task_uuid = UUID(task_id) if task_id else None

    import importlib

    opencode_client_mod = importlib.import_module("debate.opencode_client")
    opencode_api_error = opencode_client_mod.OpencodeAPIError
    opencode_client_cls = opencode_client_mod.OpencodeClient

    if model is None:
        model = await resolve_model(agent_key)

    client = opencode_client_cls(
        base_url=settings.opencode_api_url, directory=settings.opencode_directory
    )
    try:
        if settings.redis_rate_limit_enabled:
            from .rate_limit import wait_for_rate_limit

            allowed = await wait_for_rate_limit(role.value)
            if not allowed:
                return AgentResult(
                    success=False,
                    raw_output="",
                    error="Rate limit timeout",
                    duration_seconds=int((datetime.now(UTC) - start_time).total_seconds()),
                    session_id=session_id,
                    response_json=None,
                )

        if task_uuid and round_number is not None:
            from .events import emit_agent_started

            await emit_agent_started(task_uuid, role.value, round_number, phase.value)

        await client.health_check()

        if settings.opencode_directory is None:
            guessed = await client.guess_active_directory()
            if guessed:
                client.set_directory(guessed)

        if session_id is None:
            session_id = await client.create_session(
                title=f"debate:{role.value}:{phase.value}:{id(prompt)}",
            )

        agent_value = (
            agent_key.replace("debate_", "") if agent_key.startswith("debate_") else agent_key
        )
        result = await client.prompt(
            session_id=session_id,
            agent=agent_value,
            text=prompt,
            model={"id": model},
        )
        raw_output = result.raw_output
        if not raw_output:
            raw_output = await client.get_latest_assistant_text(session_id=session_id)
        if not raw_output:
            end_time = datetime.now(UTC)
            duration = int((end_time - start_time).total_seconds())
            return AgentResult(
                success=False,
                raw_output="",
                error="Empty response from OpenCode",
                duration_seconds=duration,
                session_id=session_id,
                response_json=result.response_json,
            )
        structured = extract_structured_output(raw_output)
        usage = _extract_token_usage(result.response_json)

        end_time = datetime.now(UTC)
        duration = int((end_time - start_time).total_seconds())

        if task_uuid and round_number is not None:
            from .events import emit_agent_completed

            await emit_agent_completed(
                task_uuid,
                role.value,
                round_number,
                phase.value,
                duration_ms=duration * 1000,
            )

        return AgentResult(
            success=True,
            raw_output=raw_output,
            structured_output=structured,
            duration_seconds=duration,
            session_id=session_id,
            message_id=result.message_id,
            response_json=result.response_json,
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            model_used=usage.get("model"),
        )
    except opencode_api_error as e:
        end_time = datetime.now(UTC)
        duration = int((end_time - start_time).total_seconds())
        if task_uuid and round_number is not None:
            from .events import emit_agent_failed

            await emit_agent_failed(
                task_uuid,
                role.value,
                round_number,
                phase.value,
                error=str(e),
                duration_ms=duration * 1000,
            )
        return AgentResult(
            success=False,
            raw_output="",
            error=str(e),
            duration_seconds=duration,
            session_id=session_id,
            response_json=None,
        )
    except Exception as e:
        end_time = datetime.now(UTC)
        duration = int((end_time - start_time).total_seconds())
        if task_uuid and round_number is not None:
            from .events import emit_agent_failed

            await emit_agent_failed(
                task_uuid,
                role.value,
                round_number,
                phase.value,
                error=str(e),
                duration_ms=duration * 1000,
            )
        return AgentResult(
            success=False,
            raw_output="",
            error=str(e),
            duration_seconds=duration,
            session_id=session_id,
            response_json=None,
        )
    finally:
        await client.aclose()


async def process_role_result(
    session: db.AsyncSession,
    task: Task,
    round_: Round,
    role: Role,
    agent_key: str,
    result: AgentResult,
    phase: Phase,
) -> Analysis:
    analysis = await db.get_analysis(session, task, round_, role.value)
    if analysis is None:
        analysis = await db.create_analysis(session, task, round_, role.value)

    if result.success:
        await db.complete_analysis(
            session,
            analysis,
            summary=result.structured_output.get("summary") if result.structured_output else None,
            recommendations=result.structured_output.get("recommendations")
            if result.structured_output
            else None,
            concerns=result.structured_output.get("concerns") if result.structured_output else None,
            raw_output=result.raw_output,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            model_used=result.model_used,
        )

        if result.structured_output and phase != Phase.EXPLORATION:
            findings = result.structured_output.get("findings", [])
            if findings:
                await db.add_findings(session, task, round_, analysis, role.value, findings)
                console.print(f"[green]Inserted {len(findings)} findings[/green]")

            questions = result.structured_output.get("questions", [])
            if questions:
                await db.add_questions(session, task, round_, role.value, questions)
                console.print(f"[green]Inserted {len(questions)} questions[/green]")
    else:
        await db.complete_analysis(
            session,
            analysis,
            raw_output=result.raw_output,
            error_message=result.error,
        )

    status = "completed" if result.success else "failed"
    agent_value = (
        agent_key.replace("debate_", "", 1) if agent_key.startswith("debate_") else agent_key
    )

    agent_statuses = dict(getattr(round_, "agent_statuses", {}) or {})
    agent_statuses[role.value] = status
    if agent_value:
        agent_statuses[agent_value] = status
    round_.agent_statuses = agent_statuses

    if role in (Role.PLANNER_PRIMARY, Role.PLANNER_SECONDARY):
        primary = agent_statuses.get(Role.PLANNER_PRIMARY.value)
        secondary = agent_statuses.get(Role.PLANNER_SECONDARY.value)
        if primary in ("completed", "failed") and secondary in ("completed", "failed"):
            if primary == "completed" and secondary == "completed":
                round_.status = "completed"
            else:
                round_.status = "failed"

    if (
        result.input_tokens is not None
        and result.output_tokens is not None
        and result.model_used
        and result.success
    ):
        from .costs import TokenUsage, log_cost

        cost_log = await log_cost(
            session,
            task.id,
            role.value,
            result.model_used,
            phase.value,
            TokenUsage(
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                model=result.model_used,
            ),
            analysis_id=analysis.id,
        )
        analysis.cost_estimate = cost_log.total_cost

    if phase == Phase.EXPLORATION and result.structured_output:
        await db.add_exploration(
            session,
            task,
            role.value,
            result.structured_output,
            raw_output=result.raw_output,
        )

    await db.log_event(
        session,
        task,
        phase.value,
        "completed" if result.success else "failed",
        agent=role.value,
        message=f"{role.value} ({agent_key}) {'completed' if result.success else 'failed'}",
        duration_ms=result.duration_seconds * 1000,
    )

    return analysis


@click.command()
@click.argument("agent", type=click.Choice([a.value for a in AgentType]))
@click.argument("task_slug")
@click.option("--round", "-r", "round_number", default=1, help="Round number")
@click.option(
    "--phase",
    "-p",
    default="analysis",
    type=click.Choice([p.value for p in Phase]),
    help="Workflow phase",
)
def main(agent: str, task_slug: str, round_number: int, phase: str) -> None:
    success = asyncio.run(run_agent(task_slug, AgentType(agent), round_number, Phase(phase)))
    sys.exit(0 if success else 1)


@click.command("run-role")
@click.argument("role", type=click.Choice([r.value for r in Role]))
@click.argument("task_slug")
@click.option("--round", "-r", "round_number", default=1, help="Round number")
@click.option(
    "--phase",
    "-p",
    default="analysis",
    type=click.Choice([p.value for p in Phase]),
    help="Workflow phase",
)
def run_role_cmd(role: str, task_slug: str, round_number: int, phase: str) -> None:
    success = asyncio.run(run_agent_by_role(task_slug, Role(role), round_number, Phase(phase)))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
