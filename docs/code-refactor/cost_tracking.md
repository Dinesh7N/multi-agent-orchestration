# Cost Tracking Feature

## Current State

The cost tracking **infrastructure already exists**:

### What's Already Implemented

1. **`costs.py`** - Core cost calculation logic:
   - `ModelPricing` dataclass with pricing per million tokens
   - `MODEL_PRICING` dict with prices for gemini, claude, gpt-4o, codex
   - `get_pricing()` - fetches pricing (from guardrails table or fallback)
   - `TokenUsage` dataclass
   - `log_cost()` - logs to `CostLog` table and updates `Task.total_tokens`/`Task.total_cost`

2. **`CostLog` table** (in `models.py`):
   ```python
   class CostLog(Base):
       id: str
       task_id: str
       analysis_id: str | None
       agent: str              # e.g., "gemini", "claude"
       model: str              # e.g., "gemini-2.5-pro"
       operation: str          # e.g., "analysis", "exploration"
       input_tokens: int
       output_tokens: int
       total_tokens: int
       cost_per_input_token: Decimal
       cost_per_output_token: Decimal
       total_cost: Decimal
       created_at: datetime
   ```

3. **`Task` table** has aggregates:
   ```python
   total_tokens: int
   total_cost: Decimal
   ```

4. **`run_agent.py`** already calls `log_cost()` after each agent run (lines 444-464, 861-881)

### What's Missing

**No way to display costs!** The data is logged but never shown to the user.

---

## Implementation Plan

### 1. Add `get_task_costs()` to `db.py`

```python
# Add to imports
from .models import (
    ...
    CostLog,
    ...
)

# Add new function
from dataclasses import dataclass
from sqlalchemy import func

@dataclass
class CostBreakdown:
    """Cost breakdown for a task."""
    total_cost: Decimal
    total_tokens: int
    input_tokens: int
    output_tokens: int
    by_agent: dict[str, dict]  # agent -> {cost, tokens, calls}
    by_model: dict[str, dict]  # model -> {cost, tokens, calls}
    by_operation: dict[str, dict]  # operation -> {cost, tokens, calls}


async def get_task_costs(session: AsyncSession, task: Task) -> CostBreakdown:
    """Get cost breakdown for a task."""
    # Get all cost logs for this task
    result = await session.execute(
        select(CostLog).where(CostLog.task_id == task.id)
    )
    logs = list(result.scalars().all())

    # Initialize breakdown
    by_agent: dict[str, dict] = {}
    by_model: dict[str, dict] = {}
    by_operation: dict[str, dict] = {}

    total_cost = Decimal("0")
    total_tokens = 0
    input_tokens = 0
    output_tokens = 0

    for log in logs:
        total_cost += log.total_cost
        total_tokens += log.total_tokens
        input_tokens += log.input_tokens
        output_tokens += log.output_tokens

        # By agent
        if log.agent not in by_agent:
            by_agent[log.agent] = {"cost": Decimal("0"), "tokens": 0, "calls": 0}
        by_agent[log.agent]["cost"] += log.total_cost
        by_agent[log.agent]["tokens"] += log.total_tokens
        by_agent[log.agent]["calls"] += 1

        # By model
        if log.model not in by_model:
            by_model[log.model] = {"cost": Decimal("0"), "tokens": 0, "calls": 0}
        by_model[log.model]["cost"] += log.total_cost
        by_model[log.model]["tokens"] += log.total_tokens
        by_model[log.model]["calls"] += 1

        # By operation
        if log.operation not in by_operation:
            by_operation[log.operation] = {"cost": Decimal("0"), "tokens": 0, "calls": 0}
        by_operation[log.operation]["cost"] += log.total_cost
        by_operation[log.operation]["tokens"] += log.total_tokens
        by_operation[log.operation]["calls"] += 1

    return CostBreakdown(
        total_cost=total_cost,
        total_tokens=total_tokens,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        by_agent=by_agent,
        by_model=by_model,
        by_operation=by_operation,
    )
```

### 2. Add CLI Command `debate costs <task_slug>`

Add to `cli.py`:

```python
@main.command()
@click.argument("task_slug")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def costs(task_slug: str, as_json: bool) -> None:
    """Show cost breakdown for a task.

    TASK_SLUG: The task identifier
    """
    import json as json_module

    async def show_costs() -> None:
        async with db.get_session() as session:
            task = await db.get_task_by_slug(session, task_slug)
            if not task:
                console.print(f"[red]Task not found: {task_slug}[/red]")
                return

            breakdown = await db.get_task_costs(session, task)

            if as_json:
                data = {
                    "task_slug": task_slug,
                    "total_cost_usd": float(breakdown.total_cost),
                    "total_tokens": breakdown.total_tokens,
                    "input_tokens": breakdown.input_tokens,
                    "output_tokens": breakdown.output_tokens,
                    "by_agent": {
                        k: {"cost_usd": float(v["cost"]), "tokens": v["tokens"], "calls": v["calls"]}
                        for k, v in breakdown.by_agent.items()
                    },
                    "by_model": {
                        k: {"cost_usd": float(v["cost"]), "tokens": v["tokens"], "calls": v["calls"]}
                        for k, v in breakdown.by_model.items()
                    },
                }
                console.print(json_module.dumps(data, indent=2))
                return

            # Summary panel
            console.print(
                Panel(
                    f"[bold]Total Cost:[/bold] ${breakdown.total_cost:.4f}\n"
                    f"[bold]Total Tokens:[/bold] {breakdown.total_tokens:,}\n"
                    f"  Input: {breakdown.input_tokens:,}\n"
                    f"  Output: {breakdown.output_tokens:,}",
                    title=f"Cost Summary: {task_slug}",
                    border_style="green",
                )
            )

            # By agent table
            if breakdown.by_agent:
                table = Table(title="Cost by Agent")
                table.add_column("Agent", style="cyan")
                table.add_column("Cost", style="green", justify="right")
                table.add_column("Tokens", justify="right")
                table.add_column("Calls", justify="right")

                for agent, data in sorted(breakdown.by_agent.items()):
                    table.add_row(
                        agent,
                        f"${data['cost']:.4f}",
                        f"{data['tokens']:,}",
                        str(data["calls"]),
                    )
                console.print(table)

            # By model table
            if breakdown.by_model:
                table = Table(title="Cost by Model")
                table.add_column("Model", style="cyan")
                table.add_column("Cost", style="green", justify="right")
                table.add_column("Tokens", justify="right")
                table.add_column("Calls", justify="right")

                for model, data in sorted(breakdown.by_model.items()):
                    table.add_row(
                        model,
                        f"${data['cost']:.4f}",
                        f"{data['tokens']:,}",
                        str(data["calls"]),
                    )
                console.print(table)

    asyncio.run(show_costs())
```

### 3. Print Cost Summary at End of Orchestration

Add to `langgraph_app.py` at the end of `orchestrate()`:

```python
async def _print_cost_summary(task_slug: str) -> None:
    """Print cost summary for the task."""
    async with db.get_session() as session:
        task = await db.get_task_by_slug(session, task_slug)
        if not task:
            return

        breakdown = await db.get_task_costs(session, task)

        if breakdown.total_cost > 0:
            console.print("\n[bold]Session Cost Summary[/bold]")
            console.print(f"  Total: [green]${breakdown.total_cost:.4f}[/green]")
            console.print(f"  Tokens: {breakdown.total_tokens:,} (in: {breakdown.input_tokens:,}, out: {breakdown.output_tokens:,})")

            if breakdown.by_agent:
                parts = [f"{agent}: ${data['cost']:.4f}" for agent, data in breakdown.by_agent.items()]
                console.print(f"  By agent: {', '.join(parts)}")


async def orchestrate(...) -> bool:
    ...
    final_state = await app.ainvoke(...)

    # Print cost summary
    task_slug = final_state.get("task_slug")
    if task_slug:
        await _print_cost_summary(task_slug)

    return bool(final_state.get("task_slug")) and not bool(final_state.get("cancelled"))
```

---

## Expected Output

### CLI: `debate costs my-feature`

```
╭──────────────── Cost Summary: my-feature ────────────────╮
│ Total Cost: $0.1234                                       │
│ Total Tokens: 45,678                                      │
│   Input: 40,000                                           │
│   Output: 5,678                                           │
╰───────────────────────────────────────────────────────────╯

        Cost by Agent
┏━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━┓
┃ Agent     ┃     Cost ┃  Tokens ┃ Calls ┃
┡━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━┩
│ claude    │  $0.0800 │  20,000 │     2 │
│ gemini    │  $0.0434 │  25,678 │     2 │
└───────────┴──────────┴─────────┴───────┘

        Cost by Model
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━┓
┃ Model            ┃     Cost ┃  Tokens ┃ Calls ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━┩
│ claude-sonnet-4  │  $0.0800 │  20,000 │     2 │
│ gemini-2.5-pro   │  $0.0434 │  25,678 │     2 │
└──────────────────┴──────────┴─────────┴───────┘
```

### End of Orchestration

```
Phase 5: Human Approval
...
Your decision [approve/revise/cancel] (approve): approve

Session Cost Summary
  Total: $0.1234
  Tokens: 45,678 (in: 40,000, out: 5,678)
  By agent: claude: $0.0800, gemini: $0.0434
```

---

## Files to Modify

| File | Changes |
|------|---------|
| `debate/db.py` | Add `CostLog` import, add `CostBreakdown` dataclass, add `get_task_costs()` function |
| `debate/cli.py` | Add `costs` command |
| `debate/langgraph_app.py` | Add `_print_cost_summary()`, call at end of `orchestrate()` |

---

## Model Pricing Reference

Current prices in `costs.py`:

| Model | Input (per 1M) | Output (per 1M) |
|-------|----------------|-----------------|
| gemini-2.5-pro | $1.25 | $5.00 |
| gemini-2.5-flash | $0.075 | $0.30 |
| claude-sonnet-4 | $3.00 | $15.00 |
| claude-opus-4 | $15.00 | $75.00 |
| gpt-4o | $2.50 | $10.00 |
| codex | $2.50 | $10.00 |

Prices can be overridden via the `guardrails` table (key: `model_pricing`).

---

## Notes

1. **Costs are already being logged** - The `run_agent.py` file already calls `log_cost()` after each successful agent run.

2. **Token extraction** - The `_extract_token_usage()` function in `run_agent.py` handles both OpenAI-style (`prompt_tokens`/`completion_tokens`) and Anthropic-style (`input_tokens`/`output_tokens`) responses.

3. **Pricing fallback** - If a model isn't in the pricing table, it defaults to $5.00/$15.00 per million tokens.

4. **Task totals** - `Task.total_tokens` and `Task.total_cost` are automatically updated by `log_cost()`.
