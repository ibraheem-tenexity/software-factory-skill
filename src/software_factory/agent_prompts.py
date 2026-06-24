"""Editable agent system prompts (Tenexity OS §3.4) — `public.agent_prompts`.

Operator-editable, versioned prompts keyed by agent callsign. The main orchestrator prompts
(STAGE-1/2/3 and CONCIERGE) are applied by the live pipeline; role-agent prompts are still
stored/served for editing without being applied to spawned subagents yet.
"""
from __future__ import annotations

import os

from . import dbshim


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
        pass

    def _conn(self):
        return dbshim._pg_connect(os.environ["DATABASE_URL"])

    def get(self, callsign: str) -> dict | None:
        conn = self._conn()
        try:
            with conn.transaction():
                cur = conn.cursor()
                cur.execute(
                    "SELECT callsign, prompt, version, updated_by, "
                    "extract(epoch from updated_at) AS updated_at "
                    "FROM public.agent_prompts WHERE callsign=%s", (callsign,))
                row = cur.fetchone()
                return dict(row) if row else None
        finally:
            conn.close()

    def all(self) -> dict:
        """{callsign: {version, prompt, updated_by, updated_at}} — for the roster merge."""
        conn = self._conn()
        try:
            with conn.transaction():
                cur = conn.cursor()
                cur.execute(
                    "SELECT callsign, prompt, version, updated_by, "
                    "extract(epoch from updated_at) AS updated_at FROM public.agent_prompts")
                return {r["callsign"]: dict(r) for r in cur.fetchall()}
        finally:
            conn.close()

    def set(self, callsign: str, prompt: str, by: str = "") -> dict:
        """Upsert the prompt, bumping its version; returns the new row."""
        conn = self._conn()
        try:
            with conn.transaction():
                conn.cursor().execute(
                    "INSERT INTO public.agent_prompts (callsign, prompt, version, updated_by, "
                    "updated_at) VALUES (%s,%s,1,%s, now()) "
                    "ON CONFLICT (callsign) DO UPDATE SET prompt=EXCLUDED.prompt, "
                    "version=public.agent_prompts.version+1, updated_by=EXCLUDED.updated_by, "
                    "updated_at=now()",
                    (callsign, prompt, by))
        finally:
            conn.close()
        return self.get(callsign)

    def delete(self, callsign: str) -> None:
        """Drop a stored prompt (revert-to-default for the editable orchestrator overrides)."""
        conn = self._conn()
        try:
            with conn.transaction():
                conn.cursor().execute("DELETE FROM public.agent_prompts WHERE callsign=%s", (callsign,))
        finally:
            conn.close()
