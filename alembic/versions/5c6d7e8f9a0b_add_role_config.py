"""Add role_config to guardrails table.

Revision ID: 5c6d7e8f9a0b
Revises: 4b2c3d4e5f6a
Create Date: 2025-12-25

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5c6d7e8f9a0b"
down_revision: str | None = "4b2c3d4e5f6a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Insert role_config into guardrails table.

    This creates the role-to-agent mapping that enables flexible configuration
    where any model can be used for any purpose (planning, implementing, reviewing).

    Default configuration mirrors current hardcoded behavior:
    - planner_primary: debate_gemini (large context analysis)
    - planner_secondary: debate_claude (security focus)
    - implementer: debate_codex (code generation)
    - reviewer: debate_claude (code review)
    - explorer: debate_gemini (codebase discovery)
    """
    op.execute(
        """
        INSERT INTO guardrails (key, value, description)
        VALUES (
            'role_config',
            '{
                "planner_primary": {
                    "agent_key": "debate_gemini",
                    "prompt_template": "gemini.md",
                    "description": "Primary planning agent for comprehensive analysis",
                    "capabilities": ["large_context", "pattern_recognition", "data_flow_analysis"]
                },
                "planner_secondary": {
                    "agent_key": "debate_claude",
                    "prompt_template": "claude.md",
                    "description": "Secondary planning agent focused on security and edge cases",
                    "capabilities": [
                        "security_analysis",
                        "architectural_reasoning",
                        "compliance_review"
                    ]
                },

                "implementer": {
                    "agent_key": "debate_codex",
                    "prompt_template": "codex.md",
                    "description": "Code implementation agent that executes approved plans",
                    "capabilities": ["code_generation"]
                },
                "reviewer": {
                    "agent_key": "debate_claude",
                    "prompt_template": "claude.md",
                    "description": "Code review and validation agent with security focus",
                    "capabilities": ["security_analysis", "code_quality", "compliance_review"]
                },
                "explorer": {
                    "agent_key": "debate_gemini",
                    "prompt_template": "gemini.md",
                    "description": "Codebase exploration and discovery agent",
                    "capabilities": ["large_context", "pattern_recognition"]
                }
            }'::jsonb,
            'Role-based agent configuration. Maps workflow roles (planner, implementer, reviewer) '
            || 'to agent execution contexts. '
            || 'Priority: ROLE_{ROLE}_AGENT/MODEL/PROMPT env vars > DB > hardcoded defaults. '
            || 'Use CLI: uv run debate role-config list|get|set|delete'
        )
        ON CONFLICT (key) DO UPDATE SET
            value = EXCLUDED.value,
            description = EXCLUDED.description,
            updated_at = NOW();
        """
    )


def downgrade() -> None:
    """Remove role_config from guardrails table."""
    op.execute("DELETE FROM guardrails WHERE key = 'role_config';")
