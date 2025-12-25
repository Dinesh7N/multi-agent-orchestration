"""Parallel agent invocation - runs multiple agents concurrently."""

import asyncio
import sys
from dataclasses import dataclass, field

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from debate.role_config import Role, resolve_role

from . import db
from .config import settings
from .run_agent import (
    AgentResult,
    AgentType,
    Phase,
    build_prompt,
    load_agent_instructions,
    load_instructions_from_template,
    process_agent_result,
    process_role_result,
    run_agent_cli,
    run_agent_cli_with_config,
)

console = Console()


@dataclass
class ParallelResult:
    results: dict[str, AgentResult] = field(default_factory=dict)
    both_succeeded: bool = False


async def invoke_parallel(
    task_slug: str,
    round_number: int = 1,
    agents: list[AgentType] | None = None,
    roles: list[Role] | None = None,
) -> ParallelResult:
    if roles is None and agents is None:
        roles = [Role.PLANNER_PRIMARY, Role.PLANNER_SECONDARY]

    console.print(
        f"[bold blue]Starting Parallel Execution: Round {round_number} for {task_slug}[/bold blue]"
    )

    async with db.get_session() as session:
        task = await db.get_task_by_slug(session, task_slug)
        if task is None:
            console.print(f"[red]Task not found: {task_slug}[/red]")
            return ParallelResult()

        await db.get_or_create_round(session, task, round_number)
        context = await db.build_task_context(session, task, round_number)

        role_agent_values: dict[str, str] = {}

        def agent_value_from_key(agent_key: str) -> str:
            if agent_key.startswith("debate_"):
                return agent_key.replace("debate_", "", 1)
            return agent_key

        async def run_single_role(role: Role) -> tuple[str, AgentResult]:
            try:
                role_config = await resolve_role(role, session)
                agent_key = role_config.get("agent_key", "")
                prompt_template = role_config.get("prompt_template", "")
                model_override = role_config.get("model")

                agent_value = agent_value_from_key(agent_key)
                role_agent_values[role.value] = agent_value

                instructions = load_instructions_from_template(prompt_template)
                prompt = build_prompt(
                    instructions, context, task_slug, round_number, Phase.ANALYSIS
                )

                previous_session_id: str | None = None
                if agent_value in (AgentType.GEMINI.value, AgentType.CLAUDE.value):
                    previous_session_id = await db.get_latest_agent_session_id(
                        session,
                        task,
                        agent_value,
                        before_round=round_number,
                    )

                result = await run_agent_cli_with_config(
                    agent_key=agent_key,
                    model=model_override,
                    role=role,
                    prompt=prompt,
                    timeout=role_config.get("timeout_override") or settings.agent_timeout,
                    session_id=previous_session_id,
                    task_id=task.id,
                    round_number=round_number,
                )

                async with db.get_session() as agent_session:
                    agent_task = await db.get_task_by_slug(agent_session, task_slug)
                    if not agent_task:
                        raise ValueError(f"Task not found in agent session: {task_slug}")

                    agent_round = await db.get_or_create_round(
                        agent_session, agent_task, round_number
                    )

                    if agent_value in (AgentType.GEMINI.value, AgentType.CLAUDE.value):
                        await db.set_round_agent_session_id(
                            agent_session,
                            agent_round,
                            agent_value,
                            result.session_id,
                        )

                    await process_role_result(
                        agent_session,
                        agent_task,
                        agent_round,
                        role,
                        agent_key,
                        result,
                        Phase.ANALYSIS,
                    )

                return role.value, result
            except Exception as e:
                return role.value, AgentResult(success=False, raw_output="", error=str(e))

        async def run_single_agent(agent: AgentType) -> tuple[str, AgentResult]:
            try:
                instructions = load_agent_instructions(agent)
                prompt = build_prompt(
                    instructions, context, task_slug, round_number, Phase.ANALYSIS
                )

                previous_session_id = await db.get_latest_agent_session_id(
                    session,
                    task,
                    agent.value,
                    before_round=round_number,
                )

                result = await run_agent_cli(
                    agent,
                    prompt,
                    timeout=settings.agent_timeout,
                    session_id=previous_session_id,
                    task_id=task.id,
                    round_number=round_number,
                )

                async with db.get_session() as agent_session:
                    agent_task = await db.get_task_by_slug(agent_session, task_slug)
                    if not agent_task:
                        raise ValueError(f"Task not found in agent session: {task_slug}")

                    agent_round = await db.get_or_create_round(
                        agent_session, agent_task, round_number
                    )

                    await db.set_round_agent_session_id(
                        agent_session,
                        agent_round,
                        agent.value,
                        result.session_id,
                    )

                    await process_agent_result(
                        agent_session,
                        agent_task,
                        agent_round,
                        agent,
                        result,
                        Phase.ANALYSIS,
                    )

                return agent.value, result
            except Exception as e:
                return agent.value, AgentResult(success=False, raw_output="", error=str(e))

        run_keys: list[str] = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            if roles is not None:
                task_ids = {
                    role.value: progress.add_task(f"Running {role.value}...", total=None)
                    for role in roles
                }
                run_keys = [role.value for role in roles]
                results = await asyncio.gather(
                    *[run_single_role(role) for role in roles],
                    return_exceptions=True,
                )
                for role_value in run_keys:
                    progress.update(task_ids[role_value], completed=True)
            else:
                agent_list = agents or [AgentType.GEMINI, AgentType.CLAUDE]
                task_ids = {
                    agent.value: progress.add_task(f"Running {agent.value}...", total=None)
                    for agent in agent_list
                }
                run_keys = [agent.value for agent in agent_list]
                results = await asyncio.gather(
                    *[run_single_agent(agent) for agent in agent_list],
                    return_exceptions=True,
                )
                for agent_value in run_keys:
                    progress.update(task_ids[agent_value], completed=True)

        parallel_result = ParallelResult()
        success_count = 0

        for item in results:
            if isinstance(item, BaseException):
                console.print(f"[red]Agent error: {item}[/red]")
                continue

            key, result = item
            parallel_result.results[key] = result

            if result.success:
                success_count += 1
                console.print(f"[green]{key} completed in {result.duration_seconds}s[/green]")
            else:
                console.print(f"[red]{key} failed: {result.error}[/red]")

        parallel_result.both_succeeded = success_count == len(run_keys)

        async with db.get_session() as update_session:
            update_task = await db.get_task_by_slug(update_session, task_slug)
            if update_task:
                round_to_update = await db.get_or_create_round(
                    update_session,
                    update_task,
                    round_number,
                )

                agent_statuses = dict(getattr(round_to_update, "agent_statuses", {}) or {})

                if roles is not None:
                    for role_value, result in parallel_result.results.items():
                        status = "completed" if result.success else "failed"
                        agent_statuses[role_value] = status

                        agent_value = role_agent_values.get(role_value)
                        if agent_value:
                            agent_statuses[agent_value] = status

                else:
                    if AgentType.GEMINI.value in parallel_result.results:
                        r = parallel_result.results[AgentType.GEMINI.value]
                        status = "completed" if r.success else "failed"
                        agent_statuses[AgentType.GEMINI.value] = status
                    if AgentType.CLAUDE.value in parallel_result.results:
                        r = parallel_result.results[AgentType.CLAUDE.value]
                        status = "completed" if r.success else "failed"
                        agent_statuses[AgentType.CLAUDE.value] = status

                round_to_update.agent_statuses = agent_statuses

                if parallel_result.both_succeeded:
                    round_to_update.status = "completed"
                    console.print("[bold green]Parallel run completed successfully[/bold green]")
                else:
                    console.print("[yellow]One or more roles/agents failed[/yellow]")
            else:
                console.print(f"[red]Could not update status: Task {task_slug} not found[/red]")

        return parallel_result


@click.command()
@click.argument("task_slug")
@click.option("--round", "-r", "round_number", default=1, help="Round number")
@click.option(
    "--agents",
    "-a",
    multiple=True,
    type=click.Choice([a.value for a in AgentType]),
    help="Agents to run (default: gemini, claude)",
)
def main(task_slug: str, round_number: int, agents: tuple[str, ...]) -> None:
    """Run agents in parallel for a task.

    TASK_SLUG: The task slug (e.g., auth-refactor)
    """
    agent_list = [AgentType(a) for a in agents] if agents else None
    result = asyncio.run(invoke_parallel(task_slug, round_number, agent_list))
    sys.exit(0 if result.both_succeeded else 1)


if __name__ == "__main__":
    main()
