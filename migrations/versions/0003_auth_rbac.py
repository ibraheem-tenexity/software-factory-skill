"""auth rbac: roles + role_permissions tables, redesigned users (uuid PK / google_sub / role_id /
is_internal / status invited|active|disabled / token_version / metadata jsonb), updated_at trigger.

Revision ID: 0003_auth_rbac
Revises: 0002_tenexity_os
Create Date: 2026-06-22

BIG & BREAKING (operator pre-authorized; the LAST drop+rebuild — additive-only after this). Kills the
env allowlist (SF_AUTH_EMAILS / SF_ADMIN_EMAILS) in favour of the users table as the single source of
truth for access. The OLD users table (email PK, text `role`, `tenexity`) is structurally incompatible
with the new model, so it is dropped and rebuilt rather than migrated column-by-column.

Idempotent on BOTH paths despite the rebuild:
  - FRESH DB: baseline create_all already built the NEW users + roles + role_permissions, so the DROP
    is GUARDED on the old-shape marker (the `tenexity` column) and is skipped; every create is checkfirst.
  - STAMPED PROD (0002): users is the OLD shape (has `tenexity`) → dropped and rebuilt to the new shape;
    roles/role_permissions/trigger created.
  - RE-RUN after 0003: users is already new shape (no `tenexity`) → DROP skipped → all no-ops (no data loss).

SOF-61: the two `models.metadata.create_all(...)` calls (roles/role_permissions, then the rebuilt
users) are frozen to inline DDL — byte-for-byte the schema `models.metadata` produced at commit
36e1d768 (the commit that added this migration). Everything else (the pgcrypto extension, the seed
INSERT, the guarded DROP, the updated_at trigger) was already raw SQL and is untouched.
"""
from alembic import op

revision = "0003_auth_rbac"
down_revision = "0002_tenexity_os"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # gen_random_uuid() is core in PG13+; this provides it on older servers and no-ops otherwise.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # 1) RBAC tables first (users.role_id FKs roles.id). IF NOT EXISTS = no-op if the baseline built them.
    op.execute("""
        CREATE TABLE IF NOT EXISTS roles (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name        TEXT NOT NULL UNIQUE,
            description TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS role_permissions (
            role_id     UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
            permission  TEXT NOT NULL,
            PRIMARY KEY (role_id, permission)
        )
    """)
    op.execute("""
        INSERT INTO public.roles (id, name, description) VALUES
          (gen_random_uuid(), 'admin',  'Full administrative access'),
          (gen_random_uuid(), 'member', 'Standard member access')
        ON CONFLICT (name) DO NOTHING
    """)

    # 2) Drop the OLD users table ONLY (guarded on its `tenexity` column so a fresh/already-migrated
    #    DB is untouched). CASCADE clears the self-FK; nothing else references users.
    op.execute("""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM information_schema.columns
                     WHERE table_schema='public' AND table_name='users' AND column_name='tenexity') THEN
            DROP TABLE public.users CASCADE;
          END IF;
        END $$;
    """)

    # 3) Build the new users table (IF NOT EXISTS: skipped on a fresh DB that already has it).
    op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            google_sub        TEXT UNIQUE,
            email             TEXT NOT NULL UNIQUE,
            role_id           UUID NOT NULL REFERENCES roles(id),
            is_internal       BOOLEAN NOT NULL DEFAULT false,
            status            TEXT NOT NULL DEFAULT 'invited',
            token_version     INTEGER NOT NULL DEFAULT 0,
            metadata          JSONB NOT NULL DEFAULT '{}'::jsonb,
            invited_by        UUID REFERENCES users(id),
            onboarded_at      TIMESTAMPTZ,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            org_id            TEXT,
            designation       TEXT,
            role_description  TEXT,
            CONSTRAINT users_status_check CHECK (status in ('invited', 'active', 'disabled'))
        )
    """)

    # 4) Auto-maintain updated_at (create_all cannot emit a trigger). Idempotent.
    op.execute("""
        CREATE OR REPLACE FUNCTION public.set_updated_at() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          NEW.updated_at = now();
          RETURN NEW;
        END;
        $$
    """)
    op.execute("DROP TRIGGER IF EXISTS users_set_updated_at ON public.users")
    op.execute("""
        CREATE TRIGGER users_set_updated_at
          BEFORE UPDATE ON public.users
          FOR EACH ROW EXECUTE FUNCTION public.set_updated_at()
    """)


def downgrade() -> None:
    pass
