"""Global user directory + roles — the DB behind console multi-tenancy.

Backed by Postgres `public.users` when SF_DB=postgres, else a sqlite file. Env
`SF_ADMIN_EMAILS` are always admins (bootstrap; seeded on init, never removable in-UI),
so an empty or unreachable directory can never lock the named operators out.

Role lookups happen on every request, so the directory is cached in-process with a short
TTL and invalidated on every write — a member's role change shows within seconds without a
DB round-trip per request.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid

from . import dbshim

_CACHE_TTL = 20.0

# Columns added to `users` beyond the original (email, role, created_at, created_by) for the
# org/onboarding model. org_id links a user to their organization; designation/role_description
# are the user's self-described job; tenexity flags Tenexity staff (cross-org admin panel access).
_USER_EXTRA_COLS = (
    ("org_id", "text"),
    ("designation", "text"),
    ("role_description", "text"),
    ("tenexity", "integer"),
)

# organizations columns that hold JSON-encoded lists (decoded on read).
_ORG_JSON_COLS = ("sub_focus", "connected_systems")
_ORG_COLS = ("id", "name", "industry", "sub_focus", "headcount", "revenue",
             "location", "website", "connected_systems", "created_at", "created_by")


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
                    cur = conn.cursor()
                    cur.execute(
                        "CREATE TABLE IF NOT EXISTS public.users ("
                        "email text PRIMARY KEY, role text NOT NULL DEFAULT 'member', "
                        "created_at timestamptz DEFAULT now(), created_by text)")
                    for col, typ in _USER_EXTRA_COLS:
                        cur.execute(f"ALTER TABLE public.users ADD COLUMN IF NOT EXISTS {col} {typ}")
                    cur.execute(
                        "CREATE TABLE IF NOT EXISTS public.organizations ("
                        "id text PRIMARY KEY, name text NOT NULL, industry text, sub_focus text, "
                        "headcount text, revenue text, location text, website text, "
                        "connected_systems text, created_at timestamptz DEFAULT now(), created_by text)")
            finally:
                conn.close()
        else:
            os.makedirs(os.path.dirname(self._sqlite_path) or ".", exist_ok=True)
            c = sqlite3.connect(self._sqlite_path)
            c.execute("CREATE TABLE IF NOT EXISTS users (email TEXT PRIMARY KEY, "
                      "role TEXT NOT NULL DEFAULT 'member', created_at REAL, created_by TEXT)")
            for col, typ in _USER_EXTRA_COLS:
                try:
                    c.execute(f"ALTER TABLE users ADD COLUMN {col} {typ.upper()}")
                except sqlite3.OperationalError:
                    pass  # column already present
            c.execute("CREATE TABLE IF NOT EXISTS organizations (id TEXT PRIMARY KEY, name TEXT NOT NULL, "
                      "industry TEXT, sub_focus TEXT, headcount TEXT, revenue TEXT, location TEXT, "
                      "website TEXT, connected_systems TEXT, created_at REAL, created_by TEXT)")
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
                        cur.execute("SELECT email, role, created_by, org_id, designation, "
                                    "role_description, tenexity, "
                                    "extract(epoch from created_at) AS created_at FROM public.users")
                        for r in cur.fetchall():
                            rows[r["email"].lower()] = dict(r)
                finally:
                    conn.close()
            else:
                c = sqlite3.connect(self._sqlite_path); c.row_factory = sqlite3.Row
                for r in c.execute("SELECT email, role, created_by, org_id, designation, "
                                   "role_description, tenexity, created_at FROM users"):
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

    # -- write helper (one statement, pg or sqlite) -------------------------------------
    def _write(self, sql: str, params: tuple) -> None:
        if self._pg:
            conn = dbshim._pg_connect(os.environ["DATABASE_URL"])
            try:
                with conn.transaction():
                    conn.cursor().execute(sql.replace("?", "%s"), params)
            finally:
                conn.close()
        else:
            c = sqlite3.connect(self._sqlite_path)
            c.execute(sql, params); c.commit(); c.close()

    # -- user profile (org link + self-described role) ----------------------------------
    def get_user(self, email: str) -> dict | None:
        """Full user row (role + org_id + designation + role_description + tenexity), or None."""
        return self._all().get((email or "").strip().lower())

    def set_profile(self, email: str, *, org_id: str | None = None, designation: str | None = None,
                    role_description: str | None = None, tenexity: bool | None = None) -> None:
        """Update the onboarding profile fields on an existing user (creates a member row if the
        email is unknown). Only the fields passed (non-None) are written."""
        email = (email or "").strip().lower()
        if not email:
            return
        if not self.is_member(email):
            self.upsert(email, "member")
        sets, vals = [], []
        for col, val in (("org_id", org_id), ("designation", designation),
                         ("role_description", role_description)):
            if val is not None:
                sets.append(f"{col}=?"); vals.append(val)
        if tenexity is not None:
            sets.append("tenexity=?"); vals.append(1 if tenexity else 0)
        if not sets:
            return
        vals.append(email)
        self._write(f"UPDATE users SET {', '.join(sets)} WHERE email=?", tuple(vals))
        self._cache = None

    # -- organizations ------------------------------------------------------------------
    def create_org(self, name: str, *, industry: str | None = None, sub_focus=None,
                   headcount: str | None = None, revenue: str | None = None,
                   location: str | None = None, website: str | None = None,
                   connected_systems=None, by: str = "", org_id: str | None = None) -> str:
        """Insert an organization, returning its id (generated `org-<hex8>` unless given)."""
        oid = org_id or ("org-" + uuid.uuid4().hex[:8])
        self._write(
            "INSERT INTO organizations (id, name, industry, sub_focus, headcount, revenue, "
            "location, website, connected_systems, created_at, created_by) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (oid, name, industry, json.dumps(sub_focus or []), headcount, revenue, location,
             website, json.dumps(connected_systems or []), time.time(), by))
        return oid

    def get_org(self, org_id: str) -> dict | None:
        if not org_id:
            return None
        sql = ("SELECT id, name, industry, sub_focus, headcount, revenue, location, website, "
               "connected_systems, extract(epoch from created_at) AS created_at, created_by "
               "FROM public.organizations WHERE id=%s") if self._pg else (
               "SELECT id, name, industry, sub_focus, headcount, revenue, location, website, "
               "connected_systems, created_at, created_by FROM organizations WHERE id=?")
        row = self._query_one(sql, (org_id,))
        return self._decode_org(row) if row else None

    def list_orgs(self) -> list:
        sql = ("SELECT id, name, industry, sub_focus, headcount, revenue, location, website, "
               "connected_systems, extract(epoch from created_at) AS created_at, created_by "
               "FROM public.organizations ORDER BY name") if self._pg else (
               "SELECT id, name, industry, sub_focus, headcount, revenue, location, website, "
               "connected_systems, created_at, created_by FROM organizations ORDER BY name")
        return [self._decode_org(r) for r in self._query_all(sql, ())]

    def update_org(self, org_id: str, **fields) -> None:
        """Patch the provided org columns (json-encoding sub_focus/connected_systems)."""
        cols = [c for c in _ORG_COLS if c not in ("id", "created_at", "created_by")]
        sets, vals = [], []
        for col in cols:
            if col in fields and fields[col] is not None:
                v = json.dumps(fields[col]) if col in _ORG_JSON_COLS else fields[col]
                sets.append(f"{col}=?"); vals.append(v)
        if not sets:
            return
        vals.append(org_id)
        self._write(f"UPDATE organizations SET {', '.join(sets)} WHERE id=?", tuple(vals))

    def org_for_user(self, email: str) -> dict | None:
        u = self.get_user(email)
        return self.get_org(u["org_id"]) if u and u.get("org_id") else None

    @staticmethod
    def _decode_org(row: dict) -> dict:
        d = dict(row)
        for col in _ORG_JSON_COLS:
            raw = d.get(col)
            try:
                d[col] = json.loads(raw) if raw else []
            except (TypeError, ValueError):
                d[col] = []
        return d

    def _query_one(self, sql: str, params: tuple):
        rows = self._query_all(sql, params)
        return rows[0] if rows else None

    def _query_all(self, sql: str, params: tuple) -> list:
        if self._pg:
            conn = dbshim._pg_connect(os.environ["DATABASE_URL"])
            try:
                with conn.transaction():
                    cur = conn.cursor()
                    cur.execute(sql, params)
                    return [dict(r) for r in cur.fetchall()]
            finally:
                conn.close()
        c = sqlite3.connect(self._sqlite_path); c.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in c.execute(sql, params).fetchall()]
        finally:
            c.close()
