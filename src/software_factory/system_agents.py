"""System agents store (Tenexity OS §3.4) — `public.system_agents`.

The operator-configurable agents shown and edited in Tenexity OS: the Concierge + the three skill
stages (CONCIERGE / STAGE-1 / STAGE-2 / STAGE-3). One row per agent carries its editable `prompt`
AND the LLM (`model_id`) it runs on. This store is the ONLY source for what the OS shows/edits —
nothing is seeded from code; the frontend shows only DB rows. Merges the former agent_registry
(identity) + agent_prompts (prompt) into one place.

DATA ACCESS: all SQL lives in `repositories.system_agents.SystemAgentRepository`.
"""
from __future__ import annotations

from .repositories._exec import GlobalExec
from .repositories.system_agents import SystemAgentRepository


class SystemAgentStore:
    def __init__(self, repo: SystemAgentRepository | None = None):
        self._repo = repo if repo is not None else SystemAgentRepository(GlobalExec())

    def get(self, callsign: str) -> dict | None:
        row = self._repo.by_callsign(callsign)
        return dict(row) if row else None

    def all(self) -> list[dict]:
        """All rows ordered by callsign — {callsign, name, prompt, model_id, version, updated_by,
        updated_at}. Pure read; no seeding."""
        return [dict(r) for r in self._repo.all()]

    def set(self, callsign: str, *, name=None, prompt=None, model_id=None, by: str = "") -> dict | None:
        """Upsert prompt and/or model_id (and/or name), bumping version; returns the new row.
        Only the fields passed are changed — the others keep their current value."""
        self._repo.upsert(callsign, name=name, prompt=prompt, model_id=model_id, by=by)
        return self.get(callsign)

    def delete(self, callsign: str) -> None:
        self._repo.delete(callsign)
