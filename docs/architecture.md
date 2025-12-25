# Architecture

This document describes the architecture and design of the Debate Workflow system.

## Overview

Debate Workflow is a multi-agent orchestration system that coordinates AI agents in structured debates to analyze, plan, and implement code changes. The system uses PostgreSQL for state management and Redis for distributed task queues.

## High-Level Architecture

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

## Role-Based Architecture

The system uses a **Role-Based Architecture** to decouple the *purpose* of an agent from its *implementation*. This allows for flexible assignment of models and prompts to different workflow stages.

### Roles

- **Planner Primary**: The main strategic thinker. Analyzes the task and proposes a solution.
- **Planner Secondary**: Provides an alternative perspective or critique (e.g., security-focused).
- **Implementer**: Responsible for generating code based on the approved plan.
- **Reviewer**: Validates code changes against requirements and security standards.
- **Explorer**: Scans the codebase to gather context before planning begins.

### Role Resolution

Roles are resolved to an **Agent** (execution context) and a **Model** (LLM) at runtime:

```
Role (e.g., "planner_primary")
       ↓
Configuration (DB / Env / Default)
       ↓
Resolved Config:
  - Agent Key: "debate_gemini"
  - Model: "google/gemini-pro-1.5"
  - Prompt: "templates/planner.md"
```

This allows swapping the underlying model for a specific role without changing the application code.

## Core Components

### 1. CLI Layer (`debate/cli.py`)

The command-line interface provides user interaction points:

- **Task Management**: Start, list, and monitor tasks
- **Database Operations**: View schema, statistics, and state
- **Worker Commands**: Start agent-specific workers

### 2. Orchestration Layer

#### Task Orchestrator (`debate/orchestrate.py`)

Coordinates the entire debate workflow:

- Creates and manages task lifecycle
- Implements triage to classify task complexity
- Schedules agent invocations across rounds
- Monitors consensus and resolves debates

#### Workflow Engine (`debate/workflow/`)

Defines the structured debate workflow:

- **Phases**: Exploration, Planning, Implementation, Verification
- **Steps**: Discrete actions within each phase
- **Transitions**: Rules for moving between phases

### 3. Agent Management

#### Agent Runner (`debate/run_agent.py`)

Executes individual agent invocations:

- Manages agent subprocess lifecycle
- Captures and parses agent outputs
- Handles timeouts and errors
- Stores results in database

#### Workers (`debate/workers/`)

Redis-based distributed workers for scalability:

- **Base Worker**: Common worker functionality
- **Agent-Specific Workers**: Claude, Gemini, Codex implementations
- **Queue Management**: Pull tasks from Redis queues
- **Rate Limiting**: Prevent API rate limit violations

### 4. State Management

#### Database Layer (`debate/db.py`, `debate/models.py`)

PostgreSQL-backed state persistence:

- **Tasks**: Top-level work items
- **Rounds**: Debate iterations
- **Analyses**: Agent responses per round
- **Findings**: Structured outputs from agents
- **Consensus**: Agreement detection results

Schema managed via Alembic migrations.

#### Redis Layer (`debate/redis_client.py`, `debate/queue.py`)

In-memory state for real-time operations and job queuing:

- **Job Streams**:
  - `stream:jobs:analysis`: Queue for Planner, Reviewer, and Explorer roles.
  - `stream:jobs:implement`: Queue for Implementer role.
  - `stream:jobs:priority`: High-priority channel for urgent tasks.
- **Rate Limiting**: Track API usage across workers using token buckets.
- **Locking**: Prevent concurrent modifications to the same task.

### 5. Analysis & Decision Making

#### Consensus Calculator (`debate/consensus.py`)

Detects agreement between agents:

- Compares findings across categories, files, severity
- Tracks explicit agreements/disputes in subsequent rounds
- Calculates weighted consensus scores
- Determines when sufficient agreement is reached

#### Task Triager (`debate/triage.py`)

Classifies task complexity and routes to the appropriate workflow track.

```
┌─────────────────────────────────────────────────────────────┐
│                    TRIAGE DECISION                           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  After Phase 1 (Scoping), Orchestrator assesses:            │
│                                                              │
│  TRIVIAL (skip debate):                                     │
│    • Single file change                                     │
│    • Typo/documentation fix                                 │
│    • Simple bug with obvious fix                            │
│    • User explicitly says "quick fix"                       │
│    → Fast-Track Planning:                                   │
│      1. Orchestrator creates consensus entry (fast_track)   │
│      2. Populates impl_tasks with single change             │
│      3. Gets human approval (quick yes/no)                  │
│      4. Go to Phase 6 (Implementation)                      │
│                                                              │
│  STANDARD (normal debate):                                  │
│    • Multi-file changes                                     │
│    • New feature                                            │
│    • Refactoring                                            │
│    → Full workflow (Phases 2-7)                             │
│                                                              │
│  COMPLEX (extended debate):                                 │
│    • Architectural changes                                  │
│    • Security-sensitive                                     │
│    • >10 files affected                                     │
│    → Full workflow + extra review round                     │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

- Analyzes task description and scope
- Determines required agents and phases
- Estimates resource requirements
- Routes to appropriate workflow

#### Cost Tracker (`debate/costs.py`)

Monitors API usage and costs:

- Tracks tokens and API calls per agent
- Calculates costs based on model pricing
- Provides usage reports and alerts

## Data Flow

### 1. Task Creation

```
User → CLI → Orchestrator → Database
                          ↓
                    Triage Analysis
                          ↓
                 Create Task Record
```

### 2. Debate Round

```
Orchestrator → Schedule Agents → Redis Queue
                                     ↓
Workers Poll Queue → Execute Agent → Store Results
                                          ↓
                              Check Consensus
                                    ↓
                        Continue or Resolve
```

### 3. Agent Execution

```
Worker → Spawn Agent Process → OpenCode API
              ↓                      ↓
        Monitor Output         Execute Tools
              ↓                      ↓
        Parse Results ← Complete Execution
              ↓
    Store in Database
```

## Database Schema

### Schema Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           debate schema                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  TASK-SCOPED (partitioned by task_id)                                   │
│                                                                          │
│  Core Tables:                                                            │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐        │
│  │   tasks     │ │conversations│ │ explorations│ │   rounds    │        │
│  │ (registry)  │ │(human-orch) │ │ (optional)  │ │             │        │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘        │
│                                                                          │
│  Analysis Tables:                                                        │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐        │
│  │  analyses   │ │  questions  │ │  decisions  │ │  findings   │        │
│  │(per agent)  │ │  (qa_log)   │ │ (extracted) │ │ (detailed)  │        │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘        │
│                                                                          │
│  Consensus Tables:                                                       │
│  ┌─────────────┐ ┌─────────────┐                                        │
│  │  consensus  │ │disagreements│                                        │
│  │  (agreed)   │ │(unresolved) │                                        │
│  └─────────────┘ └─────────────┘                                        │
│                                                                          │
│  Implementation Tables:                                                  │
│  ┌─────────────┐ ┌─────────────┐                                        │
│  │   impl_     │ │verifications│                                        │
│  │   tasks     │ │             │                                        │
│  └─────────────┘ └─────────────┘                                        │
│                                                                          │
│  Observability:                                                          │
│  ┌─────────────┐                                                        │
│  │execution_log│                                                        │
│  │  (audit)    │                                                        │
│  └─────────────┘                                                        │
│                                                                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  GLOBAL (cross-task persistent memory)                                  │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                        │
│  │  memories   │ │  patterns   │ │ preferences │                        │
│  │ (long-term) │ │ (learned)   │ │   (user)    │                        │
│  └─────────────┘ └─────────────┘ └─────────────┘                        │
│                                                                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  CONFIG                                                                  │
│  ┌─────────────┐                                                        │
│  │ guardrails  │                                                        │
│  │  (config)   │                                                        │
│  └─────────────┘                                                        │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Core Tables

- **tasks**: Master task records
- **rounds**: Debate iteration records
- **analyses**: Agent execution results
- **findings**: Structured outputs from agents
- **recommendations**: Agent suggestions
- **consensus**: Agreement detection results
- **verifications**: Validation results

### Relationships

```
Task (1) ──→ (N) Round
Round (1) ──→ (N) Analysis
Analysis (1) ──→ (N) Finding
Round (1) ──→ (1) Consensus
```

## Workflow Phases

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           DEBATE WORKFLOW                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ PHASE 0: EXPLORATION (Optional)                                  │    │
│  │                                                                  │    │
│  │   Orchestrator asks: "Explore codebase first?"                  │    │
│  │           │                                                      │    │
│  │           ▼                                                      │    │
│  │   If yes: Explorer Role ────► DB (explorations table)           │    │
│  │           Factual findings shared with all agents               │    │
│  │                                                                  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                              │                                           │
│                              ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ PHASE 1: SCOPING                                                 │    │
│  │                                                                  │    │
│  │   Human ◄────► Orchestrator ────► DB (conversations table)      │    │
│  │                                                                  │    │
│  │   • Gather requirements                                          │    │
│  │   • Ask clarifying questions                                     │    │
│  │   • Store ENTIRE conversation                                    │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                              │                                           │
│                              ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ PHASE 2: PARALLEL ANALYSIS & PLANNING                            │    │
│  │                                                                  │    │
│  │   Orchestrator invokes:                                          │    │
│  │                                                                  │    │
│  │   ┌────────┐          ┌────────┐                                │    │
│  │   │Planner │    &     │Planner │    (parallel)                  │    │
│  │   │Primary │          │Second. │                                │    │
│  │   └───┬────┘          └───┬────┘                                │    │
│  │       │                   │                                      │    │
│  │       ▼                   ▼                                      │    │
│  │   DB: findings, questions, recommendations                       │    │
│  │                                                                  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                              │                                           │
│                              ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ PHASE 3: BLOCKER RESOLUTION                                      │    │
│  │                                                                  │    │
│  │   Orchestrator queries DB for questions                          │    │
│  │           │                                                      │    │
│  │           ▼                                                      │    │
│  │   Human answers ────► DB updated                                 │    │
│  │                                                                  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                              │                                           │
│                              ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ PHASE 4: ITERATE UNTIL CONSENSUS                                 │    │
│  │                                                                  │    │
│  │   LOOP (max 3 rounds):                                          │    │
│  │     • Re-invoke agents with updated context                      │    │
│  │     • Check agreement rate (Consensus Calculator)                │    │
│  │     • Break if consensus ≥ Threshold                             │    │
│  │                                                                  │    │
│  │   Output: Consensus saved to DB (agreed items + plan)           │    │
│  │                                                                  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                              │                                           │
│                              ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ PHASE 5: HUMAN APPROVAL                                          │    │
│  │                                                                  │    │
│  │   Orchestrator presents plan ────► Human approves/rejects       │    │
│  │                                                                  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                              │                                           │
│                              ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ PHASE 6: IMPLEMENTATION                                          │    │
│  │                                                                  │    │
│  │   Implementer Role ────► Picks tasks from DB                    │    │
│  │                                    Updates task status           │    │
│  │                                                                  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                              │                                           │
│                              ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ PHASE 7: VERIFICATION & REVIEW                                   │    │
│  │                                                                  │    │
│  │   1. Automated Verification (Tests/Lint/Build)                   │    │
│  │                                                                  │    │
│  │   2. Semantic AI Review                                          │    │
│  │      Reviewer Role reviews diff against plan                     │    │
│  │                                                                  │    │
│  │   If issues: surface to human, optionally re-invoke              │    │
│  │                                                                  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Extensibility

### Adding New Agents

1. Create worker class in `debate/workers/`
2. Implement agent CLI command
3. Add agent type to `AgentType` enum
4. Register in configuration

### Adding Workflow Steps

1. Define step in `debate/workflow/debate_steps.py`
2. Add to workflow in `debate_workflow.py`
3. Update phase transitions if needed

### Custom Tools

1. Implement tool in `debate/tools/`
2. Register with agent executor
3. Document tool usage

## Configuration

All configuration via environment variables with `DEBATE_` prefix:

- **Database**: Connection settings
- **Redis**: Queue and rate limiting
- **Timeouts**: Agent, round, debate limits
- **Thresholds**: Consensus detection, retries
- **Agent Commands**: CLI commands for each agent

See `.env.example` for all options.

## System Guardrails

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           GUARDRAILS                                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  TIMEOUTS                                                                │
│  ┌────────────────────────────────────────────────────────────────┐     │
│  │ • Agent invocation: Configurable (default 5 min)               │     │
│  │ • Total round time: Configurable (default 12 min)              │     │
│  │ • Entire debate: Configurable (default 30 min)                 │     │
│  └────────────────────────────────────────────────────────────────┘     │
│                                                                          │
│  RETRY POLICY                                                            │
│  ┌────────────────────────────────────────────────────────────────┐     │
│  │ • Agent timeout/failure: Retry 2x with exponential backoff     │     │
│  │ • API rate limit: Wait 60s, retry 3x (Redis token bucket)      │     │
│  │ • After max retries: Mark agent as failed, continue with other │     │
│  │ • Both agents fail: Abort debate, notify human                 │     │
│  └────────────────────────────────────────────────────────────────┘     │
│                                                                          │
│  CIRCUIT BREAKERS                                                        │
│  ┌────────────────────────────────────────────────────────────────┐     │
│  │ • 3 consecutive failures: Pause workflow, ask human            │     │
│  │ • Consensus not improving after max rounds: Force synthesis    │     │
│  │ • Implementation fails same task 2x: Mark task as needs_human  │     │
│  └────────────────────────────────────────────────────────────────┘     │
│                                                                          │
│  SAFETY CHECKS                                                           │
│  ┌────────────────────────────────────────────────────────────────┐     │
│  │ • No implementation without human approval                      │     │
│  │ • Agents cannot delete files unless explicitly in plan         │     │
│  │ • Changes to sensitive paths require extra confirmation        │     │
│  └────────────────────────────────────────────────────────────────┘     │
│                                                                          │
│  HUMAN ESCALATION TRIGGERS                                               │
│  ┌────────────────────────────────────────────────────────────────┐     │
│  │ • Agents fundamentally disagree (no convergence)               │     │
│  │ • Security-critical changes detected                            │     │
│  │ • Changes affect >10 files                                      │     │
│  │ • Any step times out after retries                              │     │
│  │ • Verification fails                                            │     │
│  └────────────────────────────────────────────────────────────────┘     │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Security Considerations

- API keys stored in environment variables
- Database credentials not in code
- Agent subprocess isolation
- Rate limiting to prevent abuse
- Timeouts to prevent runaway execution

## Performance

### Optimizations

- Async database operations
- Parallel agent execution
- Redis-based queue for distribution
- Connection pooling
- Caching of frequently accessed data

### Bottlenecks

- Agent API rate limits
- Database write contention
- Agent execution time
- Consensus calculation for large result sets

## Monitoring

Track key metrics:

- Task completion time
- Agent execution time
- Consensus achievement rate
- API costs per task
- Error rates per agent

## Future Enhancements

- Web UI for task monitoring
- Real-time progress updates via WebSocket
- Plugin system for custom agents
- Automated testing of implementations
- Cost optimization recommendations
- Multi-repository support
