# Examples

This directory contains examples demonstrating various features and use cases of the Debate Workflow system.

## Available Examples

### 1. Basic Task Execution (`basic_task.py`)

Demonstrates how to programmatically create and execute a simple debate task.

```bash
python examples/basic_task.py
```

### 2. Custom Workflow (`custom_workflow.py`)

Shows how to create a custom workflow with specific phases and steps.

```bash
python examples/custom_workflow.py
```

### 3. Consensus Analysis (`consensus_analysis.py`)

Illustrates how to analyze consensus between agents and make decisions based on agreement levels.

```bash
python examples/consensus_analysis.py
```

### 4. Cost Tracking (`cost_tracking.py`)

Demonstrates how to track API costs across multiple agents and rounds.

```bash
python examples/cost_tracking.py
```

## Running Examples

### Prerequisites

1. Database and Redis must be running:
   ```bash
   docker start debate-db debate-redis
   ```

2. Environment configured:
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

3. Virtual environment activated:
   ```bash
   source .venv/bin/activate
   ```

### Execution

Run examples from the project root:

```bash
# Using uv
uv run python examples/basic_task.py

# Using standard python
python examples/basic_task.py
```

## Example Structure

Each example follows this pattern:

```python
"""
Description of what the example demonstrates.
"""

import asyncio
from debate import ...

async def main():
    # Setup
    # ...

    # Execution
    # ...

    # Results
    # ...

if __name__ == "__main__":
    asyncio.run(main())
```

## Common Patterns

### 1. Database Connection

```python
from debate.db import get_async_session

async with get_async_session() as session:
    # Your database operations
    pass
```

### 2. Task Creation

```python
from debate.models import Task

task = Task(
    slug="example-task",
    title="Example Task",
    request="Task description",
    status="created"
)
```

### 3. Agent Invocation

```python
from debate.run_agent import AgentType, run_agent

await run_agent(
    task_slug="example-task",
    agent_type=AgentType.CLAUDE,
    round_number=1
)
```

### 4. Consensus Calculation

```python
from debate.consensus import ConsensusCalculator

calc = ConsensusCalculator()
breakdown = await calc.calculate(
    gemini_findings=findings1,
    claude_findings=findings2,
    gemini_recommendations=recs1,
    claude_recommendations=recs2,
    round_number=1
)
```

## Modifying Examples

Feel free to modify these examples for your use cases:

1. **Change task descriptions** to test different scenarios
2. **Adjust thresholds** to see how consensus changes
3. **Add logging** to understand execution flow
4. **Modify workflows** to create custom debate patterns

## Troubleshooting

### Example Fails to Connect to Database

```bash
# Check database is running
docker ps | grep debate-db

# Verify connection settings
env | grep DEBATE_DB_
```

### Import Errors

```bash
# Ensure package is installed
uv pip install -e .

# Run from project root
cd /path/to/debate-workflow
python examples/basic_task.py
```

### Permission Errors

```bash
# Check database permissions
PGPASSWORD=agent psql -h localhost -p 15432 -U agent -d debate
```

## Contributing Examples

To contribute a new example:

1. Create a file in `examples/` directory
2. Add clear documentation at the top
3. Follow the async pattern
4. Include error handling
5. Add entry to this README
6. Test thoroughly

## Additional Resources

- [Architecture Documentation](../docs/architecture.md)
- [Setup Guide](../docs/setup.md)
- [Configuration Reference](../docs/configuration.md)
- [Contributing Guidelines](../CONTRIBUTING.md)
