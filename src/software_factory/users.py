"""Global user directory + roles — the DB behind console multi-tenancy.

Backed by Postgres `public.users` when SF_DB=postgres, else a sqlite file. Env
`SF_ADMIN_EMAILS` are always admins (bootstrap; seeded on init, never removable in-UI),
so an empty or unreachable directory can never lock the named operators out.

Role lookups happen on every request, so the directory is cached in-process with a short
TTL and invalidated on every write — a member's role change shows within seconds without a
DB round-trip per request.
"""
from __future__ import annotations

import os
import sqlite3
import time

from . import dbshim

_CACHE_TTL = 20.0


def _env_admins() -> list:
    return [e.strip().lower() for e in os.environ.get("SF_ADMIN_EMAILS", "").split(",") if e.strip()]


class UserStore:
    def __init__(self, sqlite_path: str):
        self._pg = (os.environ.get("SF_DB") or "").lower() == "postgres"
        self._sqlite_path = sqlite_path
        self._cache: dict | None = None
        self._cache_ts = 0.0
        self._ensure()
        for email in _env_admins():          # bootstrap admins always present
            self.upsert(email, "admin", "bootstrap")

    # -- schema -------------------------------------------------------------------------
    def _ensure(self) -> None:
        if self._pg:
            conn = dbshim._pg_connect(os.environ["DATABASE_URL"])
            try:
                with conn.transaction():
                    conn.cursor().execute(
                        "CREATE TABLE IF NOT EXISTS public.users ("
                        "email text PRIMARY KEY, role text NOT NULL DEFAULT 'member', "
                        "created_at timestamptz DEFAULT now(), created_by text)")
            finally:
                conn.close()
        else:
            os.makedirs(os.path.dirname(self._sqlite_path) or ".", exist_ok=True)
            c = sqlite3.connect(self._sqlite_path)
            c.execute("CREATE TABLE IF NOT EXISTS users (email TEXT PRIMARY KEY, "
                      "role TEXT NOT NULL DEFAULT 'member', created_at REAL, created_by TEXT)")
            c.commit(); c.close()

    # -- reads (cached) -----------------------------------------------------------------
    def _all(self) -> dict:
        now = time.time()
        if self._cache is not None and (now - self._cache_ts) < _CACHE_TTL:
            return self._cache
        rows = {}
        try:
            if self._pg:
                conn = dbshim._pg_connect(os.environ["DATABASE_URL"])
                try:
                    with conn.transaction():
                        cur = conn.cursor()
                        cur.execute("SELECT email, role, created_by, "
                                    "extract(epoch from created_at) AS created_at FROM public.users")
                        for r in cur.fetchall():
                            rows[r["email"].lower()] = dict(r)
                finally:
                    conn.close()
            else:
                c = sqlite3.connect(self._sqlite_path); c.row_factory = sqlite3.Row
                for r in c.execute("SELECT email, role, created_by, created_at FROM users"):
                    rows[r["email"].lower()] = dict(r)
                c.close()
        except Exception:
            # directory briefly unreachable — serve the last snapshot (env admins still work
            # via auth.role_for's env check, so operators are never locked out).
            return self._cache or {}
        self._cache, self._cache_ts = rows, now
        return rows

    def is_member(self, email: str) -> bool:
        return bool(email) and email.lower() in self._all()

    def get_role(self, email: str) -> str | None:
        row = self._all().get((email or "").lower())
        return row["role"] if row else None

    def list_users(self) -> list:
        return sorted(self._all().values(), key=lambda u: u["email"])

    # -- writes (invalidate cache) ------------------------------------------------------
    def upsert(self, email: str, role: str, by: str = "") -> None:
        email = email.strip().lower()
        if not email or role not in ("admin", "member"):
            return
        if self._pg:
            conn = dbshim._pg_connect(os.environ["DATABASE_URL"])
            try:
                with conn.transaction():
                    conn.cursor().execute(
                        "INSERT INTO public.users (email, role, created_by) VALUES (%s,%s,%s) "
                        "ON CONFLICT (email) DO UPDATE SET role = EXCLUDED.role", (email, role, by))
            finally:
                conn.close()
        else:
            c = sqlite3.connect(self._sqlite_path)
            c.execute("INSERT INTO users (email, role, created_at, created_by) VALUES (?,?,?,?) "
                      "ON CONFLICT(email) DO UPDATE SET role=excluded.role",
                      (email, role, time.time(), by))
            c.commit(); c.close()
        self._cache = None

    def remove(self, email: str) -> None:
        email = (email or "").strip().lower()
        if email in _env_admins():           # env-bootstrap admins are not removable in-UI
            return
        if self._pg:
            conn = dbshim._pg_connect(os.environ["DATABASE_URL"])
            try:
                with conn.transaction():
                    conn.cursor().execute("DELETE FROM public.users WHERE email = %s", (email,))
            finally:
                conn.close()
        else:
            c = sqlite3.connect(self._sqlite_path)
            c.execute("DELETE FROM users WHERE email = ?", (email,)); c.commit(); c.close()
        self._cache = None
