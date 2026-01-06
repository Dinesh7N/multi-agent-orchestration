"""
Multi-Agent Debate Workflow

This package provides tools for orchestrating multi-agent debates
between AI models (Gemini, Claude, Codex) with PostgreSQL-backed state management.
"""

__version__ = "0.1.0"

# Core models
# Configuration
from debate.config import Settings

# Consensus calculation
from debate.consensus import ConsensusBreakdown, ConsensusCalculator

# Cost tracking
from debate.costs import ModelPricing, TokenUsage
from debate.models import (
    Analysis,
    Consensus,
    CostLog,
    Decision,
    Exploration,
    Finding,
    ImplTask,
    Round,
    Task,
    Verification,
)

# Role configuration
from debate.role_config import Role, RoleConfig

# Agent types
from debate.run_agent import AgentResult, AgentType, Phase

# Task triage
from debate.triage import Complexity, TaskTriager, TriageResult

from debate.langgraph_app import orchestrate as orchestrate_langgraph

__all__ = [
    # Version
    "__version__",
    # Models
    "Task",
    "Round",
    "Consensus",
    "Exploration",
    "Analysis",
    "Finding",
    "Decision",
    "Verification",
    "ImplTask",
    "CostLog",
    # Config
    "Settings",
    # Consensus
    "ConsensusCalculator",
    "ConsensusBreakdown",
    # Costs
    "ModelPricing",
    "TokenUsage",
    # Triage
    "TaskTriager",
    "TriageResult",
    "Complexity",
    # Orchestration
    "orchestrate_langgraph",
    # Agent
    "AgentType",
    "Phase",
    "AgentResult",
    # Roles
    "Role",
    "RoleConfig",
]
