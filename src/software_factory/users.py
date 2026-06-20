"""Global user directory + roles + organizations — the DB behind console multi-tenancy.

Postgres (`public.users` / `public.organizations`); schema is owned by the SQLAlchemy models
(`models.py`) via Alembic. Env `SF_ADMIN_EMAILS` are always admins (bootstrap; seeded on init,
never removable in-UI), so an empty or unreachable directory can never lock the named operators out.

Role lookups happen on every request, so the directory is cached in-process with a short TTL and
invalidated on every write — a member's role change shows within seconds without a DB round-trip
per request.
"""
from __future__ import annotations

import json
import os
import time
import uuid

from . import dbshim

_CACHE_TTL = 20.0

# organizations columns that hold JSON-encoded lists (decoded on read).
_ORG_JSON_COLS = ("sub_focus", "connected_systems")
_ORG_COLS = ("id", "name", "industry", "sub_focus", "headcount", "revenue",
             "location", "website", "connected_systems", "plan", "monthly_budget_cap",
             "created_at", "created_by")
_ORG_SELECT = ("SELECT id, name, industry, sub_focus, headcount, revenue, location, website, "
               "connected_systems, plan, monthly_budget_cap, "
               "extract(epoch from created_at) AS created_at, created_by "
               "FROM public.organizations")


def _env_admins() -> list:
    return [e.strip().lower() for e in os.environ.get("SF_ADMIN_EMAILS", "").split(",") if e.strip()]


class UserStore:
    def __init__(self):
        self._cache: dict | None = None
        self._cache_ts = 0.0
        for email in _env_admins():          # bootstrap admins always present
            self.upsert(email, "admin", "bootstrap")

    # -- pg helpers ---------------------------------------------------------------------
    def _exec(self, sql: str, params: tuple = ()) -> None:
        conn = dbshim._pg_connect(os.environ["DATABASE_URL"])
        try:
            with conn.transaction():
                conn.cursor().execute(sql.replace("?", "%s"), params)
        finally:
            conn.close()

    def _query(self, sql: str, params: tuple = ()) -> list:
        conn = dbshim._pg_connect(os.environ["DATABASE_URL"])
        try:
            with conn.transaction():
                cur = conn.cursor()
                cur.execute(sql.replace("?", "%s"), params)
                return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    # -- reads (cached) -----------------------------------------------------------------
    def _all(self) -> dict:
        now = time.time()
        if self._cache is not None and (now - self._cache_ts) < _CACHE_TTL:
            return self._cache
        try:
            rows = {
                r["email"].lower(): r for r in self._query(
                    "SELECT email, role, created_by, org_id, designation, role_description, "
                    "tenexity, status, extract(epoch from created_at) AS created_at "
                    "FROM public.users")
            }
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
        self._exec("INSERT INTO public.users (email, role, created_by) VALUES (?,?,?) "
                   "ON CONFLICT (email) DO UPDATE SET role = EXCLUDED.role", (email, role, by))
        self._cache = None

    def remove(self, email: str) -> None:
        email = (email or "").strip().lower()
        if email in _env_admins():           # env-bootstrap admins are not removable in-UI
            return
        self._exec("DELETE FROM public.users WHERE email = ?", (email,))
        self._cache = None

    def set_status(self, email: str, status: str) -> None:
        """Sign-in allow-list status (Tenexity OS §3.6): 'invited' on invite, 'active' on first login."""
        email = (email or "").strip().lower()
        if not email or status not in ("active", "invited"):
            return
        self._exec("UPDATE public.users SET status = ? WHERE email = ?", (status, email))
        self._cache = None

    def mark_active(self, email: str) -> None:
        """Flip an invited user to active — called on first successful sign-in."""
        email = (email or "").strip().lower()
        row = self._all().get(email)
        if row and row.get("status") == "invited":
            self.set_status(email, "active")

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
        self._exec(f"UPDATE public.users SET {', '.join(sets)} WHERE email=?", tuple(vals))
        self._cache = None

    # -- organizations ------------------------------------------------------------------
    def create_org(self, name: str, *, industry: str | None = None, sub_focus=None,
                   headcount: str | None = None, revenue: str | None = None,
                   location: str | None = None, website: str | None = None,
                   connected_systems=None, by: str = "", org_id: str | None = None) -> str:
        """Insert an organization, returning its id (generated `org-<hex8>` unless given)."""
        oid = org_id or ("org-" + uuid.uuid4().hex[:8])
        self._exec(
            "INSERT INTO public.organizations (id, name, industry, sub_focus, headcount, revenue, "
            "location, website, connected_systems, created_by) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (oid, name, industry, json.dumps(sub_focus or []), headcount, revenue, location,
             website, json.dumps(connected_systems or []), by))
        return oid

    def get_org(self, org_id: str) -> dict | None:
        if not org_id:
            return None
        rows = self._query(_ORG_SELECT + " WHERE id=?", (org_id,))
        return self._decode_org(rows[0]) if rows else None

    def list_orgs(self) -> list:
        return [self._decode_org(r) for r in self._query(_ORG_SELECT + " ORDER BY name")]

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
        self._exec(f"UPDATE public.organizations SET {', '.join(sets)} WHERE id=?", tuple(vals))

    def delete_org(self, org_id: str) -> None:
        """Delete an org and unlink its members (their rows survive, org_id cleared)."""
        if not org_id:
            return
        self._exec("UPDATE public.users SET org_id = NULL WHERE org_id = ?", (org_id,))
        self._exec("DELETE FROM public.organizations WHERE id = ?", (org_id,))
        self._cache = None

    def org_for_user(self, email: str) -> dict | None:
        u = self.get_user(email)
        return self.get_org(u["org_id"]) if u and u.get("org_id") else None

    def list_org_members(self, org_id: str) -> list:
        """Users linked to this org (Team & access), ordered by email."""
        if not org_id:
            return []
        return sorted((u for u in self._all().values() if u.get("org_id") == org_id),
                      key=lambda u: u["email"])

    def invite_member(self, email: str, org_id: str, *, role: str = "member",
                      designation: str | None = None, by: str = "") -> None:
        """Add (or re-link) a user to an org with a role — the Team & access invite."""
        email = (email or "").strip().lower()
        if not email or not org_id:
            return
        self.upsert(email, role if role in ("admin", "member") else "member", by)
        self.set_profile(email, org_id=org_id, designation=designation)

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
