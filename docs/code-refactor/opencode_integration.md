# OpenCode Integration Spec

## Goal

Integrate the multi-agent debate orchestrator as a first-class OpenCode extension using:
1. **Custom Commands** (`/debate`, `/debate-costs`) - Quick slash command access
2. **Plugin with Tools** - Let AI invoke orchestrator programmatically
3. **Toast Notifications** - Show cost updates in TUI

---

## Part 1: Custom Commands

Create markdown files in `.opencode/command/` or `~/.config/opencode/command/`:

### `/debate` - Start a Debate

```markdown
<!-- .opencode/command/debate.md -->
---
description: Start a multi-agent debate for a feature request
agent: coder
subtask: true
---

Run the multi-agent debate orchestrator for the following request:

$ARGUMENTS

Execute: `debate start "$ARGUMENTS"`

After the debate completes, summarize the consensus and ask if I want to proceed with implementation.
```

**Usage:** `/debate Add user authentication with OAuth2`

**Note:** `subtask: true` is critical here - see [Subtask Explanation](#subtask-explained) below.

### `/debate-costs` - Show Costs

```markdown
<!-- .opencode/command/debate-costs.md -->
---
description: Show cost breakdown for a debate task
agent: coder
---

Get the cost breakdown for the debate task: $1

Execute: `debate costs $1 --json`

Format the output as a readable summary showing:
- Total cost
- Cost per agent (claude, gemini)
- Token usage breakdown
```

**Usage:** `/debate-costs my-feature`

### `/debate-status` - Check Status

```markdown
<!-- .opencode/command/debate-status.md -->
---
description: Check current debate orchestration status
agent: coder
---

Check the status of the current debate orchestration.

Execute: `debate status`

Show me the current phase, round number, and any pending questions.
```

---

## Part 2: Plugin with Tools

Create `.opencode/plugin/debate.ts`:

```typescript
import { tool } from "opencode/plugin"
import { z } from "zod"

export default (ctx) => {
  const { $, project } = ctx

  return {
    // Custom tools the AI can invoke
    tools: {
      debate_start: tool({
        description: "Start a multi-agent debate for a feature. Use this when the user wants multiple AI models to discuss and plan a feature before implementation.",
        parameters: z.object({
          request: z.string().describe("The feature request or task description"),
          skip_explore: z.boolean().optional().describe("Skip codebase exploration phase"),
          max_rounds: z.number().optional().describe("Maximum debate rounds (default: 3)"),
        }),
        execute: async ({ request, skip_explore, max_rounds }) => {
          const flags = [
            skip_explore ? "--skip-explore" : "",
            max_rounds ? `--max-rounds ${max_rounds}` : "",
          ].filter(Boolean).join(" ")

          const result = await $`debate start "${request}" ${flags}`.text()
          return { status: "completed", output: result }
        },
      }),

      debate_costs: tool({
        description: "Get cost breakdown for a debate task. Shows total cost, cost per agent, and token usage.",
        parameters: z.object({
          task_slug: z.string().describe("The task identifier (slug)"),
        }),
        execute: async ({ task_slug }) => {
          const result = await $`debate costs ${task_slug} --json`.json()
          return result
        },
      }),

      debate_status: tool({
        description: "Get current status of a debate task including phase, round, and consensus score.",
        parameters: z.object({
          task_slug: z.string().optional().describe("Task slug (uses latest if not provided)"),
        }),
        execute: async ({ task_slug }) => {
          const slug = task_slug ?? "latest"
          const result = await $`debate status ${slug} --json`.json()
          return result
        },
      }),

      debate_resume: tool({
        description: "Resume a paused or interrupted debate task.",
        parameters: z.object({
          task_slug: z.string().describe("The task identifier to resume"),
        }),
        execute: async ({ task_slug }) => {
          const result = await $`debate resume ${task_slug}`.text()
          return { status: "resumed", output: result }
        },
      }),

      debate_list: tool({
        description: "List all debate tasks with their status.",
        parameters: z.object({
          limit: z.number().optional().describe("Number of tasks to show (default: 10)"),
        }),
        execute: async ({ limit }) => {
          const result = await $`debate list --limit ${limit ?? 10} --json`.json()
          return result
        },
      }),
    },

    // Event hooks
    hooks: {
      // Show toast when session becomes idle
      "session.idle": async (event) => {
        try {
          const costs = await $`debate costs latest --json 2>/dev/null`.json()
          if (costs && costs.total_cost_usd > 0) {
            ctx.tui.toast.show({
              title: "Debate Session Cost",
              message: `$${costs.total_cost_usd.toFixed(4)} (${costs.total_tokens.toLocaleString()} tokens)`,
            })
          }
        } catch {
          // No active debate, ignore
        }
      },

      // Intercept after tool execution to track activity
      "tool.execute.after": async (event) => {
        // Could log tool usage to orchestrator for context
      },
    },
  }
}
```

### Plugin Dependencies

Create `.opencode/package.json`:

```json
{
  "dependencies": {
    "zod": "^3.22.0"
  }
}
```

---

## Part 3: CLI Commands to Add

For the plugin tools to work, add these CLI commands:

### `debate status [task_slug] --json`

```python
# In cli.py
@main.command()
@click.argument("task_slug", required=False)
@click.option("--json", "as_json", is_flag=True)
def status(task_slug: str | None, as_json: bool) -> None:
    """Show status of a debate task."""
    async def show_status():
        async with db.get_session() as session:
            if task_slug:
                task = await db.get_task_by_slug(session, task_slug)
            else:
                # Get latest task
                task = await db.get_latest_task(session)

            if not task:
                if as_json:
                    console.print('{"error": "No task found"}')
                else:
                    console.print("[red]No task found[/red]")
                return

            data = {
                "task_slug": task.slug,
                "status": task.status,
                "phase": task.status,  # Map to phase
                "current_round": task.current_round,
                "max_rounds": task.max_rounds,
                "complexity": task.complexity,
                "total_cost": float(task.total_cost),
                "total_tokens": task.total_tokens,
                "created_at": task.created_at.isoformat(),
            }

            if as_json:
                console.print(json.dumps(data, indent=2))
            else:
                # Rich formatted output
                ...

    asyncio.run(show_status())
```

### `debate list --limit N --json`

```python
@main.command()
@click.option("--limit", default=10, help="Number of tasks to show")
@click.option("--json", "as_json", is_flag=True)
def list(limit: int, as_json: bool) -> None:
    """List debate tasks."""
    async def list_tasks():
        async with db.get_session() as session:
            tasks = await db.get_recent_tasks(session, limit=limit)
            # Format and output...

    asyncio.run(list_tasks())
```

---

## Part 4: How It All Works Together

### User Flow 1: Start Debate via Command

```
User: /debate Add dark mode toggle to settings

OpenCode: [Executes debate start "Add dark mode toggle to settings"]
         [Shows progress as orchestrator runs]
         [Toast: "Debate Session Cost: $0.45"]

OpenCode: The debate has concluded. Here's the consensus:
         - Add ThemeContext provider
         - Create useTheme hook
         - Update 12 components

         Agreement rate: 87%
         Cost: $0.45 (claude: $0.28, gemini: $0.17)

         Would you like me to proceed with implementation?
```

### User Flow 2: AI Invokes Tool Automatically

```
User: I need to add user authentication. Can you have your AI colleagues
      debate the best approach before we implement?

OpenCode: [Recognizes intent, calls debate_start tool]
         I'll start a multi-agent debate on authentication approaches.

         [Tool: debate_start({request: "Add user authentication"})]

         [Toast: "Debate Session Cost: $0.72"]

         The debate concluded with 92% agreement. Both Claude and Gemini
         recommend:
         1. Use JWT tokens with refresh mechanism
         2. Add /auth/login, /auth/refresh, /auth/logout endpoints
         3. Create AuthContext provider

         Should I implement this plan?
```

### User Flow 3: Check Costs

```
User: /debate-costs auth-feature

OpenCode: Cost breakdown for auth-feature:

         Total: $0.72

         By Agent:
         - claude: $0.45 (62%)
         - gemini: $0.27 (38%)

         Tokens: 45,678
         - Input: 40,000
         - Output: 5,678
```

---

## Summary: What This Gets You

| Feature | Without Plugin | With Plugin |
|---------|---------------|-------------|
| Start debate | `debate start "..."` in terminal | `/debate ...` or AI auto-invokes |
| Check costs | `debate costs slug` | `/debate-costs` or AI calls tool |
| Toast notifications | None | Shows cost after session |
| AI awareness | None | AI can decide to use debate |
| Context injection | None | Orchestrator status in prompts |

**Main advantage:** The orchestrator becomes a tool the AI can choose to use, not just a separate CLI you run manually.

---

## Files to Create

| File | Purpose |
|------|---------|
| `.opencode/command/debate.md` | `/debate` slash command |
| `.opencode/command/debate-costs.md` | `/debate-costs` slash command |
| `.opencode/command/debate-status.md` | `/debate-status` slash command |
| `.opencode/plugin/debate.ts` | Plugin with tools + hooks |
| `.opencode/package.json` | Plugin dependencies |

## CLI Commands to Add

| Command | Purpose |
|---------|---------|
| `debate status [slug] --json` | Get task status |
| `debate list --limit N --json` | List recent tasks |
| `debate costs <slug> --json` | Get cost breakdown (already planned) |

---

## Part 5: Subtask Explained

### What is `subtask`?

The `subtask` option in OpenCode commands forces the command to run as a **subagent** - an isolated child session that doesn't pollute your main conversation context.

### How Subagents Work

```
┌─────────────────────────────────────────────────────┐
│  Main OpenCode Session (Primary Agent)              │
│                                                     │
│  User: /debate Add OAuth authentication             │
│                                                     │
│  ┌─────────────────────────────────────────────┐   │
│  │  Subagent Session (Isolated)                │   │
│  │                                             │   │
│  │  - Own context window                       │   │
│  │  - Can use different LLM                    │   │
│  │  - Independent tool access                  │   │
│  │  - Runs `debate start "Add OAuth..."`       │   │
│  │  - All orchestrator output stays here       │   │
│  │                                             │   │
│  │  [Returns summary when complete]            │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  OpenCode: Debate complete. Agreement: 92%...       │
└─────────────────────────────────────────────────────┘
```

### `subtask: true` vs `subtask: false`

| Setting | Behavior | Use When |
|---------|----------|----------|
| `subtask: true` | Spawns isolated subagent session | Long-running tasks, heavy output |
| `subtask: false` (default) | Runs in main conversation | Quick commands, need full context |

### Why `subtask: true` for Debate Commands

The debate orchestrator is a **long-running, output-heavy** operation:

1. **Multiple agent calls** - Runs Gemini, Claude, possibly multiple rounds
2. **Verbose output** - Each agent produces detailed analysis
3. **Context preservation** - Don't want debate logs consuming main context window
4. **Clean results** - User wants the consensus, not all intermediate steps

**Without `subtask: true`:**
```
User: /debate Add authentication

[500 lines of orchestrator output flood the conversation]
[Context window filled with debate logs]
[Main conversation polluted]
```

**With `subtask: true`:**
```
User: /debate Add authentication

[Subagent runs silently]
[Toast: "Debate Cost: $0.45"]

OpenCode: Debate complete!
         Agreement: 92%
         Recommendation: JWT + refresh tokens

         Implement?
```

### Subagent Configuration Options

From [OpenCode Agents docs](https://opencode.ai/docs/agents/):

```markdown
<!-- .opencode/command/debate.md -->
---
description: Start multi-agent debate
subtask: true           # Force subagent mode
agent: coder            # Which agent runs this
model:                  # Optional: override model
  provider: anthropic
  model: claude-sonnet-4-20250514
---
```

### Subagent Internals

Subagents are invoked through OpenCode's `task` tool:

1. Primary agent receives `/debate` command
2. Sees `subtask: true`, invokes task tool
3. Task tool creates new child session
4. Child session gets own context, tools, system prompt
5. Child runs the command independently
6. Child completes, returns result to parent
7. Parent summarizes result for user

Reference: [How Coding Agents Work - OpenCode Deep Dive](https://cefboud.com/posts/coding-agents-internals-opencode-deepdive/)

---

## Part 6: Language Requirements (Python vs TypeScript)

### Short Answer: NO Rewrite Needed

Your orchestrator **stays in Python**. Only the thin OpenCode integration layer is TypeScript.

### What's Written in What

| Component | Language | Notes |
|-----------|----------|-------|
| **Debate Orchestrator** | Python | Stays Python - no change |
| **CLI (`debate` command)** | Python | Stays Python - no change |
| **LangGraph flow** | Python | Stays Python - no change |
| **OpenCode Commands** | Markdown | Just `.md` files with shell commands |
| **OpenCode Plugin** | TypeScript | ~50 lines, shells out to Python CLI |

### How It Works

```
┌─────────────────────────────────────────────────────────────┐
│  OpenCode (TypeScript/Go)                                   │
│                                                             │
│  Plugin (.opencode/plugin/debate.ts)                        │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  export default (ctx) => ({                         │   │
│  │    tools: {                                         │   │
│  │      debate_start: tool({                           │   │
│  │        execute: async ({ request }) => {            │   │
│  │          // Shells out to Python CLI                │   │
│  │          await $`debate start "${request}"`  ──────────────┐
│  │        }                                            │   │ │
│  │      })                                             │   │ │
│  │    }                                                │   │ │
│  │  })                                                 │   │ │
│  └─────────────────────────────────────────────────────┘   │ │
└─────────────────────────────────────────────────────────────┘ │
                                                                │
┌───────────────────────────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────┐
│  Debate Orchestrator (Python)                               │
│                                                             │
│  debate/cli.py          → Entry point                       │
│  debate/langgraph_app.py → LangGraph orchestration          │
│  debate/db.py           → PostgreSQL persistence            │
│  debate/consensus.py    → Consensus calculation             │
│  debate/costs.py        → Cost tracking                     │
└─────────────────────────────────────────────────────────────┘
```

### The TypeScript Plugin is Just a Wrapper

The entire plugin is ~50 lines that shell out to your Python CLI:

```typescript
// This is ALL the TypeScript you need
execute: async ({ request }) => {
  const result = await $`debate start "${request}"`.text()
  return { output: result }
}
```

It's equivalent to running `debate start "..."` in a terminal.

### When Would You Need TypeScript?

Only if you wanted to:

| Scenario | TypeScript Needed? |
|----------|-------------------|
| Use OpenCode commands | No - markdown files |
| Create plugin tools that call CLI | Minimal (~50 lines) |
| Deep OpenCode integration (modify internals) | Yes |
| Replace orchestrator with JS | Yes (but why?) |

### Recommendation

**Keep Python for the orchestrator.** The TypeScript plugin is just glue code.

```
Your codebase:     99% Python (orchestrator, CLI, LangGraph)
OpenCode glue:      1% TypeScript (thin wrapper plugin)
```

### If You Really Wanted Full TypeScript

You'd need to rewrite:
- LangGraph flow → Use LangGraph.js or custom
- PostgreSQL layer → Use Drizzle/Prisma
- Consensus algorithm → Port to TypeScript
- OpenCode client → Already have httpx, would need fetch

**Effort:** ~2-3 weeks, **Benefit:** Marginal (tighter OpenCode coupling)

**Verdict:** Not worth it. The shell-out approach is standard and works fine.

---

## Part 7: What OpenCode CAN'T Do (Limitations)

For transparency, here's what the plugin/command approach **cannot** achieve:

| Desired Feature | Possible? | Alternative |
|-----------------|-----------|-------------|
| Custom sidebar section | No | Use toasts or separate terminal |
| Real-time cost ticker | No | Print costs at end of orchestration |
| Modify TUI layout | No | N/A |
| Custom status bar | No | Use `debate status --watch` in tmux pane |

The OpenCode TUI sidebar (Context, MCP, LSP) displays **internal state only**. There's no plugin hook to inject custom displays there.

---

## Part 7: Implementation Checklist

### Phase 1: CLI Enhancements (Required First)

- [ ] Add `debate costs <slug> --json` command
- [ ] Add `debate status [slug] --json` command
- [ ] Add `debate list --limit N --json` command
- [ ] Add `get_task_costs()` to `db.py`
- [ ] Add `get_latest_task()` to `db.py`
- [ ] Add `get_recent_tasks()` to `db.py`

### Phase 2: OpenCode Commands

- [ ] Create `.opencode/command/debate.md`
- [ ] Create `.opencode/command/debate-costs.md`
- [ ] Create `.opencode/command/debate-status.md`
- [ ] Test commands work: `/debate`, `/debate-costs`, `/debate-status`

### Phase 3: OpenCode Plugin

- [ ] Create `.opencode/plugin/debate.ts`
- [ ] Create `.opencode/package.json`
- [ ] Test tools: `debate_start`, `debate_costs`, `debate_status`
- [ ] Test toast notifications on session.idle

### Phase 4: Documentation

- [ ] Update README with OpenCode integration instructions
- [ ] Add examples of AI invoking debate tools

---

## References

- [OpenCode Commands](https://opencode.ai/docs/commands/)
- [OpenCode Agents & Subagents](https://opencode.ai/docs/agents/)
- [OpenCode Plugins](https://opencode.ai/docs/plugins/)
- [OpenCode Config](https://opencode.ai/docs/config/)
- [OpenCode CLI](https://opencode.ai/docs/cli/)
