# Langfuse telemetry — emission map + healthy baseline (SOF-25)

**Purpose:** a cheap, repeatable way to confirm the console's Langfuse telemetry is actually
landing, not just configured. Re-run the "cheap canary" recipe below after any deploy or change
touching the areas listed in "when to re-verify" — telemetry can break silently (a dependency bump,
a refactor, a key rotation, a deploy-path change) and nothing else will tell you.

There are **two independent tracing surfaces**. They have different code, different gates, and
very different re-verification cost. Don't conflate them.

## Surface 1 — Concierge live-agent tracing (the cheap canary)

**Code:** `src/software_factory/langfuse_tracing.py` (`enabled()`, `setup_langfuse()`), wired in
`src/software_factory/chat_agent.py` → `ChatAgentRunner.__init__` (`self._langfuse =
langfuse_tracing.setup_langfuse()`).

**Mechanism:** `OpenAIAgentsInstrumentor().instrument()` installs itself as the OpenAI Agents SDK's
**exclusive** trace processor (per-process, idempotent), replacing the SDK's default OpenAI-backed
exporter. Every `Runner.run` / `Runner.run_streamed` call — i.e. every turn through `POST
/api/chat` — is exported via OpenTelemetry to Langfuse.

**Gate:** `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY` present. No-op (not an error) if absent.
**Confirmed live (2026-07-01):** both keys present on `factory-console` /
`software-factory-as-skill`; boot log shows
`[langfuse] concierge tracing instrumented → https://us.cloud.langfuse.com` — instrumentation
activated successfully (no "tracing packages are missing" warning, which would fire on an
`ImportError` from `langfuse`/`openinference-instrumentation-openai-agents`).

**Not this surface:** `POST /api/projects/{pid}/converse` (the TEN-154 onboarding conversation) —
that's a separate, framework-free **mock** service (`services/conversation.py`), no LLM call, no
tracing. Don't confuse the two `/api/chat`-adjacent endpoints when re-verifying.

**Expected trace shape:** one trace/agent-run per `Runner.run(...)` call, agent name **"Factory
Concierge"**. Nested spans per tool call the model makes (one of the 14 tools in `make_tools()` —
e.g. `set_project_basics`, `get_intake_state`, `hand_off_to_factory`) and per model generation
(`gpt-5.4` by default, or Kimi K2.7 via OpenRouter when `SF_CHAT_MODEL=kimi` or no
`OPENAI_API_KEY`), with token usage on the generation span when the SDK returns it. **The exact
span/attribute naming is OpenInference's own convention, not something this codebase controls** —
confirm it once against a real dashboard trace and lock in the specifics as an addendum to this doc
rather than trusting this description alone.

**Known gap (found during this audit, not fixed — flagging, not silently patching):** the code
does not tag traces with `project_id` or any other session identifier. A trace is findable only by
timestamp + agent name + message content — not by which draft/project generated it. If
per-project trace correlation is ever needed, that's a follow-up (e.g. `langfuse.update_current_trace(session_id=project_id)`
inside `handle_message`/`handle_message_streamed`), out of scope here.

**Known nuance:** `self._langfuse` (the client `setup_langfuse()` returns) is stored but never
explicitly flushed anywhere in the codebase. Langfuse's SDK auto-flushes on its own interval in a
background thread, so this is fine for a long-running server — but a trace from a request
immediately preceding an abrupt process exit (crash, not a graceful deploy swap) could theoretically
be lost before it flushes. Not a "doesn't work" bug; worth knowing if a specific trace ever goes
missing right around a restart.

### Cheap re-verification recipe — run this after every console deploy

1. `POST /api/chat` with any short message (needs auth — `X-SF-Service-Token` header, or an authed
   session cookie) and note the returned `project_id` + the UTC timestamp.
2. In the Langfuse dashboard (**`us.cloud.langfuse.com`** — note the `us.` subdomain, not the
   global default), search traces around that timestamp for an agent run under **"Factory
   Concierge"** containing the sent message text.
3. Confirm: the trace exists, has at least one nested generation span with token usage populated,
   and total latency looks plausible (low single-digit seconds for a short turn).
4. If nothing appears within ~1 minute: check `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` presence
   on `factory-console` (Railway variables), check the deploy log for
   `[langfuse] concierge tracing instrumented` (confirms `setup_langfuse()` ran and both packages
   imported cleanly) vs. `keys set but tracing packages are missing` (confirms a dependency gap —
   check `langfuse`/`openinference-instrumentation-openai-agents` are still in `pyproject.toml` and
   actually made it into the deployed image), and confirm `LANGFUSE_BASE_URL` still points at the
   host you're checking (a silent host mismatch would look identical to "nothing landed").

**Live canary already fired for this audit** — use it as the first data point rather than waiting
to trigger a fresh one:
- **UTC timestamp:** `2026-07-01T07:14:24Z`
- **project_id:** `project-68c0f566b814421f`
- **Sent message:** `"SOF-25 Langfuse telemetry canary — please ignore, no action needed."`
- **Agent's reply (confirmed received):** `"Understood — no action needed."`
- Search the dashboard around that timestamp for a "Factory Concierge" trace containing that text.

## Surface 2 — Stage-run transcript tracing (spot-check only, not the canary)

**Code:** `src/software_factory/workspace_setup.py` (`_write_langfuse_hook`, gated on
`TRACE_TO_LANGFUSE == "true"` at workspace-setup time) installs the vendored, official Langfuse
Claude Code integration script (`resources/langfuse_hook.py`, from
`langfuse.com/integrations/developer-tools/claude-code`) into each stage workspace's
`.claude/hooks/`, registered as a Claude Code **Stop** hook via `.claude/settings.json`.
`src/software_factory/env.py`'s `_STAGE_ESSENTIAL` forwards `LANGFUSE_PUBLIC_KEY`,
`LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL`, and `TRACE_TO_LANGFUSE` from the console process into
every stage subprocess's env — this is a *completely separate* mechanism from Surface 1 (hand-rolled
Langfuse + raw OTel spans in the hook script, not OpenInference).

**Gate:** `TRACE_TO_LANGFUSE` must be the **exact string** `"true"` (case-sensitive, not a general
boolean parse) AND the Langfuse keys present. **Confirmed live (2026-07-01):** `TRACE_TO_LANGFUSE=true`
exactly, keys present — this surface is armed.

**Fires on:** the Claude Code CLI's "Stop" hook at the end of a stage's session — i.e. requires an
actual Stage 1/2/3 build to run (or resume) and finish a session. It reads the stage's transcript
JSONL incrementally (state-tracked in `~/.claude/state/langfuse_state.json`, so re-runs pick up only
new lines), and only emits for genuinely new turns.

**Expected trace shape (read directly from `emit_turn` in the hook — this one IS precisely
verifiable from source, unlike Surface 1):**
- Top span/trace name: **`"Claude Code - Turn {N}"`**, tagged `["claude-code"]`, grouped by the
  Claude Code session's own `session_id` (a session id, **not** the SF `project_id`).
- Metadata on that span: `source="claude-code"`, `session_id`, `turn_number`, `transcript_path`,
  `assistant_message_count`.
- Nested per assistant message: **`"Claude Generation {idx+1}"`** — `model`, `input` (user text or
  the prior tool-result batch), `output` (assistant text + any `tool_calls`), and `usage_details`
  (token counts) when the transcript line has them.
- The hook explicitly `flush()`s and `shutdown()`s the Langfuse client on exit (capped at 5s so a
  slow/unreachable Langfuse can't stall the stage) — more robust than Surface 1 in this respect;
  no reliance on background auto-flush.

**Why this is NOT the recurring canary:** triggering it for real costs real LLM spend (it only fires
from an actual factory build stage). Don't spin up a stage purely to test telemetry. Instead: spot-
check it opportunistically the next time a real stage run happens for its own reasons — search
Langfuse for a `"Claude Code - Turn"` trace around when that stage's session Stopped.

## When to re-verify (standing requirement — not one-and-done)

Re-run the **Surface 1 cheap canary** after any of:
- A deploy of `factory-console` (any change — this is genuinely cheap, so default to checking).
- Any dependency bump touching `langfuse`, `openinference-instrumentation-openai-agents`, or
  `opentelemetry-*` in `pyproject.toml`.
- Any refactor of `ChatAgentRunner.__init__` / `chat_agent.py`'s model selection.
- A Langfuse key rotation (Railway variable change) — this is exactly the class of change most
  likely to silently break emission without any code changing at all.
- A deploy-path change (e.g. SOF-16's native-git-source auto-deploy switch) — this class of change
  can silently drop env-var forwarding in ways a code review won't catch; SOF-24 (this same audit
  session) found exactly this failure mode in a different env var.

Spot-check **Surface 2** whenever a real stage run happens anyway, and always after touching
`workspace_setup.py`, `resources/langfuse_hook.py`, or `env.py`'s `_STAGE_ESSENTIAL` set.

## What's confirmed vs. what needs the operator

**Confirmed from code + live server state (this audit, no Langfuse dashboard access needed):**
- Both surfaces are wired correctly in code and armed live (all four gating vars present/correct).
- Concierge instrumentation activated successfully at boot (log evidence).
- A real, authenticated concierge turn was fired against production and returned the expected
  agent reply (proves the request path works end-to-end up to the point tracing would capture it).

**Needs the operator (Langfuse dashboard access, per the ticket's own credential boundary):**
- Confirm the live canary trace (timestamp/message above) actually **appears** in
  `us.cloud.langfuse.com`, with the expected shape (Factory Concierge run, nested generation span,
  token usage populated).
- Lock in the exact OpenInference trace/span naming observed (Surface 1's naming isn't fully
  determined by this codebase — see "Expected trace shape" above) as an addendum to this doc.
