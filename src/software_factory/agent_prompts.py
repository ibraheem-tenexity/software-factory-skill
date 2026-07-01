"""Editable agent system prompts (Tenexity OS §3.4) — `public.agent_prompts`.

Operator-editable, versioned prompts keyed by agent callsign. The main orchestrator prompts
(STAGE-1/2/3 and CONCIERGE) are applied by the live pipeline; role-agent prompts are still
stored/served for editing without being applied to spawned subagents yet.

DATA ACCESS: all SQL lives in `repositories.agent_prompts.AgentPromptRepository`.
"""
from __future__ import annotations

from .repositories._exec import GlobalExec
from .repositories.agent_prompts import AgentPromptRepository


def override_key(callsign: str, runtime: str | None = None) -> str:
    """Composite PromptStore key for the EDITABLE orchestrator prompts (the override that drives runs).
    Single source of truth shared by the OS Agents API and the pipeline:
      • stage skills are PER-RUNTIME → "STAGE-1::claude" / "STAGE-1::opencode" (the claude & opencode
        SKILL.md variants are framed differently and must never cross over);
      • the concierge is single → "CONCIERGE".
    Distinct from role-agent callsigns (ATLAS/…) so override rows never collide with role-prompt rows."""
    cs = (callsign or "").upper()
    return f"{cs}::{runtime}" if runtime and cs.startswith("STAGE-") else cs


class PromptStore:
    def __init__(self):
        self._repo = AgentPromptRepository(GlobalExec())

    def get(self, callsign: str) -> dict | None:
        row = self._repo.by_callsign(callsign)
        return dict(row) if row else None

    def all(self) -> dict:
        """{callsign: {version, prompt, updated_by, updated_at}} — for the roster merge."""
        return {r["callsign"]: dict(r) for r in self._repo.all()}

    def set(self, callsign: str, prompt: str, by: str = "") -> dict:
        """Upsert the prompt, bumping its version; returns the new row."""
        self._repo.upsert(callsign, prompt, by)
        return self.get(callsign)

    def delete(self, callsign: str) -> None:
        """Drop a stored prompt (revert-to-default for the editable orchestrator overrides)."""
        self._repo.delete(callsign)
