"""
Standardized event system for debate workflow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
from typing import Any, Optional
from uuid import UUID, uuid4


class EventType(str, Enum):
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"
    WORKFLOW_PAUSED = "workflow.paused"

    PHASE_STARTED = "phase.started"
    PHASE_COMPLETED = "phase.completed"

    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"
    AGENT_TIMEOUT = "agent.timeout"

    CONSENSUS_CALCULATED = "consensus.calculated"
    CONSENSUS_REACHED = "consensus.reached"
    CONSENSUS_NOT_REACHED = "consensus.not_reached"

    HUMAN_INPUT_REQUESTED = "human.input_requested"
    HUMAN_INPUT_RECEIVED = "human.input_received"
    HUMAN_APPROVAL_REQUESTED = "human.approval_requested"
    HUMAN_APPROVED = "human.approved"
    HUMAN_REJECTED = "human.rejected"

    COST_LOGGED = "cost.logged"
    BUDGET_WARNING = "budget.warning"
    BUDGET_EXCEEDED = "budget.exceeded"


@dataclass
class EventActions:
    """Actions that can be triggered by an event."""

    escalate: bool = False
    transfer_to: Optional[str] = None
    retry: bool = False
    pause: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "escalate": self.escalate,
            "transfer_to": self.transfer_to,
            "retry": self.retry,
            "pause": self.pause,
        }


@dataclass
class DebateEvent:
    """Standardized event for the debate system."""

    id: UUID = field(default_factory=uuid4)
    type: EventType = EventType.WORKFLOW_STARTED
    task_id: Optional[UUID] = None
    round_number: Optional[int] = None
    phase: Optional[str] = None
    agent: Optional[str] = None
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    actions: EventActions = field(default_factory=EventActions)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "type": self.type.value,
            "task_id": str(self.task_id) if self.task_id else None,
            "round_number": self.round_number,
            "phase": self.phase,
            "agent": self.agent,
            "message": self.message,
            "data": self.data,
            "actions": self.actions.to_dict(),
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": self.duration_ms,
        }


class EventEmitter:
    """Emits events to registered handlers."""

    def __init__(self) -> None:
        self._handlers: list[callable] = []

    def on_event(self, handler: callable) -> None:
        self._handlers.append(handler)

    async def emit(self, event: DebateEvent) -> None:
        for handler in self._handlers:
            try:
                result = handler(event)
                if hasattr(result, "__await__"):
                    await result
            except Exception as exc:
                print(f"Event handler error: {exc}")


event_bus = EventEmitter()


async def emit_agent_started(
    task_id: UUID, agent: str, round_number: int, phase: str
) -> DebateEvent:
    event = DebateEvent(
        type=EventType.AGENT_STARTED,
        task_id=task_id,
        agent=agent,
        round_number=round_number,
        phase=phase,
        message=f"Agent {agent} started for round {round_number}",
    )
    await event_bus.emit(event)
    return event


async def emit_agent_completed(
    task_id: UUID,
    agent: str,
    round_number: int,
    phase: str,
    *,
    duration_ms: int | None = None,
) -> DebateEvent:
    event = DebateEvent(
        type=EventType.AGENT_COMPLETED,
        task_id=task_id,
        agent=agent,
        round_number=round_number,
        phase=phase,
        message=f"Agent {agent} completed for round {round_number}",
        duration_ms=duration_ms,
    )
    await event_bus.emit(event)
    return event


async def emit_agent_failed(
    task_id: UUID,
    agent: str,
    round_number: int,
    phase: str,
    error: str,
    *,
    duration_ms: int | None = None,
) -> DebateEvent:
    event = DebateEvent(
        type=EventType.AGENT_FAILED,
        task_id=task_id,
        agent=agent,
        round_number=round_number,
        phase=phase,
        message=f"Agent {agent} failed for round {round_number}",
        data={"error": error},
        duration_ms=duration_ms,
    )
    await event_bus.emit(event)
    return event


async def emit_consensus_calculated(
    task_id: UUID,
    round_number: int,
    agreement_rate: float,
    breakdown: dict[str, Any],
) -> DebateEvent:
    threshold_met = agreement_rate >= 80.0
    event = DebateEvent(
        type=EventType.CONSENSUS_REACHED if threshold_met else EventType.CONSENSUS_NOT_REACHED,
        task_id=task_id,
        round_number=round_number,
        message=f"Consensus {'reached' if threshold_met else 'not reached'}: {agreement_rate:.1f}%",
        data={
            "agreement_rate": agreement_rate,
            "breakdown": breakdown,
        },
        actions=EventActions(escalate=threshold_met),
    )
    await event_bus.emit(event)
    return event


async def persist_event_handler(event: DebateEvent) -> None:
    """Handler that persists events to the database."""
    from .db import get_session, log_event

    async with get_session() as session:
        task = None
        if event.task_id:
            from .db import get_task_by_id

            task = await get_task_by_id(session, str(event.task_id))
        if not task:
            return

        await log_event(
            session,
            task_id=task.id,
            phase=event.phase or "unknown",
            event=event.type.value,
            agent=event.agent,
            message=event.message,
            details=event.data,
            duration_ms=event.duration_ms,
        )
        await session.commit()


event_bus.on_event(persist_event_handler)


async def publish_event_handler(event: DebateEvent) -> None:
    """Handler that publishes events to Redis Pub/Sub."""
    if not event.task_id:
        return

    try:
        from .redis_client import get_redis_client

        redis = get_redis_client()
        channel = f"channel:task:{event.task_id}"
        await redis.publish(channel, json.dumps(event.to_dict()))
    except Exception as exc:
        print(f"Redis publish failed: {exc}")


event_bus.on_event(publish_event_handler)
