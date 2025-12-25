from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "3a9b1f0e2c91"
down_revision: str | None = "2f3a1c0c7e8a"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "findings",
        sa.Column("agreed_by", postgresql.ARRAY(sa.String()), nullable=True),
    )
    op.add_column(
        "findings",
        sa.Column("disputed_by", postgresql.ARRAY(sa.String()), nullable=True),
    )
    op.add_column("findings", sa.Column("dispute_reason", sa.Text(), nullable=True))

    op.add_column("analyses", sa.Column("input_tokens", sa.Integer(), nullable=True))
    op.add_column("analyses", sa.Column("output_tokens", sa.Integer(), nullable=True))
    op.add_column("analyses", sa.Column("total_tokens", sa.Integer(), nullable=True))
    op.add_column("analyses", sa.Column("cost_estimate", sa.Numeric(10, 6), nullable=True))
    op.add_column("analyses", sa.Column("model_used", sa.Text(), nullable=True))
    op.add_column(
        "analyses",
        sa.Column("recommendation_embeddings", postgresql.ARRAY(sa.Float()), nullable=True),
    )
    op.add_column(
        "analyses", sa.Column("recommendation_embedding_model", sa.Text(), nullable=True)
    )
    op.add_column(
        "analyses", sa.Column("recommendation_embedding_dim", sa.Integer(), nullable=True)
    )

    op.add_column("rounds", sa.Column("consensus_breakdown", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")))

    op.add_column("tasks", sa.Column("total_tokens", sa.Integer(), server_default="0"))
    op.add_column("tasks", sa.Column("total_cost", sa.Numeric(10, 6), server_default="0"))

    op.add_column("explorations", sa.Column("input_tokens", sa.Integer(), nullable=True))
    op.add_column("explorations", sa.Column("output_tokens", sa.Integer(), nullable=True))
    op.add_column("explorations", sa.Column("cost_estimate", sa.Numeric(10, 6), nullable=True))

    op.create_table(
        "cost_log",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "analysis_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("analyses.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("agent", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_per_input_token", sa.Numeric(12, 10), nullable=True),
        sa.Column("cost_per_output_token", sa.Numeric(12, 10), nullable=True),
        sa.Column("total_cost", sa.Numeric(10, 6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_cost_log_task", "cost_log", ["task_id"])
    op.create_index("idx_cost_log_created", "cost_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_cost_log_created", table_name="cost_log")
    op.drop_index("idx_cost_log_task", table_name="cost_log")
    op.drop_table("cost_log")

    op.drop_column("explorations", "cost_estimate")
    op.drop_column("explorations", "output_tokens")
    op.drop_column("explorations", "input_tokens")

    op.drop_column("tasks", "total_cost")
    op.drop_column("tasks", "total_tokens")

    op.drop_column("rounds", "consensus_breakdown")

    op.drop_column("analyses", "recommendation_embedding_dim")
    op.drop_column("analyses", "recommendation_embedding_model")
    op.drop_column("analyses", "recommendation_embeddings")
    op.drop_column("analyses", "model_used")
    op.drop_column("analyses", "cost_estimate")
    op.drop_column("analyses", "total_tokens")
    op.drop_column("analyses", "output_tokens")
    op.drop_column("analyses", "input_tokens")

    op.drop_column("findings", "dispute_reason")
    op.drop_column("findings", "disputed_by")
    op.drop_column("findings", "agreed_by")
