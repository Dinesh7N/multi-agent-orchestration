"""Main CLI entry point for debate-workflow."""

import asyncio
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import db
from .config import settings
from .invoke_parallel import invoke_parallel
from .orchestrate import orchestrate
from .role_config import Role
from .run_agent import AgentType, run_agent
from .verify import verify_task

console = Console()


@click.group()
@click.version_option(version="0.1.0")
def main() -> None:
    """Multi-agent debate workflow CLI.

    Orchestrate AI agents (Gemini, Claude, Codex) to analyze and implement code changes.
    """
    pass


@main.command()
@click.argument("request")
@click.option("--skip-explore", is_flag=True, help="Skip exploration phase")
@click.option("--max-rounds", default=3, help="Maximum debate rounds")
def start(request: str, skip_explore: bool, max_rounds: int) -> None:
    """Start a new task with the given request.

    REQUEST: Description of what you want to accomplish
    """
    asyncio.run(orchestrate(request))


@main.command()
@click.argument("task_slug")
def status(task_slug: str) -> None:
    """Show status of a task.

    TASK_SLUG: The task identifier (e.g., auth-refactor)
    """

    async def show_status() -> None:
        async with db.get_session() as session:
            task = await db.get_task_by_slug(session, task_slug)
            if not task:
                console.print(f"[red]Task not found: {task_slug}[/red]")
                return

            # Task info panel
            console.print(
                Panel(
                    f"[bold]{task.title}[/bold]\n\n"
                    f"Status: [cyan]{task.status}[/cyan]\n"
                    f"Round: {task.current_round}/{task.max_rounds}\n"
                    f"Created: {task.created_at.strftime('%Y-%m-%d %H:%M')}\n"
                    f"Complexity: {task.complexity or 'Not assessed'}",
                    title=f"Task: {task.slug}",
                )
            )

            # Get rounds
            from sqlalchemy import select

            from .models import Round

            result = await session.execute(
                select(Round).where(Round.task_id == task.id).order_by(Round.round_number)
            )
            rounds = result.scalars().all()

            if rounds:
                table = Table(title="Debate Rounds")
                table.add_column("Round", style="cyan")
                table.add_column("Status")
                table.add_column("Agent Statuses")
                table.add_column("Agreement")

                for r in rounds:
                    statuses = r.agent_statuses or {}
                    if isinstance(statuses, dict) and statuses:
                        status_str = ", ".join(
                            f"{k}:{v}" for k, v in sorted(statuses.items()) if isinstance(k, str)
                        )
                    else:
                        status_str = "-"

                    table.add_row(
                        str(r.round_number),
                        r.status,
                        status_str,
                        f"{r.agreement_rate}%" if r.agreement_rate else "-",
                    )
                console.print(table)

    asyncio.run(show_status())


@main.command()
@click.option("--limit", default=10, help="Number of tasks to show")
@click.option("--status-filter", "status_filter", default=None, help="Filter by status")
def list_tasks(limit: int, status_filter: str | None) -> None:
    """List recent tasks."""

    async def list_all() -> None:
        async with db.get_session() as session:
            from sqlalchemy import select

            from .models import Task

            query = select(Task).order_by(Task.created_at.desc()).limit(limit)
            if status_filter:
                query = query.where(Task.status == status_filter)

            result = await session.execute(query)
            tasks = result.scalars().all()

            if not tasks:
                console.print("[yellow]No tasks found[/yellow]")
                return

            table = Table(title="Tasks")
            table.add_column("Slug", style="cyan")
            table.add_column("Title")
            table.add_column("Status")
            table.add_column("Round")
            table.add_column("Created")

            for t in tasks:
                table.add_row(
                    t.slug,
                    t.title[:40] + "..." if len(t.title) > 40 else t.title,
                    t.status,
                    f"{t.current_round}/{t.max_rounds}",
                    t.created_at.strftime("%Y-%m-%d %H:%M"),
                )
            console.print(table)

    asyncio.run(list_all())


@main.command()
@click.argument("task_slug")
@click.argument("agent", type=click.Choice(["gemini", "claude", "codex"]))
@click.option("--round", "-r", "round_number", default=1, help="Round number")
@click.option("--phase", default="analysis", help="Workflow phase")
def run(task_slug: str, agent: str, round_number: int, phase: str) -> None:
    """Run a specific agent for a task.

    TASK_SLUG: The task identifier
    AGENT: Which agent to run (gemini, claude, codex)
    """
    from .run_agent import Phase

    agent_type = AgentType(agent)
    phase_enum = Phase(phase)
    asyncio.run(run_agent(task_slug, agent_type, round_number=round_number, phase=phase_enum))


@main.command(name="run-role")
@click.argument("task_slug")
@click.argument("role", type=click.Choice([r.value for r in Role]))
@click.option("--round", "-r", "round_number", default=1, help="Round number")
@click.option("--phase", default="analysis", help="Workflow phase")
def run_role(task_slug: str, role: str, round_number: int, phase: str) -> None:
    from .run_agent import Phase, run_agent_by_role

    phase_enum = Phase(phase)
    asyncio.run(
        run_agent_by_role(task_slug, Role(role), round_number=round_number, phase=phase_enum)
    )


@main.command()
@click.argument("task_slug")
@click.option("--round", "-r", "round_number", default=1, help="Round number")
def parallel(task_slug: str, round_number: int) -> None:
    """Run planner roles in parallel for a task.

    Defaults to planner_primary + planner_secondary (see `debate role-config`).

    TASK_SLUG: The task identifier
    """
    asyncio.run(invoke_parallel(task_slug, round_number))


@main.command(name="schema-check", help="Check DB schema readiness for current code.")
def schema_check() -> None:
    async def check() -> None:
        from sqlalchemy import text

        async with db.get_session() as session:
            result = await session.execute(
                text(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'rounds'
                    """
                )
            )
            columns = {row[0] for row in result}

            required = {"agent_statuses", "agent_session_ids"}
            legacy = {
                "gemini_status",
                "claude_status",
                "gemini_session_id",
                "claude_session_id",
            }

            missing = required - columns
            present_legacy = legacy & columns

            if missing:
                console.print(f"[red]Missing required columns: {sorted(missing)}[/red]")
                console.print("Run: `uv run alembic upgrade head`")
                raise SystemExit(1)

            console.print("[green]Schema ready[/green]")
            if present_legacy:
                console.print(
                    f"[yellow]Legacy columns still present: {sorted(present_legacy)}[/yellow]"
                )
                console.print("Optional: run the drop-legacy-columns migration after stabilization")

    asyncio.run(check())


@main.command()
@click.argument("task_slug")
@click.option("--cwd", "-C", type=click.Path(exists=True, path_type=Path), help="Working directory")
def verify(task_slug: str, cwd: Path | None) -> None:
    """Verify implementation for a task.

    TASK_SLUG: The task identifier
    """
    result = asyncio.run(verify_task(task_slug, cwd))
    raise SystemExit(0 if result.overall_status == "passed" else 1)


@main.command()
@click.argument("task_slug")
def resume(task_slug: str) -> None:
    """Resume a paused or failed task.

    TASK_SLUG: The task identifier
    """

    async def do_resume() -> None:
        async with db.get_session() as session:
            task = await db.get_task_by_slug(session, task_slug)
            if not task:
                console.print(f"[red]Task not found: {task_slug}[/red]")
                return

            if task.status == "completed":
                console.print(f"[yellow]Task {task_slug} is already completed[/yellow]")
                return

            console.print(f"[green]Resuming task: {task_slug}[/green]")
            console.print(f"Current status: {task.status}, Round: {task.current_round}")

            # Build context and continue orchestration
            context = await db.build_task_context(session, task, task.current_round)

        await orchestrate(context.get("original_request", task.title))

    asyncio.run(do_resume())


@main.command()
@click.argument("task_slug")
@click.argument("question_id")
@click.argument("answer")
def answer(task_slug: str, question_id: str, answer_text: str) -> None:
    """Answer a pending question for a task.

    TASK_SLUG: The task identifier
    QUESTION_ID: The question UUID
    ANSWER: Your answer text
    """

    async def do_answer() -> None:
        async with db.get_session() as session:
            from sqlalchemy import select, update

            from .models import Question

            result = await session.execute(select(Question).where(Question.id == question_id))
            question = result.scalar_one_or_none()

            if not question:
                console.print(f"[red]Question not found: {question_id}[/red]")
                return

            from datetime import UTC, datetime

            await session.execute(
                update(Question)
                .where(Question.id == question_id)
                .values(
                    answer=answer_text,
                    answered_by="human",
                    status="answered",
                    answered_at=datetime.now(UTC),
                )
            )
            await session.commit()
            console.print(f"[green]Answer recorded for question {question_id}[/green]")

    asyncio.run(do_answer())


@main.command()
@click.argument("task_slug")
def questions(task_slug: str) -> None:
    """List pending questions for a task.

    TASK_SLUG: The task identifier
    """

    async def show_questions() -> None:
        async with db.get_session() as session:
            task = await db.get_task_by_slug(session, task_slug)
            if not task:
                console.print(f"[red]Task not found: {task_slug}[/red]")
                return

            from sqlalchemy import select

            from .models import Question

            result = await session.execute(
                select(Question)
                .where(Question.task_id == task.id)
                .where(Question.status == "pending")
                .order_by(Question.created_at)
            )
            questions_list = result.scalars().all()

            if not questions_list:
                console.print("[yellow]No pending questions[/yellow]")
                return

            for q in questions_list:
                console.print(
                    Panel(
                        f"[bold]{q.question}[/bold]\n\n"
                        f"From: [cyan]{q.agent}[/cyan]\n"
                        f"Category: {q.category or 'General'}\n"
                        f"Context: {q.context or 'None provided'}",
                        title=f"Question {q.id}",
                    )
                )

    asyncio.run(show_questions())


@main.command()
def db_info() -> None:
    """Show database connection info."""
    console.print(
        Panel(
            f"Host: {settings.db_host}\n"
            f"Port: {settings.db_port}\n"
            f"Database: {settings.db_name}\n"
            f"User: {settings.db_user}",
            title="Database Configuration",
        )
    )


@main.command()
def agents() -> None:
    """List currently running agents."""
    from .config import RUNNING_AGENTS

    if not RUNNING_AGENTS:
        console.print("[yellow]No agents currently running[/yellow]")
        return

    table = Table(title="Running Agents")
    table.add_column("Key", style="cyan")
    table.add_column("PID", style="green")
    table.add_column("Status")

    import os

    for key, pid in RUNNING_AGENTS.items():
        # Check if process is still running
        try:
            os.kill(pid, 0)  # Signal 0 just checks if process exists
            status = "[green]Running[/green]"
        except OSError:
            status = "[red]Dead[/red]"

        table.add_row(key, str(pid), status)

    console.print(table)


@main.command()
@click.argument("identifier")
@click.option("--force", "-f", is_flag=True, help="Force kill (SIGKILL instead of SIGTERM)")
def kill(identifier: str, force: bool) -> None:
    """Kill a running agent by key or PID.

    IDENTIFIER: Agent key (e.g., 'gemini_12345') or PID number
    """
    import os
    import signal

    from .config import RUNNING_AGENTS

    pid: int | None = None

    # Check if identifier is a PID
    if identifier.isdigit():
        pid = int(identifier)
    else:
        # Look up by key
        pid = RUNNING_AGENTS.get(identifier)

    if pid is None:
        console.print(f"[red]Agent not found: {identifier}[/red]")
        console.print("[dim]Use 'debate agents' to list running agents[/dim]")
        return

    sig = signal.SIGKILL if force else signal.SIGTERM

    try:
        os.kill(pid, sig)
        console.print(f"[green]Sent {'SIGKILL' if force else 'SIGTERM'} to PID {pid}[/green]")

        # Remove from tracking
        for key, p in list(RUNNING_AGENTS.items()):
            if p == pid:
                del RUNNING_AGENTS[key]
                break

    except ProcessLookupError:
        console.print(f"[yellow]Process {pid} not found (already dead?)[/yellow]")
    except PermissionError:
        console.print(f"[red]Permission denied to kill PID {pid}[/red]")


@main.command()
@click.option("--force", "-f", is_flag=True, help="Force kill all")
def kill_all(force: bool) -> None:
    """Kill all running agents."""
    import os
    import signal

    from .config import RUNNING_AGENTS

    if not RUNNING_AGENTS:
        console.print("[yellow]No agents currently running[/yellow]")
        return

    sig = signal.SIGKILL if force else signal.SIGTERM
    killed = 0

    for key, pid in list(RUNNING_AGENTS.items()):
        try:
            os.kill(pid, sig)
            console.print(f"[green]Killed {key} (PID {pid})[/green]")
            killed += 1
        except ProcessLookupError:
            console.print(f"[yellow]{key} (PID {pid}) already dead[/yellow]")
        except PermissionError:
            console.print(f"[red]Permission denied: {key} (PID {pid})[/red]")

    RUNNING_AGENTS.clear()
    console.print(f"\n[bold]Killed {killed} agent(s)[/bold]")


# =============================================================================
# Agent-facing commands (for use in agent prompts instead of raw SQL)
# =============================================================================


@main.command()
@click.argument("slug")
@click.argument("title")
@click.option(
    "--complexity", "-c", default="standard", type=click.Choice(["trivial", "standard", "complex"])
)
@click.option("--max-rounds", "-r", default=3, help="Maximum debate rounds")
def create_task(slug: str, title: str, complexity: str, max_rounds: int) -> None:
    """Create a new task in the database.

    SLUG: Task identifier (kebab-case)
    TITLE: Human-readable task title
    """

    async def do_create() -> None:
        async with db.get_session() as session:
            # Check if task already exists
            existing = await db.get_task_by_slug(session, slug)
            if existing:
                console.print(f"[yellow]Task already exists: {slug}[/yellow]")
                console.print(
                    f'{{"id": "{existing.id}", "slug": "{existing.slug}", "status": "exists"}}'
                )
                return

            task = await db.create_task(
                session,
                slug=slug,
                title=title,
                complexity=complexity,
                metadata={"max_rounds": max_rounds},
            )
            console.print(f'{{"id": "{task.id}", "slug": "{task.slug}", "status": "created"}}')

    asyncio.run(do_create())


@main.command()
@click.argument("task_slug")
@click.argument("role", type=click.Choice(["human", "orchestrator", "gemini", "claude", "codex"]))
@click.argument("content")
@click.option("--phase", "-p", default="scoping", help="Workflow phase")
def add_message(task_slug: str, role: str, content: str, phase: str) -> None:
    """Add a conversation message to a task.

    TASK_SLUG: The task identifier
    ROLE: Who sent the message
    CONTENT: The message content
    """

    async def do_add() -> None:
        async with db.get_session() as session:
            task = await db.get_task_by_slug(session, task_slug)
            if not task:
                console.print(f'{{"error": "Task not found: {task_slug}"}}')
                raise SystemExit(1)

            conv = await db.add_conversation(session, task, role, content, phase)
            console.print(f'{{"id": "{conv.id}", "status": "added"}}')

    asyncio.run(do_add())


@main.command()
@click.argument("task_slug")
@click.option("--round", "-r", "round_number", default=1, help="Round number for context")
def get_context(task_slug: str, round_number: int) -> None:
    """Get full task context as JSON (for agent prompts).

    TASK_SLUG: The task identifier
    """
    import json

    async def do_get() -> None:
        async with db.get_session() as session:
            task = await db.get_task_by_slug(session, task_slug)
            if not task:
                console.print(f'{{"error": "Task not found: {task_slug}"}}')
                raise SystemExit(1)

            context = await db.build_task_context(session, task, round_number)
            console.print(json.dumps(context, indent=2, default=str))

    asyncio.run(do_get())


@main.command()
@click.argument("task_slug")
@click.argument(
    "new_status",
    type=click.Choice(
        [
            "scoping",
            "analyzing",
            "debating",
            "consensus",
            "approved",
            "implementing",
            "verifying",
            "completed",
            "failed",
            "cancelled",
        ]
    ),
)
@click.option("--error", "-e", default=None, help="Error message if failed")
def update_status(task_slug: str, new_status: str, error: str | None) -> None:
    """Update task status.

    TASK_SLUG: The task identifier
    NEW_STATUS: The new status
    """

    async def do_update() -> None:
        async with db.get_session() as session:
            task = await db.get_task_by_slug(session, task_slug)
            if not task:
                console.print(f'{{"error": "Task not found: {task_slug}"}}')
                raise SystemExit(1)

            old_status = task.status
            await db.update_task_status(session, task, new_status, error)

            console.print(
                f'{{"old_status": "{old_status}", '
                f'"new_status": "{new_status}", '
                f'"status": "updated"}}'
            )

    asyncio.run(do_update())


@main.command()
@click.argument("task_slug")
@click.argument("round_number", type=int)
def create_round(task_slug: str, round_number: int) -> None:
    """Create a new debate round.

    TASK_SLUG: The task identifier
    ROUND_NUMBER: The round number (1, 2, 3, ...)
    """

    async def do_create() -> None:
        async with db.get_session() as session:
            task = await db.get_task_by_slug(session, task_slug)
            if not task:
                console.print(f'{{"error": "Task not found: {task_slug}"}}')
                raise SystemExit(1)

            round_ = await db.get_or_create_round(session, task, round_number)
            task.current_round = round_number
            console.print(
                f'{{"id": "{round_.id}", "round_number": {round_number}, "status": "created"}}'
            )

    asyncio.run(do_create())


@main.command()
@click.argument("task_slug")
@click.argument("topic")
@click.argument("decision")
@click.option("--source", "-s", default="human", help="Decision source")
@click.option("--rationale", "-r", default=None, help="Rationale for decision")
def add_decision(
    task_slug: str, topic: str, decision: str, source: str, rationale: str | None
) -> None:
    """Add a decision to a task.

    TASK_SLUG: The task identifier
    TOPIC: What the decision is about
    DECISION: The actual decision
    """

    async def do_add() -> None:
        async with db.get_session() as session:
            task = await db.get_task_by_slug(session, task_slug)
            if not task:
                console.print(f'{{"error": "Task not found: {task_slug}"}}')
                raise SystemExit(1)

            dec = await db.add_decision(session, task, topic, decision, source, rationale)
            console.print(f'{{"id": "{dec.id}", "status": "added"}}')

    asyncio.run(do_add())


@main.command()
@click.argument("task_slug")
@click.argument("phase")
@click.argument("event")
@click.option("--agent", "-a", default=None, help="Agent name")
@click.option("--message", "-m", default=None, help="Log message")
def log_event(
    task_slug: str, phase: str, event: str, agent: str | None, message: str | None
) -> None:
    """Log an execution event.

    TASK_SLUG: The task identifier
    PHASE: Workflow phase
    EVENT: Event type (e.g., started, completed, failed)
    """

    async def do_log() -> None:
        async with db.get_session() as session:
            task = await db.get_task_by_slug(session, task_slug)
            if not task:
                console.print(f'{{"error": "Task not found: {task_slug}"}}')
                raise SystemExit(1)

            log = await db.log_event(session, task, phase, event, agent=agent, message=message)
            console.print(f'{{"id": "{log.id}", "status": "logged"}}')

    asyncio.run(do_log())


@main.command()
@click.argument("task_slug")
@click.argument("question")
@click.option("--agent", "-a", default="orchestrator", help="Agent asking the question")
@click.option("--category", "-c", default="clarification", help="Question category")
@click.option("--context", default=None, help="Additional context")
def add_question(
    task_slug: str, question: str, agent: str, category: str, context: str | None
) -> None:
    """Add a question that needs human input.

    TASK_SLUG: The task identifier
    QUESTION: The question text
    """

    async def do_add() -> None:
        async with db.get_session() as session:
            task = await db.get_task_by_slug(session, task_slug)
            if not task:
                console.print(f'{{"error": "Task not found: {task_slug}"}}')
                raise SystemExit(1)

            questions_list = await db.add_questions(
                session,
                task,
                None,
                agent,
                [{"question": question, "category": category, "context": context}],
            )
            q = questions_list[0]
            console.print(f'{{"id": "{q.id}", "status": "added"}}')

    asyncio.run(do_add())


@main.command()
@click.argument("task_slug")
@click.argument("final_round", type=int)
@click.option("--summary", "-s", default=None, help="Consensus summary")
@click.option("--agreement-rate", "-a", type=float, default=None, help="Agreement percentage")
def create_consensus(
    task_slug: str, final_round: int, summary: str | None, agreement_rate: float | None
) -> None:
    """Create a consensus record.

    TASK_SLUG: The task identifier
    FINAL_ROUND: The round number when consensus was reached
    """

    async def do_create() -> None:
        async with db.get_session() as session:
            task = await db.get_task_by_slug(session, task_slug)
            if not task:
                console.print(f'{{"error": "Task not found: {task_slug}"}}')
                raise SystemExit(1)

            consensus = await db.create_consensus(
                session,
                task,
                final_round,
                summary=summary,
                agreement_rate=agreement_rate,
            )
            console.print(f'{{"id": "{consensus.id}", "status": "created"}}')

    asyncio.run(do_create())


@main.command()
@click.argument("task_slug")
@click.option("--notes", "-n", default=None, help="Human notes on approval")
def approve(task_slug: str, notes: str | None) -> None:
    """Approve the consensus for a task.

    TASK_SLUG: The task identifier
    """

    async def do_approve() -> None:
        async with db.get_session() as session:
            task = await db.get_task_by_slug(session, task_slug)
            if not task:
                console.print(f'{{"error": "Task not found: {task_slug}"}}')
                raise SystemExit(1)

            consensus = await db.get_consensus(session, task)
            if not consensus:
                console.print(f'{{"error": "No consensus found for task: {task_slug}"}}')
                raise SystemExit(1)

            await db.approve_consensus(session, consensus, notes)
            await db.update_task_status(session, task, "approved")
            console.print(f'{{"consensus_id": "{consensus.id}", "status": "approved"}}')

    asyncio.run(do_approve())


# =============================================================================
# Codex-facing commands (for implementation phase)
# =============================================================================


@main.command()
@click.argument("task_slug")
def check_approval(task_slug: str) -> None:
    """Check if a task has been approved for implementation.

    TASK_SLUG: The task identifier
    """

    async def do_check() -> None:
        async with db.get_session() as session:
            task = await db.get_task_by_slug(session, task_slug)
            if not task:
                console.print(f'{{"error": "Task not found: {task_slug}"}}')
                raise SystemExit(1)

            consensus = await db.get_consensus(session, task)
            if not consensus:
                console.print('{"approved": false, "reason": "No consensus found"}')
                raise SystemExit(1)

            if consensus.human_approved:
                console.print(f'{{"approved": true, "consensus_id": "{consensus.id}"}}')
            else:
                console.print('{"approved": false, "reason": "Not yet approved by human"}')
                raise SystemExit(1)

    asyncio.run(do_check())


@main.command()
@click.argument("task_slug")
def get_impl_tasks(task_slug: str) -> None:
    """Get pending implementation tasks for a task.

    TASK_SLUG: The task identifier
    """
    import json

    async def do_get() -> None:
        async with db.get_session() as session:
            task = await db.get_task_by_slug(session, task_slug)
            if not task:
                console.print(f'{{"error": "Task not found: {task_slug}"}}')
                raise SystemExit(1)

            impl_tasks = await db.get_pending_impl_tasks(session, task)

            tasks_data = []
            for t in impl_tasks:
                tasks_data.append(
                    {
                        "id": str(t.id),
                        "sequence": t.sequence,
                        "title": t.title,
                        "description": t.description,
                        "files_to_modify": t.files_to_modify,
                        "files_to_create": t.files_to_create,
                        "files_to_delete": t.files_to_delete,
                        "acceptance_criteria": t.acceptance_criteria,
                        "dependencies": t.dependencies,
                    }
                )

            console.print(json.dumps({"tasks": tasks_data}, indent=2))

    asyncio.run(do_get())


@main.command()
@click.argument("impl_task_id")
@click.argument(
    "new_status", type=click.Choice(["pending", "in_progress", "completed", "failed", "skipped"])
)
@click.option("--error", "-e", default=None, help="Error message if failed")
@click.option("--output", "-o", default=None, help="Task output/result")
@click.option("--duration", "-d", type=int, default=None, help="Duration in seconds")
def update_impl_task(
    impl_task_id: str, new_status: str, error: str | None, output: str | None, duration: int | None
) -> None:
    """Update implementation task status.

    IMPL_TASK_ID: The implementation task UUID
    NEW_STATUS: The new status
    """

    async def do_update() -> None:
        async with db.get_session() as session:
            from sqlalchemy import select

            from .models import ImplTask

            result = await session.execute(select(ImplTask).where(ImplTask.id == impl_task_id))
            impl_task = result.scalar_one_or_none()

            if not impl_task:
                console.print(f'{{"error": "Implementation task not found: {impl_task_id}"}}')
                raise SystemExit(1)

            old_status = impl_task.status
            await db.update_impl_task_status(session, impl_task, new_status, error)

            if output:
                impl_task.output = output
            if duration:
                impl_task.duration_seconds = duration

            await session.commit()
            console.print(
                f'{{"old_status": "{old_status}", '
                f'"new_status": "{new_status}", '
                f'"status": "updated"}}'
            )

    asyncio.run(do_update())


@main.command()
@click.argument("task_slug")
def impl_progress(task_slug: str) -> None:
    """Show implementation progress for a task.

    TASK_SLUG: The task identifier
    """
    import json

    async def do_progress() -> None:
        async with db.get_session() as session:
            task = await db.get_task_by_slug(session, task_slug)
            if not task:
                console.print(f'{{"error": "Task not found: {task_slug}"}}')
                raise SystemExit(1)

            from sqlalchemy import func, select

            from .models import ImplTask

            # Get counts by status
            result = await session.execute(
                select(ImplTask.status, func.count(ImplTask.id).label("task_count"))
                .where(ImplTask.task_id == task.id)
                .group_by(ImplTask.status)
            )
            counts = {row.status: row.task_count for row in result}

            total = sum(counts.values())
            completed = counts.get("completed", 0)
            percent = round(completed / total * 100) if total > 0 else 0

            console.print(
                json.dumps(
                    {
                        "task_slug": task_slug,
                        "total": total,
                        "completed": completed,
                        "in_progress": counts.get("in_progress", 0),
                        "failed": counts.get("failed", 0),
                        "pending": counts.get("pending", 0),
                        "percent_complete": percent,
                    },
                    indent=2,
                )
            )

    asyncio.run(do_progress())


@main.group(name="model-config")
def model_config_group() -> None:
    """Manage model configurations for agents.

    Model resolution priority: ENV variable > Database > Hardcoded defaults.

    ENV variables use the pattern: <AGENT_NAME>_MODEL
    (e.g., ORCHESTRATOR_MODEL, DEBATE_GEMINI_MODEL)
    """
    pass


@model_config_group.command(name="list")
def model_config_list() -> None:
    """List all model configurations with their sources."""
    from .model_config import get_all_configs

    async def do_list() -> None:
        async with db.get_session() as session:
            configs = await get_all_configs(session)

            table = Table(title="Model Configurations")
            table.add_column("Agent", style="cyan")
            table.add_column("Model", style="green")
            table.add_column("Source", style="yellow")

            for agent, info in configs.items():
                source_style = {"env": "bold green", "db": "blue", "default": "dim"}[info["source"]]
                table.add_row(
                    agent, info["model"], f"[{source_style}]{info['source']}[/{source_style}]"
                )

            console.print(table)

    asyncio.run(do_list())


@model_config_group.command(name="get")
@click.argument("agent_name")
def model_config_get(agent_name: str) -> None:
    """Get resolved model for a specific agent.

    AGENT_NAME: Agent name (e.g., orchestrator, debate_gemini)
    """
    from .model_config import get_env_key, resolve_model_with_source

    async def do_get() -> None:
        async with db.get_session() as session:
            model, source = await resolve_model_with_source(agent_name, session)
            env_key = get_env_key(agent_name)

            console.print(f"[cyan]{agent_name}[/cyan]: [green]{model}[/green]")
            console.print(f"  Source: [yellow]{source}[/yellow]")
            console.print(f"  ENV override: [dim]{env_key}[/dim]")

    asyncio.run(do_get())


@model_config_group.command(name="set")
@click.argument("agent_name")
@click.argument("model")
def model_config_set(agent_name: str, model: str) -> None:
    """Set model configuration in database for an agent.

    AGENT_NAME: Agent name (e.g., orchestrator, debate_gemini)

    MODEL: Full model identifier (e.g., google/gemini-3-pro-high)
    """
    from .model_config import update_db_model

    async def do_set() -> None:
        async with db.get_session() as session:
            await update_db_model(session, agent_name, model)
            console.print(f"[green]✓[/green] Set {agent_name} -> {model}")

    asyncio.run(do_set())


@model_config_group.command(name="delete")
@click.argument("agent_name")
def model_config_delete(agent_name: str) -> None:
    """Remove model configuration from database (reverts to default).

    AGENT_NAME: Agent name to remove from DB config
    """
    from .model_config import delete_db_model

    async def do_delete() -> None:
        async with db.get_session() as session:
            deleted = await delete_db_model(session, agent_name)
            if deleted:
                console.print(f"[green]✓[/green] Removed {agent_name} from DB config")
            else:
                console.print(f"[yellow]![/yellow] {agent_name} not found in DB config")

    asyncio.run(do_delete())


@main.group(name="role-config")
def role_config_group() -> None:
    """Manage role-to-agent mappings.

    Role resolution priority: ENV variables > Database > Hardcoded defaults.

    ENV variables use the pattern: ROLE_<ROLE>_AGENT / ROLE_<ROLE>_MODEL / ROLE_<ROLE>_PROMPT
    (e.g., ROLE_PLANNER_PRIMARY_AGENT)
    """


@role_config_group.command(name="list")
def role_config_list() -> None:
    """List all role configurations with their sources."""
    from .role_config import get_all_role_configs

    async def do_list() -> None:
        async with db.get_session() as session:
            configs = await get_all_role_configs(session)

            table = Table(title="Role Configurations")
            table.add_column("Role", style="cyan")
            table.add_column("Agent Key", style="green")
            table.add_column("Model", style="green")
            table.add_column("Prompt", style="magenta")
            table.add_column("Source", style="yellow")

            for role_name, info in configs.items():
                config = info.get("config") if isinstance(info, dict) else None
                if not isinstance(config, dict):
                    continue
                source = info.get("source", "unknown") if isinstance(info, dict) else "unknown"
                source_style = {"env": "bold green", "db": "blue", "default": "dim"}.get(
                    str(source), "dim"
                )

                table.add_row(
                    role_name,
                    str(config.get("agent_key", "")),
                    str(config.get("model", "")),
                    str(config.get("prompt_template", "")),
                    f"[{source_style}]{source}[/{source_style}]",
                )

            console.print(table)

    asyncio.run(do_list())


@role_config_group.command(name="get")
@click.argument("role", type=click.Choice([r.value for r in Role]))
def role_config_get(role: str) -> None:
    """Get resolved configuration for a specific role."""
    from .role_config import get_env_keys, resolve_role_with_source

    async def do_get() -> None:
        async with db.get_session() as session:
            config, source = await resolve_role_with_source(Role(role), session)
            env_keys = get_env_keys(Role(role))

            console.print(f"[cyan]{role}[/cyan]")
            console.print(f"  Agent Key: [green]{config.get('agent_key', '')}[/green]")
            console.print(f"  Model: [green]{config.get('model', '')}[/green]")
            console.print(f"  Prompt: [magenta]{config.get('prompt_template', '')}[/magenta]")
            console.print(f"  Source: [yellow]{source}[/yellow]")
            console.print(
                "  ENV overrides: [dim]{}[/dim] [dim]{}[/dim] [dim]{}[/dim]".format(
                    env_keys["agent_key"],
                    env_keys["model"],
                    env_keys["prompt_template"],
                )
            )

    asyncio.run(do_get())


@role_config_group.command(name="set")
@click.argument("role", type=click.Choice([r.value for r in Role]))
@click.option("--agent", "agent_key", default=None, help="Agent key (e.g., debate_gemini)")
@click.option("--model", "model", default=None, help="Model identifier override")
@click.option("--prompt", "prompt_template", default=None, help="Prompt template path")
@click.option("--description", "description", default=None, help="Role description")
@click.option(
    "--capability",
    "capabilities",
    multiple=True,
    help="Capability tag (repeatable)",
)
@click.option(
    "--timeout", "timeout_override", default=None, type=int, help="Timeout override seconds"
)
@click.option(
    "--job-type",
    "job_type",
    default=None,
    type=click.Choice(["analysis", "implement"]),
    help="Queue intent for this role",
)
def role_config_set(
    role: str,
    agent_key: str | None,
    model: str | None,
    prompt_template: str | None,
    description: str | None,
    capabilities: tuple[str, ...],
    timeout_override: int | None,
    job_type: str | None,
) -> None:
    """Update role configuration in database.

    Only the provided fields are updated.
    """
    from .role_config import (
        resolve_role,
        update_role_config,
        validate_role_agent_compatibility,
        validate_role_config,
    )

    async def do_set() -> None:
        async with db.get_session() as session:
            await update_role_config(
                session,
                Role(role),
                agent_key=agent_key,
                model=model,
                prompt_template=prompt_template,
                description=description,
                capabilities=list(capabilities) if capabilities else None,
                timeout_override=timeout_override,
                job_type=job_type,
            )
            role_enum = Role(role)

            errors = await validate_role_config(session, role_enum)
            if errors:
                console.print(f"[yellow]![/yellow] Updated {role}, but validation failed:")
                for e in errors:
                    console.print(f"  - {e}")
            else:
                console.print(f"[green]✓[/green] Updated role config: {role}")

            resolved = await resolve_role(role_enum, session)
            resolved_agent_key = resolved.get("agent_key")
            if isinstance(resolved_agent_key, str) and resolved_agent_key:
                warnings = validate_role_agent_compatibility(role_enum, resolved_agent_key)
                for w in warnings:
                    console.print(f"[yellow]Warning:[/yellow] {w}")

    asyncio.run(do_set())


@role_config_group.command(name="templates", help="List available prompt templates.")
def role_config_templates() -> None:
    template_dir = settings.agent_dir / "templates"

    console.print("[bold]Prompt templates[/bold]")
    if template_dir.exists():
        for file in sorted(template_dir.glob("*.md")):
            console.print(f"  templates/{file.name}")
    else:
        console.print("  (no templates directory)")

    console.print("\n[bold]Agent prompts[/bold]")
    for file in sorted(settings.agent_dir.glob("*.md")):
        console.print(f"  {file.name}")


@role_config_group.command(name="delete")
@click.argument("role", type=click.Choice([r.value for r in Role]))
def role_config_delete(role: str) -> None:
    """Remove role configuration from database (reverts to default)."""
    from .role_config import delete_role_override

    async def do_delete() -> None:
        async with db.get_session() as session:
            deleted = await delete_role_override(session, Role(role))
            if deleted:
                console.print(f"[green]✓[/green] Removed {role} from DB role config")
            else:
                console.print(f"[yellow]![/yellow] {role} not found in DB role config")

    asyncio.run(do_delete())


if __name__ == "__main__":
    main()
