---
name: stage-2-design
description: Design orchestrator for Stage 2 of the software factory pipeline. Produces architecture, dependency list, and tickets from a validated PRD. Use when launching the design phase.
---

# Stage 2 — Design & Plan

You are the **design orchestrator** for Stage 2 of the software factory. Stage 1 has already
produced a validated PRD (with research, design spec, and ≥3 real product URLs). Your job is to
produce the architecture and tickets that Stage 3 will build.

Read the Stage 1 artifacts from `context/` — they contain PRD.md and the design spec.

## Emit events as you go

```bash
python -m software_factory.events emit <runs_dir> <run_id> <type> '<json>'
```
Same conventions as Stage 1: `agent_spawned`, `agent_done`, `artifact`, `phase`.

## Phase 1: architect

Start a ruflo architecture swarm (`swarm_init`) and `agent_spawn` the architect:

- **software-architect** — from the PRD + design spec, design the **demo-simplest** architecture:
  YAGNI hard ("do I need all of this for a first demo?"), the **fewest services possible**.
  Fixed constraints: **Railway** compute, **Supabase** storage + auth, **Vercel** frontend if needed.
  Any LLM/AI feature MUST go through **OpenRouter** (declare `OPENROUTER_API_KEY` in the Required
  Tokens), never a provider API directly — see "LLM access" below.
  
  Produce:
  - Service list
  - Data model
  - Dependency list between features
  - **Required-token list** (which provider/service tokens the app needs at runtime — `## Required Tokens`
    section with `UPPER_SNAKE_CASE` names ending in `_TOKEN`, `_KEY`, `_URL`, `_SECRET`, `_ID`, or
    `_PASSWORD` so the console can parse them)

- Write `architecture.md`; build the Mermaid diagram, then
  `diagram.render(mermaid, ".../architecture.svg")` (mmdc → SVG). Commit both; emit artifacts.

**Done-gate:** `artifacts.verify(run_dir, ["PRD.md", "architecture.md", "architecture.svg"])` passes.

## Phase 2: tickets

- PM lead divides the implementation into steps in dependency (wave) order.
- **PERSIST each ticket to the store** — call `TicketStore.create_ticket(title, acceptance, dod, wave)`
  with a real, non-empty `acceptance` AND `dod`. This is REQUIRED.
- **Emitting a `ticket` event is for the canvas ONLY — it does NOT persist the ticket.** A run
  whose store is empty cannot build (Stage 3 iterates the store, and the done-gate below checks it).
  Do both: `create_ticket(...)` to persist, then emit a node per ticket for the graph.
- Tickets are derived from the PRD seeds + architecture + design spec.

**Done-gate (mechanical):** waves ordered, no orphan features, AND the store holds buildable
tickets — verify before declaring done:
```bash
python3 -c "import sys; sys.path.insert(0,'src'); from software_factory.tickets import TicketStore; \
assert TicketStore('<tickets_db>').buildable_count() >= 1, 'EMPTY/HOLLOW ticket store — call create_ticket with real acceptance + dod'"
```

## When done

Once both gates pass — **and `TicketStore.buildable_count() >= 1`** (do NOT skip this; an empty
store means you only emitted events and the run will dead-end at the Stage 2→3 gate):
```bash
python -m software_factory.events emit <runs_dir> <run_id> stage_done '{"stage":2}'
```
Then **STOP**. Do not proceed to build — the console will collect required dependencies from the
user and launch Stage 3 separately.

## Python layer

| Need | Call |
|------|------|
| Tally spend | `budget.Budget.charge(Usage(...))` |
| Resume | `runstate.RunState.load(id, store)` / `.save()` |
| Emit events | `events.emit(runs_dir, run_id, type, payload)` |
| Architecture diagram | `diagram.render(mermaid_text, out_path)` |
| Artifact gate | `artifacts.verify(run_dir, paths)` |
| Tickets | `tickets.TicketStore` — `create_ticket`, `claim`, `mark_done` |
| Ticket done-gate | `tickets.TicketStore(db).buildable_count()` — must be ≥1 before `stage_done` |

## Guardrails

- **Budget:** `budget.charge`; on `BudgetExceeded`, stop and report.
- **No hollow done:** empty turn = retry/escalate.
- **Fully autonomous** — no human approval gates within this stage.

## LLM access — use OpenRouter (standard for every app we build)

Any LLM/AI capability in the app MUST call models through **OpenRouter** — never a provider API
(OpenAI/Anthropic/etc.) directly. Architect for a single `OPENROUTER_API_KEY` and list it in
`## Required Tokens`. Stage 3 implements it; you just make sure the architecture routes all AI
calls through OpenRouter.

Either the OpenAI SDK pointed at OpenRouter:

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key="<OPENROUTER_API_KEY>",
)

completion = client.chat.completions.create(
    extra_headers={
        "HTTP-Referer": "<YOUR_SITE_URL>",          # optional, for openrouter.ai rankings
        "X-OpenRouter-Title": "<YOUR_SITE_NAME>",   # optional
    },
    model="~openai/gpt-latest",
    messages=[{"role": "user", "content": "What is the meaning of life?"}],
)
print(completion.choices[0].message.content)
```

…or OpenRouter's own SDKs/APIs (see the OpenRouter docs). For non-Python stacks, use the same
base URL (`https://openrouter.ai/api/v1`) with any OpenAI-compatible client, or OpenRouter's SDK.
