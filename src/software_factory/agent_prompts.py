"""Editable agent system prompts (Tenexity OS §3.4) — `public.agent_prompts`.

Operator-editable, versioned prompts keyed by agent callsign. NOTE: the live pipeline does NOT read
these yet (it still builds prompts in code) — storing/serving here is decoupled from applying them;
wiring is a follow-up. Callers/UI should present a saved prompt as "saved, not yet applied".
"""
from __future__ import annotations

import os

from . import dbshim


class PromptStore:
    def __init__(self, sqlite_path: str = ""):
        # `sqlite_path` is vestigial (Postgres everywhere); kept for call-site symmetry.
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
