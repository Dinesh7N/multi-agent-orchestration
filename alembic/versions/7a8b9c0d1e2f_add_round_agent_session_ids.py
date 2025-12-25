"""Add agent_session_ids JSONB to rounds.

Revision ID: 7a8b9c0d1e2f
Revises: 6d7e8f9a0b1c
Create Date: 2025-12-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "7a8b9c0d1e2f"
down_revision: str | None = "6d7e8f9a0b1c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rounds",
        sa.Column(
            "agent_session_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    op.execute(
        """
        UPDATE rounds
        SET agent_session_ids = jsonb_strip_nulls(
            jsonb_build_object(
                'gemini', gemini_session_id,
                'claude', claude_session_id
            )
        )
        WHERE gemini_session_id IS NOT NULL OR claude_session_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_column("rounds", "agent_session_ids")
