"""DB-backed Concierge prompt resolution plus code-owned context composition."""
from __future__ import annotations

import logging
import time
from typing import Callable

from software_factory.constants import (
    CONCIERGE_CONTEXTS,
    CONCIERGE_PROMPT_CACHE_TTL_SECONDS,
)

logger = logging.getLogger(__name__)

# SOF-154: the intake-only streamed-reply format override. Lives HERE (per-context framing), never
# in the base concierge instructions (the DB-sourced CONCIERGE.prompt) — "intake" is the ONLY
# context that ever constructs its ChatAgent with use_tagged_output=True (services/conversation.py); the dock
# (console/chat_dock.py) only ever uses "overview"/"build" and stays on ToolStrategy(ConciergeTurn)
# unchanged. Telling the dock's agent to emit these tags AND forcing structured-output JSON on it
# would be a broken, contradictory instruction — keeping this scoped to one context string is what
# prevents that.
_TAGGED_REPLY_FORMAT = (
    "\n\n## Reply format override\nIgnore the 'reply is the structured ConciergeTurn' instruction "
    "above — for this session, your final user-facing reply is PLAIN TEXT using these tags instead:\n"
    '  <say>your prose here</say>\n'
    '  <option type="single">a pick-one choice</option>\n'
    '  <option type="multi">a pick-many choice</option>\n'
    "Wrap your whole utterance in exactly one <say>...</say>. Offer each choice as its own "
    '<option> tag right after it — type="single" for pick-one (radios), type="multi" for '
    "pick-many (checkboxes); omit <option> tags entirely for a plain free-text turn. Your final "
    "reply MUST begin with <say> and nothing before it — no preamble, no markdown fence, nothing. "
    "This format applies ONLY to your final user-facing answer — call your tools exactly as "
    "before, with no tags involved in a tool call."
)

# Per-context framing appended to the base prompt. Same identity/voice; only the focus changes.
_CONTEXT_FRAMING = {
    "intake": "You are running first-time project intake — capture the company (first-time users "
              "only) and then this project, saving durable facts as you go." + _TAGGED_REPLY_FORMAT,
    "overview": "You are answering questions about an existing project and what is known about it.",
    "build": "The project is building — report progress accurately and help unblock any dependencies.",
    "docs": "You are helping the user understand their ingested documents and what you learned from them.",
    "ingesting": "Documents are being ingested right now — set expectations and answer from what is "
                 "available so far.",
}


class _ConciergePromptCache:
    """The concierge system prompt comes SOLELY from the DB (`system_agents` CONCIERGE.prompt) —
    there is NO code default. A short in-process cache avoids a DB read every turn; on a DB *error*
    it keeps serving the last-known-good DB prompt loaded this process, but it NEVER fabricates a
    hardcoded fallback: an absent/blank row raises, and a DB error with no cache re-raises."""

    def __init__(self, ttl_seconds: float, clock: Callable[[], float] = time.monotonic):
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._prompt: str | None = None  # last-known-good DB prompt this process; None until loaded
        self._expires_at = 0.0

    def get(self) -> str:
        now = self._clock()
        if self._prompt is not None and now < self._expires_at:
            return self._prompt
        try:
            # Deferred import: SystemAgentStore touches the DB, so importing it at module load would
            # couple this prompt module to a live connection (kept function-local on purpose).
            from software_factory.system_agents import SystemAgentStore
            row = SystemAgentStore().get("CONCIERGE")
        except Exception:
            # DB error (e.g. connection blip): keep serving the last-known-good DB prompt if one has
            # loaded this process — but NEVER fall back to a hardcoded prompt. With no cache, re-raise.
            logger.exception("[default_prompt] failed to read CONCIERGE prompt from system_agents")
            if self._prompt is not None:
                return self._prompt
            raise
        prompt = (row.get("prompt") if row else "") or ""
        if not prompt.strip():
            raise RuntimeError(
                "No CONCIERGE prompt configured in system_agents — the DB is the sole source; "
                "seed/set it via the Agents screen")
        self._prompt = prompt
        self._expires_at = now + self._ttl_seconds
        return self._prompt

    def reset(self) -> None:
        self._prompt = None
        self._expires_at = 0.0


_CONCIERGE_PROMPT_CACHE = _ConciergePromptCache(CONCIERGE_PROMPT_CACHE_TTL_SECONDS)


def resolve_concierge_instructions() -> str:
    """The concierge system prompt from the DB (`system_agents` CONCIERGE.prompt), short-cached.
    Raises if no CONCIERGE row exists or its prompt is empty — the DB is the sole source, there is
    no code default."""
    return _CONCIERGE_PROMPT_CACHE.get()


def reset_concierge_prompt_cache() -> None:
    """Test/maintenance hook: force the next prompt resolve to hit SystemAgentStore."""
    _CONCIERGE_PROMPT_CACHE.reset()


def build_system_prompt(context: str = "intake", first_turn_context: str | None = None) -> str:
    """The base concierge prompt framed for `context` — one identity, focus set per session.

    `first_turn_context` (SOF-62) is the server-assembled project-context block — the user's own
    input, the selected recipe body, document summaries, and existing per-document assumptions —
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
