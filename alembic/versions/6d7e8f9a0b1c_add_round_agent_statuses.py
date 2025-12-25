"""Add agent_statuses JSONB to rounds.

Revision ID: 6d7e8f9a0b1c
Revises: 5c6d7e8f9a0b
Create Date: 2025-12-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "6d7e8f9a0b1c"
down_revision: str | None = "5c6d7e8f9a0b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rounds",
        sa.Column(
            "agent_statuses",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    # Backfill for existing rows so legacy statuses remain visible.
    op.execute(
        """
        UPDATE rounds
        SET agent_statuses = jsonb_build_object(
            'gemini', gemini_status,
            'claude', claude_status
        )
        """
    )


def downgrade() -> None:
    op.drop_column("rounds", "agent_statuses")
