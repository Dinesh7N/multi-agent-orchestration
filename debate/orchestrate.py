"""Main orchestrator - coordinates the multi-agent debate workflow."""

import asyncio
import re
import sys
from dataclasses import dataclass

import click
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from . import db
from .config import settings
from .invoke_parallel import invoke_parallel
from .models import Consensus, Task
from .role_config import Role, resolve_role
from .run_agent import AgentType, Phase, run_agent_by_role
from .triage import TaskTriager

console = Console()


@dataclass
class TaskScope:
    """Scoped task information."""

    slug: str
    title: str
    description: str
    scope: str
    complexity: str  # 'trivial', 'standard', 'complex'


def generate_slug(title: str) -> str:
    """Generate a kebab-case slug from a title."""
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")[:50]


def assess_complexity(description: str) -> str:
    """Assess task complexity based on description."""
    description_lower = description.lower()

    # Complex indicators
    complex_keywords = [
        "architecture",
        "security",
        "refactor",
        "migration",
        "redesign",
        "multi-component",
    ]
    if any(kw in description_lower for kw in complex_keywords):
        return "complex"

    # Trivial indicators
    trivial_keywords = ["typo", "fix bug", "simple", "quick", "update comment", "rename"]
    if any(kw in description_lower for kw in trivial_keywords):
        return "trivial"

    return "standard"


async def phase_0_exploration(task: Task, session: db.AsyncSession) -> bool:
    """Phase 0: Optional codebase exploration."""
    console.print("\n[bold]Phase 0: Exploration (Optional)[/bold]")

    explore = Confirm.ask(
        "Would you like the Explorer role to scan the codebase first?", default=False
    )
    if not explore:
        console.print("[dim]Skipping exploration...[/dim]")
        return True

    success = await run_agent_by_role(
        task.slug, Role.EXPLORER, round_number=0, phase=Phase.EXPLORATION
    )

    if success:
        console.print("[green]Exploration complete![/green]")
    else:
        console.print("[yellow]Exploration had issues, but continuing...[/yellow]")

    return True


async def phase_1_scoping(user_request: str) -> Task:
    """Phase 1: Scoping and task creation."""
    console.print("\n[bold]Phase 1: Scoping & Task Creation[/bold]")

    # Generate task metadata
    title = user_request[:100]
    slug = generate_slug(title)
    complexity = assess_complexity(user_request)

    console.print(f"  Task: {title}")
    console.print(f"  Slug: {slug}")
    console.print(f"  Complexity: {complexity}")

    # Create task in database
    async with db.get_session() as session:
        task = await db.create_task(
            session,
            slug=slug,
            title=title,
            complexity=complexity,
            metadata={"description": user_request, "scope": "auto-detected"},
        )

        # Store the user's message
        await db.add_conversation(session, task, "human", user_request, "scoping")

        # Log the event
        await db.log_event(
            session,
            task,
            "scoping",
            "task_created",
            message=f"Task created: {slug}",
            details={"complexity": complexity},
        )

        # Automated triage
        conversations = await db.get_conversations(session, task)
        triager = TaskTriager()
        triage_result = await triager.classify(session, task, conversations)
        task.complexity = triage_result.complexity.value
        await db.log_event(
            session,
            task,
            "scoping",
            "triage_classified",
            details={
                "complexity": triage_result.complexity.value,
                "confidence": triage_result.confidence,
                "reasons": triage_result.reasons,
                "recommended_action": triage_result.recommended_action,
            },
        )

        console.print(f"[green]Task created in database (ID: {task.id})[/green]")

        return task


async def phase_2_analysis(task: Task, round_number: int = 1) -> bool:
    """Phase 2: Parallel analysis by agents."""
    console.print(f"\n[bold]Phase 2: Parallel Analysis (Round {round_number})[/bold]")

    if settings.redis_queue_enabled:
        from .queue import JobPayload, enqueue_job, wait_for_round_status

        def agent_value_from_key(agent_key: str) -> str:
            return (
                agent_key.replace("debate_", "", 1)
                if agent_key.startswith("debate_")
                else agent_key
            )

        async with db.get_session() as session:
            primary_cfg = await resolve_role(Role.PLANNER_PRIMARY, session)
            secondary_cfg = await resolve_role(Role.PLANNER_SECONDARY, session)

        primary_agent = agent_value_from_key(primary_cfg.get("agent_key", ""))
        secondary_agent = agent_value_from_key(secondary_cfg.get("agent_key", ""))

        queue_supported = {AgentType.GEMINI.value, AgentType.CLAUDE.value}
        if primary_agent in queue_supported and secondary_agent in queue_supported:
            jobs = [
                JobPayload(
                    task_id=task.id,
                    task_slug=task.slug,
                    round_number=round_number,
                    agent=primary_agent,
                    phase=Phase.ANALYSIS.value,
                    role=Role.PLANNER_PRIMARY.value,
                ),
                JobPayload(
                    task_id=task.id,
                    task_slug=task.slug,
                    round_number=round_number,
                    agent=secondary_agent,
                    phase=Phase.ANALYSIS.value,
                    role=Role.PLANNER_SECONDARY.value,
                ),
            ]
            for job in jobs:
                await enqueue_job(job)

            return await wait_for_round_status(
                task.slug, round_number, timeout_seconds=settings.round_timeout
            )

        console.print(
            "[yellow]Redis queue enabled, but planner roles map to unsupported agents. "
            "Falling back to direct parallel execution.[/yellow]"
        )

    result = await invoke_parallel(task.slug, round_number)

    return result.both_succeeded


async def phase_3_questions(task: Task) -> bool:
    """Phase 3: Question resolution."""
    console.print("\n[bold]Phase 3: Question Resolution[/bold]")

    async with db.get_session() as session:
        # Refresh task
        refreshed_task = await db.get_task_by_slug(session, task.slug)
        if not refreshed_task:
            console.print(f"[red]Task not found: {task.slug}[/red]")
            return False
        task = refreshed_task

        questions = await db.get_pending_questions(session, task)

        if not questions:
            console.print("[dim]No pending questions from agents.[/dim]")
            return True

        console.print(f"[yellow]{len(questions)} questions need your input:[/yellow]\n")

        for i, q in enumerate(questions, 1):
            console.print(f"[bold]{i}. [{q.agent}] {q.question}[/bold]")
            if q.context:
                console.print(f"   [dim]Context: {q.context}[/dim]")

            answer = Prompt.ask("   Your answer (or 'skip')")
            if answer.lower() != "skip":
                await db.answer_question(session, q, answer, "human")
                console.print("   [green]Answer recorded.[/green]")
            else:
                q.status = "skipped"
                console.print("   [dim]Skipped.[/dim]")

        return True


async def phase_4_consensus(task: Task, final_round: int) -> Consensus | None:
    """Phase 4: Build consensus from analyses."""
    console.print("\n[bold]Phase 4: Building Consensus[/bold]")

    async with db.get_session() as session:
        refreshed_task = await db.get_task_by_slug(session, task.slug)
        if not refreshed_task:
            console.print("[red]Task not found[/red]")
            return None
        task = refreshed_task

        from .consensus import calculate_round_consensus

        round_obj = await db.get_or_create_round(session, task, final_round)
        agreement_rate, breakdown = await calculate_round_consensus(session, round_obj)
        await db.complete_round(session, round_obj, agreement_rate, breakdown.to_dict())
        console.print(f"  Agreement rate: {agreement_rate:.1f}%")
        try:
            from .events import emit_consensus_calculated

            await emit_consensus_calculated(
                task_id=round_obj.task_id,
                round_number=round_obj.round_number,
                agreement_rate=agreement_rate,
                breakdown=breakdown.to_dict(),
            )
        except Exception:
            pass

        # Collect recommendations
        analyses = await db.get_analyses_for_round(session, round_obj.id)
        all_recommendations: list[str] = []
        for a in analyses:
            if a.recommendations:
                all_recommendations.extend(
                    a.recommendations if isinstance(a.recommendations, list) else []
                )

        # Create consensus
        consensus = await db.create_consensus(
            session,
            task,
            final_round=final_round,
            summary=f"Consensus from {len(analyses)} analyses",
            agreement_rate=agreement_rate,
            agreed_items=list(set(all_recommendations))[:10],
            implementation_plan=[],
        )

        console.print(f"[green]Consensus created (ID: {consensus.id})[/green]")
        return consensus


async def phase_5_approval(task: Task, consensus: Consensus) -> bool:
    """Phase 5: Human approval."""
    console.print("\n[bold]Phase 5: Human Approval[/bold]")

    # Display summary
    table = Table(title="Debate Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Task", task.slug)
    table.add_row("Agreement Rate", f"{consensus.agreement_rate or 0:.1f}%")
    table.add_row("Agreed Items", str(len(consensus.agreed_items or [])))

    console.print(table)

    if consensus.agreed_items:
        console.print("\n[bold]Recommendations:[/bold]")
        for i, item in enumerate(consensus.agreed_items[:5], 1):
            console.print(f"  {i}. {item}")

    # Get approval
    console.print("\n[bold]Options:[/bold]")
    console.print("  [green]approve[/green] - Proceed with implementation")
    console.print("  [yellow]revise[/yellow] - Run another analysis round")
    console.print("  [red]cancel[/red] - Cancel the task")

    choice = Prompt.ask("Your decision", choices=["approve", "revise", "cancel"], default="approve")

    async with db.get_session() as session:
        refreshed_task = await db.get_task_by_slug(session, task.slug)
        if not refreshed_task:
            console.print("[red]Task not found[/red]")
            return False
        task = refreshed_task
        consensus_to_update = await db.get_consensus(session, task)

        if not consensus_to_update:
            console.print("[red]Consensus not found[/red]")
            return False

        if choice == "approve":
            await db.approve_consensus(session, consensus_to_update)
            await db.update_task_status(session, task, "approved")
            console.print("[green]Task approved! Ready for implementation.[/green]")
            return True
        elif choice == "revise":
            console.print("[yellow]Running another round...[/yellow]")
            return False
        else:
            await db.update_task_status(session, task, "cancelled", "User cancelled")
            console.print("[red]Task cancelled.[/red]")
            return True


async def orchestrate(user_request: str) -> bool:
    """Main orchestration workflow."""
    console.print(
        Panel(
            f"[bold]Multi-Agent Debate Orchestrator[/bold]\n\n{user_request}",
            title="New Task",
            border_style="blue",
        )
    )

    if settings.redis_queue_enabled:
        from .reconciliation import reconcile_running_rounds

        await reconcile_running_rounds()

    # Phase 1: Scoping
    task = await phase_1_scoping(user_request)

    # Check complexity for fast-track
    if task.complexity == "trivial":
        if settings.triage_shadow_mode:
            console.print(
                "[yellow]Triage shadow mode: fast-track suggested but not applied.[/yellow]"
            )
            async with db.get_session() as session:
                task = await db.get_task_by_slug(session, task.slug)
                if task:
                    await db.log_event(
                        session,
                        task,
                        "scoping",
                        "triage_shadow_mode",
                        details={"recommended_action": "fast_track"},
                    )
        else:
            if Confirm.ask("This looks like a trivial task. Skip the debate?", default=True):
                console.print("[green]Fast-tracking trivial task...[/green]")
                async with db.get_session() as session:
                    task = await db.get_task_by_slug(session, task.slug)
                    if task:
                        await db.update_task_status(session, task, "approved")
                return True

    # Phase 0: Optional exploration
    async with db.get_session() as session:
        # Avoid accessing task.slug when task is None
        current_slug = task.slug
        refreshed_task = await db.get_task_by_slug(session, current_slug)
        if not refreshed_task:
            console.print(f"[red]Task not found: {current_slug}[/red]")
            return False
        task = refreshed_task
        await phase_0_exploration(task, session)

    # Iterative debate loop
    max_rounds = settings.max_rounds if task.complexity == "complex" else 2
    current_round = 1

    while current_round <= max_rounds:
        # Phase 2: Analysis
        async with db.get_session() as session:
            current_slug = task.slug
            refreshed_task = await db.get_task_by_slug(session, current_slug)
            if not refreshed_task:
                console.print(f"[red]Task not found: {current_slug}[/red]")
                return False
            task = refreshed_task

        success = await phase_2_analysis(task, current_round)
        if not success:
            console.print("[red]Analysis phase failed.[/red]")
            if not Confirm.ask("Continue anyway?", default=False):
                return False

        # Phase 3: Questions
        async with db.get_session() as session:
            current_slug = task.slug
            refreshed_task = await db.get_task_by_slug(session, current_slug)
            if not refreshed_task:
                console.print(f"[red]Task not found: {current_slug}[/red]")
                return False
            task = refreshed_task
        await phase_3_questions(task)

        # Phase 4: Consensus
        async with db.get_session() as session:
            current_slug = task.slug
            refreshed_task = await db.get_task_by_slug(session, current_slug)
            if not refreshed_task:
                console.print(f"[red]Task not found: {current_slug}[/red]")
                return False
            task = refreshed_task
        consensus = await phase_4_consensus(task, current_round)
        if not consensus:
            console.print("[red]Failed to build consensus.[/red]")
            return False

        # Check if we have enough agreement
        if consensus.agreement_rate and consensus.agreement_rate >= settings.consensus_threshold:
            rate = consensus.agreement_rate
            thresh = settings.consensus_threshold
            console.print(f"[green]Consensus reached ({rate:.1f}% >= {thresh}%)[/green]")
            break

        # Phase 5: Approval
        async with db.get_session() as session:
            current_slug = task.slug
            refreshed_task = await db.get_task_by_slug(session, current_slug)
            if not refreshed_task:
                console.print(f"[red]Task not found: {current_slug}[/red]")
                return False
            task = refreshed_task
            consensus = await db.get_consensus(session, task)
            if not consensus:
                console.print(f"[red]Consensus not found for task: {current_slug}[/red]")
                return False

        approved = await phase_5_approval(task, consensus)
        if approved:
            break

        current_round += 1
        console.print(f"\n[bold]Starting Round {current_round}...[/bold]\n")

    console.print("\n[bold green]Orchestration complete![/bold green]")
    console.print(f"Task: {task.slug}")
    console.print("Status: Check database for full details")

    return True


@click.command()
@click.argument("request", nargs=-1, required=True)
def main(request: tuple[str, ...]) -> None:
    """Orchestrate a multi-agent debate.

    REQUEST: The task description (e.g., "Add user authentication to the API")
    """
    user_request = " ".join(request)
    success = asyncio.run(orchestrate(user_request))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
