"""user management: first-class user columns (name / sign_in_method / last_active / password_hash)

Revision ID: 0004_user_mgmt
Revises: 0003_auth_rbac
Create Date: 2026-06-22

ADDITIVE / idempotent ONLY (crew migrations policy — no drop+rebuild). Adds the columns the
user-management screen + email/password auth need to `public.users`:
  • name           text         — display name
  • designation    text         — already added in 0003; ADD IF NOT EXISTS is a no-op here
  • sign_in_method text default 'google'  — google | microsoft | password | sso
  • last_active    timestamptz  — touched per authed request
  • password_hash  text NULL    — bcrypt hash for email+password sign-in (NULL = no password set)

Idempotent: ADD COLUMN IF NOT EXISTS, so it no-ops on a fresh DB where the baseline's create_all
already built these from models.metadata, and creates them on a stamped-prod upgrade.
"""
from alembic import op

revision = "0004_user_mgmt"
down_revision = "0003_auth_rbac"
branch_labels = None
depends_on = None

_COLS = (
    ("name", "text"),
    ("designation", "text"),                       # already in 0003 → no-op
    ("sign_in_method", "text NOT NULL DEFAULT 'google'"),
    ("last_active", "timestamptz"),
    ("password_hash", "text"),
)


def upgrade() -> None:
    for col, typ in _COLS:
        op.execute(f"ALTER TABLE public.users ADD COLUMN IF NOT EXISTS {col} {typ}")


def downgrade() -> None:
    for col, _typ in (("name", ""), ("sign_in_method", ""), ("last_active", ""),
                      ("password_hash", "")):
        op.execute(f"ALTER TABLE public.users DROP COLUMN IF EXISTS {col}")
