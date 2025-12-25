"""
Base workflow abstractions for debate system.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generic, Optional, TypeVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


class WorkflowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


@dataclass
class WorkflowContext:
    """Context passed through workflow execution."""

    session: AsyncSession
    task_id: UUID
    task_slug: str
    round_number: int = 0
    state: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.state.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.state[key] = value


@dataclass
class WorkflowResult:
    """Result of a workflow step."""

    status: WorkflowStatus
    output: Any = None
    error: Optional[str] = None
    next_step: Optional[str] = None

    @classmethod
    def success(cls, output: Any = None) -> "WorkflowResult":
        return cls(status=WorkflowStatus.COMPLETED, output=output)

    @classmethod
    def failed(cls, error: str) -> "WorkflowResult":
        return cls(status=WorkflowStatus.FAILED, error=error)

    @classmethod
    def paused(cls, reason: str) -> "WorkflowResult":
        return cls(status=WorkflowStatus.PAUSED, output=reason)


T = TypeVar("T")


class WorkflowStep(ABC, Generic[T]):
    """Base class for a workflow step."""

    name: str
    description: str = ""

    @abstractmethod
    async def execute(self, ctx: WorkflowContext) -> WorkflowResult:
        pass

    async def on_start(self, ctx: WorkflowContext) -> None:
        del ctx

    async def on_complete(self, ctx: WorkflowContext, result: WorkflowResult) -> None:
        del ctx
        del result

    async def on_error(self, ctx: WorkflowContext, error: Exception) -> None:
        del ctx
        del error


class SequentialWorkflow(WorkflowStep):
    """Executes steps in sequence."""

    def __init__(self, name: str, steps: list[WorkflowStep]):
        self.name = name
        self.steps = steps

    async def execute(self, ctx: WorkflowContext) -> WorkflowResult:
        for step in self.steps:
            await step.on_start(ctx)
            try:
                result = await step.execute(ctx)
            except Exception as exc:
                await step.on_error(ctx, exc)
                return WorkflowResult.failed(str(exc))
            await step.on_complete(ctx, result)
            if result.status != WorkflowStatus.COMPLETED:
                return result
        return WorkflowResult.success()


class ParallelWorkflow(WorkflowStep):
    """Executes steps in parallel."""

    def __init__(self, name: str, steps: list[WorkflowStep]):
        self.name = name
        self.steps = steps

    async def execute(self, ctx: WorkflowContext) -> WorkflowResult:
        import asyncio

        async def run_step(step: WorkflowStep) -> WorkflowResult:
            await step.on_start(ctx)
            try:
                result = await step.execute(ctx)
                await step.on_complete(ctx, result)
                return result
            except Exception as exc:
                await step.on_error(ctx, exc)
                return WorkflowResult.failed(str(exc))

        results = await asyncio.gather(
            *[run_step(step) for step in self.steps],
            return_exceptions=True,
        )

        for result in results:
            if isinstance(result, Exception):
                return WorkflowResult.failed(str(result))
            if result.status == WorkflowStatus.FAILED:
                return result

        return WorkflowResult.success(output=[r.output for r in results])


class LoopWorkflow(WorkflowStep):
    """Executes steps in a loop until condition is met."""

    def __init__(
        self,
        name: str,
        steps: list[WorkflowStep],
        max_iterations: int = 3,
        break_condition: Optional[callable] = None,
    ):
        self.name = name
        self.steps = steps
        self.max_iterations = max_iterations
        self.break_condition = break_condition or (lambda ctx, result: False)

    async def execute(self, ctx: WorkflowContext) -> WorkflowResult:
        for iteration in range(1, self.max_iterations + 1):
            ctx.state["current_iteration"] = iteration
            for step in self.steps:
                await step.on_start(ctx)
                try:
                    result = await step.execute(ctx)
                except Exception as exc:
                    await step.on_error(ctx, exc)
                    return WorkflowResult.failed(str(exc))
                await step.on_complete(ctx, result)
                if result.status in (WorkflowStatus.FAILED, WorkflowStatus.PAUSED):
                    return result
                if self.break_condition(ctx, result):
                    return WorkflowResult.success(
                        output={"iterations": iteration, "result": result.output}
                    )

        return WorkflowResult.success(
            output={"iterations": self.max_iterations, "max_reached": True}
        )
