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

LAYERING (CRUD/app-logic separation): `UserRepository` (repositories/users_repo.py) holds the pure,
parameterized SQL as SQLAlchemy Core constructs (no cache, no normalization, no lifecycle decisions).
`UserStore` is the business layer: it owns the read cache + fallback-to-stale, email normalization,
the invited→active lifecycle, RBAC validation, cold-start seeding, and org orchestration, delegating
every query/write to the repository. `UserStore`'s public surface is unchanged (callers + tests
untouched).

This is the sanctioned "Store already encapsulates the logic" shape of the CRUD/app-logic split
(vs. the "logic was inlined in a router → extract a Service" shape used for org — see
docs/ARCHITECTURE.md §3): keep the Store as the service layer, extract a pure-CRUD Repository it
delegates to. Two classes, not three — a separate `UserService` behind a façade would be pure
indirection since `UserStore` already IS the service and its name must be preserved.
"""
from __future__ import annotations

import json
import os
import time
import uuid

from . import auth
from .repositories._exec import GlobalExec
from .repositories.users_repo import UserRepository

_CACHE_TTL = 20.0
# Canonical internal organization — every Tenexity staff member links to it (so "Your organization"
# resolves + the admin-dashboard card, gated on isAdmin && org, shows). Seeded at boot, idempotently.
TENEXITY_ORG_ID = "org-tenexity"

# organizations columns that hold JSON-encoded lists (decoded on read).
_ORG_JSON_COLS = ("sub_focus", "connected_systems")
_ORG_COLS = ("id", "name", "industry", "sub_focus", "headcount", "revenue",
             "location", "website", "connected_systems", "plan", "monthly_budget_cap",
             "created_at", "created_by")


def _bootstrap_admin_email() -> str:
    return (os.environ.get("SF_BOOTSTRAP_ADMIN_EMAIL", "") or "").strip().lower()


class UserStore:
    """Business layer over `UserRepository`: read cache (+ fallback-to-stale), email normalization,
    the invited→active lifecycle, RBAC validation, cold-start seeding, and org orchestration."""

    def __init__(self):
        self._repo = UserRepository(GlobalExec())
        self._cache: dict | None = None
        self._cache_ts = 0.0
        self._roles: dict | None = None        # {role name -> id} cache
        try:
            self._ensure_roles()                # seed admin/member (covers create_all test DBs)
            self.ensure_tenexity_org()          # canonical internal org (before bootstrap admin links to it)
            self.ensure_bootstrap_admin()       # cold-start: the one env-seeded admin
        except Exception:
            # DB briefly unreachable at boot — the migration already seeded roles in prod, and the
            # next write will retry. Never block startup on the directory.
            pass

    # -- roles (RBAC) -------------------------------------------------------------------
    def _ensure_roles(self) -> None:
        """Seed the two baseline roles if absent. The migration seeds them in prod; this covers a
        fresh `create_all` test DB (which builds tables but runs no migration data step)."""
        for name, desc in (("admin", "Full administrative access"),
                           ("member", "Standard member access")):
            self._repo.seed_role(str(uuid.uuid4()), name, desc)
        self._roles = None

    def _roles_map(self) -> dict:
        if self._roles is None:
            self._roles = {r["name"]: r["id"] for r in self._repo.roles_rows()}
        return self._roles

    def _role_id(self, name: str) -> str | None:
        return self._roles_map().get(name)

    # -- reads (cached) -----------------------------------------------------------------
    def _all(self) -> dict:
        now = time.time()
        if self._cache is not None and (now - self._cache_ts) < _CACHE_TTL:
            return self._cache
        try:
            rows = {r["email"].lower(): r for r in self._repo.all_users()}
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
            row = self._first(self._repo.by_google_sub(google_sub))
        if row is None and email:
            row = self._first(self._repo.by_email(email))
        if row is None or row["status"] == "disabled":
            return None
        self._repo.set_identity(row["id"], google_sub)
        self._cache = None
        return self.get_by_id(row["id"])

    @staticmethod
    def _first(rows) -> dict | None:
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
        self._repo.upsert_user(str(uuid.uuid4()), email, rid, inviter)
        self._cache = None

    def _id_for_email(self, email: str) -> str | None:
        u = self._all().get((email or "").strip().lower())
        return u["id"] if u else None

    def remove(self, email: str) -> None:
        """Hard-delete a user. The bootstrap admin is never removable (cold-start safety)."""
        email = (email or "").strip().lower()
        if not email or email == _bootstrap_admin_email():
            return
        self._repo.delete_user(email)
        self._cache = None

    def set_status(self, email: str, status: str) -> None:
        """Set lifecycle status: 'invited' | 'active' | 'disabled'."""
        email = (email or "").strip().lower()
        if not email or status not in ("invited", "active", "disabled"):
            return
        self._repo.update_status(email, status)
        self._cache = None

    def disable(self, email: str) -> None:
        """Revoke access immediately: status→'disabled' AND bump token_version, which invalidates the
        user's current signed cookie on its next request (the per-user logout lever)."""
        email = (email or "").strip().lower()
        if not email or email == _bootstrap_admin_email():   # never lock the cold-start admin out
            return
        self._repo.disable_user(email)
        self._cache = None

    def bump_token_version(self, email: str) -> None:
        """Invalidate the user's existing sessions without changing status (force re-login)."""
        email = (email or "").strip().lower()
        if not email:
            return
        self._repo.bump_token_version(email)
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
        self._repo.upsert_admin(str(uuid.uuid4()), email, rid)
        self._cache = None
        # Link the bootstrap admin to the canonical Tenexity org (org_id only — preserves role/is_internal)
        # so "Your organization" resolves and the admin-dashboard card (isAdmin && org) shows.
        self.set_profile(email, org_id=TENEXITY_ORG_ID)

    def ensure_tenexity_org(self) -> None:
        """Cold-start seed of the canonical internal org. Guarded by an existence check because
        create_org's INSERT has no ON CONFLICT — an unconditional call would dup-PK on the 2nd boot."""
        if self.get_org(TENEXITY_ORG_ID) is None:
            self.create_org("Tenexity", org_id=TENEXITY_ORG_ID, by="system")

    # -- user profile (org link + self-described role) ----------------------------------
    def set_profile(self, email: str, *, org_id: str | None = None, designation: str | None = None,
                    role_description: str | None = None, is_internal: bool | None = None,
                    name: str | None = None, sign_in_method: str | None = None) -> None:
        """Update onboarding/user-mgmt profile fields on an existing user (creates a member row if
        unknown). Only the non-None fields are written. `is_internal` flags Tenexity staff."""
        email = (email or "").strip().lower()
        if not email:
            return
        if not self._exists(email):
            self.upsert(email, "member")
        cols: dict = {}
        for col, val in (("org_id", org_id), ("designation", designation),
                         ("role_description", role_description), ("name", name),
                         ("sign_in_method", sign_in_method)):
            if val is not None:
                cols[col] = val
        if is_internal is not None:
            cols["is_internal"] = bool(is_internal)
        if not cols:
            return
        self._repo.update_user_columns(email, cols)
        self._cache = None

    # -- email+password sign-in ---------------------------------------------------------
    def set_password(self, email: str, raw_password: str) -> None:
        """Provision/replace a user's password: store the scrypt hash + flip sign_in_method to
        'password'. Does NOT change status — the caller (invite) decides active vs invited."""
        email = (email or "").strip().lower()
        if not email or not raw_password:
            return
        self._repo.set_password_hash(email, auth.hash_password(raw_password))
        self._cache = None

    def authenticate_password(self, email: str, raw_password: str) -> dict | None:
        """Resolve an email+password sign-in, applying the SAME allowlist/lifecycle as Google: the
        user must exist, be 'active', and have a password set; the hash is verified constant-time.
        Returns the user row (no hash) on success, else None. Touches last_active on success."""
        email = (email or "").strip().lower()
        if not email or not raw_password:
            return None
        rows = self._repo.credentials(email)
        u = rows[0] if rows else None
        if not u or u["status"] != "active" or not u.get("password_hash"):
            return None
        if not auth.verify_password(raw_password, u["password_hash"]):
            return None
        self.touch_last_active(u["id"])
        return self.get_by_id(u["id"])

    def touch_last_active(self, uid: str) -> None:
        """Stamp last_active = now() (display-only activity; cheap, no cache invalidation)."""
        uid = str(uid or "")
        if not uid:
            return
        self._repo.touch_last_active(uid)

    # -- organizations ------------------------------------------------------------------
    def create_org(self, name: str, *, industry: str | None = None, sub_focus=None,
                   headcount: str | None = None, revenue: str | None = None,
                   location: str | None = None, website: str | None = None,
                   connected_systems=None, by: str = "", org_id: str | None = None) -> str:
        """Insert an organization, returning its id (generated `org-<hex8>` unless given)."""
        oid = org_id or ("org-" + uuid.uuid4().hex[:8])
        self._repo.insert_org(oid, name, industry, json.dumps(sub_focus or []), headcount, revenue,
                              location, website, json.dumps(connected_systems or []), by)
        return oid

    def get_org(self, org_id: str) -> dict | None:
        if not org_id:
            return None
        rows = self._repo.org_by_id(org_id)
        return self._decode_org(rows[0]) if rows else None

    def list_orgs(self) -> list:
        return [self._decode_org(r) for r in self._repo.all_orgs()]

    def update_org(self, org_id: str, **fields) -> None:
        """Patch the provided org columns (json-encoding sub_focus/connected_systems)."""
        cols = [c for c in _ORG_COLS if c not in ("id", "created_at", "created_by")]
        patch: dict = {}
        for col in cols:
            if col in fields and fields[col] is not None:
                patch[col] = json.dumps(fields[col]) if col in _ORG_JSON_COLS else fields[col]
        if not patch:
            return
        self._repo.update_org_columns(org_id, patch)

    def delete_org(self, org_id: str) -> None:
        """Delete an org and unlink its members (their rows survive, org_id cleared)."""
        if not org_id:
            return
        self._repo.unlink_org_members(org_id)
        self._repo.delete_org_row(org_id)
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
