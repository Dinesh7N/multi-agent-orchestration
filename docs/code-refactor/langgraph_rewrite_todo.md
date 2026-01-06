# LangGraph Rewrite TODO (Full Migration)

**Date:** 2025-12-30  
**Reference:** `docs/code-refactor/consolidated_refactor_plan.md`

This TODO assumes a **full cutover** to LangGraph as the *only* orchestration engine. Legacy orchestration/Redis worker paths will be removed (or left only as inert historical code if you prefer, but not used).

## 0) Baseline and invariants
- [ ] LangGraph orchestrates; **OpenCode stays the execution substrate** (no direct vendor API keys required).
- [ ] Human approval is a **hard gate** before implementation.
- [ ] Postgres remains the audit trail (tasks/rounds/analyses/consensus/costs/logs).

## 1) LangGraph app (new single source of truth)
- [ ] Create a single LangGraph app module (e.g. `debate/langgraph_app.py`) that owns:
  - [ ] State schema (TypedDict)
  - [ ] Node functions (scoping/explore/debate/consensus/approval/implementation/review/verify)
  - [ ] Conditional edges for round looping and approval gating
- [ ] Ensure **round rows are created once** before parallel planner runs (avoid unique constraint races).
- [ ] Ensure planner runs do not share a DB session (each role run opens its own session).

## 2) CLI cutover
- [ ] `debate start` calls LangGraph app
- [ ] Make `--skip-explore` and `--max-rounds` effective
- [ ] Keep `debate run-role` and `debate verify` (useful utilities)
- [ ] Remove/replace commands that exist only for the legacy queue/workflow engine (`parallel`, Redis workers, etc.)

## 3) Remove legacy architecture
- [ ] Delete:
  - [ ] `debate/orchestrate.py`
  - [ ] `debate/workflow/`
  - [ ] `debate/workers/`
  - [ ] `debate/queue.py`
  - [ ] `debate/reconciliation.py`
  - [ ] `debate/redis_client.py`
  - [ ] `debate/invoke_parallel.py`
- [ ] Remove any imports/entrypoints referencing these.

## 4) pyproject cleanup
- [ ] Remove worker entrypoints from `[project.scripts]`
- [ ] Remove `redis` dependency if nothing else uses it
- [ ] (Optional) align Python requirement to a stable baseline (3.12/3.13) once the rewrite compiles cleanly

## 5) Follow-up “trust breakers” (next iteration)
- [ ] Stop writing prompts/outputs to `/tmp` by default (make opt-in)
- [ ] Add end-to-end timeout enforcement around agent runs
- [ ] Make structured output parsing schema-driven (Pydantic validation + error persistence)
- [ ] Update verification to tri-state `skipped/passed/failed` and remove `HEAD~1` assumption

