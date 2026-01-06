# Multi-Agent Debate System: "Roast" & Refactoring Recommendations

> **Date:** December 30, 2025
> **Author:** Gemini (CLI Agent)
> **Target:** `multi-agent-orchestration` codebase

## Executive Summary

The codebase is a classic example of **"Not Invented Here" syndrome**. It builds a custom orchestration engine, a custom job queue, a custom consensus algorithm, and a custom state machine—all things that mature libraries do better. While the *intent* (role-based, auditable multi-agent collaboration) is excellent, the *implementation* is over-engineered for a local CLI tool yet under-engineered for a distributed system.

## 1. The "Reinventing the Wheel" Roast

### 1.1. Custom Orchestration vs. Workflow Engines
**The Code:** `debate/workflow/` and `debate/orchestrate.py` implement a custom state machine with steps, loops, and breaks.
**The Roast:** You've built a fragile version of **LangGraph** or **Temporal**. The `orchestrate.py` file is a 500-line monolith mixing UI logic (`rich.console`), database transactions, and workflow control flow. If the process crashes in the middle of a "round", recovery is messy (relying on DB state but manual reconciliation).
**Recommendation:**
*   **Adoption:** Switch to **LangGraph** (Python). It handles state persistence, cycles (loops), and human-in-the-loop natively.
*   **Benefit:** Deletes ~60% of your boilerplate code. You get graph visualization and state recovery for free.

### 1.2. Redis Streams for Local Workers?
**The Code:** `debate/queue.py` and `debate/workers/` manually implement a job queue using Redis Streams.
**The Roast:** Using Redis Streams (`XADD`, `XLEN`) directly is cool if you're building a high-throughput microservice at Netflix. For a CLI tool coordinating 3 agents? It's overkill. Plus, `wait_for_round_status` uses a **polling loop** (`while ... sleep(2)`) to check the database for completion. You built a real-time stream architecture only to poll the database at the end?
**Recommendation:**
*   **Simplification:** If this is single-user, just use Python's `asyncio.TaskGroup` or `Celery` if you absolutely need process isolation.
*   **Fix:** If keeping Redis, use **Pub/Sub** or `XREAD block=...` for result notification instead of polling Postgres.

### 1.3. Heuristic Consensus
**The Code:** `debate/consensus.py` calculates "agreement" using Jaccard indices of string sets and an optional heavy `sentence-transformers` dependency.
**The Roast:** You are running LLMs (Gemini, Claude, Codex) but using `set.intersection()` to see if they agree? That's like buying a Ferrari to deliver pizza. String matching is fragile. A typo in a file path or a slightly different phrasing of a recommendation yields 0% consensus.
**Recommendation:**
*   **LLM-as-a-Judge:** Use a "Meta-Reviewer" agent (cheap model) to compare the outputs. "Do these two plans describe the same approach? [Yes/No]".
*   **Benefit:** Removes `sentence-transformers` dependency (huge) and handles semantic nuance significantly better.

## 2. Architecture & Performance

### 2.1. Database Modeling
**The Code:** `debate/models.py`
**Critique:**
*   **JSONB Abuse:** `Analysis.recommendations` is a JSONB list, but `ImplTask.files_to_modify` is a Postgres ARRAY. Inconsistent.
*   **Bloat:** `FileSnapshot` table seems to store `content_hash` but could easily bloat if you decide to store diffs or full content.
*   **Embedding Storage:** `Analysis.recommendation_embeddings` stores raw float arrays. Without `pgvector`, this is useless for search.
*   **Status Fields:** Statuses are raw strings ("scoping", "in_progress"). Use Python `Enum` mapped to SQL `Enum` or strictly validated strings to prevent typo-induced bugs.

### 2.2. Context Window & File Scanning
**The Code:** `Exploration` phase and `Explorer` role.
**Critique:** The system reads file contents and stuffs them into the context. For large repos, this will hit token limits immediately or cost a fortune.
**Recommendation:**
*   Use a **Vector Store** (ChromaDB, PGVector) for the codebase.
*   Implement RAG (Retrieval Augmented Generation) instead of full-context stuffing.

## 3. Code Quality & Maintainability

### 3.1. The "God Object" Orchestrator
**The Code:** `debate/orchestrate.py`
**Critique:** This file does everything:
*   Prints to console (UI)
*   Manages DB sessions (Persistence)
*   Decides logic (Business Rules)
*   Manages Redis (Infrastructure)
*   **Fix:** Split into `DebateService` (logic), `DebateRepository` (DB), and `DebateUI` (Rich).

### 3.2. Hardcoded Configuration
**The Code:** `debate/role_config.py`
**Critique:**
*   `validate_role_agent_compatibility` has hardcoded maps: `{"debate_gemini": {"analysis", ...}}`.
*   Adding a new model requires editing python code.
*   **Fix:** Move capabilities to the `db` or `config.yaml`. Make the system data-driven.

## 4. Specific Refactoring Plan

### Phase 1: Rip and Replace "Workflow"
1.  **Delete** `debate/workflow/` custom engine.
2.  **Install** `langgraph`.
3.  **Implement** the Debate flow as a StateGraph:
    ```python
    workflow = StateGraph(AgentState)
    workflow.add_node("planner", planner_agent)
    workflow.add_node("reviewer", reviewer_agent)
    workflow.add_conditional_edges("planner", check_consensus)
    ...
    ```

### Phase 2: Simplify Infrastructure
1.  **Remove Redis** (unless strictly needed for multi-user web deployment). Run agents as concurrent asyncio tasks.
2.  **Remove** `debate/consensus.py`'s math logic. Replace with `ConsensusAgent` prompt.

### Phase 3: Optimize Data
1.  **Enable `pgvector`** extension in Postgres.
2.  **Migrate** `recommendation_embeddings` to `Vector(N)`.
3.  **Implement** proper RAG for the `Explorer` role.

## 5. Conclusion
The system works, but it's heavy. It carries the weight of a distributed enterprise system for a task that is essentially "ask 3 LLMs to agree on a diff".
**Strip it down. Lean on modern frameworks. Let the LLMs do the thinking, not the Python `set` logic.**
