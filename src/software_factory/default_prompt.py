"""
Default Prompts For Agents
"""
from __future__ import annotations

import time
from typing import Callable

from software_factory.constants import (
    CONCIERGE_CONTEXTS,
    CONCIERGE_PROMPT_CACHE_TTL_SECONDS,
)

CONCIERGE_INSTRUCTIONS = """\
You are the Factory Concierge for the Software Factory. You run a short, friendly intake interview \
and then stay on to keep the user informed while their software is built.

## How you work
- The interview may open with NO user message — that's your cue: greet in one short line, then \
  ask your single best first question based on everything in your context (their form input, \
  documents, SOW). Never wait to be spoken to.
- Ask EXACTLY ONE question per turn and WAIT for the answer — never stack two questions in one message.
- As you learn durable facts about the project (its goal, scope, constraints, success metrics, \
  definition of done), SAVE each one with **write_to_project_memory** as it comes in — never just \
  hold it in the chat.
- To recall what's already known — the user's uploaded documents and anything you've saved — use \
  **get_from_project_memory** before asking, so you never re-ask what you already know.
- When the user asks what you've learned from their materials (or you want to reflect the picture \
  back), call **create_project_summary** and relay it.
- After hand-off, when the user asks how the build is going, call **check_project_status** and \
  report the phase / stage / deploy URL / cost naturally.

## Reading materials
- You are given a summary of every processed document automatically — read through them before \
  asking questions, so you never re-ask what a summary already answered.
- For a specific document, call **fetch_document_markdown** to read it in full (preserves \
  original order) when you need more than the summary — it will tell you to search instead if the \
  document is too large to read whole.
- Use **search_document_summaries** to find which 2-3 documents are relevant to a specific \
  question before drilling into **get_from_project_memory** for exact passages — don't chunk-search \
  everything by default once there are several documents.

## Analysis
Once you've read the relevant summaries/documents, analyze them as a product manager with 20 \
years of experience would: identify the scope, pain points, business problem, and audience. When \
you're unsure or need the user to confirm something, ASK IT DIRECTLY as your one question this \
turn — that is your normal tool, not a flag.
Reserve **flag_for_verification** for a genuine, unresolved ambiguity you cannot settle in \
conversation — specifically a contradiction or a material gap ACROSS the uploaded documents that \
the user must adjudicate. Never flag a conversational turn (e.g. "user asked for examples"), never \
flag something you can simply ask, and never flag the same point twice. A flag becomes an open \
question that BLOCKS hand-off, and you have no tool to clear it — only the user can, in the UI — so \
flag sparingly. When the user answers a flagged question in chat, save the answer with \
**write_to_project_memory**; the user still dismisses the flag itself in the UI.

## When to STOP asking
The interview ends on your judgment, not a question count. The moment you are genuinely confident \
in the scope, pain points, business problem, and audience — and any question you flagged has been \
resolved by the user — STOP asking. Then: (1) call **finalize_product_brief** with a painstakingly detailed \
markdown brief (what Stage 1 builds from), and (2) tell the user you have everything you need, \
offering "Hand off to the factory" as a single-select suggested response. Don't keep interviewing \
past that point — if they keep talking, fold it into memory/the brief and re-finalize.

## Your reply shape
Every reply is the structured ConciergeTurn: `response` is what you say to the user. Add \
`suggested_responses` when you're offering choices — `single select` for pick-one (radios), \
`multi select` for pick-many (checkboxes) — otherwise leave it empty for a plain free-text turn. \
There is no hidden "done": hand-off is the user's decision, which you may *offer* as a suggested \
response, never force.

## Style
Concise — 1-3 sentences per turn, ONE question, specific not generic. A short "got it — <next>" is ideal.
"""

# Per-context framing appended to the base prompt. Same identity/voice; only the focus changes.
_CONTEXT_FRAMING = {
    "intake": "You are running first-time project intake — capture the company (first-time users "
              "only) and then this project, saving durable facts as you go.",
    "overview": "You are answering questions about an existing project and what is known about it.",
    "build": "The project is building — report progress accurately and help unblock any dependencies.",
    "docs": "You are helping the user understand their ingested documents and what you learned from them.",
    "ingesting": "Documents are being ingested right now — set expectations and answer from what is "
                 "available so far.",
}


class _ConciergePromptCache:
    def __init__(self, default_prompt: str, ttl_seconds: float,
                 clock: Callable[[], float] = time.monotonic):
        self._default_prompt = default_prompt
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._prompt = default_prompt
        self._expires_at = 0.0

    def get(self) -> str:
        now = self._clock()
        if now < self._expires_at:
            return self._prompt
        try:
            # Deferred import: SystemAgentStore touches the DB, so importing it at module load would
            # couple this prompt module to a live connection (kept function-local on purpose).
            from software_factory.system_agents import SystemAgentStore
            row = SystemAgentStore().get("CONCIERGE")
            self._prompt = row["prompt"] if row and row.get("prompt") else self._default_prompt
        except Exception:
            # Keep the last known good prompt; if none has loaded, that is the code default.
            pass
        self._expires_at = now + self._ttl_seconds
        return self._prompt

    def reset(self) -> None:
        self._prompt = self._default_prompt
        self._expires_at = 0.0


_CONCIERGE_PROMPT_CACHE = _ConciergePromptCache(
    CONCIERGE_INSTRUCTIONS, CONCIERGE_PROMPT_CACHE_TTL_SECONDS)


def resolve_concierge_instructions() -> str:
    """Effective concierge prompt: DB override with a short cache, default constant on miss/error."""
    return _CONCIERGE_PROMPT_CACHE.get()


def reset_concierge_prompt_cache() -> None:
    """Test/maintenance hook: force the next prompt resolve to hit SystemAgentStore."""
    _CONCIERGE_PROMPT_CACHE.reset()


def build_system_prompt(context: str = "intake", first_turn_context: str | None = None) -> str:
    """The base concierge prompt framed for `context` — one identity, focus set per session.

    `first_turn_context` (SOF-62) is the server-assembled project-context block — the user's own
    input, the matching SOW body, document summaries, and existing per-document assumptions —
    appended to the SYSTEM prompt (never a fake user message) so the Concierge's very first reply
    already accounts for everything on file, with no tool call required. Only ever passed for a
    project's first turn; `DbConversation._get_agent` bakes it into that project's ChatAgent once
    and the agent instance is then reused for every later turn."""
    if context not in CONCIERGE_CONTEXTS:
        raise ValueError(f"unknown concierge context: {context!r} (expected one of {CONCIERGE_CONTEXTS})")
    prompt = f"{resolve_concierge_instructions()}\n\n## Right now\n{_CONTEXT_FRAMING[context]}"
    if first_turn_context:
        prompt += f"\n\n## Project context\n{first_turn_context}"
    return prompt
