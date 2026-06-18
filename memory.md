# Memory & context architecture + comms  (Proposal §4 + §5)

## §4 — Memory & context (the core fix: pull, not push)

- **Storage of record:** the GitHub repo (code) + **ruflo memory** (AgentDB) for product/decision
  knowledge + coordination state.
- **Access = pull over MCP.** Each agent gets a tiny **memory-first instruction** ("query ruflo for
  what you need before acting") + the ruflo MCP tools (`memory_usage` retrieve/search,
  `retrieveWithReasoning`) — *not* a fixed context dump. Retrieval is hybrid (vector + BM25 + RRF +
  rerank), scoped by **namespace**: `project/<id>`, `run/<id>`, `tickets/<id>`, `coordination`.
  → `memory.project_ns / run_ns / ticket_ns / COORDINATION`; local fallback `memory.MemoryStore`.
- **Reasoning/precedent loop (ReasoningBank):** each agent's trajectory + outcome is written back
  (trajectory → verdict → distill → prune) so later agents query "how was this handled" by
  similarity, with confidence/success counts. → `memory.record_precedent`, `memory.recall_precedent`.
- **Consolidation:** distil + prune **between phases**, so memory stays sharp and small instead of an
  ever-larger blob re-sent every turn. → `memory.consolidate`.

In production these bind to ruflo over MCP (`npx -y ruflo@latest mcp start`); `memory.py` is the
namespace + precedent convention + a local fallback so the behaviour is deterministic/testable.

## §5 — Agent communication model (two complementary channels)

- **Direct peer messaging (`claude-peers` / session-bridge MCP)** — synchronous, push,
  conversational. The **live bus**: the **co-design pair** negotiating architecture/features
  ("two agents communicating exactly"), orchestrator↔worker "I'm blocked / here's feedback" pings,
  fix-loop dispatch. Best for the **persistent** agents (orchestrator + co-design pair).
- **Shared memory (ruflo AgentDB: `coordination` + project namespaces)** — async, durable,
  queryable. The **system-of-record + handoff + precedent**: artifacts, decisions, ticket state,
  "what's done," dependency status. Survives crashes; **ephemeral per-ticket build agents
  write-and-exit here** (`swarm/<agent>/{status,progress,complete}`, `swarm/shared/<component>`).

**Rule of thumb:** *live / "I need you now" / decide-together* → `claude-peers`; *durable / async /
"what happened"* → shared memory. The **orchestrator** is the hub and the only actor that declares a
phase complete.

# main-owner (software-factory-skill) Update at Time: 18:06:2026:04:30:00.000
1. Implemented the Nick-feedback plan on branch feature/console-v2 (off consolidated-base): interview→council PRD, React console + graph/kanban toggle, docx2md ingestion, multi-deliverable.
2. src/software_factory/{brief.py,console.py,chat_agent.py,runstate.py,tickets.py,db.py,docx_extract.py,input_pipeline.py}, console/app.py, console/web/** (Vite+React+TS SPA), skills/stage-1/2/3 SKILL(.opencode).md; plan at ~/.claude/plans/this-is-the-feedback-purring-donut.md
3. Operator goal "implement this plan without my input"; built phases 1,2,D,A,B,H-step1. SF_CONSOLE=react serves the SPA (legacy index.html still default → nothing breaks). Drafts mint canonical run-<8hex> up front (poller-invisible).
4. Summary: full unit suite 412 passed/1 skipped; live E2E smoke green (draft/brief/tickets/deployments/React all serve). REMAINING (operator-gated): F = live babysit (needs real API/Railway/GitHub keys + spend — not run autonomously); H steps 3-5 (Build IR, screenshot-diff verify) deferred per plan. 6 commits c3c6e0e..d2f2303.
