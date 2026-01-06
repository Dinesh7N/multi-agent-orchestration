# Improvement Suggestions (Codex Roast Edition)

This is a candid, code-reading-based assessment of the repo as-is (I did not run the full system end-to-end here). The goal is to optimize for: correctness, operability, clarity, and “does this actually work under concurrency?”.

## Clarified Use Case (from you)

You’re using this to build **new complex features** in your projects:
- You want a **debate between different models** to surface pros/cons and corner cases (not just “resolve disagreements”).
- You want **human-in-the-loop control** before implementation.
- You want to keep the **Opencode interface** and run this “inside Opencode” to leverage sessions/UI.
- Today you mostly run **one task at a time**, but you may run multiple tasks concurrently later (e.g., multiple tmux panes); not a hard requirement.
- You want **role-based control** of which agent/model implements/reviews (via env/DB), e.g.:
  - `ROLE_PLANNER_PRIMARY_MODEL=...`
  - `ROLE_PLANNER_SECONDARY_MODEL=...`
  - `ROLE_IMPLEMENTER_MODEL=...`
  - `ROLE_REVIEWER_MODEL=...`
- Redis/distributed execution is optional: you chose it assuming it’s “better”, but you’re open to dropping it if it’s overkill.

## Executive Summary (what’s good, what’s… not)

**What’s good:**
- The intent is strong: role-based multi-model “debate → consensus → implementation” with persistent state is a real product direction.
- The docs exist and explain architecture (rare for v0s).
- The primitives are sensible: tasks, rounds, analyses, consensus, costs, events.

**What’s not good (the roast):**
- You’ve built **three orchestration systems** (manual `orchestrate.py`, `workflow/`, Redis workers) that don’t cleanly align. The system’s “truth” is smeared across them.
- The Redis queue implementation is **quietly wrong** in a way that can drop retries and lose work.
- “Timeouts” exist as config, but the agent execution path **does not actually enforce them** where it matters.
- DB migrations/schema are **heavy and inconsistent**, and a migration likely **fails on vanilla Postgres**.
- Several “this cannot work” correctness bugs suggest copy/paste drift (unused flags, broken tool abstraction, dead code).

Net: this looks like an ambitious v0 that grew surface area faster than it paid down correctness + integration debt. Totally fine for exploration—but if the goal is a reliable tool others can use, the foundation needs tightening.

## Are you reinventing the wheel?

### Multi-agent orchestration
Yes and no.

**Yes:** Most orchestration mechanics (state machines, retries, timeouts, parallelism, persistence) are solved problems. Existing frameworks to steal from:
- **LangGraph (LangChain)**: graph/state-machine for agent workflows, retries, timeouts, parallel branches, persistence hooks.
- **Microsoft AutoGen / AgentChat**: multi-agent patterns and routing.
- **CrewAI**: role-based “teams” and task decomposition.
- **LlamaIndex workflows/agents**: workflows + memory abstractions.
- **Temporal / Prefect / Dagster**: if you want “real” workflow reliability and observability (maybe overkill for local dev, but correct).

**No:** You’re integrating with the **OpenCode local server** + approval-based coding workflow. That niche integration is defensible. But you should still reuse mature workflow semantics rather than re-implementing them partially.

**Given your clarified use case:** if you want *repeatable* “debate rounds + gating + human approval + resume”, you want a real workflow/state-machine layer. This repo is already trying to be that; adopting a purpose-built workflow engine (or making yours correct and singular) will pay off immediately.

### Code review / analysis tooling
If your goal is “assess a codebase and produce actionable suggestions”, then yes: static analysis tools already do a huge chunk:
- Python: `ruff`, `mypy`, `bandit`, `pip-audit`, `semgrep`
- General: `semgrep`, `gitleaks`, `trivy`, `osv-scanner`

Your differentiator should be: **LLM-assisted synthesis, prioritization, and workflow integration** (including “approved changes get implemented safely”), not reinventing linters.

## Stop-Ship Issues (fix before you trust results)

### 1) Redis worker retries are effectively broken (work can be dropped)
File: `debate/workers/base.py`

The idempotency mechanism:
- sets `idempotency:{task_id}:{round}:{agent}` with `NX`,
- but **never clears it**, and it’s set **before** processing.

That means:
- On failure, `_requeue()` re-adds a message, but the idempotency key still exists → next attempt gets treated as duplicate and ACKed without processing.
- If two distinct jobs share `(task_id, round, agent)` but represent different roles, one can be dropped.

**Fix direction:**
- Add a real `job_id` to payload and use that for idempotency, or persist job attempts in Postgres.
- Separate “inflight” keys (short TTL) from “done” markers.

### 2) Concurrent tasks use a shared SQLAlchemy `AsyncSession`
Files: `debate/invoke_parallel.py`, `debate/workflow/base.py`

In `invoke_parallel`, parallel branches call `resolve_role(...)`, `get_latest_agent_session_id(...)`, etc. using the same outer `session` concurrently. `AsyncSession` is not designed for concurrent use → expect correctness issues under load.

**Fix direction:**
- Precompute DB reads before `asyncio.gather`, or
- give each parallel branch its own session (recommended).

### 3) Agent execution “timeout” isn’t actually enforced
File: `debate/run_agent.py`

`run_agent_cli(..., timeout=...)` accepts a timeout, but doesn’t wrap the OpenCode call in `asyncio.wait_for(...)`. You mostly rely on the HTTP client’s timeout—which is not the same as “this whole run must finish”.

**Fix direction:**
- Enforce timeouts with `asyncio.wait_for(...)`, handle cancellation, and store timeout status in DB.

### 4) Alembic migration likely fails on vanilla Postgres (`gen_random_uuid()`)
File: `alembic/versions/1bef516cb306_add_uuid_defaults.py`

`ALTER TABLE ... SET DEFAULT gen_random_uuid()` will fail unless Postgres has that function available (typically requires `CREATE EXTENSION pgcrypto;`). No migration creates the extension.

**Fix direction:**
- Add `CREATE EXTENSION IF NOT EXISTS pgcrypto;` early, or remove DB-side defaults and generate UUIDs solely in app code.

### 5) “AgentTool” is broken (interface drift)
File: `debate/tools/agent_tool.py`

`run_agent()` returns `bool`, but the tool treats it like an `AgentResult` and reads `.raw_output`. This is a correctness bug and a symptom: the codebase has multiple partially maintained abstractions.

## High-Leverage Architecture Improvements

## Framework Fit (LangGraph vs CrewAI) with Opencode in mind

Given your constraints (Opencode UI, role-configured models, debate rounds that surface *new* corner cases, human approval gates), **LangGraph is the better fit than CrewAI**.

### Why LangGraph fits your “debate → consensus → implement” loop
- You can model your workflow as an explicit graph/state machine: parallel planner nodes → merge/consensus node → (optional) additional round(s) → interrupt for human approval → implementer node → reviewer/verify node.
- Human-in-the-loop is natural: LangGraph supports “pause/interrupt” semantics and deterministic resume.
- It’s easier to build **clear stopping criteria** that aren’t just “disagreement exists” (e.g., “risk checklist covered”, “no unanswered questions”, “coverage threshold met”, “human says stop”).
- You can keep Opencode as the execution substrate: each LangGraph node just becomes “call Opencode agent X with prompt template Y and model override Z”, then store results.

### Where CrewAI is weaker for your specific needs
- CrewAI shines for “role team executes a task plan”, but debate loops + multi-round gating + strict resumability typically turn into “prompt choreography” and ad-hoc state.
- You’ll likely end up rebuilding state-machine semantics on top of it anyway (which is where you already are).

### Recommended architecture (keeping Opencode)
- **Opencode remains the UI and agent runtime.**
- **LangGraph (or a single in-repo workflow engine) becomes the only orchestrator.**
- Postgres remains the audit trail (and optionally the checkpoint store), but the “truth” of the workflow should be one clear state machine.

If you don’t want an external dependency yet, you can still take the LangGraph *shape* (explicit states/transitions, interrupts, deterministic resume) and implement it once in this repo—just don’t maintain three competing orchestrators.

### Unify orchestration: pick one source of truth
You currently have:
- `debate/orchestrate.py` (interactive phase loop),
- `debate/workflow/*` (workflow abstractions),
- Redis workers + reconciliation (distributed execution).

This is architectural debt, not modularity.

**Recommendation:**
- Choose an execution model:
  1) **Single-process orchestrator** (simpler; fewer moving parts), or
  2) **Distributed workers** (Redis) with an orchestrator that only schedules + reacts to events.
- Retire the other path (or keep it as an explicit mode with parity + tests).

**Given your use case:** start with **single-process orchestration** first. It matches “one task at a time”, is easier to reason about, and will be more reliable sooner. Add distributed workers only when you actually need cross-process throughput or resilience beyond a single long-running orchestrator.

### Make the workflow an explicit state machine
Right now status fields exist but aren’t used consistently:
- `Task.current_round` exists but isn’t kept in sync.
- `Task.status` isn’t advanced through phases consistently.
- Round completion depends on ad-hoc rules in result processors and polling loops.

**Recommendation:**
- Define a small explicit state machine:
  - Task states: `created → exploring → analyzing → consensus → awaiting_approval → implementing → verifying → completed/failed/cancelled`
  - Round states: `scheduled → running → completed/failed`
  - Agent run states: `scheduled → running → completed/failed/timeout`
- Enforce valid transitions and store transition timestamps.

### Stop mixing “role” and “agent” as the primary identity
In some places analyses are keyed by `"gemini"/"claude"`, in others by `"planner_primary"/...`. Meanwhile consensus calculation assumes `"gemini"` and `"claude"`.

**Recommendation:**
- Add a first-class `AgentRun` table (or equivalent) that stores both role + agent/model explicitly and becomes the core query surface.

## Prompting + Structured Output: too fragile right now

### Regex JSON extraction will fail in real life
File: `debate/run_agent.py`

`extract_structured_output()` hunts code fences and hopes the JSON is valid. Models regularly produce “almost JSON”.

**Recommendation:**
- Define a strict Pydantic schema for structured outputs and validate it.
- Store: raw text + parsed JSON + parse errors.
- Consider “JSON-only mode” where non-JSON output is treated as failure.

### Context bloat and leakage risks
Files: `debate/db.py`, `debate/run_agent.py`

Prompt context isn’t systematically token-budgeted, and some sections can grow without bounds. Additionally, prompts/outputs are written to `/tmp/` by default (no redaction, noisy side effects).

**Recommendation:**
- Add a per-section budget and truncation strategy.
- Make debug dumps opt-in.
- Store large artifacts separately (or compress).

## Redis Queue + Worker Model: either get serious or simplify

Files: `debate/workers/base.py`, `debate/queue.py`, `debate/reconciliation.py`

If you want reliable distributed execution, you need:
- pending message handling (`XAUTOCLAIM` / recovery for dead consumers),
- correct retry semantics,
- atomic state updates (JSON dict read-modify-write races will lose updates under concurrency).

**Recommendation options:**
1) Use a mature queue (Celery/RQ/Dramatiq/arq).
2) Stay Redis Streams but implement proper job identity + claims + atomic DB updates.

**Given your use case:** Redis is likely overkill right now. The fastest path to a usable tool is:
- run planners in parallel in-process (`asyncio.gather` with separate DB sessions),
- store results and events in Postgres,
- only reintroduce Redis when you need to run multiple tasks concurrently *reliably* across processes/machines.

## Database modeling: ambitious schema, uneven payoff

### Schema is overbuilt relative to current code paths
Files: `debate/models.py`, `alembic/versions/001_initial_schema.py`

You ship tables/views/functions for artifacts, file snapshots, patterns, preferences, interventions, drift views, PL/pgSQL helpers, etc.—but the app primarily uses tasks/rounds/analyses/findings/questions/consensus/costs/logs.

**Recommendation:**
- Either park/remove unused schema until features exist, or implement the features that justify them.
- Avoid DB-level functions/triggers unless you test them and actually call them.

### Versioning and dependency choices are risky
Files: `pyproject.toml`, `.github/workflows/ci.yml`, `docker-compose.yml`, `README.md`

You currently push:
- Python `>=3.14` (bleeding edge) while docs claim 3.12+.
- Postgres image `postgres:18.1-alpine3.22` (not a normal stable baseline).

**Recommendation:**
- Target Python 3.12/3.13 unless you truly need 3.14 features.
- Use a stable Postgres baseline (16/17) unless there’s a hard requirement.

## CLI / UX: some commands lie
File: `debate/cli.py`

Examples:
- `debate start --skip-explore --max-rounds` accepts flags but doesn’t use them.
- `debate resume` expects `original_request` that isn’t present in the context builder.

These are trust killers. If the CLI lies, users stop believing anything else.

## Verification tooling: currently fails “by default”
File: `debate/verify.py`

Many repos have no build step; you treat “no build command detected” as failure. Git diff uses `HEAD~1`, which breaks in shallow/no-history contexts.

**Recommendation:**
- Use tri-state results: `skipped/passed/failed`.
- Let callers specify the git base ref or default to `git diff --name-only`.

## Security posture (fine for local; not for anything else)

Right now:
- DB/Redis credentials default to `agent/agent`.
- services are exposed on localhost ports without auth (ok for local, not ok beyond that).
- debug dumps can leak sensitive content to `/tmp/`.
- prompt template reading trusts DB/env values without enforcing path sandboxing at load time.

**Recommendation:**
- Add “production hardening” defaults and docs: required secrets, disable debug dumps, path sandboxing, optional Redis auth/TLS.

## What I’d do to make this a better tool (pragmatic roadmap)

### Phase 1: Correctness + reliability (1–2 weeks)
- Fix Redis retry/idempotency semantics.
- Fix AsyncSession concurrency in parallel execution.
- Enforce timeouts for agent runs.
- Make migrations deterministic and add required extensions.
- Fix broken code paths (`AgentTool`, CLI flags, resume).

### Phase 2: Simplify and tighten architecture (2–4 weeks)
- Pick one orchestration path and delete or quarantine the other.
- Introduce a single `AgentRun` record and drive status/UI from it.
- Implement explicit task/round state transitions.

### Phase 3: Differentiation (why this should exist)
- Strong schema discipline for agent outputs (Pydantic + validation).
- Integrate real linters/scanners and let agents synthesize/prioritize (don’t replace them).
- Better human-in-the-loop UX: streaming events, actionable questions, decision capture.
- Evaluation harness: measure cost/time/quality across strategies.

## The blunt conclusion

This repo is a promising idea wrapped in prototype-grade reliability. The main issue isn’t “bad code” so much as **too many half-finished systems and too few correctness guarantees**. Tighten workflow semantics, fix queue reliability, enforce timeouts, and delete unused surface area. Do that, and you’ll have a strong base instead of a fragile demo that sometimes works.
