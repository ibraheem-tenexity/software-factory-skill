"""Global user directory + RBAC roles + organizations — the DB behind console multi-tenancy.

Postgres (`public.users` / `public.roles` / `public.role_permissions` / `public.organizations`);
schema is owned by the SQLAlchemy models (`models.py`) via Alembic. This table is the SINGLE source
of truth for "who can access the platform" — there is no env allowlist any more. Cold-start is solved
by `SF_BOOTSTRAP_ADMIN_EMAIL`: the one email allowed to live in env, seeded once as an admin so the
first invite can be sent from the Team & access screen. After that, all access is managed in the table.

Lifecycle of a row: invited (on the allowlist, never signed in) → active (completed first Google
sign-in; `google_sub`/`onboarded_at` set) → disabled (revoked). Identity matches on `email` before the
first sign-in and on the stable `google_sub` after. Role is resolved per request from `role_id`→roles,
never carried in the session cookie, so a demotion/disable takes effect on the very next request.

Role lookups happen on every request, so the directory is cached in-process with a short TTL and
invalidated on every write — a status/role/token_version change shows within seconds (and immediately
for changes made through this process) without a DB round-trip per request.
"""
from __future__ import annotations

import json
import os
import time
import uuid

from . import dbshim

_CACHE_TTL = 20.0

# The full user row the console reads — role resolved to its NAME via the roles join; uuid columns
# surfaced as plain strings (clean for JSON responses and the session cookie).
_USER_SELECT = (
    "SELECT u.id::text AS id, u.google_sub, u.email, r.name AS role, "
    "u.is_internal, u.status, u.token_version, u.org_id, u.designation, u.role_description, "
    "extract(epoch from u.created_at) AS created_at, "
    "extract(epoch from u.onboarded_at) AS onboarded_at "
    "FROM public.users u JOIN public.roles r ON r.id = u.role_id")

# organizations columns that hold JSON-encoded lists (decoded on read).
_ORG_JSON_COLS = ("sub_focus", "connected_systems")
_ORG_COLS = ("id", "name", "industry", "sub_focus", "headcount", "revenue",
             "location", "website", "connected_systems", "plan", "monthly_budget_cap",
             "created_at", "created_by")
_ORG_SELECT = ("SELECT id, name, industry, sub_focus, headcount, revenue, location, website, "
               "connected_systems, plan, monthly_budget_cap, "
               "extract(epoch from created_at) AS created_at, created_by "
               "FROM public.organizations")


def _bootstrap_admin_email() -> str:
    return (os.environ.get("SF_BOOTSTRAP_ADMIN_EMAIL", "") or "").strip().lower()


class UserStore:
    def __init__(self):
        self._cache: dict | None = None
        self._cache_ts = 0.0
        self._roles: dict | None = None        # {role name -> id} cache
        try:
            self._ensure_roles()                # seed admin/member (covers create_all test DBs)
            self.ensure_bootstrap_admin()       # cold-start: the one env-seeded admin
        except Exception:
            # DB briefly unreachable at boot — the migration already seeded roles in prod, and the
            # next write will retry. Never block startup on the directory.
            pass

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

    # -- roles (RBAC) -------------------------------------------------------------------
    def _ensure_roles(self) -> None:
        """Seed the two baseline roles if absent. The migration seeds them in prod; this covers a
        fresh `create_all` test DB (which builds tables but runs no migration data step)."""
        for name, desc in (("admin", "Full administrative access"),
                           ("member", "Standard member access")):
            self._exec("INSERT INTO public.roles (id, name, description) VALUES (?::uuid, ?, ?) "
                       "ON CONFLICT (name) DO NOTHING", (str(uuid.uuid4()), name, desc))
        self._roles = None

    def _roles_map(self) -> dict:
        if self._roles is None:
            self._roles = {r["name"]: r["id"] for r in
                           self._query("SELECT id::text AS id, name FROM public.roles")}
        return self._roles

    def _role_id(self, name: str) -> str | None:
        return self._roles_map().get(name)

    # -- reads (cached) -----------------------------------------------------------------
    def _all(self) -> dict:
        now = time.time()
        if self._cache is not None and (now - self._cache_ts) < _CACHE_TTL:
            return self._cache
        try:
            rows = {r["email"].lower(): r for r in self._query(_USER_SELECT)}
        except Exception:
            # directory briefly unreachable — serve the last snapshot rather than locking everyone out.
            return self._cache or {}
        self._cache, self._cache_ts = rows, now
        return rows

    def _exists(self, email: str) -> bool:
        return bool(email) and email.lower() in self._all()

    def get_user(self, email: str) -> dict | None:
        """Full user row (role NAME + is_internal + status + org link), or None."""
        return self._all().get((email or "").strip().lower())

    def get_by_id(self, uid: str) -> dict | None:
        """User row by internal uuid (string) — the per-request lookup behind the session cookie."""
        uid = str(uid or "")
        if not uid:
            return None
        for r in self._all().values():
            if str(r["id"]) == uid:
                return r
        return None

    def list_users(self) -> list:
        return sorted(self._all().values(), key=lambda u: u["email"])

    # -- sign-in (auth flow) ------------------------------------------------------------
    def authenticate(self, google_sub: str, email: str) -> dict | None:
        """Resolve a Google sign-in to a user row, applying the allowlist + lifecycle rules.

        Match on `google_sub` (subsequent sign-ins) then `email` (first sign-in, before sub is known).
        Reject if no row exists (not invited) or status is 'disabled'. On success, establish the
        identity: set `google_sub`, flip to 'active', stamp `onboarded_at` once. Returns the row, or None.
        """
        email = (email or "").strip().lower()
        row = None
        if google_sub:
            row = self._fetch_one("u.google_sub = ?", google_sub)
        if row is None and email:
            row = self._fetch_one("u.email = ?", email)
        if row is None or row["status"] == "disabled":
            return None
        self._exec("UPDATE public.users SET google_sub = ?, status = 'active', "
                   "onboarded_at = COALESCE(onboarded_at, now()), updated_at = now() WHERE id = ?::uuid",
                   (google_sub, row["id"]))
        self._cache = None
        return self.get_by_id(row["id"])

    def _fetch_one(self, where_sql: str, val) -> dict | None:
        rows = self._query(f"{_USER_SELECT} WHERE {where_sql}", (val,))
        return rows[0] if rows else None

    # -- writes (invalidate cache) ------------------------------------------------------
    def upsert(self, email: str, role: str, by: str = "") -> None:
        """Invite or re-role a user by email. New rows start 'invited'; an existing row keeps its
        status and only its role is updated. `by` is the inviter's email (recorded as invited_by)."""
        email = email.strip().lower()
        if not email or role not in ("admin", "member"):
            return
        rid = self._role_id(role)
        if not rid:                              # roles missing (transient) — seed and retry once
            self._ensure_roles()
            rid = self._role_id(role)
        inviter = self._id_for_email(by) if by and "@" in by else None
        self._exec(
            "INSERT INTO public.users (id, email, role_id, invited_by) VALUES (?::uuid, ?, ?::uuid, ?::uuid) "
            "ON CONFLICT (email) DO UPDATE SET role_id = EXCLUDED.role_id, updated_at = now()",
            (str(uuid.uuid4()), email, rid, inviter))
        self._cache = None

    def _id_for_email(self, email: str) -> str | None:
        u = self._all().get((email or "").strip().lower())
        return u["id"] if u else None

    def remove(self, email: str) -> None:
        """Hard-delete a user. The bootstrap admin is never removable (cold-start safety)."""
        email = (email or "").strip().lower()
        if not email or email == _bootstrap_admin_email():
            return
        self._exec("DELETE FROM public.users WHERE email = ?", (email,))
        self._cache = None

    def set_status(self, email: str, status: str) -> None:
        """Set lifecycle status: 'invited' | 'active' | 'disabled'."""
        email = (email or "").strip().lower()
        if not email or status not in ("invited", "active", "disabled"):
            return
        self._exec("UPDATE public.users SET status = ?, updated_at = now() WHERE email = ?",
                   (status, email))
        self._cache = None

    def disable(self, email: str) -> None:
        """Revoke access immediately: status→'disabled' AND bump token_version, which invalidates the
        user's current signed cookie on its next request (the per-user logout lever)."""
        email = (email or "").strip().lower()
        if not email or email == _bootstrap_admin_email():   # never lock the cold-start admin out
            return
        self._exec("UPDATE public.users SET status = 'disabled', token_version = token_version + 1, "
                   "updated_at = now() WHERE email = ?", (email,))
        self._cache = None

    def bump_token_version(self, email: str) -> None:
        """Invalidate the user's existing sessions without changing status (force re-login)."""
        email = (email or "").strip().lower()
        if not email:
            return
        self._exec("UPDATE public.users SET token_version = token_version + 1, updated_at = now() "
                   "WHERE email = ?", (email,))
        self._cache = None

    def ensure_bootstrap_admin(self) -> None:
        """Cold-start seed: guarantee SF_BOOTSTRAP_ADMIN_EMAIL exists as an INTERNAL admin so the first
        invite can be sent and the operator can reach /admin. A net-new row is 'invited' (flips to
        'active' on first sign-in); an existing row keeps its status but is forced admin + internal."""
        email = _bootstrap_admin_email()
        if not email:
            return
        rid = self._role_id("admin")
        if not rid:
            self._ensure_roles()
            rid = self._role_id("admin")
        self._exec(
            "INSERT INTO public.users (id, email, role_id, is_internal) VALUES (?::uuid, ?, ?::uuid, true) "
            "ON CONFLICT (email) DO UPDATE SET role_id = EXCLUDED.role_id, is_internal = true, "
            "updated_at = now()",
            (str(uuid.uuid4()), email, rid))
        self._cache = None

    # -- user profile (org link + self-described role) ----------------------------------
    def set_profile(self, email: str, *, org_id: str | None = None, designation: str | None = None,
                    role_description: str | None = None, is_internal: bool | None = None) -> None:
        """Update onboarding profile fields on an existing user (creates a member row if unknown).
        Only the non-None fields are written. `is_internal` flags Tenexity staff vs external collaborator."""
        email = (email or "").strip().lower()
        if not email:
            return
        if not self._exists(email):
            self.upsert(email, "member")
        sets, vals = [], []
        for col, val in (("org_id", org_id), ("designation", designation),
                         ("role_description", role_description)):
            if val is not None:
                sets.append(f"{col}=?"); vals.append(val)
        if is_internal is not None:
            sets.append("is_internal=?"); vals.append(bool(is_internal))
        if not sets:
            return
        vals.append(email)
        self._exec(f"UPDATE public.users SET {', '.join(sets)}, updated_at = now() WHERE email=?",
                   tuple(vals))
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
        self._exec("UPDATE public.users SET org_id = NULL, updated_at = now() WHERE org_id = ?", (org_id,))
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
