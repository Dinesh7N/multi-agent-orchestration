# Multi-Agent Orchestration

[![CI](https://github.com/Dinesh7N/multi-agent-orchestration/actions/workflows/ci.yml/badge.svg)](https://github.com/Dinesh7N/multi-agent-orchestration/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> Multi-agent debate workflow for AI-assisted code analysis and implementation

A sophisticated orchestration system that coordinates multiple AI agents (Gemini, Claude, Codex) in a structured debate workflow to analyze, plan, and implement code changes with PostgreSQL-backed state management.

**Built for [opencode](https://github.com/anthropics/opencode)** - This project is designed to work within the opencode ecosystem, leveraging its AI agent infrastructure for coordinated multi-model debates.

## Features

- **Multi-Agent Coordination**: Orchestrate Gemini, Claude, and Codex agents in collaborative debates
- **Structured Workflow**: Phase-based execution (exploration, planning, implementation, verification)
- **State Management**: PostgreSQL-backed persistence for tasks, rounds, and agent responses
- **Consensus Building**: Intelligent consensus detection across agent responses
- **Cost Tracking**: Monitor API usage and costs across all agents
- **Redis Queue**: Distributed task queue for worker processes
- **Rich CLI**: Beautiful terminal interface with progress tracking
- **Extensible**: Plugin architecture for custom agents and workflow steps

## Quick Start

### Prerequisites

- **OpenCode CLI**: `brew install opencode` (or see [docs](https://opencode.ai/docs/))
- **Authentication**: Run `opencode auth login` to authenticate with providers (see [docs](https://opencode.ai/docs/cli/#login))
- Python 3.12 or higher
- PostgreSQL 14+
- Redis 5+
- Docker (recommended for database)
- [uv](https://github.com/astral-sh/uv) package manager

### Authentication Options

To use the AI agents, you must be authenticated with the respective providers.

1.  **Standard Authentication**:
    Run `opencode auth login` to authenticate using your API keys.
    [Documentation](https://opencode.ai/docs/cli/#login)

2.  **Advanced / Subscription-based**:
    If you prefer to use subscriptions (e.g., Antigravity, ChatGPT Pro) instead of direct API keys, or for advanced configuration, check out [oh-my-opencode](https://github.com/code-yeongyu/oh-my-opencode). This tool extends opencode to support subscription-based models not available out-of-the-box.

### Installation

### Installation

1.  **Clone into OpenCode config directory**
    ```bash
    mkdir -p ~/.config/opencode
    cd ~/.config/opencode
    git clone https://github.com/Dinesh7N/multi-agent-orchestration.git
    cd multi-agent-orchestration
    ```

2.  **Run setup script**
   ```bash
   chmod +x scripts/setup.sh
   ./scripts/setup.sh
   ```

   This will:
   - Start PostgreSQL and Redis via Docker Compose
   - Create virtual environment
   - Install dependencies
   - Run database migrations

3. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

4. **Verify installation**
   ```bash
   uv run debate --help
   ```

5. **Connect TUI Client**
   ```bash
   npm run connect
   # Or from anywhere:
   # opencode --hostname localhost --port 4096
   ```

## Usage

### CLI Usage

#### Start a Task

```bash
uv run debate start "Add authentication to the API"
```

### List Tasks

```bash
uv run debate list-tasks
```

### Check Task Status

```bash
uv run debate status auth-api
```

### View Database Info

```bash
uv run debate db-info
```

### Run Worker Processes

Start agent-specific workers to process tasks:

```bash
# Terminal 1: Claude worker
uv run claude-worker

# Terminal 2: Gemini worker
uv run gemini-worker

# Terminal 3: Codex worker
uv run codex-worker
```

### Programmatic Usage

```python
from debate import (
    Task,
    ConsensusCalculator,
    ConsensusBreakdown,
    Settings,
    AgentType,
    Role,
)

# Access configuration
settings = Settings()

# Calculate consensus from agent responses
calculator = ConsensusCalculator()
breakdown: ConsensusBreakdown = calculator.calculate(responses)

# Check agent types
print(AgentType.CLAUDE)  # claude
print(Role.EXPLORER)     # explorer
```

## Documentation

For more detailed information, check out the full documentation:

- [**Setup Guide**](docs/setup.md): Complete installation and troubleshooting.
- [**Architecture**](docs/architecture.md): Deep dive into the role-based system, orchestration, and Redis integration.
- [**Configuration**](docs/configuration.md): Reference for all environment variables, including Role and Model settings.
- [**CLI Reference**](docs/cli_reference.md): Comprehensive guide to all `debate` commands.

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                         CLI Layer                            │
│                     (debate, orchestrate)                    │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                    Orchestration Layer                       │
│        (Task Management, Workflow Coordination)              │
└───────────┬──────────────────────────────────┬──────────────┘
            │                                  │
┌───────────▼────────────┐        ┌───────────▼──────────────┐
│   PostgreSQL Database  │        │      Redis Queue         │
│   (State & History)    │        │   (Task Distribution)    │
└───────────┬────────────┘        └───────────┬──────────────┘
            │                                  │
┌───────────▼──────────────────────────────────▼──────────────┐
│                      Agent Workers                           │
│         Claude Worker | Gemini Worker | Codex Worker         │
└──────────────────────────────────────────────────────────────┘
```

### Workflow Phases

1. **Exploration**: Agents explore the codebase and gather context
2. **Planning**: Agents propose implementation strategies
3. **Debate**: Agents discuss and refine approaches through multiple rounds
4. **Consensus**: System detects agreement or escalates conflicts
5. **Implementation**: Winning approach is implemented
6. **Verification**: Changes are validated

## Agent Prompts

The `agent/` directory contains system prompts that define how each AI agent behaves:

| File | Purpose |
|------|---------|
| `orchestrator.md` | Main orchestrator that coordinates the workflow and interfaces with humans |
| `claude.md` | Claude agent - security-focused analysis with strong reasoning |
| `gemini.md` | Gemini agent - leverages 1M token context for large codebase analysis |
| `codex.md` | Codex agent - executes approved implementation plans |

### Role Templates

The `agent/templates/` directory contains role-specific prompts:

| Template | Role |
|----------|------|
| `explorer.md` | Scans and maps codebase structure before planning |
| `planner.md` | Analyzes code and proposes implementation strategies |
| `implementer.md` | Executes approved changes from the planning phase |
| `reviewer.md` | Reviews implemented changes for correctness and security |

### Customizing Prompts

You can customize agent behavior by:

1. **Editing prompts directly** in the `agent/` directory
2. **Using a custom location** via `DEBATE_AGENT_DIR` environment variable:
   ```bash
   export DEBATE_AGENT_DIR=/path/to/custom/prompts
   ```

## opencode Integration

This project is designed to work with [opencode](https://github.com/anthropics/opencode). The orchestrator prompt (`agent/orchestrator.md`) can be used as a system prompt in opencode to enable multi-agent debate workflows.

### Setup with opencode

1. **Install in opencode config directory**:
   ```bash
   cd ~/.config/opencode
   git clone https://github.com/Dinesh7N/multi-agent-orchestration.git
   ```

2. **Start infrastructure**:
   ```bash
   cd multi-agent-orchestration
   ./scripts/setup.sh
   ```

3. **Use the orchestrator prompt** in your opencode session to enable the debate workflow.

## Project Structure

```
multi-agent-orchestration/
├── .github/                   # GitHub configuration
│   └── workflows/
│       └── ci.yml            # CI/CD pipeline
├── agent/                     # Agent system prompts
│   ├── orchestrator.md       # Main orchestrator instructions
│   ├── claude.md             # Claude agent prompt (security-focused)
│   ├── gemini.md             # Gemini agent prompt (large context)
│   ├── codex.md              # Codex agent prompt (implementation)
│   └── templates/            # Role-specific templates
│       ├── explorer.md       # Codebase exploration role
│       ├── planner.md        # Planning and analysis role
│       ├── implementer.md    # Implementation role
│       └── reviewer.md       # Code review role
├── debate/                    # Main Python package
│   ├── __init__.py           # Public API exports
│   ├── py.typed              # PEP 561 type marker
│   ├── cli.py                # CLI commands
│   ├── orchestrate.py        # Main orchestration logic
│   ├── run_agent.py          # Agent execution
│   ├── db.py                 # Database operations
│   ├── models.py             # SQLAlchemy models
│   ├── config.py             # Configuration management
│   ├── consensus.py          # Consensus detection
│   ├── costs.py              # Cost tracking
│   ├── triage.py             # Task classification
│   ├── workers/              # Agent workers
│   │   ├── base.py
│   │   ├── claude_worker.py
│   │   ├── gemini_worker.py
│   │   └── codex_worker.py
│   ├── workflow/             # Workflow definitions
│   │   ├── base.py
│   │   ├── debate_steps.py
│   │   └── debate_workflow.py
│   └── tools/                # Agent tools
│       └── agent_tool.py
├── alembic/                  # Database migrations
│   └── versions/
├── tests/                    # Test suite
├── docs/                     # Documentation
├── examples/                 # Usage examples
├── scripts/                  # Utility scripts
│   └── setup.sh
├── pyproject.toml            # Project configuration
└── README.md                 # This file
```

## Configuration

Configuration is managed via environment variables and `.env` file:

```bash
# Database
DATABASE_URL=postgresql://agent:agent@localhost:15432/debate

# Redis
REDIS_URL=redis://localhost:6379

# API Keys
ANTHROPIC_API_KEY=your_key
GOOGLE_API_KEY=your_key
OPENAI_API_KEY=your_key

# Workflow Settings
MAX_DEBATE_ROUNDS=3
CONSENSUS_THRESHOLD=0.8
```

See `.env.example` for all available options.
Model identifiers should be selected from https://models.dev/.

## Development

### Setup Development Environment

```bash
# Install with dev dependencies
uv pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check .

# Format
ruff format .

# Type check
mypy debate/
```

### Database Management

```bash
# Create a new migration
uv run alembic revision -m "description"

# Apply migrations
uv run alembic upgrade head

# Rollback one migration
uv run alembic downgrade -1

# View migration history
uv run alembic history
```

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_consensus.py

# Run with coverage
pytest --cov=debate --cov-report=html
```

## Database Commands

Using `docker-compose`:

```bash
docker-compose up -d debate-db    # Start PostgreSQL
docker-compose down               # Stop all services
docker-compose logs -f debate-db  # View logs
```

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built with [SQLAlchemy](https://www.sqlalchemy.org/) for database ORM
- Uses [Click](https://click.palletsprojects.com/) for CLI interface
- UI powered by [Rich](https://rich.readthedocs.io/)
- Package management via [uv](https://github.com/astral-sh/uv)

## Support

- Documentation: [docs/](docs/)
- Issues: [GitHub Issues](https://github.com/Dinesh7N/debate-workflow/issues)
- Discussions: [GitHub Discussions](https://github.com/Dinesh7N/debate-workflow/discussions)

---

Made with care for better AI-assisted development workflows.
