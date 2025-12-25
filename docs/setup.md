# Setup Guide

Complete guide to setting up Debate Workflow for development and production use.

## Prerequisites

### Required Software

- **OpenCode CLI**:
  ```bash
  brew install opencode
  # Or check official docs: https://opencode.ai/docs/
  ```
- **Python**: 3.12 or higher
- **PostgreSQL**: 14 or higher
- **Redis**: 5 or higher
- **Docker**: Latest stable version (recommended for database)
- **uv**: Package manager ([installation guide](https://github.com/astral-sh/uv))

### Optional Software

- **npm**: For database management scripts
- **psql**: PostgreSQL client for database inspection

## Installation Methods

### Method 1: Automated Setup (Recommended)

The quickest way to get started. We recommend installing this inside your OpenCode configuration directory so the agent definitions are automatically picked up.

```bash
# 1. Ensure OpenCode config directory exists
mkdir -p ~/.config/opencode
cd ~/.config/opencode

# 2. Clone repository
git clone https://github.com/yourusername/multi-agent-orchestration.git
cd multi-agent-orchestration

# 3. Run setup script
chmod +x scripts/setup.sh
./scripts/setup.sh
```

This script will:
1. Check prerequisites
2. Start PostgreSQL in Docker
3. Create Python virtual environment
4. Install dependencies
5. Run database migrations
6. Verify installation

### Method 2: Manual Setup

For more control over the installation:

#### 1. Start Infrastructure (Database & Redis)

We use `docker-compose` to manage services.

```bash
# Start all services (PostgreSQL, Redis)
docker-compose up -d debate-db debate-redis

# Check status
docker-compose ps
```

This will start:
- **PostgreSQL** on port 15432
- **Redis** on port 16379

#### 2. Install Python Package

```bash
# Create virtual environment
uv venv

# Activate virtual environment
source .venv/bin/activate  # On macOS/Linux
# or
.venv\Scripts\activate     # On Windows

# Install package in development mode
uv pip install -e .

# Install development dependencies
uv pip install -e ".[dev]"
```

#### 4. Run Database Migrations

```bash
# Apply all migrations
uv run alembic upgrade head

# Verify tables were created
PGPASSWORD=agent psql -h localhost -p 15432 -U agent -d debate -c "\dt"
```

#### 5. Configure Environment

```bash
# Copy example configuration
cp .env.example .env

# Edit with your settings
nano .env  # or vim, code, etc.
```

### Connecting the Client (TUI)

Since the OpenCode server is running in a Docker container (port 4096), your local terminal needs to connect to it.

**Option 1: Using the convenience script (inside config dir)**
```bash
cd ~/.config/opencode
npm run connect
```

**Option 2: Using the raw command (from anywhere)**
```bash
opencode --hostname localhost --port 4096
```

**Option 3: Create a Shell Alias (Recommended)**
Add this to your shell profile (`.zshrc`, `.bashrc`):
```bash
alias opencode-remote="opencode --hostname localhost --port 4096"
```
Then you can just type `opencode-remote` to connect.

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# Database
DEBATE_DB_HOST=localhost
DEBATE_DB_PORT=15432
DEBATE_DB_NAME=debate
DEBATE_DB_USER=agent
DEBATE_DB_PASSWORD=agent

# Redis
DEBATE_REDIS_URL=redis://localhost:16379/0

# OpenCode API
DEBATE_OPENCODE_API_URL=http://localhost:4096

# Timeouts (seconds)
DEBATE_AGENT_TIMEOUT=300
DEBATE_ROUND_TIMEOUT=720
DEBATE_DEBATE_TIMEOUT=1800

# Workflow
DEBATE_CONSENSUS_THRESHOLD=80.0
DEBATE_MAX_ROUNDS=3
```

### Database Connection

Test your database connection:

```bash
# Using the CLI
uv run debate db-info

# Using psql directly
PGPASSWORD=agent psql -h localhost -p 15432 -U agent -d debate
```

### Redis Connection

Test Redis connectivity:

```bash
# Using redis-cli
redis-cli -p 16379 ping
# Should return: PONG

# Test from Python
python -c "import redis; r = redis.from_url('redis://localhost:16379'); print(r.ping())"
```

## Verification

### 1. Test CLI

```bash
uv run debate --help
uv run debate list-tasks
```

### 2. Run Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_consensus.py

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=debate --cov-report=html
open htmlcov/index.html
```

### 3. Check Database Schema

```bash
# View all tables
uv run debate db-info

# Or use psql
PGPASSWORD=agent psql -h localhost -p 15432 -U agent -d debate -c "\dt"
```

Expected tables:
- tasks
- rounds
- analyses
- findings
- recommendations
- consensus
- verifications
- alembic_version

### 4. Start a Test Task

```bash
uv run debate start "Test task: analyze authentication"
```

## Troubleshooting

### Database Connection Fails

**Problem**: `psycopg2.OperationalError: could not connect to server`

**Solutions**:
```bash
# Check if PostgreSQL is running
docker ps | grep debate-db

# Check logs
docker logs debate-db

# Restart container
docker restart debate-db

# Verify port is accessible
telnet localhost 15432
```

### Redis Connection Fails

**Problem**: `redis.exceptions.ConnectionError`

**Solutions**:
```bash
# Check if Redis is running
docker ps | grep debate-redis

# Test connection
redis-cli -p 16379 ping

# Restart Redis
docker restart debate-redis
```

### Migration Errors

**Problem**: `alembic.util.exc.CommandError`

**Solutions**:
```bash
# Check current migration version
uv run alembic current

# View migration history
uv run alembic history

# Rollback and retry
uv run alembic downgrade -1
uv run alembic upgrade head

# Reset database (WARNING: destroys data)
./scripts/setup.sh --reset
```

### Import Errors

**Problem**: `ModuleNotFoundError: No module named 'debate'`

**Solutions**:
```bash
# Reinstall package
uv pip install -e . --reinstall

# Verify installation
uv pip list | grep debate

# Check virtual environment is activated
which python
# Should point to .venv/bin/python
```

### Permission Errors

**Problem**: `Permission denied` when running scripts

**Solutions**:
```bash
# Make scripts executable
chmod +x scripts/setup.sh

# Or run with bash
bash scripts/setup.sh
```

## Development Setup

### IDE Configuration

**VS Code** (`settings.json`):
```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
  "python.linting.enabled": true,
  "python.linting.ruffEnabled": true,
  "python.formatting.provider": "ruff",
  "python.testing.pytestEnabled": true
}
```

**PyCharm**:
1. File → Settings → Project → Python Interpreter
2. Add Interpreter → Existing Environment
3. Select `.venv/bin/python`

### Pre-commit Hooks

```bash
# Install pre-commit
pip install pre-commit

# Set up hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

### Running Development Server

```bash
# Terminal 1: Start infrastructure
docker-compose up -d debate-db debate-redis

# Terminal 2: Start Claude worker
uv run claude-worker

# Terminal 4: Start Gemini worker
uv run gemini-worker

# Terminal 5: Start Codex worker
uv run codex-worker

# Terminal 6: Use CLI
uv run debate start "Your task here"
```

## Production Setup

### Security Hardening

1. **Change default passwords**:
   ```bash
   DEBATE_DB_PASSWORD=<strong-random-password>
   ```

2. **Use SSL for database**:
   ```bash
   DATABASE_URL=postgresql://user:pass@host:5432/debate?sslmode=require
   ```

3. **Restrict network access**:
   - Configure firewall rules
   - Use private networks
   - Enable authentication on Redis

4. **Secure API keys**:
   - Use secrets management (Vault, AWS Secrets Manager)
   - Never commit `.env` file
   - Rotate keys regularly

### Performance Tuning

1. **Database connection pooling**:
   ```python
   # In config.py
   pool_size = 20
   max_overflow = 10
   ```

2. **Redis persistence**:
   ```bash
   # In redis.conf
   appendonly yes
   appendfsync everysec
   ```

3. **Worker scaling**:
   ```bash
   # Run multiple workers per agent
   for i in {1..3}; do
     uv run claude-worker &
   done
   ```

### Monitoring

1. **Database monitoring**:
   ```sql
   -- Active connections
   SELECT count(*) FROM pg_stat_activity;

   -- Slow queries
   SELECT query, calls, total_time
   FROM pg_stat_statements
   ORDER BY total_time DESC
   LIMIT 10;
   ```

2. **Redis monitoring**:
   ```bash
   redis-cli INFO stats
   redis-cli MONITOR
   ```

3. **Application logs**:
   ```bash
   # View CLI logs
   uv run debate --verbose

   # Worker logs
   uv run claude-worker 2>&1 | tee worker.log
   ```

## Uninstallation

```bash
# Stop and remove containers
docker-compose down

# Remove volumes (destroys data)
docker volume prune

# Remove virtual environment
rm -rf .venv

# Remove installed package
pip uninstall debate-workflow
```

## Next Steps

- **Reference**: See [CLI Reference](cli_reference.md) for all available commands.
- **Architecture**: Read [Architecture](architecture.md) to understand the role-based system.
- **Configuration**: Check [Configuration](configuration.md) for role and model options.
- **Verification**: Run `uv run debate role-config list` to verify default agent mappings.
- **Contributing**: Read [Contributing](../CONTRIBUTING.md) to help improve the project.
