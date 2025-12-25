"""
Debate-specific workflow steps.
"""

from __future__ import annotations

from .. import db
from ..consensus import calculate_round_consensus
from ..role_config import Role
from ..run_agent import AgentType, Phase, run_agent, run_agent_by_role
from .base import WorkflowContext, WorkflowResult, WorkflowStep


class AgentAnalysisStep(WorkflowStep):
    """Run a single agent's analysis."""

    def __init__(self, agent: AgentType):
        self.agent = agent
        self.name = f"{agent.value}_analysis"
        self.description = f"Run {agent.value} analysis"

    async def execute(self, ctx: WorkflowContext) -> WorkflowResult:
        try:
            result = await run_agent(
                task_slug=ctx.task_slug,
                agent=self.agent,
                round_number=ctx.round_number,
                phase=Phase.ANALYSIS,
            )
            ctx.set(f"{self.agent.value}_result", result)
            return WorkflowResult.success(output=result)
        except Exception as exc:
            return WorkflowResult.failed(str(exc))


class RoleAnalysisStep(WorkflowStep):
    def __init__(self, role: Role):
        self.role = role
        self.name = f"{role.value}_analysis"
        self.description = f"Run {role.value} analysis"

    async def execute(self, ctx: WorkflowContext) -> WorkflowResult:
        try:
            result = await run_agent_by_role(
                task_slug=ctx.task_slug,
                role=self.role,
                round_number=ctx.round_number,
                phase=Phase.ANALYSIS,
            )
            ctx.set(f"{self.role.value}_result", result)
            return WorkflowResult.success(output=result)
        except Exception as exc:
            return WorkflowResult.failed(str(exc))


class CreateRoundStep(WorkflowStep):
    """Create a new debate round."""

    name = "create_round"
    description = "Initialize a new debate round"

    async def execute(self, ctx: WorkflowContext) -> WorkflowResult:
        task = await db.get_task_by_id(ctx.session, str(ctx.task_id))
        if not task:
            return WorkflowResult.failed("Task not found for round creation")
        round_obj = await db.get_or_create_round(ctx.session, task, ctx.round_number)
        ctx.set("current_round", round_obj)
        return WorkflowResult.success(output=round_obj)


class ConsensusCheckStep(WorkflowStep):
    """Calculate consensus and check if threshold is met."""

    name = "consensus_check"
    description = "Calculate agreement rate between agents"

    def __init__(self, threshold: float = 80.0):
        self.threshold = threshold

    async def execute(self, ctx: WorkflowContext) -> WorkflowResult:
        round_obj = ctx.get("current_round")
        if not round_obj:
            return WorkflowResult.failed("Missing round context")

        agreement_rate, breakdown = await calculate_round_consensus(ctx.session, round_obj)
        ctx.set("agreement_rate", agreement_rate)
        ctx.set("consensus_breakdown", breakdown.to_dict())

        await db.complete_round(ctx.session, round_obj, agreement_rate, breakdown.to_dict())

        return WorkflowResult.success(
            output={
                "agreement_rate": agreement_rate,
                "threshold_met": agreement_rate >= self.threshold,
                "breakdown": breakdown.to_dict(),
            }
        )


class HumanApprovalStep(WorkflowStep):
    """Wait for human approval."""

    name = "human_approval"
    description = "Request human approval for the plan"

    async def execute(self, ctx: WorkflowContext) -> WorkflowResult:
        task = await db.get_task_by_id(ctx.session, str(ctx.task_id))
        if not task:
            return WorkflowResult.failed("Task not found")

        consensus = await db.get_consensus(ctx.session, task)
        if not consensus:
            return WorkflowResult.failed("No consensus found")

        return WorkflowResult.paused("Waiting for human approval")


class ImplementationStep(WorkflowStep):
    name = "implementation"
    description = "Execute implementation with implementer role"

    async def execute(self, ctx: WorkflowContext) -> WorkflowResult:
        result = await run_agent_by_role(
            task_slug=ctx.task_slug,
            role=Role.IMPLEMENTER,
            round_number=0,
            phase=Phase.IMPLEMENTATION,
        )
        ctx.set("implementation_result", result)
        return WorkflowResult.success(output=result)
