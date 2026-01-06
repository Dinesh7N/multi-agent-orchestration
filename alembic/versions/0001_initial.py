"""Initial schema (reset Alembic history).

Revision ID: 0001_initial
Revises: None
Create Date: 2025-12-30
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    from debate.models import Base

    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    from debate.models import Base

    Base.metadata.drop_all(bind=bind)

