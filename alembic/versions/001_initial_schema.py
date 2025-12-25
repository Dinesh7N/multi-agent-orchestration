"""Initial schema - all tables for debate workflow.

Revision ID: 001
Revises:
Create Date: 2024-12-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Tasks table
    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("slug", sa.String(), nullable=False, unique=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("status", sa.String(), server_default="scoping"),
        sa.Column("current_round", sa.Integer(), server_default="0"),
        sa.Column("max_rounds", sa.Integer(), server_default="3"),
        sa.Column("complexity", sa.String(), nullable=True),
        sa.Column("skip_debate", sa.Boolean(), server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}"),
    )
    op.create_index("idx_tasks_slug", "tasks", ["slug"])
    op.create_index("idx_tasks_status", "tasks", ["status"])

    # Conversations table
    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tasks.id", ondelete="CASCADE")),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("phase", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_conversations_task", "conversations", ["task_id"])

    # Explorations table
    op.create_table(
        "explorations",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tasks.id", ondelete="CASCADE")),
        sa.Column("agent", sa.String(), server_default="gemini"),
        sa.Column("relevant_files", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("tech_stack", postgresql.JSONB(), nullable=True),
        sa.Column("existing_patterns", postgresql.JSONB(), nullable=True),
        sa.Column("dependencies", postgresql.JSONB(), nullable=True),
        sa.Column("schema_summary", sa.Text(), nullable=True),
        sa.Column("directory_structure", sa.Text(), nullable=True),
        sa.Column("raw_output", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_explorations_task", "explorations", ["task_id"])

    # Rounds table
    op.create_table(
        "rounds",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tasks.id", ondelete="CASCADE")),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), server_default="in_progress"),
        sa.Column("gemini_status", sa.String(), server_default="pending"),
        sa.Column("claude_status", sa.String(), server_default="pending"),
        sa.Column("agreement_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("task_id", "round_number"),
    )
    op.create_index("idx_rounds_task", "rounds", ["task_id"])

    # Analyses table
    op.create_table(
        "analyses",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tasks.id", ondelete="CASCADE")),
        sa.Column("round_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("rounds.id", ondelete="CASCADE")),
        sa.Column("agent", sa.String(), nullable=False),
        sa.Column("status", sa.String(), server_default="running"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("recommendations", postgresql.JSONB(), server_default="[]"),
        sa.Column("concerns", postgresql.JSONB(), server_default="[]"),
        sa.Column("raw_output", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.UniqueConstraint("task_id", "round_id", "agent"),
    )
    op.create_index("idx_analyses_task", "analyses", ["task_id"])
    op.create_index("idx_analyses_agent", "analyses", ["agent"])

    # Questions table
    op.create_table(
        "questions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tasks.id", ondelete="CASCADE")),
        sa.Column("round_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("rounds.id", ondelete="CASCADE"), nullable=True),
        sa.Column("agent", sa.String(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("answered_by", sa.String(), nullable=True),
        sa.Column("status", sa.String(), server_default="pending"),
        sa.Column("duplicate_of", postgresql.UUID(as_uuid=False), sa.ForeignKey("questions.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_questions_task", "questions", ["task_id"])
    op.create_index("idx_questions_status", "questions", ["status"])

    # Decisions table
    op.create_table(
        "decisions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tasks.id", ondelete="CASCADE")),
        sa.Column("topic", sa.String(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("confidence", sa.String(), nullable=True),
        sa.Column("supersedes", postgresql.UUID(as_uuid=False), sa.ForeignKey("decisions.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_decisions_task", "decisions", ["task_id"])

    # Findings table
    op.create_table(
        "findings",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tasks.id", ondelete="CASCADE")),
        sa.Column("round_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("rounds.id", ondelete="CASCADE")),
        sa.Column("analysis_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("analyses.id", ondelete="CASCADE")),
        sa.Column("agent", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("finding", sa.Text(), nullable=False),
        sa.Column("file_path", sa.String(), nullable=True),
        sa.Column("line_start", sa.Integer(), nullable=True),
        sa.Column("line_end", sa.Integer(), nullable=True),
        sa.Column("code_snippet", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(), nullable=True),
        sa.Column("confidence", sa.String(), nullable=True),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_findings_task", "findings", ["task_id"])
    op.create_index("idx_findings_agent", "findings", ["agent"])
    op.create_index("idx_findings_severity", "findings", ["severity"])

    # Consensus table
    op.create_table(
        "consensus",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tasks.id", ondelete="CASCADE")),
        sa.Column("final_round", sa.Integer(), nullable=False),
        sa.Column("agreement_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("agreed_items", postgresql.JSONB(), server_default="[]"),
        sa.Column("implementation_plan", postgresql.JSONB(), nullable=True),
        sa.Column("human_approved", sa.Boolean(), server_default="false"),
        sa.Column("human_notes", sa.Text(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_consensus_task", "consensus", ["task_id"])

    # Disagreements table
    op.create_table(
        "disagreements",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tasks.id", ondelete="CASCADE")),
        sa.Column("consensus_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("consensus.id", ondelete="CASCADE")),
        sa.Column("topic", sa.String(), nullable=False),
        sa.Column("gemini_position", sa.Text(), nullable=False),
        sa.Column("gemini_evidence", sa.Text(), nullable=True),
        sa.Column("claude_position", sa.Text(), nullable=False),
        sa.Column("claude_evidence", sa.Text(), nullable=True),
        sa.Column("impact", sa.Text(), nullable=True),
        sa.Column("human_decision", sa.String(), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("resolved", sa.Boolean(), server_default="false"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_disagreements_task", "disagreements", ["task_id"])

    # Implementation tasks table
    op.create_table(
        "impl_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tasks.id", ondelete="CASCADE")),
        sa.Column("consensus_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("consensus.id", ondelete="CASCADE"), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("files_to_modify", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("files_to_create", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("files_to_delete", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("acceptance_criteria", sa.Text(), nullable=True),
        sa.Column("dependencies", postgresql.ARRAY(sa.Integer()), nullable=True),
        sa.Column("status", sa.String(), server_default="pending"),
        sa.Column("codex_attempts", sa.Integer(), server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_impl_tasks_task", "impl_tasks", ["task_id"])
    op.create_index("idx_impl_tasks_status", "impl_tasks", ["status"])

    # Verifications table
    op.create_table(
        "verifications",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tasks.id", ondelete="CASCADE")),
        sa.Column("tests_ran", sa.Boolean(), server_default="false"),
        sa.Column("tests_passed", sa.Boolean(), nullable=True),
        sa.Column("tests_total", sa.Integer(), nullable=True),
        sa.Column("tests_failed", sa.Integer(), nullable=True),
        sa.Column("tests_output", sa.Text(), nullable=True),
        sa.Column("lint_ran", sa.Boolean(), server_default="false"),
        sa.Column("lint_passed", sa.Boolean(), nullable=True),
        sa.Column("lint_warnings", sa.Integer(), nullable=True),
        sa.Column("lint_errors", sa.Integer(), nullable=True),
        sa.Column("lint_output", sa.Text(), nullable=True),
        sa.Column("build_ran", sa.Boolean(), server_default="false"),
        sa.Column("build_passed", sa.Boolean(), nullable=True),
        sa.Column("build_output", sa.Text(), nullable=True),
        sa.Column("files_changed", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("files_created", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("files_deleted", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("lines_added", sa.Integer(), nullable=True),
        sa.Column("lines_removed", sa.Integer(), nullable=True),
        sa.Column("matches_plan", sa.Boolean(), nullable=True),
        sa.Column("plan_deviations", postgresql.JSONB(), server_default="[]"),
        sa.Column("issues", postgresql.JSONB(), server_default="[]"),
        sa.Column("overall_status", sa.String(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_verifications_task", "verifications", ["task_id"])

    # Execution log table
    op.create_table(
        "execution_log",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tasks.id", ondelete="CASCADE")),
        sa.Column("phase", sa.String(), nullable=False),
        sa.Column("event", sa.String(), nullable=False),
        sa.Column("agent", sa.String(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_execution_log_task", "execution_log", ["task_id"])
    op.create_index("idx_execution_log_phase", "execution_log", ["phase"])

    # Global tables

    # Memories table
    op.create_table(
        "memories",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("source_task_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Numeric(3, 2), server_default="1.0"),
        sa.Column("times_referenced", sa.Integer(), server_default="0"),
        sa.Column("last_referenced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("category", "key"),
    )
    op.create_index("idx_memories_category", "memories", ["category"])

    # Patterns table
    op.create_table(
        "patterns",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("pattern_type", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("examples", postgresql.JSONB(), server_default="[]"),
        sa.Column("applies_to", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("source_tasks", postgresql.ARRAY(postgresql.UUID(as_uuid=False)), nullable=True),
        sa.Column("times_applied", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("pattern_type", "name"),
    )
    op.create_index("idx_patterns_type", "patterns", ["pattern_type"])

    # Preferences table
    op.create_table(
        "preferences",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("key", sa.String(), unique=True, nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("set_by", sa.String(), server_default="human"),
        sa.Column("source_task_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Guardrails table
    op.create_table(
        "guardrails",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Human interventions table
    op.create_table(
        "human_interventions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tasks.id", ondelete="CASCADE")),
        sa.Column("intervention_type", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("target_agent", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("acknowledged", sa.Boolean(), server_default="false"),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Artifacts table
    op.create_table(
        "artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tasks.id", ondelete="CASCADE")),
        sa.Column("round_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("rounds.id", ondelete="CASCADE"), nullable=True),
        sa.Column("agent", sa.String(), nullable=True),
        sa.Column("artifact_type", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_artifacts_task", "artifacts", ["task_id"])

    # File snapshots table
    op.create_table(
        "file_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tasks.id", ondelete="CASCADE")),
        sa.Column("round_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("rounds.id"), nullable=True),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("line_count", sa.Integer(), nullable=True),
        sa.Column("byte_size", sa.Integer(), nullable=True),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("task_id", "round_id", "file_path"),
    )

    # Reviews table
    op.create_table(
        "reviews",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tasks.id", ondelete="CASCADE")),
        sa.Column("agent", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("issues", postgresql.JSONB(), server_default="[]"),
        sa.Column("raw_output", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Insert default guardrails
    op.execute("""
        INSERT INTO guardrails (key, value, description) VALUES
        ('timeouts', '{"agent_invocation_seconds": 300, "round_total_seconds": 720, "debate_total_seconds": 1800, "codex_per_task_seconds": 600, "verification_seconds": 120}', 'Timeout values for various operations'),
        ('retries', '{"agent_failure": 2, "rate_limit": 3, "codex_per_task": 2, "verification": 1}', 'Maximum retry attempts'),
        ('thresholds', '{"consensus_target_percent": 80, "max_rounds": 3, "max_files_without_confirmation": 10, "max_questions_per_round": 10, "deadlock_threshold_percent": 60, "deadlock_round": 2}', 'Decision thresholds'),
        ('backoff', '{"initial_wait_seconds": 5, "multiplier": 2, "max_wait_seconds": 60}', 'Exponential backoff configuration'),
        ('escalation', '{"consecutive_failures": 3, "security_keywords": ["password", "secret", "token", "credential", "auth", "private_key"], "sensitive_paths": [".env", "credentials", "secrets", "config/prod", "*.pem", "*.key"]}', 'Human escalation triggers')
    """)

    # ============================================================
    # VIEWS
    # ============================================================

    # Current status of all tasks
    op.execute("""
        CREATE OR REPLACE VIEW v_task_status AS
        SELECT
            t.id,
            t.slug,
            t.title,
            t.status,
            t.complexity,
            t.current_round,
            t.max_rounds,
            COUNT(DISTINCT q.id) FILTER (WHERE q.status = 'pending') as pending_questions,
            COUNT(DISTINCT a.id) FILTER (WHERE a.status = 'completed') as completed_analyses,
            COUNT(DISTINCT it.id) as total_impl_tasks,
            COUNT(DISTINCT it.id) FILTER (WHERE it.status = 'completed') as completed_impl_tasks,
            c.human_approved,
            t.created_at,
            t.updated_at
        FROM tasks t
        LEFT JOIN questions q ON q.task_id = t.id
        LEFT JOIN analyses a ON a.task_id = t.id
        LEFT JOIN consensus c ON c.task_id = t.id
        LEFT JOIN impl_tasks it ON it.task_id = t.id
        GROUP BY t.id, c.human_approved
    """)

    # Pending questions needing answers
    op.execute("""
        CREATE OR REPLACE VIEW v_pending_questions AS
        SELECT
            t.slug as task_slug,
            q.id as question_id,
            q.agent,
            q.question,
            q.context,
            q.category,
            r.round_number,
            q.created_at
        FROM questions q
        JOIN tasks t ON q.task_id = t.id
        LEFT JOIN rounds r ON q.round_id = r.id
        WHERE q.status = 'pending'
        ORDER BY q.created_at
    """)

    # Latest analysis per agent per task
    op.execute("""
        CREATE OR REPLACE VIEW v_latest_analyses AS
        SELECT DISTINCT ON (a.task_id, a.agent)
            t.slug as task_slug,
            a.agent,
            a.status,
            a.summary,
            a.recommendations,
            a.concerns,
            r.round_number,
            a.completed_at
        FROM analyses a
        JOIN tasks t ON a.task_id = t.id
        JOIN rounds r ON a.round_id = r.id
        ORDER BY a.task_id, a.agent, r.round_number DESC
    """)

    # Memory search helper
    op.execute("""
        CREATE OR REPLACE VIEW v_memory_search AS
        SELECT
            category,
            key,
            value,
            context,
            confidence,
            times_referenced,
            last_referenced_at
        FROM memories
        ORDER BY confidence DESC, times_referenced DESC
    """)

    # Implementation progress
    op.execute("""
        CREATE OR REPLACE VIEW v_impl_progress AS
        SELECT
            t.slug as task_slug,
            COUNT(*) as total_tasks,
            COUNT(*) FILTER (WHERE it.status = 'completed') as completed,
            COUNT(*) FILTER (WHERE it.status = 'in_progress') as in_progress,
            COUNT(*) FILTER (WHERE it.status = 'failed') as failed,
            COUNT(*) FILTER (WHERE it.status = 'needs_human') as needs_human,
            COUNT(*) FILTER (WHERE it.status = 'pending') as pending
        FROM impl_tasks it
        JOIN tasks t ON it.task_id = t.id
        GROUP BY t.slug
    """)

    # Recent execution events (for debugging)
    op.execute("""
        CREATE OR REPLACE VIEW v_recent_events AS
        SELECT
            t.slug as task_slug,
            el.phase,
            el.event,
            el.agent,
            el.message,
            el.duration_ms,
            el.created_at
        FROM execution_log el
        JOIN tasks t ON el.task_id = t.id
        ORDER BY el.created_at DESC
        LIMIT 100
    """)

    # File drift detection
    op.execute("""
        CREATE OR REPLACE VIEW v_file_drift AS
        SELECT
            t.slug,
            fs1.file_path,
            fs1.content_hash as round1_hash,
            fs2.content_hash as round2_hash,
            fs1.content_hash != fs2.content_hash as has_drift
        FROM file_snapshots fs1
        JOIN file_snapshots fs2 ON fs1.task_id = fs2.task_id AND fs1.file_path = fs2.file_path
        JOIN tasks t ON fs1.task_id = t.id
        JOIN rounds r1 ON fs1.round_id = r1.id
        JOIN rounds r2 ON fs2.round_id = r2.id
        WHERE r1.round_number = 1 AND r2.round_number > 1
    """)

    # ============================================================
    # HELPER FUNCTIONS
    # ============================================================

    # Get guardrail value with type safety
    op.execute("""
        CREATE OR REPLACE FUNCTION get_guardrail(p_key TEXT, p_subkey TEXT)
        RETURNS TEXT AS $$
        BEGIN
            RETURN (SELECT value->>p_subkey FROM guardrails WHERE key = p_key);
        END;
        $$ LANGUAGE plpgsql
    """)

    # Log an execution event
    op.execute("""
        CREATE OR REPLACE FUNCTION log_event(
            p_task_id UUID,
            p_phase TEXT,
            p_event TEXT,
            p_agent TEXT DEFAULT NULL,
            p_message TEXT DEFAULT NULL,
            p_details JSONB DEFAULT NULL,
            p_duration_ms INTEGER DEFAULT NULL
        ) RETURNS UUID AS $$
        DECLARE
            v_id UUID;
        BEGIN
            INSERT INTO execution_log (id, task_id, phase, event, agent, message, details, duration_ms)
            VALUES (gen_random_uuid(), p_task_id, p_phase, p_event, p_agent, p_message, p_details, p_duration_ms)
            RETURNING id INTO v_id;
            RETURN v_id;
        END;
        $$ LANGUAGE plpgsql
    """)

    # Update task status with logging
    op.execute("""
        CREATE OR REPLACE FUNCTION update_task_status(
            p_task_id UUID,
            p_new_status TEXT,
            p_error_message TEXT DEFAULT NULL
        ) RETURNS VOID AS $$
        DECLARE
            v_old_status TEXT;
        BEGIN
            SELECT status INTO v_old_status FROM tasks WHERE id = p_task_id;

            UPDATE tasks
            SET status = p_new_status,
                updated_at = NOW(),
                error_message = COALESCE(p_error_message, error_message),
                completed_at = CASE WHEN p_new_status IN ('completed', 'failed') THEN NOW() ELSE completed_at END
            WHERE id = p_task_id;

            PERFORM log_event(
                p_task_id,
                'status_change',
                'status_updated',
                NULL,
                format('Status changed from %s to %s', v_old_status, p_new_status),
                jsonb_build_object('old_status', v_old_status, 'new_status', p_new_status)
            );
        END;
        $$ LANGUAGE plpgsql
    """)

    # Reference a memory (updates usage stats)
    op.execute("""
        CREATE OR REPLACE FUNCTION reference_memory(p_memory_id UUID)
        RETURNS VOID AS $$
        BEGIN
            UPDATE memories
            SET times_referenced = times_referenced + 1,
                last_referenced_at = NOW()
            WHERE id = p_memory_id;
        END;
        $$ LANGUAGE plpgsql
    """)

    # Check if task has exceeded timeout
    op.execute("""
        CREATE OR REPLACE FUNCTION check_task_timeout(p_task_id UUID)
        RETURNS BOOLEAN AS $$
        DECLARE
            v_created_at TIMESTAMPTZ;
            v_timeout_seconds INTEGER;
        BEGIN
            SELECT created_at INTO v_created_at FROM tasks WHERE id = p_task_id;
            SELECT (value->>'debate_total_seconds')::INTEGER INTO v_timeout_seconds FROM guardrails WHERE key = 'timeouts';
            RETURN (EXTRACT(EPOCH FROM (NOW() - v_created_at)) > v_timeout_seconds);
        END;
        $$ LANGUAGE plpgsql
    """)

    # ============================================================
    # TRIGGERS
    # ============================================================

    # Automatically update tasks.updated_at on any change
    op.execute("""
        CREATE OR REPLACE FUNCTION update_task_timestamp()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    op.execute("DROP TRIGGER IF EXISTS trigger_update_task_timestamp ON tasks")
    op.execute("""
        CREATE TRIGGER trigger_update_task_timestamp
        BEFORE UPDATE ON tasks
        FOR EACH ROW
        EXECUTE FUNCTION update_task_timestamp()
    """)


def downgrade() -> None:
    op.drop_table("reviews")
    op.drop_table("file_snapshots")
    op.drop_table("artifacts")
    op.drop_table("human_interventions")
    op.drop_table("guardrails")
    op.drop_table("preferences")
    op.drop_table("patterns")
    op.drop_table("memories")
    op.drop_table("execution_log")
    op.drop_table("verifications")
    op.drop_table("impl_tasks")
    op.drop_table("disagreements")
    op.drop_table("consensus")
    op.drop_table("findings")
    op.drop_table("decisions")
    op.drop_table("questions")
    op.drop_table("analyses")
    op.drop_table("rounds")
    op.drop_table("explorations")
    op.drop_table("conversations")
    op.drop_table("tasks")
