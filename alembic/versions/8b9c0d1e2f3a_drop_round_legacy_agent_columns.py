"""Drop legacy per-agent status/session columns from rounds.

Revision ID: 8b9c0d1e2f3a
Revises: 7a8b9c0d1e2f
Create Date: 2025-12-25

"""

from collections.abc import Sequence

from alembic import op

revision: str = "8b9c0d1e2f3a"
down_revision: str | None = "7a8b9c0d1e2f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE rounds DROP COLUMN IF EXISTS gemini_status")
    op.execute("ALTER TABLE rounds DROP COLUMN IF EXISTS claude_status")
    op.execute("ALTER TABLE rounds DROP COLUMN IF EXISTS gemini_session_id")
    op.execute("ALTER TABLE rounds DROP COLUMN IF EXISTS claude_session_id")


def downgrade() -> None:
    raise RuntimeError("Irreversible migration: legacy columns cannot be restored safely")
