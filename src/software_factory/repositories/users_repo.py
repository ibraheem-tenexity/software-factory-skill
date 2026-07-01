"""Pure CRUD for `users` / `roles` / `organizations` (SQLAlchemy Core). Global tables.

UUID columns (users.id, users.role_id, users.invited_by, roles.id) are compared/bound without an
explicit ::uuid cast — Postgres infers the bind parameter's type from the comparison/insert context
against the typed column, the standard behavior for parameterized queries (no prior raw SQL cast
needed, unlike the old `?::uuid` strings this replaces).
"""
from __future__ import annotations

from sqlalchemy import select, insert, update, delete, func, cast, Text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..models import users, roles, organizations

_inv = users.alias("inv")  # self-join: the user who sent the invite

_USER_COLS = (
    cast(users.c.id, Text).label("id"),
    users.c.google_sub,
    users.c.email,
    roles.c.name.label("role"),
    users.c.is_internal,
    users.c.status,
    users.c.token_version,
    users.c.org_id,
    users.c.designation,
    users.c.role_description,
    users.c.name.label("name"),
    users.c.sign_in_method,
    _inv.c.email.label("invited_by"),
    func.extract("epoch", users.c.created_at).label("created_at"),
    func.extract("epoch", users.c.onboarded_at).label("onboarded_at"),
    func.extract("epoch", users.c.last_active).label("last_active"),
)
# password_hash is deliberately NOT in _USER_COLS — this row feeds /api/users etc., so the hash must
# never ride along. It's read only by `credentials()`'s dedicated query.

_USER_FROM = users.join(roles, roles.c.id == users.c.role_id).outerjoin(_inv, _inv.c.id == users.c.invited_by)

_ORG_COLS = (
    organizations.c.id, organizations.c.name, organizations.c.industry, organizations.c.sub_focus,
    organizations.c.headcount, organizations.c.revenue, organizations.c.location,
    organizations.c.website, organizations.c.connected_systems, organizations.c.plan,
    organizations.c.monthly_budget_cap,
    func.extract("epoch", organizations.c.created_at).label("created_at"), organizations.c.created_by,
)


class UserRepository:
    def __init__(self, exec_):
        self._x = exec_

    # -- roles (RBAC) -------------------------------------------------------------------
    def seed_role(self, rid: str, name: str, desc: str) -> None:
        stmt = pg_insert(roles).values(id=rid, name=name, description=desc)
        self._x.execute(stmt.on_conflict_do_nothing(index_elements=["name"]))

    def roles_rows(self) -> list:
        return self._x.fetchall(select(cast(roles.c.id, Text).label("id"), roles.c.name))

    # -- users --------------------------------------------------------------------------
    def all_users(self) -> list:
        return self._x.fetchall(select(*_USER_COLS).select_from(_USER_FROM))

    def by_google_sub(self, google_sub) -> list:
        return self._x.fetchall(
            select(*_USER_COLS).select_from(_USER_FROM).where(users.c.google_sub == google_sub))

    def by_email(self, email) -> list:
        return self._x.fetchall(
            select(*_USER_COLS).select_from(_USER_FROM).where(users.c.email == email))

    def upsert_user(self, uid: str, email: str, rid: str | None, inviter: str | None) -> None:
        stmt = pg_insert(users).values(id=uid, email=email, role_id=rid, invited_by=inviter)
        stmt = stmt.on_conflict_do_update(
            index_elements=["email"], set_={"role_id": stmt.excluded.role_id, "updated_at": func.now()})
        self._x.execute(stmt)

    def upsert_admin(self, uid: str, email: str, rid: str | None) -> None:
        stmt = pg_insert(users).values(id=uid, email=email, role_id=rid, is_internal=True)
        stmt = stmt.on_conflict_do_update(
            index_elements=["email"],
            set_={"role_id": stmt.excluded.role_id, "is_internal": True, "updated_at": func.now()})
        self._x.execute(stmt)

    def set_identity(self, uid: str, google_sub: str) -> None:
        self._x.execute(update(users).where(users.c.id == uid).values(
            google_sub=google_sub, status="active",
            onboarded_at=func.coalesce(users.c.onboarded_at, func.now()), updated_at=func.now()))

    def delete_user(self, email: str) -> None:
        self._x.execute(delete(users).where(users.c.email == email))

    def update_status(self, email: str, status: str) -> None:
        self._x.execute(update(users).where(users.c.email == email)
                        .values(status=status, updated_at=func.now()))

    def disable_user(self, email: str) -> None:
        self._x.execute(update(users).where(users.c.email == email).values(
            status="disabled", token_version=users.c.token_version + 1, updated_at=func.now()))

    def bump_token_version(self, email: str) -> None:
        self._x.execute(update(users).where(users.c.email == email)
                        .values(token_version=users.c.token_version + 1, updated_at=func.now()))

    def update_user_columns(self, email: str, cols: dict) -> None:
        """Patch the given user columns (+ updated_at). Callers MUST pass only trusted, code-defined
        column names (never request-derived input) — all current callers pass a fixed allowlist built
        in `UserStore.set_profile`."""
        if not cols:
            return
        self._x.execute(update(users).where(users.c.email == email).values(**cols, updated_at=func.now()))

    def set_password_hash(self, email: str, password_hash: str) -> None:
        self._x.execute(update(users).where(users.c.email == email).values(
            password_hash=password_hash, sign_in_method="password", updated_at=func.now()))

    def credentials(self, email: str) -> list:
        return self._x.fetchall(
            select(cast(users.c.id, Text).label("id"), users.c.status, users.c.password_hash)
            .where(users.c.email == email))

    def touch_last_active(self, uid: str) -> None:
        self._x.execute(update(users).where(users.c.id == uid).values(last_active=func.now()))

    # -- organizations ------------------------------------------------------------------
    def insert_org(self, oid: str, name: str, industry, sub_focus_json: str, headcount,
                   revenue, location, website, connected_systems_json: str, by: str) -> None:
        self._x.execute(insert(organizations).values(
            id=oid, name=name, industry=industry, sub_focus=sub_focus_json, headcount=headcount,
            revenue=revenue, location=location, website=website,
            connected_systems=connected_systems_json, created_by=by))

    def org_by_id(self, org_id: str) -> list:
        return self._x.fetchall(select(*_ORG_COLS).where(organizations.c.id == org_id))

    def all_orgs(self) -> list:
        return self._x.fetchall(select(*_ORG_COLS).order_by(organizations.c.name))

    def update_org_columns(self, org_id: str, cols: dict) -> None:
        """Patch the given organization columns (no updated_at column on organizations). Callers
        MUST pass only trusted, code-defined column names — all current callers pass the fixed
        `_ORG_COLS` allowlist built in `UserStore.update_org`."""
        if not cols:
            return
        self._x.execute(update(organizations).where(organizations.c.id == org_id).values(**cols))

    def unlink_org_members(self, org_id: str) -> None:
        self._x.execute(update(users).where(users.c.org_id == org_id)
                        .values(org_id=None, updated_at=func.now()))

    def delete_org_row(self, org_id: str) -> None:
        self._x.execute(delete(organizations).where(organizations.c.id == org_id))
