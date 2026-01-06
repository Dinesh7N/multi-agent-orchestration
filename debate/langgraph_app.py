"""LangGraph-based orchestrator (single source of truth).

Design goals:
- Keep OpenCode integration (no direct vendor API keys required).
- Keep Postgres as the audit trail.
- Make the workflow explicit and deterministic (state machine).
- Avoid legacy Redis/workflow/worker orchestration layers.
"""

from __future__ import annotations

import asyncio
import re
from typing import Literal, TypedDict

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from . import db
from .config import settings
from .consensus import calculate_round_consensus
from .models import Consensus, Round, Task
from .role_config import Role
from .run_agent import Phase, run_agent_by_role
from .triage import TaskTriager

console = Console()

Decision = Literal["approve", "revise", "cancel"]


class DebateState(TypedDict, total=False):
    user_request: str
    skip_explore: bool
    max_rounds: int

    task_slug: str
    task_id: str
    task_complexity: str
    round_number: int

    analysis_ok: bool
    agreement_rate: float
    consensus_id: str

    decision: Decision
    cancelled: bool


def _require_langgraph() -> tuple[object, object]:
    try:
        from langgraph.graph import END, StateGraph  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "LangGraph is not installed. Install dependencies and retry (e.g. `uv sync`)."
        ) from exc
    return END, StateGraph


def _require_postgres_checkpointer() -> type:
    try:
        from langgraph.checkpoint.postgres import PostgresSaver  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "Postgres checkpointer is not installed. Install `langgraph-checkpoint-postgres`."
        ) from exc
    return PostgresSaver


def _generate_slug(title: str) -> str:
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9\\s-]", "", slug)
    slug = re.sub(r"[\\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")[:50]


def _assess_complexity(description: str) -> str:
    description_lower = description.lower()
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
    trivial_keywords = ["typo", "fix bug", "simple", "quick", "update comment", "rename"]
    if any(kw in description_lower for kw in trivial_keywords):
        return "trivial"
    return "standard"


async def _load_task(task_slug: str) -> Task:
    async with db.get_session() as session:
        task = await db.get_task_by_slug(session, task_slug)
        if not task:
            raise RuntimeError(f"Task not found: {task_slug}")
        return task


async def _load_consensus(task_slug: str) -> Consensus:
    async with db.get_session() as session:
        task = await db.get_task_by_slug(session, task_slug)
        if not task:
            raise RuntimeError(f"Task not found: {task_slug}")
        consensus = await db.get_consensus(session, task)
        if not consensus:
            raise RuntimeError(f"Consensus not found for task: {task_slug}")
        return consensus


async def _ensure_round(task_slug: str, round_number: int) -> Round:
    async with db.get_session() as session:
        task = await db.get_task_by_slug(session, task_slug)
        if not task:
            raise RuntimeError(f"Task not found: {task_slug}")
        return await db.get_or_create_round(session, task, round_number)


async def node_scoping(state: DebateState) -> DebateState:
    user_request = state["user_request"]
    title = user_request[:100]
    slug = state.get("task_slug") or _generate_slug(title)
    complexity = _assess_complexity(user_request)

    console.print("\n[bold]Phase 1: Scoping & Task Creation[/bold]")
    console.print(f"  Task: {title}")
    console.print(f"  Slug: {slug}")
    console.print(f"  Complexity (heuristic): {complexity}")

    async with db.get_session() as session:
        existing = await db.get_task_by_slug(session, slug)
        if existing:
            task = existing
            console.print(f"[yellow]Task already exists; resuming: {slug}[/yellow]")
        else:
            task = await db.create_task(
                session,
                slug=slug,
                title=title,
                complexity=complexity,
                metadata={"description": user_request, "scope": "auto-detected"},
            )
            await db.add_conversation(session, task, "human", user_request, "scoping")
            await db.log_event(
                session,
                task,
                "scoping",
                "task_created",
                message=f"Task created: {slug}",
                details={"complexity": complexity},
            )

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
            console.print(f"[green]Task created (ID: {task.id})[/green]")

        requested_max_rounds = int(state.get("max_rounds") or settings.max_rounds)
        default_max_rounds = settings.max_rounds if task.complexity == "complex" else 2
        effective_max_rounds = max(1, min(requested_max_rounds, default_max_rounds))

        return {
            "task_slug": task.slug,
            "task_id": task.id,
            "task_complexity": task.complexity or "standard",
            "round_number": max(1, int(getattr(task, "current_round", 1) or 1)),
            "max_rounds": effective_max_rounds,
            "analysis_ok": True,
            "cancelled": False,
        }


async def node_exploration(state: DebateState) -> DebateState:
    if state.get("skip_explore"):
        console.print("\n[dim]Skipping exploration (CLI flag).[/dim]")
        return {}

    console.print("\n[bold]Phase 0: Exploration (Optional)[/bold]")
    explore = Confirm.ask(
        "Would you like the Explorer role to scan the codebase first?", default=False
    )
    if not explore:
        console.print("[dim]Skipping exploration...[/dim]")
        return {}

    ok = await run_agent_by_role(
        state["task_slug"], Role.EXPLORER, round_number=0, phase=Phase.EXPLORATION
    )
    console.print("[green]Exploration complete![/green]" if ok else "[yellow]Exploration had issues.[/yellow]")
    return {}


async def node_analysis(state: DebateState) -> DebateState:
    round_number = int(state["round_number"])
    task_slug = state["task_slug"]

    console.print(f"\n[bold]Phase 2: Parallel Analysis (Round {round_number})[/bold]")
    await _ensure_round(task_slug, round_number)

    primary = asyncio.create_task(
        run_agent_by_role(task_slug, Role.PLANNER_PRIMARY, round_number=round_number, phase=Phase.ANALYSIS)
    )
    secondary = asyncio.create_task(
        run_agent_by_role(task_slug, Role.PLANNER_SECONDARY, round_number=round_number, phase=Phase.ANALYSIS)
    )

    primary_ok, secondary_ok = await asyncio.gather(primary, secondary)
    return {"analysis_ok": bool(primary_ok and secondary_ok)}


async def node_analysis_failure_decision(state: DebateState) -> DebateState:
    console.print("[red]One or more planners failed.[/red]")
    if Confirm.ask("Continue anyway?", default=False):
        return {"analysis_ok": True}
    return {"cancelled": True}


async def node_questions(state: DebateState) -> DebateState:
    console.print("\n[bold]Phase 3: Question Resolution[/bold]")
    task_slug = state["task_slug"]
    async with db.get_session() as session:
        task = await db.get_task_by_slug(session, task_slug)
        if not task:
            raise RuntimeError(f"Task not found: {task_slug}")

        questions = await db.get_pending_questions(session, task)
        if not questions:
            console.print("[dim]No pending questions from agents.[/dim]")
            return {}

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

    return {}


async def node_consensus(state: DebateState) -> DebateState:
    console.print("\n[bold]Phase 4: Building Consensus[/bold]")
    task_slug = state["task_slug"]
    round_number = int(state["round_number"])

    async with db.get_session() as session:
        task = await db.get_task_by_slug(session, task_slug)
        if not task:
            raise RuntimeError(f"Task not found: {task_slug}")

        round_obj = await db.get_or_create_round(session, task, round_number)
        agreement_rate, breakdown = await calculate_round_consensus(session, round_obj)
        await db.complete_round(session, round_obj, agreement_rate, breakdown.to_dict())
        console.print(f"  Agreement rate: {agreement_rate:.1f}%")

        analyses = await db.get_analyses_for_round(session, round_obj.id)
        all_recommendations: list[str] = []
        for a in analyses:
            if a.recommendations:
                all_recommendations.extend(a.recommendations if isinstance(a.recommendations, list) else [])

        consensus = await db.create_consensus(
            session,
            task,
            final_round=round_number,
            summary=f"Consensus from {len(analyses)} analyses",
            agreement_rate=agreement_rate,
            agreed_items=list(set(all_recommendations))[:10],
            implementation_plan=[],
        )

        return {
            "agreement_rate": float(agreement_rate),
            "consensus_id": str(consensus.id),
        }


async def node_approval(state: DebateState) -> DebateState:
    task_slug = state["task_slug"]
    task = await _load_task(task_slug)
    consensus = await _load_consensus(task_slug)

    console.print("\n[bold]Phase 5: Human Approval[/bold]")

    table = Table(title="Debate Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Task", task.slug)
    table.add_row("Round", f"{state['round_number']}/{state['max_rounds']}")
    table.add_row("Agreement Rate", f"{consensus.agreement_rate or 0:.1f}%")
    table.add_row("Agreed Items", str(len(consensus.agreed_items or [])))
    console.print(table)

    if consensus.agreed_items:
        console.print("\n[bold]Recommendations:[/bold]")
        for i, item in enumerate(consensus.agreed_items[:5], 1):
            console.print(f"  {i}. {item}")

    can_revise = int(state["round_number"]) < int(state["max_rounds"])
    choices: list[Decision] = ["approve", "cancel"] if not can_revise else ["approve", "revise", "cancel"]
    decision = Prompt.ask("Your decision", choices=choices, default="approve")  # type: ignore[arg-type]

    async with db.get_session() as session:
        task_db = await db.get_task_by_slug(session, task_slug)
        if not task_db:
            raise RuntimeError(f"Task not found: {task_slug}")
        consensus_db = await db.get_consensus(session, task_db)
        if not consensus_db:
            raise RuntimeError(f"Consensus not found for task: {task_slug}")

        if decision == "approve":
            await db.approve_consensus(session, consensus_db)
            await db.update_task_status(session, task_db, "approved")
        elif decision == "cancel":
            await db.update_task_status(session, task_db, "cancelled", "User cancelled")

    return {"decision": decision, "cancelled": decision == "cancel"}


async def node_increment_round(state: DebateState) -> DebateState:
    return {"round_number": int(state["round_number"]) + 1}


def _route_after_scoping(_: DebateState) -> str:
    return "exploration"


def _route_after_analysis(state: DebateState) -> str:
    if state.get("cancelled"):
        return "end"
    return "questions" if state.get("analysis_ok") else "analysis_failure_decision"


def _route_after_analysis_failure_decision(state: DebateState) -> str:
    return "end" if state.get("cancelled") else "questions"


def _route_after_approval(state: DebateState) -> str:
    if state.get("cancelled"):
        return "end"
    if state.get("decision") == "revise":
        return "increment_round"
    return "end"


async def orchestrate(
    user_request: str,
    *,
    skip_explore: bool = False,
    max_rounds: int | None = None,
) -> bool:
    console.print(
        Panel(
            f"[bold]Multi-Agent Debate Orchestrator (LangGraph)[/bold]\n\n{user_request}",
            title="New Task",
            border_style="blue",
        )
    )

    END, StateGraph = _require_langgraph()
    PostgresSaver = _require_postgres_checkpointer()

    graph = StateGraph(DebateState)
    graph.add_node("scoping", node_scoping)
    graph.add_node("exploration", node_exploration)
    graph.add_node("analysis", node_analysis)
    graph.add_node("analysis_failure_decision", node_analysis_failure_decision)
    graph.add_node("questions", node_questions)
    graph.add_node("consensus", node_consensus)
    graph.add_node("approval", node_approval)
    graph.add_node("increment_round", node_increment_round)

    graph.set_entry_point("scoping")
    graph.add_conditional_edges("scoping", _route_after_scoping, {"exploration": "exploration"})
    graph.add_edge("exploration", "analysis")
    graph.add_conditional_edges(
        "analysis",
        _route_after_analysis,
        {
            "questions": "questions",
            "analysis_failure_decision": "analysis_failure_decision",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "analysis_failure_decision",
        _route_after_analysis_failure_decision,
        {"questions": "questions", "end": END},
    )
    graph.add_edge("questions", "consensus")
    graph.add_edge("consensus", "approval")
    graph.add_conditional_edges(
        "approval",
        _route_after_approval,
        {"increment_round": "increment_round", "end": END},
    )
    graph.add_edge("increment_round", "analysis")

    checkpointer = PostgresSaver.from_conn_string(settings.database_url)
    app = graph.compile(checkpointer=checkpointer)

    # Use a deterministic thread_id so resume can target an existing task.
    title = user_request[:100]
    task_slug = _generate_slug(title)

    initial_state: DebateState = {
        "user_request": user_request,
        "skip_explore": skip_explore,
        "task_slug": task_slug,
    }
    if max_rounds is not None:
        initial_state["max_rounds"] = int(max_rounds)

    final_state = await app.ainvoke(
        initial_state,
        config={"configurable": {"thread_id": task_slug}},
    )
    try:
        async with db.get_session() as session:
            task = await db.get_task_by_slug(session, task_slug)
            if task:
                costs = await db.get_task_costs(session, task)
                console.print("\n[bold]Session Cost Summary[/bold]")
                console.print(
                    f"  Total: ${float(costs['total_cost']):.4f}\n"
                    f"  Tokens: {int(costs['total_tokens']):,} "
                    f"(in: {int(costs['input_tokens']):,}, out: {int(costs['output_tokens']):,})"
                )
                by_agent = ", ".join(
                    f"{row['agent']}: ${float(row['total_cost']):.4f}" for row in costs["by_agent"]
                )
                if by_agent:
                    console.print(f"  By agent: {by_agent}")
    except Exception:
        # Cost display is best-effort; do not fail the workflow.
        pass
    return bool(final_state.get("task_slug")) and not bool(final_state.get("cancelled"))


async def resume(task_slug: str) -> bool:
    """Best-effort resume using the Postgres checkpointer.

    This relies on a previously-started LangGraph run having checkpointed state under
    `thread_id == task_slug`.
    """
    END, StateGraph = _require_langgraph()
    PostgresSaver = _require_postgres_checkpointer()

    graph = StateGraph(DebateState)
    graph.add_node("scoping", node_scoping)
    graph.add_node("exploration", node_exploration)
    graph.add_node("analysis", node_analysis)
    graph.add_node("analysis_failure_decision", node_analysis_failure_decision)
    graph.add_node("questions", node_questions)
    graph.add_node("consensus", node_consensus)
    graph.add_node("approval", node_approval)
    graph.add_node("increment_round", node_increment_round)

    graph.set_entry_point("scoping")
    graph.add_conditional_edges("scoping", _route_after_scoping, {"exploration": "exploration"})
    graph.add_edge("exploration", "analysis")
    graph.add_conditional_edges(
        "analysis",
        _route_after_analysis,
        {
            "questions": "questions",
            "analysis_failure_decision": "analysis_failure_decision",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "analysis_failure_decision",
        _route_after_analysis_failure_decision,
        {"questions": "questions", "end": END},
    )
    graph.add_edge("questions", "consensus")
    graph.add_edge("consensus", "approval")
    graph.add_conditional_edges(
        "approval",
        _route_after_approval,
        {"increment_round": "increment_round", "end": END},
    )
    graph.add_edge("increment_round", "analysis")

    checkpointer = PostgresSaver.from_conn_string(settings.database_url)
    app = graph.compile(checkpointer=checkpointer)

    final_state = await app.ainvoke(
        {},
        config={"configurable": {"thread_id": task_slug}},
    )
    return bool(final_state.get("task_slug")) and not bool(final_state.get("cancelled"))
