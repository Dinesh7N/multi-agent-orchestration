from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2f3a1c0c7e8a"
down_revision: str | None = "1c0640e3ceda"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("rounds", sa.Column("gemini_session_id", sa.String(), nullable=True))
    op.add_column("rounds", sa.Column("claude_session_id", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("rounds", "claude_session_id")
    op.drop_column("rounds", "gemini_session_id")
