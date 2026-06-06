# What the canvas actually renders — and why it looks "stupid"

This maps, table by table, exactly what the graph on the console canvas is showing for
`run-84fa2d86` (the VAMAC build), where each node comes from, and which nodes are
artifacts of sloppy event emission rather than real signal.

**One-sentence model:** the canvas is a *dumb, faithful renderer* of three data sources —
the run's `events.jsonl`, the headless `claude` stream log (`run.log`), and the static
pipeline skeleton. It invents nothing. So every weird node traces back to a weird event.
The builder is `Console.graph()` in `src/software_factory/console.py:457-595`.

---

## Table 1 — The node kinds and where each comes from

| Kind | Color | Source | Built at |
|------|-------|--------|----------|
| `orchestrator` | navy | always present, the root ("Claude · software-factory") | console.py (root node) |
| `phase` | gray=pending · orange=active · green=done | the **static** pipeline list `PIPELINE` (extract→provision→research→architect→tickets→build→deploy→test→teardown), colored by `phase` events | `console.py:482-489` |
| `gate` | teal=pending · green=passed | **static** nodes inserted after `research` (Stage 1 Gate) and after `tickets` (Stage 2 Gate). Color = `state.stage1_done`/`stage2_done` | `console.py:492-504` |
| `deps` | orange=pending · green=satisfied | one **static** "wait for deps" node between Stage 2 Gate and build | `console.py:506-513` |
| `agent` | green=done · orange=running · gray=planned · red=failed/no_op | union of: the **planned roster** (`PHASE_AGENTS`), `agent_spawned`/`agent_done` events, and `Task`-tool spawns parsed from `run.log` | `console.py:518-558` |
| `artifact` | purple=created · **red=missing** | **one node per `artifact` event** in `events.jsonl` | `console.py:560-570` |
| `blocker` | red | one node per uncleared `blocker` event | `console.py:573-581` |

Two rules below are the entire reason the graph looks dumb:

- **Label rule (`console.py:567`):** `label = payload.get("title", "artifact")`. No title in the event → the node is literally labeled **"artifact"**.
- **Status rule (`console.py:562-566`):** an artifact is `created` (purple) only if its `path` resolves to a real file *relative to the run base* and that file has content. Otherwise it's **`missing` (red)**. A bare/relative path that doesn't resolve → red, even if the file exists elsewhere.

---

## Table 2 — Every artifact event in THIS run (the real data)

Pulled live from `/data/runs/run-84fa2d86/events.jsonl`:

| # | `title` | `path` | `agent` | Renders as | Why |
|---|---------|--------|---------|-----------|-----|
| 1 | `input` | `input/vamac-proposal.pdf.md` | – | purple **"input"** | console emitted it; file exists → created |
| 2 | `input` | `input/context.txt` | – | purple **"input"** | console emitted it; file exists → created |
| 3 | `Input: VAMAC Proposal` | `input/vamac-proposal.pdf.md` | – | purple **"Input: VAMAC Proposal"** | **Stage-1 agent re-emitted** the same input |
| 4 | `PRD` | `workspace/vamac-employee-experience/PRD.md` | `HORIZON-2` | purple **"PRD"** | exists → created |
| 5 | *(none)* | `architecture.md` | – | **red "artifact"** | no title → "artifact"; bare path doesn't resolve from base → missing |
| 6 | *(none)* | `architecture.svg` | – | **red "artifact"** | same as #5 |

So your two questions answered exactly:

### The multiple "input" nodes (3 of them)
- **#1 and #2** are emitted by the **console itself** — my new input pipeline writes two files into `input/` (the extracted `…pdf.md` and the composed `context.txt`) and emits one `artifact{title:"input"}` per file (`console.py` `start_run`, via `persist_and_compose`).
- **#3** is emitted by the **Stage-1 research agent**, which re-announces the same proposal as `Input: VAMAC Proposal` — even though `skills/stage-1-research/SKILL.md` explicitly says *"The console has already saved the input — do NOT emit another input artifact."* The agent ignored that line.
- Net: **one uploaded PDF → three input nodes** (two from the console for two derived files, one duplicate from a disobedient agent).

### The two empty red "artifact" nodes
- They are events **#5 and #6**, emitted by the **Stage-2 architect** for `architecture.md` and `architecture.svg`.
- They render empty + red for two independent reasons, both sloppy emission:
  1. **No `title`** in the event → label falls back to the literal string `"artifact"` (`console.py:567`).
  2. **Bare relative `path`** (`architecture.md`, not `workspace/<repo>/architecture.md`) → the existence check resolves it against the run base, doesn't find it, marks it **`missing`/red** (`console.py:562-566`) — even though the file really does exist inside the workspace subdir.

---

## Table 3 — The other node groups in your screenshot

| Node(s) | Kind | Where it came from |
|---------|------|--------------------|
| `Claude · software-factory` | orchestrator | root, always |
| `scout.librarian`, `pm.lead`, `domain.expert`, `design.lead` | agent | planned roster `PHASE_AGENTS` + `agent_spawned/done` events |
| `frontend-design` | agent | the DESIGNER roster entry (uses the frontend-design skill) |
| `agent` (generic) | agent | an `agent_spawned`/Task spawn with no recognizable role → label fell back to `"agent"` |
| `PRD`, `input`, `Input: VAMAC Proposal` | artifact | Table 2 |
| `provision`, `extract`, `research`, … | phase | static pipeline |

---

## Why the agent nodes have empty inspector panels (your earlier question)

Clicking an agent node shows only `subagent · done` and nothing else because **the agent
nodes carry no payload beyond `{label, status, role}`**. The "agents" are not separate
logged processes — the whole run is **one** `claude` process, and the named agents
(HORIZON, VANGUARD, …) are roster markers derived from `agent_spawned`/`agent_done`
events and `Task`-tool mentions in the stream. Their actual work lives in the single
orchestrator transcript (the "Full claude transcript" you said is useful). Nothing is
stored per-agent, so the per-agent panel has nothing to show. Only **artifacts** get
attributed to an agent (e.g. PRD → HORIZON-2), and even that attribution falls back to
the orchestrator if the agent id isn't in the node set (`console.py:569`).

## Where the bottom-panel commands come from (your other question)

The LIVE ACTIVITY feed is the **headless `claude` stream-json log** (`run.log`), fetched
via `/api/runs/<id>/log` and rendered by `renderActivity()` in `index.html`. Each line is
one stream event: `💬` = assistant text, `🔧 Bash {"command":…}` / `Read {…}` = the actual
tool calls the orchestrator is making, `▸ phase` / `✦ artifact` = the pipeline's own
emitted events. It's a live transcript of what the agent is literally doing — not synthesized.

---

## So, the actual flaws ("why it's stupid")

1. **No emission discipline.** `title` is optional and silently defaults to `"artifact"`; paths aren't normalized to a single convention. Garbage in → mystery nodes out. *Fix: make the artifact gate reject a titleless artifact and normalize paths to run-relative before emit.*
2. **Duplicate inputs.** The console emits an input node per derived file (2), and the Stage-1 agent emits another despite being told not to. *Fix: one canonical input node; drop the agent's re-emit (or have the gate dedupe by path).*
3. **False "missing" reds.** The existence check only resolves paths relative to the run base, so a workspace-relative file emitted with a bare name shows red. *Fix: resolve artifact paths against the workspace too, or require workspace-relative paths.*
4. **Dead stage gates** (separate issue): the static `Stage 1/2 Gate` nodes render a "Run paused for review / Continue" panel, but `detect_stage1_done`/`detect_stage2_done` are never called in the live loop, so the run never auto-advances and the Continue button posts `gate=undefined` (does nothing). That's why both gates "stuck" and I had to nudge them by hand.

All four are emission/wiring problems in `console.py` + the stage skills — **not** the renderer. The canvas is doing exactly what it's told; it's being told sloppy things.
