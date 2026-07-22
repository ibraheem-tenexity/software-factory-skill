# Concierge Agent — How It's Programmed

**Date:** 2026-06-30 · **Repo home when committed:** `docs/concierge-agent-spec.md` (the path `services/conversation.py` already points at).
**One line:** the Concierge is **a system prompt + a LangChain agent + a small set of tools that actually work** — nothing else. It emits a fixed JSON shape to the human; the multiple-choice UI is derived purely from that shape.

---

## 1. What we are removing (explicitly)

The current `chat_agent.py` is built on the **OpenAI Agents SDK** (`Agent(...)` + `Runner.run/run_streamed`) with **fourteen tools** wired in `make_tools()`:

`get_company_profile`, `set_company_profile`, `set_connected_systems`, `set_project_basics`, `set_project_scope`, `attach_project_materials`, `request_materials`, `get_intake_state`, `validate_intake_complete`, `hand_off_to_factory`, `check_status`, `restart_pipeline`, `request_dep_input`, `get_result`.

**All fourteen are removed.** They don't work reliably and we are not fixing them. The scripted mock in `services/conversation.py` is removed too. We do **not** port them. The agent starts with a **clean, empty-or-tiny tool belt** and we add back only tools that are genuinely wired to working backends (see §5).

> **Runtime change:** the agent framework moves from OpenAI Agents SDK → **LangChain agent SDK**, by your explicit call (and it matches the repo's own stated direction — `conversation.py` already says "stands in until the real LangChain agent"). Note the scope: LangChain is the **agent runtime only**. Retrieval/ingestion plumbing stays framework-free per the earlier anti-bloat decision — no LangChain in the memory pipeline.

---

## 2. The three parts, and only these three

```
Concierge = System Prompt  +  LangChain agent  +  Tools
```

1. **System prompt** — one editable prompt (as shipped, kept in `system_agents` under the `callsign='CONCIERGE'` row — `prompt`/`model_id` columns — with the 60s-TTL operator-override cache so a Tenexity OS edit drives the next session). It carries the identity/voice (spec Principle 2), the "one question per turn" style, and a **context** framing (`intake` | `overview` | `build` | `docs` | `ingesting`) passed in per session so the *same* agent changes focus without changing identity.
2. **LangChain agent** — a single tool-calling agent (LangGraph `create_react_agent`-style loop, or `AgentExecutor`): bind the model (via OpenRouter/OpenAI, using the project's chosen engine), bind the tools, run the reason→act→observe loop until it produces a final answer. No multi-agent graphs, no chains-of-chains, no memory abstractions — the loop and nothing more.
3. **Tools** — plain functions the agent may call. Empty is a valid starting state. Every tool must hit a real, working backend or it doesn't get bound.

---

## 3. The output contract (this is what drives the UI)

The Concierge's message **to the human** is always this JSON — never free text on the wire:

```jsonc
{
  "response": "string, REQUIRED — what the Concierge says to the user",
  "suggested_responses": [            // may be empty
    { "response": "string", "type": "single select" | "multi select" }
  ]
}
```

Rules the whole system relies on:
- **`response` is required and non-empty.** It's the assistant's utterance.
- **`suggested_responses` empty ⇒ a plain-text turn.** The FE shows just the message + the free-text Composer.
- **`suggested_responses` non-empty ⇒ the FE renders selectable options.** Each item carries its own `type`: `single select` → radio rows (clicking submits immediately); `multi select` → checkbox rows (tick several → Confirm submits the joined set). *The multiple-choice behavior is 100% determined by the shape of this output — there is no separate "choices" field and no server-side question-type state.*
- **No `done` flag.** The old readiness flag is gone. After the user and Concierge agree to proceed, hand-off may come from the on-screen button or the real Concierge tool. A completed turn carries the factual `handed_off` result so the UI navigates after a successful tool call; readiness is never a hidden boolean.

This replaces the old `ConverseOut {message, choices, done}`. New `ConverseOut` is `{response: str, suggested_responses: [{response: str, type: str}], handed_off: bool}`; `handed_off` reflects the real post-turn project phase rather than agent judgment.

### Enforcing the shape in LangChain
The final turn is coerced to a Pydantic schema so the JSON is guaranteed, not hoped for:

```python
class SuggestedResponse(BaseModel):
    response: str
    type: Literal["single select", "multi select"]

class ConciergeTurn(BaseModel):
    response: str
    suggested_responses: list[SuggestedResponse] = []
```

The agent runs its normal tool loop; the **final** step produces a `ConciergeTurn` via structured output (`llm.with_structured_output(ConciergeTurn)` on the closing synthesis, or a single `respond_to_user` structured tool that terminates the loop). Tools run as intermediate steps; only the terminal message is shaped. Invalid/parse-fail → one retry, then a safe `{response: "...", suggested_responses: []}` fallback so a bad generation never 500s the turn.

---

## 4. One turn, end to end

```
POST /api/projects/{pid}/converse   { message, session_id? }
  1. Resolve/mint session_id (thread) + author user_id; load prior turns for session_id from `conversation`.
  2. Build LangChain message list from history via to_provider(...) (canonical blocks → provider shape).
  3. Run the LangChain agent (system prompt + context + tools) over that history + the new user message.
       · tool calls execute as intermediate steps (each recorded as agent/tool rows — §6)
  4. Coerce the final step to ConciergeTurn (structured output).
  5. Persist: one `user` row (the incoming message) + one `agent` row (response + suggested_responses in json_blob),
     with session_id, message_id, model, provider, tokens, cost.
  6. Return ConciergeTurn → FE renders text or single/multi-select from suggested_responses.
```

Same agent object serves the persistent dock and the onboarding rail — only the `context` differs (spec §4.6).

---

## 5. Tools: start empty, add only what's real

Because the fourteen tools are gone, the belt begins minimal. We add back **only** tools with a working backend, one at a time, each behind the same LangChain binding:

- **Memory read tools** (from the Project Memory milestone): `get_project_overview`, `search_memory`, `get_document_summary` — these become the Concierge's way to answer "what did you learn from my docs" for real. Read-only.
- **Intake persistence** — *only if/when* it actually writes (e.g., a single `save_project_field` over the real store). If it's not wired to persistence, it isn't a tool; the Concierge just converses and the FE form owns the writes.
- **Handoff** — a real tool over the same `promote_draft` function as the button. Its successful turn reports `handed_off: true`, which moves onboarding to the Factory Console.

Principle: **an unbound-to-reality tool is worse than no tool.** Empty belt is fine; the agent is still useful as prompt + structured conversation.

---

## 6. Conversation store: session_id + message_id are first-class

Your call on session/history is right — they're core. Reconciling naming with the store design:

- **`session_id`** (was `thread_id`) — the conversation/thread id; groups all turns of one Concierge conversation. For onboarding it's deterministic per draft; a project can have several (intake vs. persistent dock contexts).
- **`message_id`** — the per-message primary key (`id`), returned to the FE so a specific turn is addressable (edit, cite, jump-to).
- Every row still carries `user_id`, `project_id`, `org_id` (denormalized), `role` (`user`|`agent`|`tool`|`system`), `input`, `json_blob` (canonical blocks incl. `suggested_responses` on agent turns), `model`, `provider`, tokens/cost, `created_at`/`updated_at`.
- A tool call is an `agent` row whose `json_blob` has a `tool_use` block; its result is a following `tool` row — so the LangChain intermediate steps are fully reconstructable and replayable.

---

## 7. Admin history table (Tenexity OS)

A new operator screen: **one filterable table of all conversation history across the platform.**

- **Endpoint:** `GET /api/admin/conversations` (staff-gated via `_staff_session`), filterable by `org_id`, `project_id`, `user_id`, `session_id`, role, date range; paginated. It's a straight query over `conversation` (which already carries all four scopes).
- **Two views:** a **threads** roll-up (session_id + org + project + user + last activity + turn count) and a **messages** drill-down (each turn with role, model/provider, cost, and the rendered `response`/`suggested_responses`).
- **Screen:** lives in Tenexity OS alongside §5.4's produced-files index — a history/observability surface. Filters map 1:1 to the columns; clicking a thread opens its full transcript.
- Ties into cost/telemetry: because agent rows store `model`/`provider`/tokens/`cost`, the admin view doubles as per-conversation spend visibility.

---

## 8. Net changes to the plan

- **Phase 2 (Concierge)** becomes: *rip out* the OpenAI-Agents-SDK agent + all 14 tools + the scripted mock; *build* the LangChain agent = system prompt + tool belt (starts empty) + `ConciergeTurn` structured output; new `ConverseOut` = `{response, suggested_responses[], handed_off}`.
- **Conversation store**: rename `thread_id`→`session_id`; guarantee `message_id` in the FE response; `suggested_responses` live in the agent row's `json_blob`.
- **New ticket — Admin history table** (Tenexity OS): the filterable cross-tenant conversation index (§7).
- **Dependency:** the LangChain agent depends on the conversation store (history replay) and, for real tools, on the Memory MCP — but it can ship with an **empty tool belt** the moment the store is ready.
```
