# Langfuse telemetry — current surfaces + re-verification (SOF-25)

**Purpose:** a cheap, repeatable way to confirm the console's Langfuse telemetry is actually
landing, not just configured. Telemetry can break silently (a dependency bump, a refactor, a key
rotation, a deploy-path change) and nothing else will tell you.

> **2026-07 — this doc was rewritten.** The original baseline documented a "Surface 1" concierge
> live-agent canary built on the OpenAI Agents SDK (`OpenAIAgentsInstrumentor`, `Runner.run`, a
> "Factory Concierge" trace). **That surface no longer exists.** `setup_langfuse()` and the
> `ChatAgentRunner` it instrumented were removed in SOF-35 when the concierge was rebuilt on
> LangChain (`chat_agent.py`). The LangChain concierge has **no Langfuse tracing wired yet** — that
> would be new work (e.g. an OpenInference LangChain instrumentor), not a port. Do not go looking
> for a "Factory Concierge" trace; its absence is expected, not a regression. The stale historical
> canary logs (specific 2026-07-01 project ids / dashboard pulls) were dropped.

`src/software_factory/langfuse_tracing.py` is now just `enabled()` — `bool(LANGFUSE_PUBLIC_KEY and
LANGFUSE_SECRET_KEY)` — the single gate every surviving surface shares.

## Surface A — Stage-run transcript tracing

**Code:** `src/software_factory/workspace_setup.py` (`_write_langfuse_hook`) installs the vendored,
official Langfuse Claude Code integration script (`resources/langfuse_hook.py`, from
`langfuse.com/integrations/developer-tools/claude-code`) into each stage workspace's
`.claude/hooks/`, registered as a Claude Code **Stop** hook via `.claude/settings.json`.

**Gate:** `langfuse_tracing.enabled()` — i.e. both Langfuse keys present. Tracing is **default-on
when keys exist**; there is no longer a `TRACE_TO_LANGFUSE` toggle (removed). `env.py`'s
`_STAGE_ESSENTIAL` forwards `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_BASE_URL`
from the console process into every stage subprocess's env; the hook itself re-checks the keys at
runtime and silently skips if absent. `.claude/` is gitignored in the workspace so the hook and any
env-injected secrets never reach the customer's app repo.

**Fires on:** the Claude Code CLI's Stop hook at the end of a stage's session — i.e. it requires an
actual Stage 1/2/3 build to run (or resume) and finish a session. It reads the stage's transcript
JSONL incrementally (state-tracked in `~/.claude/state/langfuse_state.json`), emitting only new
turns.

**Expected trace shape** (defined entirely by `resources/langfuse_hook.py`'s `emit_turn` — verify
from that source, it is not something the console controls):
- Top span/trace name **`"Claude Code - Turn {N}"`**, tagged `["claude-code"]`, grouped by the
  Claude Code session's own `session_id` (**not** the SF `project_id`).
- Nested per assistant message: **`"Claude Generation {idx+1}"`** — `model`, `input`, `output`
  (assistant text + any `tool_calls`), and `usage_details` when the transcript line carries them.
- The hook `flush()`s + `shutdown()`s the Langfuse client on exit (capped at 5s so a slow/unreachable
  Langfuse can't stall the stage).

**Why this is NOT a cheap canary:** triggering it for real costs real LLM spend (it only fires from
an actual factory build stage). Spot-check it opportunistically the next time a real stage run
happens — search Langfuse for a `"Claude Code - Turn"` trace around when that session Stopped.

## Surface B — Ingestion-cost spans

**Code:** `src/software_factory/memory/cost.py` (`_emit_langfuse_span`) records a Langfuse span per
document-ingestion embedding batch (raw `openai` SDK calls to OpenRouter, not the Agents SDK), gated
on the same `langfuse_tracing.enabled()`. This is the cost-accounting channel for Project Memory
ingestion, independent of any agent tracing.

## When to re-verify (standing requirement — SOF-25)

- After any deploy of the console (Surface A env forwarding can silently break).
- After any dependency bump touching `langfuse` / `opentelemetry-*` in `pyproject.toml`.
- After touching `workspace_setup.py`, `resources/langfuse_hook.py`, `env.py`'s `_STAGE_ESSENTIAL`,
  or `memory/cost.py`.
- After a Langfuse key rotation (Railway variable change) — the class of change most likely to
  silently break emission with no code change.
- After a deploy-path change (e.g. a native-git-source auto-deploy switch) — can silently drop
  env-var forwarding in ways code review won't catch.

Dashboard verification needs the operator's Langfuse access (keys live in Railway); the console
audits only that the surfaces are wired and the gate vars are present.
