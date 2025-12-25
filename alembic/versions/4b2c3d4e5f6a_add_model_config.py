"""Add model_config to guardrails table.

Revision ID: 4b2c3d4e5f6a
Revises: 3a9b1f0e2c91
Create Date: 2025-12-24

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "4b2c3d4e5f6a"
down_revision: str | None = "3a9b1f0e2c91"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Insert model_config into guardrails table."""
    op.execute(
        """
        INSERT INTO guardrails (key, value, description)
        VALUES (
            'model_config',
            '{
                "orchestrator": "amazon-bedrock/anthropic.claude-sonnet-4-5-20250929-v1:0",
                "librarian": "opencode/big-pickle",
                "frontend-ui-ux-engineer": "google/gemini-3-pro-high",
                "document-writer": "google/gemini-3-flash",
                "multimodal-looker": "google/gemini-3-flash",
                "debate_gemini": "google/gemini-3-pro-high",
                "debate_claude": "amazon-bedrock/anthropic.claude-sonnet-4-5-20250929-v1:0",
                "debate_codex": "openai/gpt-5.1-codex-max-medium",
                "oracle": "openai/gpt-5.2-high",
                "explore": "google/gemini-3-flash",
                "general": "google/gemini-3-pro-high"
            }'::jsonb,
            'Model configuration for agents. Priority: ENV variable > DB > hardcoded defaults. Use <AGENT_NAME>_MODEL env var to override (e.g., ORCHESTRATOR_MODEL, DEBATE_GEMINI_MODEL).'
        )
        ON CONFLICT (key) DO UPDATE SET
            value = EXCLUDED.value,
            description = EXCLUDED.description,
            updated_at = NOW();
        """
    )


def downgrade() -> None:
    """Remove model_config from guardrails table."""
    op.execute("DELETE FROM guardrails WHERE key = 'model_config';")
