"""SQLAlchemy models for the debate workflow database."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """Base class for all models."""

    type_annotation_map = {
        dict[str, Any]: JSONB,
        list[str]: ARRAY(String),
        list[int]: ARRAY(Integer),
        list[float]: ARRAY(Float),
    }


# =============================================================================
# TASK-SCOPED TABLES
# =============================================================================


class Task(Base):
    """Registry of all debate tasks."""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    slug: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="scoping")
    current_round: Mapped[int] = mapped_column(Integer, default=0)
    max_rounds: Mapped[int] = mapped_column(Integer, default=3)
    complexity: Mapped[str | None] = mapped_column(String, nullable=True)
    skip_debate: Mapped[bool] = mapped_column(Boolean, default=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)

    # Relationships
    conversations: Mapped[list[Conversation]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    explorations: Mapped[list[Exploration]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    rounds: Mapped[list[Round]] = relationship(back_populates="task", cascade="all, delete-orphan")
    analyses: Mapped[list[Analysis]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    questions: Mapped[list[Question]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    decisions: Mapped[list[Decision]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    findings: Mapped[list[Finding]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    consensus: Mapped[list[Consensus]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    impl_tasks: Mapped[list[ImplTask]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    verifications: Mapped[list[Verification]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    execution_logs: Mapped[list[ExecutionLog]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class Conversation(Base):
    """Full orchestrator-human transcript."""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    task_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tasks.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String, nullable=False)  # 'human', 'orchestrator'
    content: Mapped[str] = mapped_column(Text, nullable=False)
    phase: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped[Task] = relationship(back_populates="conversations")


class Exploration(Base):
    """Optional codebase scan results (Phase 0)."""

    __tablename__ = "explorations"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    task_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tasks.id", ondelete="CASCADE")
    )
    agent: Mapped[str] = mapped_column(String, default="gemini")
    relevant_files: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    tech_stack: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    existing_patterns: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    dependencies: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    schema_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    directory_structure: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_estimate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped[Task] = relationship(back_populates="explorations")


class Round(Base):
    """Tracks debate rounds."""

    __tablename__ = "rounds"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    task_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tasks.id", ondelete="CASCADE")
    )
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, default="in_progress")
    agent_statuses: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    agent_session_ids: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    agreement_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    consensus_breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("task_id", "round_number"),)

    task: Mapped[Task] = relationship(back_populates="rounds")
    analyses: Mapped[list[Analysis]] = relationship(
        back_populates="round", cascade="all, delete-orphan"
    )
    findings: Mapped[list[Finding]] = relationship(
        back_populates="round", cascade="all, delete-orphan"
    )
    questions: Mapped[list[Question]] = relationship(
        back_populates="round", cascade="all, delete-orphan"
    )


class Analysis(Base):
    """Agent outputs per round (high-level)."""

    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    task_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tasks.id", ondelete="CASCADE")
    )
    round_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("rounds.id", ondelete="CASCADE")
    )
    agent: Mapped[str] = mapped_column(String, nullable=False)  # 'gemini', 'claude'
    status: Mapped[str] = mapped_column(String, default="running")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendations: Mapped[list[str]] = mapped_column(JSONB, default=list)
    concerns: Mapped[list[str]] = mapped_column(JSONB, default=list)
    recommendation_embeddings: Mapped[list[float] | None] = mapped_column(
        ARRAY(Float), nullable=True
    )
    recommendation_embedding_model: Mapped[str | None] = mapped_column(String, nullable=True)
    recommendation_embedding_dim: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_estimate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    model_used: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (UniqueConstraint("task_id", "round_id", "agent"),)

    task: Mapped[Task] = relationship(back_populates="analyses")
    round: Mapped[Round] = relationship(back_populates="analyses")


class Question(Base):
    """Questions needing human input."""

    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    task_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tasks.id", ondelete="CASCADE")
    )
    round_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("rounds.id", ondelete="CASCADE"), nullable=True
    )
    agent: Mapped[str] = mapped_column(String, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    answered_by: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending")
    duplicate_of: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("questions.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    task: Mapped[Task] = relationship(back_populates="questions")
    round: Mapped[Round] = relationship(back_populates="questions")


class Decision(Base):
    """Extracted key decisions."""

    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    task_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tasks.id", ondelete="CASCADE")
    )
    topic: Mapped[str] = mapped_column(String, nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False)  # 'human', 'orchestrator', etc.
    confidence: Mapped[str | None] = mapped_column(String, nullable=True)
    supersedes: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("decisions.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped[Task] = relationship(back_populates="decisions")


class Finding(Base):
    """Detailed findings with file references."""

    __tablename__ = "findings"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    task_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tasks.id", ondelete="CASCADE")
    )
    round_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("rounds.id", ondelete="CASCADE")
    )
    analysis_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("analyses.id", ondelete="CASCADE")
    )
    agent: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    finding: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str | None] = mapped_column(String, nullable=True)
    line_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    line_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    code_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str | None] = mapped_column(String, nullable=True)
    confidence: Mapped[str | None] = mapped_column(String, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    agreed_by: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    disputed_by: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    dispute_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped[Task] = relationship(back_populates="findings")
    round: Mapped[Round] = relationship(back_populates="findings")


class Consensus(Base):
    """Final agreed recommendations."""

    __tablename__ = "consensus"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    task_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tasks.id", ondelete="CASCADE")
    )
    final_round: Mapped[int] = mapped_column(Integer, nullable=False)
    agreement_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    agreed_items: Mapped[list[str]] = mapped_column(JSONB, default=list)
    implementation_plan: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    human_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    human_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped[Task] = relationship(back_populates="consensus")
    disagreements: Mapped[list[Disagreement]] = relationship(
        back_populates="consensus", cascade="all, delete-orphan"
    )


class Disagreement(Base):
    """Unresolved conflicts needing human decision."""

    __tablename__ = "disagreements"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    task_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tasks.id", ondelete="CASCADE")
    )
    consensus_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("consensus.id", ondelete="CASCADE")
    )
    topic: Mapped[str] = mapped_column(String, nullable=False)
    gemini_position: Mapped[str] = mapped_column(Text, nullable=False)
    gemini_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    claude_position: Mapped[str] = mapped_column(Text, nullable=False)
    claude_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    impact: Mapped[str | None] = mapped_column(Text, nullable=True)
    human_decision: Mapped[str | None] = mapped_column(String, nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped[Task] = relationship()
    consensus: Mapped[Consensus] = relationship(back_populates="disagreements")


class ImplTask(Base):
    """Todo list for implementation (Codex)."""

    __tablename__ = "impl_tasks"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    task_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tasks.id", ondelete="CASCADE")
    )
    consensus_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("consensus.id", ondelete="CASCADE"), nullable=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    files_to_modify: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    files_to_create: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    files_to_delete: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    acceptance_criteria: Mapped[str | None] = mapped_column(Text, nullable=True)
    dependencies: Mapped[list[int] | None] = mapped_column(ARRAY(Integer), nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending")
    codex_attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped[Task] = relationship(back_populates="impl_tasks")


class Verification(Base):
    """Post-implementation checks."""

    __tablename__ = "verifications"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    task_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tasks.id", ondelete="CASCADE")
    )
    tests_ran: Mapped[bool] = mapped_column(Boolean, default=False)
    tests_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    tests_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tests_failed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tests_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    lint_ran: Mapped[bool] = mapped_column(Boolean, default=False)
    lint_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    lint_warnings: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lint_errors: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lint_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    build_ran: Mapped[bool] = mapped_column(Boolean, default=False)
    build_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    build_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    files_changed: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    files_created: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    files_deleted: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    lines_added: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lines_removed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    matches_plan: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    plan_deviations: Mapped[dict[str, Any]] = mapped_column(JSONB, default=list)
    issues: Mapped[dict[str, Any]] = mapped_column(JSONB, default=list)
    overall_status: Mapped[str | None] = mapped_column(String, nullable=True)
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    task: Mapped[Task] = relationship(back_populates="verifications")


class ExecutionLog(Base):
    """Audit trail for debugging and guardrails."""

    __tablename__ = "execution_log"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    task_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tasks.id", ondelete="CASCADE")
    )
    phase: Mapped[str] = mapped_column(String, nullable=False)
    event: Mapped[str] = mapped_column(String, nullable=False)
    agent: Mapped[str | None] = mapped_column(String, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped[Task] = relationship(back_populates="execution_logs")


class CostLog(Base):
    """Detailed API cost tracking per call."""

    __tablename__ = "cost_log"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    task_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tasks.id", ondelete="CASCADE")
    )
    analysis_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("analyses.id", ondelete="SET NULL"), nullable=True
    )
    agent: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    operation: Mapped[str] = mapped_column(String, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_per_input_token: Mapped[Decimal | None] = mapped_column(Numeric(12, 10), nullable=True)
    cost_per_output_token: Mapped[Decimal | None] = mapped_column(Numeric(12, 10), nullable=True)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# =============================================================================
# GLOBAL TABLES (Cross-task persistent memory)
# =============================================================================


class Memory(Base):
    """Long-term facts learned from debates."""

    __tablename__ = "memories"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    source_task_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    category: Mapped[str] = mapped_column(String, nullable=False)
    key: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=1.0)
    times_referenced: Mapped[int] = mapped_column(Integer, default=0)
    last_referenced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (UniqueConstraint("category", "key"),)


class Pattern(Base):
    """Code patterns/conventions learned."""

    __tablename__ = "patterns"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    pattern_type: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    examples: Mapped[dict[str, Any]] = mapped_column(JSONB, default=list)
    applies_to: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    source_tasks: Mapped[list[str] | None] = mapped_column(
        ARRAY(UUID(as_uuid=False)), nullable=True
    )
    times_applied: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (UniqueConstraint("pattern_type", "name"),)


class Preference(Base):
    """User preferences."""

    __tablename__ = "preferences"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    set_by: Mapped[str] = mapped_column(String, default="human")
    source_task_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# =============================================================================
# CONFIG TABLES
# =============================================================================


class Guardrail(Base):
    """Configurable timeouts, retries, thresholds."""

    __tablename__ = "guardrails"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class HumanIntervention(Base):
    """Async human interventions during workflow."""

    __tablename__ = "human_interventions"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    task_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tasks.id", ondelete="CASCADE")
    )
    intervention_type: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    target_agent: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Artifact(Base):
    """Large outputs (diagrams, diffs, patches)."""

    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    task_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tasks.id", ondelete="CASCADE")
    )
    round_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("rounds.id", ondelete="CASCADE"), nullable=True
    )
    agent: Mapped[str | None] = mapped_column(String, nullable=True)
    artifact_type: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FileSnapshot(Base):
    """Track file state when agents read them."""

    __tablename__ = "file_snapshots"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    task_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tasks.id", ondelete="CASCADE")
    )
    round_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("rounds.id"), nullable=True
    )
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    line_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    byte_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (UniqueConstraint("task_id", "round_id", "file_path"),)


class Review(Base):
    """Code review results."""

    __tablename__ = "reviews"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    task_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tasks.id", ondelete="CASCADE")
    )
    agent: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    issues: Mapped[dict[str, Any]] = mapped_column(JSONB, default=list)
    raw_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
