"""
API cost tracking and calculation.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import CostLog, Guardrail, Task


@dataclass
class ModelPricing:
    """Pricing per million tokens."""

    input_per_million: Decimal
    output_per_million: Decimal

    def calculate_cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        input_cost = (Decimal(input_tokens) / Decimal(1_000_000)) * self.input_per_million
        output_cost = (Decimal(output_tokens) / Decimal(1_000_000)) * self.output_per_million
        return input_cost + output_cost


MODEL_PRICING: dict[str, ModelPricing] = {
    "gemini-2.5-pro": ModelPricing(
        input_per_million=Decimal("1.25"),
        output_per_million=Decimal("5.00"),
    ),
    "gemini-2.5-flash": ModelPricing(
        input_per_million=Decimal("0.075"),
        output_per_million=Decimal("0.30"),
    ),
    "claude-sonnet-4": ModelPricing(
        input_per_million=Decimal("3.00"),
        output_per_million=Decimal("15.00"),
    ),
    "claude-opus-4": ModelPricing(
        input_per_million=Decimal("15.00"),
        output_per_million=Decimal("75.00"),
    ),
    "gpt-4o": ModelPricing(
        input_per_million=Decimal("2.50"),
        output_per_million=Decimal("10.00"),
    ),
    "codex": ModelPricing(
        input_per_million=Decimal("2.50"),
        output_per_million=Decimal("10.00"),
    ),
}


async def get_pricing(session: AsyncSession, model: str) -> ModelPricing:
    """Fetch pricing from guardrails with fallback to constants."""
    model_lower = model.lower()
    result = await session.execute(select(Guardrail).where(Guardrail.key == "model_pricing"))
    guardrail = result.scalar_one_or_none()
    if guardrail and isinstance(guardrail.value, dict):
        pricing_map = guardrail.value.get("pricing", {})
        for key, pricing in pricing_map.items():
            if key in model_lower and isinstance(pricing, dict):
                input_price = pricing.get("input_per_million")
                output_price = pricing.get("output_per_million")
                if input_price is not None and output_price is not None:
                    return ModelPricing(
                        input_per_million=Decimal(str(input_price)),
                        output_per_million=Decimal(str(output_price)),
                    )

    for key, pricing in MODEL_PRICING.items():
        if key in model_lower:
            return pricing

    return ModelPricing(
        input_per_million=Decimal("5.00"),
        output_per_million=Decimal("15.00"),
    )


@dataclass
class TokenUsage:
    """Token usage from an API call."""

    input_tokens: int
    output_tokens: int
    model: str

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


async def log_cost(
    session: AsyncSession,
    task_id: str,
    agent: str,
    model: str,
    operation: str,
    usage: TokenUsage,
    analysis_id: str | None = None,
) -> CostLog:
    """Log a cost entry and update task totals."""
    pricing = await get_pricing(session, model)
    total_cost = pricing.calculate_cost(usage.input_tokens, usage.output_tokens)

    cost_log = CostLog(
        task_id=task_id,
        analysis_id=analysis_id,
        agent=agent,
        model=model,
        operation=operation,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
        cost_per_input_token=pricing.input_per_million / Decimal(1_000_000),
        cost_per_output_token=pricing.output_per_million / Decimal(1_000_000),
        total_cost=total_cost,
    )
    session.add(cost_log)

    await session.execute(
        update(Task)
        .where(Task.id == task_id)
        .values(
            total_tokens=Task.total_tokens + usage.total_tokens,
            total_cost=Task.total_cost + total_cost,
        )
    )
    return cost_log
