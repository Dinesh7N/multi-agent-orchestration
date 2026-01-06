# Consolidated Refactor Recommendations & Roadmap

**Date:** 2025-12-30
**Last updated:** 2025-12-30 (added quick wins, deletion table, validation hypotheses, keep/remove summary)
**Sources:**
- `docs/code-refactor/improvement_suggestions_codex.md`
- `docs/code-refactor/improvement_suggestions_claude.md`
- `docs/code-refactor/improvement_suggestions_gemini.md`  

This document consolidates the three refactor/“roast” docs into a single, opinionated plan with rationale. It is written to answer: **what should we do next, why, and in what order**.

---

## TL;DR (recommended direction)

1. **Choose one execution model now:** default to **single-process orchestration** (async concurrency in-process) and **disable/quarantine Redis workers** until there is a proven multi-task / multi-host need.
2. **Fix “trust breakers” before adding features:** timeouts that don’t time out, CLI flags that don’t do anything, broken tool abstractions, flaky migrations, and concurrency-unsafe DB access.
3. **Make the workflow a single explicit state machine:** one source of truth for task/round/run state (whether via **LangGraph** or an in-repo equivalent).
4. **Keep the differentiators custom:** **OpenCode integration**, **debate-specific consensus**, **triage**, and **cost tracking**.
5. **Add an evaluation loop:** validate that debate rounds and consensus scoring correlate with human satisfaction before investing in large migrations.

---

## What all three reviews agree on

### 1) The system currently has “too many truths”
There are multiple orchestration layers (`debate/orchestrate.py`, `debate/workflow/*`, and Redis workers/reconciliation). Even if each is individually reasonable, **the combined surface area makes correctness and resumability fragile**. The highest-leverage refactor is to **pick one orchestrator** and make it the single source of truth.

### 2) Distributed execution is overkill (for the stated use case)
All three docs converge on: **Redis Streams + custom workers is not buying value right now**, and it introduces correctness requirements (idempotency, retry semantics, consumer recovery, atomic state updates) that are easy to get wrong.

The consistent advice: **start with a reliable single-process orchestrator**, and only add distributed workers when you can justify the complexity with real workloads.

### 3) Reliability gaps block trust
Several issues fall into the “if this happens once, you stop trusting the tool” category:
- retries that can drop work (queue/idempotency)
- “timeouts” that don’t actually enforce a deadline
- concurrency-unsafe DB session usage
- CLI flags / resume paths that don’t align with actual behavior
- brittle structured output parsing
- migrations that depend on missing Postgres extensions

### 4) The DB/schema is ambitious relative to what the code uses today
The schema contains many tables/views/functions that aren’t clearly exercised by the main workflow. This creates migration risk and makes development slower. All reviews recommend **either deleting/parking unused schema** or **implementing the features that justify them**, but not sitting in the middle.

---

## Key decision points (and why)

### Decision A: Single-process vs distributed workers

**Recommendation:** default to **single-process** today.

**Why:**
- Matches current use (“one task at a time”, occasional concurrency at most).
- Immediately reduces failure modes (retry semantics, dead consumer recovery, reconciliation).
- Makes correctness, resumability, and debugging simpler.

**Keep the door open:** if/when you need distributed execution, reintroduce it behind a clear interface (or use a mature queue like Celery/RQ/Dramatiq/arq), not a bespoke Redis Streams implementation.

### Decision B: Adopt LangGraph vs keep a custom workflow engine

**Recommendation:** a **hybrid approach** is the best fit:
- Use **LangGraph** (or another proven state-machine/workflow library) for orchestration semantics.
- Keep the **domain-specific logic** (debate phases, consensus scoring, OpenCode integration, triage/cost tracking) as custom nodes/services.

**Why:**
- The unique value here is not “we can run a while-loop”; it’s **debate + human gates + auditable history inside OpenCode**.
- Workflow correctness (cycles, interrupts, retries, checkpointing) is a solved problem; re-implementing it competes with feature work.

**If you don’t want the dependency yet:** still adopt the **LangGraph “shape”**: explicit states/transitions, deterministic resume, and a single orchestrator.

### Decision C: Keep consensus math vs LLM-as-a-judge

**Recommendation:** keep the existing consensus approach, but make it **pluggable** and add an alternate "judge" mode.

**Why:**
- Your weighted consensus is genuinely novel and provides inspectable signals (breakdowns).
- Pure string/set similarity is fragile; an optional judge model can provide semantic equivalence judgments.
- The right choice is empirical: **evaluate correlation with human satisfaction** and keep what works.

**Gemini's alternative:** Use a cheap "Meta-Reviewer" agent: *"Do these two plans describe the same approach? [Yes/No]"*. This removes the `sentence-transformers` dependency and handles semantic nuance better. Worth A/B testing.

---

## Consolidated “must-fix” issues (prioritized)

### Quick wins (< 1 hour, high confidence)

| Issue | File:Line | Fix |
|-------|-----------|-----|
| Dead code (duplicate return) | `opencode_client.py:210-215` | Delete lines 210-215 |
| Stub always returns 0.5 | `triage.py:_historical_analysis()` | Either implement or remove |
| Magic consensus weights | `consensus.py` | Extract `0.15, 0.25, 0.20` to named constants |

### Stop-ship (fix before expanding scope)
These are correctness/trust blockers called out explicitly (especially in the Codex doc):

1. **Concurrency-unsafe DB access** — `invoke_parallel.py`, `workflow/base.py` — `AsyncSession` shared across concurrent tasks.
2. **Agent timeouts not enforced** — `run_agent.py` — needs `asyncio.wait_for()`, not just HTTP timeout.
3. **Queue idempotency broken** — `workers/base.py` — idempotency key set *before* processing, never cleared on failure → retries dropped.
4. **Migration fails on vanilla Postgres** — `alembic/versions/1bef516cb306_...` — `gen_random_uuid()` requires `pgcrypto` extension.
5. **Broken tool abstraction** — `tools/agent_tool.py` — expects `AgentResult` but receives `bool`.
6. **CLI flags that lie** — `cli.py` — `--skip-explore`, `--max-rounds` accepted but not used.
7. **Verification fails by default** — `verify.py` — treats "no build command" as failure; `HEAD~1` breaks shallow clones.  

### High-leverage structural fixes
1. **Single source of truth for workflow state** (task/round/run state machine).  
2. **Unify identity model:** don’t mix “agent name” (claude/gemini) with “role” (planner_primary/secondary). Introduce a first-class “run” concept (e.g., `AgentRun`) that records role + model + status + outputs.  
3. **Structured output robustness:** validate against Pydantic schemas; store raw + parsed + parse errors.  
4. **Context budget + artifact handling:** enforce per-section limits and make debug dumps opt-in.  
5. **Pluggable agents/config:** move away from hardcoded agent enums/capability maps; introduce a registry/config-driven model list and role→model selection.

### Operational hardening (when you care about non-local usage)
- remove hardcoded default credentials
- add “production safe” defaults and docs
- tighten temp/debug artifact handling
- consider auth/TLS for any network-exposed services

---

## Proposed target architecture (conceptual)

### Core principles
- **One orchestrator** (state machine) owns transitions.
- **Pure functions where possible:** nodes read state → call an agent/tool → persist results → emit events → return updated state.
- **Resumability by design:** deterministic transitions, checkpointable state, idempotent updates.
- **OpenCode stays** as the interaction/runtime surface (intentional differentiator).

### Suggested state model (minimal, explicit)
- **Task states:** `created → exploring → scoping → debating → consensus → awaiting_approval → implementing → verifying → completed | failed | cancelled`
- **Round states:** `scheduled → running → completed | failed`
- **Agent run states:** `scheduled → running → completed | failed | timeout | cancelled`

Store transition timestamps and enforce valid transitions.

---

## Implementation roadmap (phased, with “why”)

### Phase 0 — Validate the product hypothesis (1–2 days)
**Why:** refactors are expensive; validate the debate pattern and consensus signals first.

Run **5–10 real debates** on representative feature requests. Track specific hypotheses:

| Hypothesis | How to Test | Success Criteria |
|------------|-------------|------------------|
| Models produce different perspectives | Run 10 feature debates | >50% have meaningful differences |
| Multiple rounds improve consensus | Compare round 1 vs round 2 outputs | Round 2 addresses round 1 gaps |
| Consensus score correlates with quality | Track scores vs human satisfaction | Higher scores = better plans |
| Human approval adds value | Compare auto-approved vs human-reviewed | Human catches real issues |

Decide what "good" looks like (success criteria) before migrating architecture.

### Phase 1 — Correctness & trust (1–2 weeks)
**Why:** without these, any architecture change will be unstable and hard to debug.

- Make orchestration concurrency-safe (no shared `AsyncSession` across concurrent tasks).
- Enforce end-to-end timeouts for agent runs (record timeout status).
- Align supported runtime baselines (Python/Postgres) across `pyproject.toml`, CI, docs, and `docker-compose.yml`.
- Configure DB connection pooling explicitly (and expose settings) rather than relying on defaults.
- Fix migrations for vanilla Postgres (extensions or app-side UUID defaults).
- Repair broken tool interfaces and remove dead code paths.
- Make CLI honest: flags must work or be removed; resume must build the context it expects.
- Make verification results tri-state (`skipped/passed/failed`) and remove brittle git assumptions.
- Security hygiene: disable `/tmp` dumps by default; document safe defaults.

**Exit criteria:** “single task run” succeeds deterministically; failures are visible and resumable; no silent drops.

### Phase 2 — Reduce to one orchestration system (1–2 weeks)
**Why:** this is the main complexity multiplier today.

Option 2A (recommended): **Introduce LangGraph** and wrap existing logic as nodes.  
Option 2B: Implement an in-repo state machine with the same semantics (states, transitions, interrupts).

Regardless of option:
- Pick one orchestrator path and delete/quarantine the others.
- Introduce a first-class `AgentRun` record (role + model + status + outputs).
- Drive UI/status from the state machine + AgentRuns, not ad-hoc queries.

**Exit criteria:** workflow is defined in one place; resuming uses checkpoints + DB state consistently.

#### Files to delete after Phase 2 (if adopting LangGraph)

| File/Module | ~Lines | Replaced By |
|-------------|--------|-------------|
| `orchestrate.py` | 500 | LangGraph graph definition |
| `invoke_parallel.py` | 300 | LangGraph parallel branches |
| `queue.py` | 106 | Not needed (no distributed workers) |
| `redis_client.py` | 50 | Not needed |
| `workers/base.py` | 123 | Not needed |
| `workers/claude_worker.py` | 50 | Inline in graph node |
| `workers/gemini_worker.py` | 50 | Inline in graph node |
| `workers/codex_worker.py` | 50 | Inline in graph node |
| `workflow/` directory | 200 | LangGraph replaces this |
| `reconciliation.py` | 100 | LangGraph handles state |
| **Total** | **~1,500** | |

### Phase 3 — Simplify persistence and make outputs robust (1–2 weeks)
**Why:** schema complexity and brittle parsing are recurring failure sources.

- Remove/park unused tables (or clearly label as future work).
- Add output schemas per agent role (Pydantic); store raw + parsed + validation errors.
- Add context budgets + artifact storage strategy (avoid unbounded prompt growth).
- Replace polling loops with eventing if still needed (Postgres LISTEN/NOTIFY or in-process signals).
- Add focused tests around the differentiators and failure modes (consensus scoring, state transitions, timeouts/cancellation, schema validation).

**Exit criteria:** DB migrations are predictable; large tasks don’t balloon prompt context; parsing failures are diagnosable.

### Phase 4 — Differentiation & evaluation (ongoing)
**Why:** this is where the project becomes defensible vs generic agent frameworks.

- Add an evaluation harness: compare cost/time/quality across strategies (1 vs 2 planners, different models, judge vs math consensus).
- Consider an optional “judge” consensus mode and keep the most predictive approach.
- Integrate “real” static analysis tools and have agents synthesize/prioritize results.
- Improve human-in-loop UX: actionable questions, decision capture, and clear “what changes if you approve?” summaries.

### Phase 5 — Optional scalability upgrades (only when justified)
- If multi-task/multi-host becomes real: introduce a mature queue or implement Redis Streams correctly (claims, retries, recovery, atomic updates).
- Consider RAG/pgvector only when repos routinely exceed context limits and it’s blocking outcomes.

---

## Open questions to resolve early

1. ~~**Do you want distributed workers at all?**~~ **ANSWERED:** Not a strict requirement. User thought Redis was "quick for message passing" but is open to dropping it. → Remove Redis complexity.
2. **What is the minimal audit trail you actually use?** This determines how much schema to keep.
3. **What outputs must be structured vs free-form?** This determines strictness of schemas and parsing.
4. **What is the "approval contract"?** (what exactly gets approved: plan, file list, diffs, or commands?)

---

## Summary: What to Keep vs Remove

### Keep (unique value)
| Component | Why |
|-----------|-----|
| `consensus.py` | Core differentiator — no framework has this |
| `opencode_client.py` | Intentional integration (minus dead code) |
| `triage.py` | Domain-specific complexity assessment |
| `costs.py` | Your specific pricing/tracking needs |
| PostgreSQL subset (tasks, rounds, analyses, consensus, cost_log) | Audit trail |

### Remove/Replace
| Component | Why |
|-----------|-----|
| `queue.py`, `redis_client.py`, `workers/` | Redis overkill for single-user CLI |
| `orchestrate.py` | Replace with LangGraph graph |
| `invoke_parallel.py` | LangGraph handles parallel branches |
| `workflow/` directory | LangGraph replaces custom state machine |
| Unused DB tables (memories, patterns, preferences, guardrails, file_snapshots) | Schema bloat |

---

## Suggested next action (practical)

**Option A (cautious):** Start with Phase 0 — run 5-10 real debates and capture what you wish the system did better. Use that to confirm priorities.

**Option B (pragmatic):** Start with quick wins (30 min), then Phase 1 stop-ship fixes. This builds confidence and unblocks further work.

**Option C (aggressive):** Fix quick wins → start LangGraph migration immediately. The debate pattern is the hypothesis; the framework is just scaffolding.

**Recommended:** Option B. The stop-ship issues (concurrency, timeouts) affect trust regardless of which orchestration approach you choose.
