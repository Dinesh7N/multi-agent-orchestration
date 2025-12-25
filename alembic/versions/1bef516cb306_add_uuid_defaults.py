"""Add UUID defaults

Revision ID: 1bef516cb306
Revises: 001
Create Date: 2025-12-10 16:23:01.943518

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '1bef516cb306'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tables with UUID primary keys that need defaults
TABLES_WITH_UUID_PK = [
    "tasks",
    "conversations",
    "explorations",
    "rounds",
    "analyses",
    "questions",
    "decisions",
    "findings",
    "consensus",
    "disagreements",
    "impl_tasks",
    "verifications",
    "execution_log",
    "memories",
    "patterns",
    "preferences",
    "human_interventions",
    "artifacts",
    "file_snapshots",
    "reviews",
]


def upgrade() -> None:
    for table in TABLES_WITH_UUID_PK:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN id SET DEFAULT gen_random_uuid()")


def downgrade() -> None:
    for table in TABLES_WITH_UUID_PK:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN id DROP DEFAULT")
