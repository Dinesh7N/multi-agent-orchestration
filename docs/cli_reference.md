# CLI Reference

This document provides a comprehensive reference for the Debate Workflow command-line interface (`debate`).

## General Commands

### `start`
Start a new debate task.

```bash
uv run debate start [OPTIONS] REQUEST
```
**Arguments:**
- `REQUEST`: Description of the task you want to accomplish.

**Options:**
- `--skip-explore`: Skip the initial codebase exploration phase.
- `--max-rounds`: Maximum number of debate rounds (default: 3).

### `status`
Show detailed status of a specific task.

```bash
uv run debate status TASK_SLUG
```
**Arguments:**
- `TASK_SLUG`: The unique identifier for the task (e.g., `auth-refactor`).

### `list-tasks`
List recent tasks.

```bash
uv run debate list-tasks [OPTIONS]
```
**Options:**
- `--limit`: Number of tasks to show (default: 10).
- `--status-filter`: Filter tasks by status (e.g., `completed`, `in_progress`).

### `resume`
Resume a paused, failed, or interrupted task.

```bash
uv run debate resume TASK_SLUG
```

### `verify`
Run verification checks (tests, linting, build) for an implemented task.

```bash
uv run debate verify [OPTIONS] TASK_SLUG
```
**Options:**
- `--cwd`, `-C`: Specify the working directory for verification.

## Role & Agent Management

### `run-role`
Run a specific role for a task. This is the preferred way to invoke agents manually in the new architecture.

```bash
uv run debate run-role [OPTIONS] TASK_SLUG ROLE
```
**Arguments:**
- `TASK_SLUG`: The task identifier.
- `ROLE`: One of `planner_primary`, `planner_secondary`, `implementer`, `reviewer`, `explorer`.

**Options:**
- `--round`, `-r`: Round number (default: 1).
- `--phase`: Workflow phase (default: `analysis`).

### `parallel`
Run the configured planner roles (Primary & Secondary) in parallel.

```bash
uv run debate parallel [OPTIONS] TASK_SLUG
```

### `run` (Legacy)
Run a specific agent type directly.

```bash
uv run debate run [OPTIONS] TASK_SLUG AGENT
```
**Arguments:**
- `AGENT`: `gemini`, `claude`, or `codex`.

### `agents`
List currently running agent processes.

```bash
uv run debate agents
```

### `kill` / `kill-all`
Terminate running agent processes.

```bash
uv run debate kill IDENTIFIER
uv run debate kill-all
```

## Configuration Management

### `role-config`
Manage the mapping between Roles (e.g., Planner) and Agents/Models.

**Subcommands:**
- `list`: Show all role configurations and their sources (Default/DB/Env).
- `get ROLE`: Show configuration for a specific role.
- `set ROLE [OPTIONS]`: Update role configuration.
    - `--agent`: Agent key (e.g., `debate_gemini`).
    - `--model`: Specific model identifier.
    - `--prompt`: Path to prompt template.
    - `--job-type`: Queue intent (`analysis` or `implement`).
- `delete ROLE`: Remove database override for a role.
- `templates`: List available prompt templates.

**Example:**
```bash
# Change the primary planner to use Codex with GPT-4
uv run debate role-config set planner_primary --agent debate_codex --model openai/gpt-4
```

### `model-config`
Manage model configurations for specific agents.

**Subcommands:**
- `list`: List all model configurations.
- `get AGENT`: Get resolved model for an agent.
- `set AGENT MODEL`: Set a specific model for an agent.
- `delete AGENT`: Remove model override.

## Interactive & Workflow Commands

### `answer`
Answer a pending question from an agent.

```bash
uv run debate answer TASK_SLUG QUESTION_ID ANSWER_TEXT
```

### `questions`
List pending questions for a task.

```bash
uv run debate questions TASK_SLUG
```

### `approve`
Approve the consensus for a task, moving it to implementation.

```bash
uv run debate approve TASK_SLUG [--notes NOTES]
```

## Utility Commands

### `db-info`
Show current database connection details.

```bash
uv run debate db-info
```

### `schema-check`
Check if the database schema matches the current code requirements.

```bash
uv run debate schema-check
```
