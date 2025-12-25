"""
Complete debate workflow composed from steps.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ..role_config import Role
from .base import (
    LoopWorkflow,
    ParallelWorkflow,
    SequentialWorkflow,
    WorkflowContext,
    WorkflowResult,
)
from .debate_steps import (
    ConsensusCheckStep,
    CreateRoundStep,
    HumanApprovalStep,
    ImplementationStep,
    RoleAnalysisStep,
)


def create_debate_workflow(
    consensus_threshold: float = 80.0,
    max_rounds: int = 3,
) -> SequentialWorkflow:
    parallel_analysis = ParallelWorkflow(
        name="parallel_analysis",
        steps=[
            RoleAnalysisStep(Role.PLANNER_PRIMARY),
            RoleAnalysisStep(Role.PLANNER_SECONDARY),
        ],
    )

    debate_round = SequentialWorkflow(
        name="debate_round",
        steps=[
            CreateRoundStep(),
            parallel_analysis,
            ConsensusCheckStep(threshold=consensus_threshold),
        ],
    )

    def consensus_reached(ctx: WorkflowContext, result: WorkflowResult) -> bool:
        if result.output and isinstance(result.output, dict):
            return result.output.get("threshold_met", False)
        return False

    debate_loop = LoopWorkflow(
        name="debate_loop",
        steps=[debate_round],
        max_iterations=max_rounds,
        break_condition=consensus_reached,
    )

    return SequentialWorkflow(
        name="complete_debate",
        steps=[
            debate_loop,
            HumanApprovalStep(),
            ImplementationStep(),
        ],
    )


async def run_debate_workflow(
    session: AsyncSession,
    task_id: UUID,
    task_slug: str,
    consensus_threshold: float = 80.0,
    max_rounds: int = 3,
) -> WorkflowResult:
    ctx = WorkflowContext(
        session=session,
        task_id=task_id,
        task_slug=task_slug,
    )
    workflow = create_debate_workflow(
        consensus_threshold=consensus_threshold,
        max_rounds=max_rounds,
    )
    return await workflow.execute(ctx)
