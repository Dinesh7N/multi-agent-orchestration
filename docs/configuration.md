# Configuration Guide

Complete reference for all configuration options in Debate Workflow.

## Configuration Methods

Configuration is managed through:

1. **Environment variables**: Highest priority
2. **`.env` file**: Default configuration
3. **Code defaults**: Fallback values

All configuration uses the `DEBATE_` prefix for environment variables.

## Database Configuration

### Connection Settings

```bash
# Host where PostgreSQL is running
DEBATE_DB_HOST=localhost

# PostgreSQL port
DEBATE_DB_PORT=15432

# Database name
DEBATE_DB_NAME=debate

# Database user
DEBATE_DB_USER=agent

# Database password
DEBATE_DB_PASSWORD=agent
```

### Connection String

The system automatically constructs connection strings:

```python
# Synchronous (for migrations)
postgresql://agent:agent@localhost:15432/debate

# Asynchronous (for application)
postgresql+asyncpg://agent:agent@localhost:15432/debate
```

You can also override with a full connection string:

```bash
DATABASE_URL=postgresql://user:pass@host:5432/db?sslmode=require
```

### Connection Pooling

Configure in code (future enhancement):

```python
engine = create_async_engine(
    url,
    pool_size=20,          # Max connections in pool
    max_overflow=10,       # Additional connections when pool full
    pool_timeout=30,       # Seconds to wait for connection
    pool_recycle=3600,     # Recycle connections after 1 hour
)
```

## Redis Configuration

### Connection

```bash
# Full Redis URL with database number
DEBATE_REDIS_URL=redis://localhost:16379/0

# With authentication
DEBATE_REDIS_URL=redis://:password@localhost:16379/0

# With SSL
DEBATE_REDIS_URL=rediss://localhost:6380/0
```

### Queue Settings

```bash
# Enable Redis-based task queue
DEBATE_REDIS_QUEUE_ENABLED=false

# Maximum queue depth before blocking
DEBATE_REDIS_QUEUE_MAX_DEPTH=100
```

### Rate Limiting

```bash
# Enable rate limiting via Redis
DEBATE_REDIS_RATE_LIMIT_ENABLED=true

# Wait time when rate limit hit (seconds)
DEBATE_REDIS_RATE_LIMIT_WAIT_SECONDS=60
```

## Path Configuration

### Directory Paths

```bash
# Base configuration directory
DEBATE_CONFIG_DIR=/path/to/config
# Default: ~/.config/opencode

# Agent directory for temporary files
DEBATE_AGENT_DIR=/path/to/agents
# Default: ~/.config/opencode/agent
```

### OpenCode Integration

```bash
# OpenCode API server URL
DEBATE_OPENCODE_API_URL=http://localhost:4096

# Project directory for OpenCode
DEBATE_OPENCODE_DIRECTORY=/path/to/project
# Default: None (uses current directory)
```

## Timeout Configuration

### Agent Execution

```bash
# Maximum time for single agent execution (seconds)
DEBATE_AGENT_TIMEOUT=300  # 5 minutes
```

When an agent exceeds this timeout:
- Process is terminated
- Error is logged
- Round continues with available results

### Round Timeout

```bash
# Maximum time for one debate round (seconds)
DEBATE_ROUND_TIMEOUT=720  # 12 minutes
```

A round includes:
- All agent executions
- Result processing
- Consensus calculation

### Debate Timeout

```bash
# Maximum time for entire debate (seconds)
DEBATE_DEBATE_TIMEOUT=1800  # 30 minutes
```

Total time for all rounds, including:
- Exploration phase
- Planning phase
- All debate rounds
- Consensus resolution

## Workflow Thresholds

### Consensus Detection

```bash
# Percentage agreement needed for consensus (0-100)
DEBATE_CONSENSUS_THRESHOLD=80.0
```

Consensus score calculation includes:
- Category agreement (40% weight)
- File path agreement (30% weight)
- Severity agreement (10% weight)
- Explicit agreements (20% weight)

### Round Limits

```bash
# Maximum number of debate rounds
DEBATE_MAX_ROUNDS=3
```

After max rounds:
- If consensus reached: proceed
- If no consensus: escalate to human

### Retry Configuration

```bash
# Number of retries for failed operations
DEBATE_MAX_RETRIES=2
```

Retries apply to:
- Agent execution failures
- Database connection errors
- API rate limit errors

### Triage Mode

```bash
# Enable shadow mode for triage (logs but doesn't enforce)
DEBATE_TRIAGE_SHADOW_MODE=true
```

When `true`:
- Triage runs but doesn't block tasks
- Useful for testing triage rules

When `false`:
- Triage actively routes tasks
- Can skip phases based on complexity

## Agent Commands

### CLI Commands

```bash
# Command to invoke Gemini agent
DEBATE_GEMINI_CMD=gemini

# Command to invoke Claude agent
DEBATE_CLAUDE_CMD=claude

# Command to invoke Codex agent
DEBATE_CODEX_CMD=codex
```

These should be executable commands in your PATH or full paths:

```bash
# Using full paths
DEBATE_CLAUDE_CMD=/usr/local/bin/claude

# Using aliases
DEBATE_CLAUDE_CMD="docker run -it claude-agent"
```

## Role Configuration

The system uses a role-based architecture. You can override the default agent, model, and prompt for each role using environment variables.

### Role Environment Variables

The pattern is `ROLE_<ROLE_NAME>_<FIELD>`.

**Available Roles:** `PLANNER_PRIMARY`, `PLANNER_SECONDARY`, `IMPLEMENTER`, `REVIEWER`, `EXPLORER`

```bash
# Override the Primary Planner
ROLE_PLANNER_PRIMARY_AGENT=debate_codex
ROLE_PLANNER_PRIMARY_MODEL=openai/gpt-4
ROLE_PLANNER_PRIMARY_PROMPT=templates/planner_custom.md

# Override the Implementer
ROLE_IMPLEMENTER_AGENT=debate_gemini
ROLE_IMPLEMENTER_MODEL=google/gemini-pro-1.5
```

## Model Configuration

You can also override the default model for a specific agent key globally (if not overridden by a specific role).

### Model Environment Variables

The pattern is `<AGENT_KEY>_MODEL`.

```bash
# Use a specific model for all 'debate_gemini' instances
DEBATE_GEMINI_MODEL=google/gemini-1.5-pro-latest

# Use a specific model for 'debate_codex'
DEBATE_CODEX_MODEL=openai/gpt-4-turbo-preview
```

## External API Keys

If your agents require direct API access:

```bash
# Anthropic API key for Claude
ANTHROPIC_API_KEY=sk-ant-...

# Google API key for Gemini
GOOGLE_API_KEY=AIza...

# OpenAI API key for Codex
OPENAI_API_KEY=sk-proj-...
```

**Note**: The default implementation uses OpenCode API, which manages agent access internally.

## Logging Configuration

### Log Levels

```bash
# Application log level
DEBATE_LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL
```

### Log Formats

Configure in code:

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('debate.log'),
        logging.StreamHandler()
    ]
)
```

## Example Configurations

### Development

```bash
# .env.development
DEBATE_DB_HOST=localhost
DEBATE_DB_PORT=15432
DEBATE_REDIS_URL=redis://localhost:16379/0
DEBATE_AGENT_TIMEOUT=600
DEBATE_CONSENSUS_THRESHOLD=70.0
DEBATE_TRIAGE_SHADOW_MODE=true
DEBATE_LOG_LEVEL=DEBUG
```

### Production

```bash
# .env.production
DEBATE_DB_HOST=prod-db.example.com
DEBATE_DB_PORT=5432
DEBATE_DB_PASSWORD=${DB_PASSWORD_FROM_VAULT}
DEBATE_REDIS_URL=rediss://:${REDIS_PASSWORD}@prod-redis.example.com:6380/0
DEBATE_AGENT_TIMEOUT=300
DEBATE_CONSENSUS_THRESHOLD=85.0
DEBATE_MAX_ROUNDS=5
DEBATE_TRIAGE_SHADOW_MODE=false
DEBATE_LOG_LEVEL=INFO
```

### Testing

```bash
# .env.test
DEBATE_DB_HOST=localhost
DEBATE_DB_PORT=5433
DEBATE_DB_NAME=debate_test
DEBATE_REDIS_URL=redis://localhost:6379/1
DEBATE_AGENT_TIMEOUT=30
DEBATE_MAX_ROUNDS=2
DEBATE_TRIAGE_SHADOW_MODE=true
```

## Configuration Loading

### Load Priority

1. Environment variables (highest)
2. `.env` file
3. Code defaults (lowest)

### Multiple Environments

```bash
# Load specific environment file
export DEBATE_ENV=production
uv run debate --env production start "task"

# Override specific values
DEBATE_MAX_ROUNDS=5 uv run debate start "task"
```

### Validation

The system validates configuration on startup:

```python
from debate.config import settings

# Raises exception if invalid
settings.validate()

# Check specific values
assert settings.max_rounds > 0
assert 0 <= settings.consensus_threshold <= 100
```

## Advanced Configuration

### Custom Agent Implementations

```bash
# Use custom agent wrapper scripts
DEBATE_CLAUDE_CMD=/path/to/custom-claude-wrapper.sh
```

Wrapper script example:

```bash
#!/bin/bash
# custom-claude-wrapper.sh

# Add authentication
export ANTHROPIC_API_KEY=$(vault read -field=key secret/anthropic)

# Add telemetry
echo "Starting Claude agent at $(date)" >> /var/log/agents.log

# Execute actual agent
exec claude "$@"
```

### Database Migrations

```bash
# Alembic configuration
ALEMBIC_CONFIG=alembic.ini

# Migration directory
ALEMBIC_SCRIPT_LOCATION=alembic/versions
```

### Worker Configuration

For distributed workers:

```bash
# Worker identification
WORKER_ID=claude-worker-01
WORKER_GROUP=claude-workers

# Concurrency
WORKER_CONCURRENCY=5  # Process 5 tasks concurrently
WORKER_PREFETCH=2     # Prefetch 2 tasks from queue
```

## Security Best Practices

### 1. Credential Management

```bash
# Never commit secrets
echo ".env" >> .gitignore

# Use secret management
DEBATE_DB_PASSWORD=$(vault kv get -field=password secret/debate/db)
```

### 2. Network Security

```bash
# Use SSL for database
DATABASE_URL=postgresql://user:pass@host:5432/db?sslmode=require

# Restrict Redis access
redis-cli CONFIG SET requirepass "strong-password"
```

### 3. Access Control

```bash
# Limit database permissions
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO agent;
REVOKE DELETE ON ALL TABLES IN SCHEMA public FROM agent;
```

## Troubleshooting

### View Current Configuration

```bash
# Python interactive shell
python
>>> from debate.config import settings
>>> print(settings.model_dump())
```

### Test Configuration

```bash
# Verify database connection
uv run debate db-info

# Test agent commands
which claude
which gemini
which codex

# Check Redis connectivity
redis-cli -u $DEBATE_REDIS_URL ping
```

### Common Issues

**Issue**: Configuration not loading

**Solution**: Check environment variable names (must have `DEBATE_` prefix)

```bash
# Wrong
DB_HOST=localhost

# Correct
DEBATE_DB_HOST=localhost
```

**Issue**: Permission denied errors

**Solution**: Verify file permissions and database grants

```bash
chmod 600 .env
ls -la .env
```

## Configuration Reference

Complete list of all configuration options:

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `DEBATE_DB_HOST` | string | localhost | Database host |
| `DEBATE_DB_PORT` | int | 15432 | Database port |
| `DEBATE_DB_NAME` | string | debate | Database name |
| `DEBATE_DB_USER` | string | agent | Database user |
| `DEBATE_DB_PASSWORD` | string | agent | Database password |
| `DEBATE_REDIS_URL` | string | redis://localhost:16379/0 | Redis connection URL |
| `DEBATE_REDIS_RATE_LIMIT_ENABLED` | bool | true | Enable rate limiting |
| `DEBATE_REDIS_QUEUE_ENABLED` | bool | false | Enable Redis queue |
| `DEBATE_REDIS_QUEUE_MAX_DEPTH` | int | 100 | Max queue depth |
| `DEBATE_REDIS_RATE_LIMIT_WAIT_SECONDS` | int | 60 | Rate limit wait time |
| `DEBATE_AGENT_TIMEOUT` | int | 300 | Agent timeout (seconds) |
| `DEBATE_ROUND_TIMEOUT` | int | 720 | Round timeout (seconds) |
| `DEBATE_DEBATE_TIMEOUT` | int | 1800 | Debate timeout (seconds) |
| `DEBATE_CONSENSUS_THRESHOLD` | float | 80.0 | Consensus percentage |
| `DEBATE_MAX_ROUNDS` | int | 3 | Maximum debate rounds |
| `DEBATE_MAX_RETRIES` | int | 2 | Operation retry count |
| `DEBATE_TRIAGE_SHADOW_MODE` | bool | true | Triage shadow mode |
| `DEBATE_GEMINI_CMD` | string | gemini | Gemini command |
| `DEBATE_CLAUDE_CMD` | string | claude | Claude command |
| `DEBATE_CODEX_CMD` | string | codex | Codex command |
| `DEBATE_CONFIG_DIR` | path | ~/.config/opencode | Config directory |
| `DEBATE_AGENT_DIR` | path | ~/.config/opencode/agent | Agent directory |
| `DEBATE_OPENCODE_API_URL` | string | http://localhost:4096 | OpenCode API URL |
| `DEBATE_OPENCODE_DIRECTORY` | string | None | OpenCode project dir |
| `ROLE_<ROLE>_AGENT` | string | - | Agent override for role |
| `ROLE_<ROLE>_MODEL` | string | - | Model override for role |
| `<AGENT>_MODEL` | string | - | Model override for agent |
