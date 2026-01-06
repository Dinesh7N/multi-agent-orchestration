"""Async database connection and operations for the debate workflow."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import settings
from .errors import SchemaNotInitializedError, is_schema_missing_error, schema_not_initialized_message
from .models import (
    Analysis,
    Base,
    Consensus,
    Conversation,
    CostLog,
    Decision,
    Disagreement,
    ExecutionLog,
    Exploration,
    Finding,
    ImplTask,
    Question,
    Round,
    Task,
)

# Create async engine and session factory
engine = create_async_engine(settings.async_database_url, echo=False, pool_pre_ping=True)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    """Create all tables (for development/testing)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession]:
    """Async context manager for database sessions."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception as exc:
            await session.rollback()
            if isinstance(exc, SQLAlchemyError) and is_schema_missing_error(exc):
                raise SchemaNotInitializedError(
                    schema_not_initialized_message(exc)
                ) from exc
            raise


# =============================================================================
# Task Operations
# =============================================================================


async def get_task_by_slug(session: AsyncSession, slug: str) -> Task | None:
    """Get a task by its slug."""
    result = await session.execute(select(Task).where(Task.slug == slug))
    return result.scalar_one_or_none()


async def get_task_costs(session: AsyncSession, task: Task) -> dict[str, Any]:
    """Return cost/tokens breakdown for a task from the cost_log table."""
    totals_row = (
        await session.execute(
            select(
                func.coalesce(func.sum(CostLog.total_cost), 0),
                func.coalesce(func.sum(CostLog.total_tokens), 0),
                func.coalesce(func.sum(CostLog.input_tokens), 0),
                func.coalesce(func.sum(CostLog.output_tokens), 0),
            ).where(CostLog.task_id == task.id)
        )
    ).one()

    total_cost: Decimal = totals_row[0]
    total_tokens: int = int(totals_row[1] or 0)
    total_input_tokens: int = int(totals_row[2] or 0)
    total_output_tokens: int = int(totals_row[3] or 0)

    by_agent_rows = (
        await session.execute(
            select(
                CostLog.agent,
                func.coalesce(func.sum(CostLog.total_cost), 0),
                func.coalesce(func.sum(CostLog.total_tokens), 0),
                func.coalesce(func.sum(CostLog.input_tokens), 0),
                func.coalesce(func.sum(CostLog.output_tokens), 0),
            )
            .where(CostLog.task_id == task.id)
            .group_by(CostLog.agent)
            .order_by(func.sum(CostLog.total_cost).desc())
        )
    ).all()

    by_model_rows = (
        await session.execute(
            select(
                CostLog.agent,
                CostLog.model,
                func.coalesce(func.sum(CostLog.total_cost), 0),
                func.coalesce(func.sum(CostLog.total_tokens), 0),
            )
            .where(CostLog.task_id == task.id)
            .group_by(CostLog.agent, CostLog.model)
            .order_by(func.sum(CostLog.total_cost).desc())
        )
    ).all()

    by_agent: list[dict[str, Any]] = []
    for agent, cost, tokens, in_tokens, out_tokens in by_agent_rows:
        by_agent.append(
            {
                "agent": agent,
                "total_cost": cost,
                "total_tokens": int(tokens or 0),
                "input_tokens": int(in_tokens or 0),
                "output_tokens": int(out_tokens or 0),
            }
        )

    by_model: list[dict[str, Any]] = []
    for agent, model, cost, tokens in by_model_rows:
        by_model.append(
            {
                "agent": agent,
                "model": model,
                "total_cost": cost,
                "total_tokens": int(tokens or 0),
            }
        )

    return {
        "task_slug": task.slug,
        "task_id": task.id,
        "total_cost": total_cost,
        "total_tokens": total_tokens,
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "by_agent": by_agent,
        "by_model": by_model,
    }


async def get_task_by_id(session: AsyncSession, task_id: str) -> Task | None:
    """Get a task by its ID."""
    result = await session.execute(select(Task).where(Task.id == task_id))
    return result.scalar_one_or_none()


async def create_task(
    session: AsyncSession,
    slug: str,
    title: str,
    complexity: str = "standard",
    metadata: dict[str, Any] | None = None,
) -> Task:
    """Create a new task."""
    task = Task(
        slug=slug,
        title=title,
        status="scoping",
        complexity=complexity,
        metadata_=metadata or {},
    )
    session.add(task)
    await session.flush()
    return task


async def update_task_status(
    session: AsyncSession,
    task: Task,
    new_status: str,
    error_message: str | None = None,
) -> Task:
    """Update task status with logging."""
    old_status = task.status
    task.status = new_status
    task.updated_at = datetime.now(UTC)

    if error_message:
        task.error_message = error_message

    if new_status in ("completed", "failed"):
        task.completed_at = datetime.now(UTC)

    # Log the status change
    log = ExecutionLog(
        task_id=task.id,
        phase="status_change",
        event="status_updated",
        message=f"Status changed from {old_status} to {new_status}",
        details={"old_status": old_status, "new_status": new_status},
    )
    session.add(log)

    return task


# =============================================================================
# Conversation Operations
# =============================================================================


async def add_conversation(
    session: AsyncSession,
    task: Task,
    role: str,
    content: str,
    phase: str,
) -> Conversation:
    """Add a conversation message."""
    conv = Conversation(
        task_id=task.id,
        role=role,
        content=content,
        phase=phase,
    )
    session.add(conv)
    await session.flush()
    return conv


async def get_conversations(session: AsyncSession, task: Task) -> list[Conversation]:
    """Get all conversations for a task."""
    result = await session.execute(
        select(Conversation)
        .where(Conversation.task_id == task.id)
        .order_by(Conversation.created_at)
    )
    return list(result.scalars().all())


# =============================================================================
# Round Operations
# =============================================================================


async def get_or_create_round(session: AsyncSession, task: Task, round_number: int) -> Round:
    """Get or create a round for a task."""
    result = await session.execute(
        select(Round).where(Round.task_id == task.id, Round.round_number == round_number)
    )
    round_ = result.scalar_one_or_none()

    if round_ is None:
        round_ = Round(
            task_id=task.id,
            round_number=round_number,
            status="in_progress",
        )
        session.add(round_)
        await session.flush()

    return round_


async def complete_round(
    session: AsyncSession,
    round_: Round,
    agreement_rate: float | None = None,
    consensus_breakdown: dict[str, Any] | None = None,
) -> Round:
    """Mark a round as completed."""
    round_.status = "completed"
    round_.completed_at = datetime.now(UTC)
    if agreement_rate is not None:
        round_.agreement_rate = Decimal(agreement_rate)
    if consensus_breakdown is not None:
        round_.consensus_breakdown = consensus_breakdown
    return round_


async def get_latest_agent_session_id(
    session: AsyncSession,
    task: Task,
    agent: str,
    *,
    before_round: int | None = None,
) -> str | None:
    query = select(Round).where(Round.task_id == task.id)
    if before_round is not None:
        query = query.where(Round.round_number < before_round)
    query = query.order_by(Round.round_number.desc())

    result = await session.execute(query)
    rounds = list(result.scalars().all())
    for r in rounds:
        agent_session_ids = getattr(r, "agent_session_ids", None)
        if isinstance(agent_session_ids, dict):
            session_id = agent_session_ids.get(agent)
            if isinstance(session_id, str) and session_id:
                return session_id

    return None


async def set_round_agent_session_id(
    session: AsyncSession,
    round_: Round,
    agent: str,
    session_id: str | None,
) -> Round:
    agent_session_ids = dict(getattr(round_, "agent_session_ids", {}) or {})
    if session_id:
        agent_session_ids[agent] = session_id
    else:
        agent_session_ids.pop(agent, None)

    round_.agent_session_ids = agent_session_ids

    await session.flush()
    return round_


# =============================================================================
# Analysis Operations
# =============================================================================


async def create_analysis(
    session: AsyncSession,
    task: Task,
    round_: Round,
    agent: str,
) -> Analysis:
    """Create an analysis placeholder."""
    analysis = Analysis(
        task_id=task.id,
        round_id=round_.id,
        agent=agent,
        status="running",
    )
    session.add(analysis)
    await session.flush()
    return analysis


async def complete_analysis(
    session: AsyncSession,
    analysis: Analysis,
    *,
    summary: str | None = None,
    recommendations: list[str] | None = None,
    concerns: list[str] | None = None,
    raw_output: str | None = None,
    error_message: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    model_used: str | None = None,
) -> Analysis:
    """Complete an analysis with results."""
    now = datetime.now(UTC)
    analysis.completed_at = now
    analysis.status = "failed" if error_message else "completed"

    if summary:
        analysis.summary = summary
    if recommendations:
        analysis.recommendations = recommendations  # type: ignore
    if concerns:
        analysis.concerns = concerns  # type: ignore
    if raw_output:
        analysis.raw_output = raw_output
    if error_message:
        analysis.error_message = error_message
    if input_tokens is not None:
        analysis.input_tokens = input_tokens
    if output_tokens is not None:
        analysis.output_tokens = output_tokens
        analysis.total_tokens = (analysis.input_tokens or 0) + output_tokens
    if model_used:
        analysis.model_used = model_used

    # Calculate duration
    if analysis.started_at:
        delta = now - analysis.started_at
        analysis.duration_seconds = int(delta.total_seconds())

    return analysis


async def get_analysis(
    session: AsyncSession,
    task: Task,
    round_: Round,
    agent: str,
) -> Analysis | None:
    """Get an analysis by task, round, and agent."""
    result = await session.execute(
        select(Analysis).where(
            Analysis.task_id == task.id,
            Analysis.round_id == round_.id,
            Analysis.agent == agent,
        )
    )
    return result.scalar_one_or_none()


async def get_previous_analyses(
    session: AsyncSession,
    task: Task,
    round_number: int,
) -> list[Analysis]:
    """Get analyses from previous rounds."""
    result = await session.execute(
        select(Analysis)
        .join(Round)
        .where(Analysis.task_id == task.id, Round.round_number < round_number)
        .order_by(Round.round_number, Analysis.agent)
    )
    return list(result.scalars().all())


# =============================================================================
# Finding Operations
# =============================================================================


async def add_findings(
    session: AsyncSession,
    task: Task,
    round_: Round,
    analysis: Analysis,
    agent: str,
    findings: list[dict[str, Any]],
) -> list[Finding]:
    """Add findings from an analysis."""
    result: list[Finding] = []
    for f in findings:
        references_agent = f.get("references_agent")
        agreement_type = f.get("agreement_type")
        ref_summary = f.get("referenced_finding_summary")

        agreed_by = None
        disputed_by = None
        dispute_reason = None
        if references_agent and agreement_type in ("agrees", "extends"):
            agreed_by = [references_agent]
        elif references_agent and agreement_type == "disagrees":
            disputed_by = [references_agent]
            dispute_reason = ref_summary

        finding = Finding(
            task_id=task.id,
            round_id=round_.id,
            analysis_id=analysis.id,
            agent=agent,
            category=f.get("category"),
            finding=f["finding"],
            file_path=f.get("file_path"),
            line_start=f.get("line_start"),
            line_end=f.get("line_end"),
            code_snippet=f.get("code_snippet"),
            severity=f.get("severity"),
            confidence=f.get("confidence"),
            recommendation=f.get("recommendation"),
            agreed_by=agreed_by,
            disputed_by=disputed_by,
            dispute_reason=dispute_reason,
            metadata_=f.get("metadata") or {},
        )
        session.add(finding)
        result.append(finding)
    await session.flush()
    return result


# =============================================================================
# Question Operations
# =============================================================================


async def add_questions(
    session: AsyncSession,
    task: Task,
    round_: Round | None,
    agent: str,
    questions: list[dict[str, Any]],
) -> list[Question]:
    """Add questions from an analysis."""
    result: list[Question] = []
    for q in questions:
        question = Question(
            task_id=task.id,
            round_id=round_.id if round_ else None,
            agent=agent,
            question=q["question"],
            context=q.get("context"),
            category=q.get("category"),
            status="pending",
        )
        session.add(question)
        result.append(question)
    await session.flush()
    return result


async def get_pending_questions(session: AsyncSession, task: Task) -> list[Question]:
    """Get all pending questions for a task."""
    result = await session.execute(
        select(Question)
        .where(Question.task_id == task.id, Question.status == "pending")
        .order_by(Question.created_at)
    )
    return list(result.scalars().all())


async def answer_question(
    session: AsyncSession,
    question: Question,
    answer: str,
    answered_by: str = "human",
) -> Question:
    """Answer a question."""
    question.answer = answer
    question.answered_by = answered_by
    question.status = "answered"
    question.answered_at = datetime.now(UTC)
    return question


# =============================================================================
# Decision Operations
# =============================================================================


async def add_decision(
    session: AsyncSession,
    task: Task,
    topic: str,
    decision: str,
    source: str,
    rationale: str | None = None,
    confidence: str | None = None,
) -> Decision:
    """Add a decision."""
    dec = Decision(
        task_id=task.id,
        topic=topic,
        decision=decision,
        source=source,
        rationale=rationale,
        confidence=confidence,
    )
    session.add(dec)
    await session.flush()
    return dec


async def get_decisions(session: AsyncSession, task: Task) -> list[Decision]:
    """Get all decisions for a task."""
    result = await session.execute(
        select(Decision).where(Decision.task_id == task.id).order_by(Decision.created_at)
    )
    return list(result.scalars().all())


# =============================================================================
# Exploration Operations
# =============================================================================


async def add_exploration(
    session: AsyncSession,
    task: Task,
    agent: str,
    exploration: dict[str, Any],
    *,
    raw_output: str | None = None,
) -> Exploration:
    """Add exploration results for a task."""
    record = Exploration(
        task_id=task.id,
        agent=agent,
        relevant_files=exploration.get("relevant_files"),
        tech_stack=exploration.get("tech_stack"),
        existing_patterns=exploration.get("existing_patterns"),
        dependencies=exploration.get("dependencies"),
        schema_summary=exploration.get("schema_summary"),
        directory_structure=exploration.get("directory_structure"),
        raw_output=raw_output,
        input_tokens=exploration.get("input_tokens"),
        output_tokens=exploration.get("output_tokens"),
        cost_estimate=exploration.get("cost_estimate"),
    )
    session.add(record)
    await session.flush()
    return record


async def get_explorations(session: AsyncSession, task: Task) -> list[Exploration]:
    """Get exploration records for a task."""
    result = await session.execute(
        select(Exploration)
        .where(Exploration.task_id == task.id)
        .order_by(Exploration.created_at.desc())
    )
    return list(result.scalars().all())


# =============================================================================
# Consensus Operations
# =============================================================================


async def create_consensus(
    session: AsyncSession,
    task: Task,
    final_round: int,
    *,
    summary: str | None = None,
    agreement_rate: float | None = None,
    agreed_items: list[Any] | None = None,
    implementation_plan: list[dict[str, Any]] | None = None,
) -> Consensus:
    """Create a consensus record."""
    consensus = Consensus(
        task_id=task.id,
        final_round=final_round,
        summary=summary,
        agreement_rate=agreement_rate,
        agreed_items=agreed_items or [],
        implementation_plan=implementation_plan,
    )
    session.add(consensus)
    await session.flush()
    return consensus


async def approve_consensus(
    session: AsyncSession,
    consensus: Consensus,
    human_notes: str | None = None,
) -> Consensus:
    """Approve a consensus."""
    consensus.human_approved = True
    consensus.approved_at = datetime.now(UTC)
    if human_notes:
        consensus.human_notes = human_notes
    return consensus


async def get_consensus(session: AsyncSession, task: Task) -> Consensus | None:
    """Get the consensus for a task."""
    result = await session.execute(
        select(Consensus).where(Consensus.task_id == task.id).order_by(Consensus.created_at.desc())
    )
    return result.scalars().first()


# =============================================================================
# Consensus Helpers
# =============================================================================


async def get_findings_for_round(session: AsyncSession, round_id: str) -> list[Finding]:
    """Get findings for a round."""
    result = await session.execute(select(Finding).where(Finding.round_id == round_id))
    return list(result.scalars().all())


async def get_analyses_for_round(session: AsyncSession, round_id: str) -> list[Analysis]:
    """Get analyses for a round."""
    result = await session.execute(select(Analysis).where(Analysis.round_id == round_id))
    return list(result.scalars().all())


async def get_open_disagreements(session: AsyncSession, task: Task) -> list[Disagreement]:
    """Get unresolved disagreements for a task."""
    result = await session.execute(
        select(Disagreement)
        .where(Disagreement.task_id == task.id, Disagreement.resolved.is_(False))
        .order_by(Disagreement.created_at.desc())
    )
    return list(result.scalars().all())


# =============================================================================
# Implementation Task Operations
# =============================================================================


async def create_impl_tasks(
    session: AsyncSession,
    task: Task,
    consensus: Consensus,
    implementation_plan: list[dict[str, Any]],
) -> list[ImplTask]:
    """Create implementation tasks from a plan."""
    result: list[ImplTask] = []
    for item in implementation_plan:
        impl_task = ImplTask(
            task_id=task.id,
            consensus_id=consensus.id,
            sequence=item["sequence"],
            title=item["title"],
            description=item["description"],
            files_to_modify=item.get("files_to_modify"),
            files_to_create=item.get("files_to_create"),
            files_to_delete=item.get("files_to_delete"),
            acceptance_criteria=item.get("acceptance_criteria"),
            dependencies=item.get("dependencies"),
            status="pending",
        )
        session.add(impl_task)
        result.append(impl_task)
    await session.flush()
    return result


async def get_pending_impl_tasks(session: AsyncSession, task: Task) -> list[ImplTask]:
    """Get pending implementation tasks in sequence order."""
    result = await session.execute(
        select(ImplTask)
        .where(ImplTask.task_id == task.id, ImplTask.status == "pending")
        .order_by(ImplTask.sequence)
    )
    return list(result.scalars().all())


async def update_impl_task_status(
    session: AsyncSession,
    impl_task: ImplTask,
    status: str,
    error: str | None = None,
) -> ImplTask:
    """Update implementation task status."""
    impl_task.status = status
    if status == "in_progress":
        impl_task.started_at = datetime.now(UTC)
    elif status in ("completed", "failed"):
        impl_task.completed_at = datetime.now(UTC)
    if error:
        impl_task.last_error = error
        impl_task.codex_attempts += 1
    return impl_task


# =============================================================================
# Execution Log Operations
# =============================================================================


async def log_event(
    session: AsyncSession,
    task: Task | None = None,
    phase: str | None = None,
    event: str | None = None,
    *,
    task_id: str | None = None,
    agent: str | None = None,
    message: str | None = None,
    details: dict[str, Any] | None = None,
    duration_ms: int | None = None,
) -> ExecutionLog:
    """Log an execution event."""
    resolved_task_id = task_id or (task.id if task else None)
    if not resolved_task_id or not phase or not event:
        raise ValueError("log_event requires task/task_id, phase, and event.")

    log = ExecutionLog(
        task_id=resolved_task_id,
        phase=phase,
        event=event,
        agent=agent,
        message=message,
        details=details,
        duration_ms=duration_ms,
    )
    session.add(log)
    await session.flush()
    return log


# =============================================================================
# Context Building (for agent prompts)
# =============================================================================


async def build_task_context(
    session: AsyncSession,
    task: Task,
    round_number: int = 1,
    *,
    include_exploration: bool = True,
) -> dict[str, Any]:
    """Build complete context for an agent prompt."""
    conversations = await get_conversations(session, task)
    decisions = await get_decisions(session, task)
    explorations = await get_explorations(session, task) if include_exploration else []
    disagreements = await get_open_disagreements(session, task)

    # Get answered questions
    result = await session.execute(
        select(Question).where(Question.task_id == task.id, Question.status == "answered")
    )
    answered_questions = list(result.scalars().all())

    context: dict[str, Any] = {
        "task": {
            "id": task.id,
            "slug": task.slug,
            "title": task.title,
            "status": task.status,
            "complexity": task.complexity,
            "metadata": task.metadata_,
        },
        "conversations": [
            {"role": c.role, "content": c.content, "phase": c.phase} for c in conversations
        ],
        "decisions": [
            {"topic": d.topic, "decision": d.decision, "source": d.source} for d in decisions
        ],
        "answered_questions": [
            {"question": q.question, "answer": q.answer, "category": q.category}
            for q in answered_questions
        ],
        "explorations": [
            {
                "agent": e.agent,
                "relevant_files": e.relevant_files,
                "tech_stack": e.tech_stack,
                "existing_patterns": e.existing_patterns,
                "dependencies": e.dependencies,
                "schema_summary": e.schema_summary,
                "directory_structure": e.directory_structure,
                "created_at": e.created_at,
            }
            for e in explorations
        ],
        "conflict_summary": [
            {
                "topic": d.topic,
                "positions": d.positions,
                "evidence": d.evidence,
                "impact": d.impact,
            }
            for d in disagreements
        ],
        "previous_analyses": [],
    }

    # Add previous round analyses if round > 1
    if round_number > 1:
        prev_analyses = await get_previous_analyses(session, task, round_number)
        for analysis in prev_analyses:
            context["previous_analyses"].append(
                {
                    "agent": analysis.agent,
                    "summary": analysis.summary,
                    "recommendations": analysis.recommendations,
                    "concerns": analysis.concerns,
                }
            )

    return context
