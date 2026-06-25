"""SQLAlchemy models — the SINGLE, object-oriented definition of every table.

Postgres everywhere: the schema is owned by Alembic in prod and by `metadata.create_all`
against the test Postgres in the suite — both build from THIS `metadata`, so they cannot drift.
Query routing goes through `dbshim` (the Postgres connection wrapper that handles the Supabase 6543
transaction pooler) — the recorded "hybrid": ORM for schema definition, `dbshim` for DML.

Flat schema: one set of tables, every per-project table keyed by `project_id`. `gates`/`agents` use composite
`(project_id, …)` PKs since their natural keys are only unique within a run. The global directory tables
(organizations, users, blobs) are single row-sets, not per-project.
"""
from __future__ import annotations

from sqlalchemy import (Boolean, CheckConstraint, Column, DateTime, Float, ForeignKey,
                        Integer, MetaData, Table, Text, UniqueConstraint, func, text)
from sqlalchemy.dialects.postgresql import JSONB, UUID

metadata = MetaData()

_UUID = UUID(as_uuid=False)  # uuid columns surface as plain strings at the dbshim boundary

projectstate = Table(
    "projectstate", metadata,
    Column("project_id", Text, primary_key=True),
    Column("data", Text, nullable=False),
)

phases = Table(
    "phases", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("project_id", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("status", Text, nullable=False, server_default="active"),
    Column("stage", Integer),
    Column("ts", Float, nullable=False),
)

artifacts = Table(
    "artifacts", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("project_id", Text, nullable=False),
    Column("title", Text),
    Column("path", Text),
    Column("kind", Text),
    Column("agent", Text),
    Column("ts", Float, nullable=False),
)

blockers = Table(
    "blockers", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("project_id", Text, nullable=False),
    Column("what", Text),
    Column("blocks", Text),
    Column("cleared", Integer, nullable=False, server_default="0"),
    Column("ts", Float, nullable=False),
)

gates = Table(
    "gates", metadata,
    Column("project_id", Text, primary_key=True),
    Column("name", Text, primary_key=True),
    Column("status", Text, nullable=False),
    Column("ts", Float, nullable=False),
)

verifications = Table(
    "verifications", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("project_id", Text, nullable=False),
    Column("url", Text),
    Column("passed", Integer, nullable=False),
    Column("result", Text),
    Column("ts", Float, nullable=False),
)

deployments = Table(
    "deployments", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("project_id", Text, nullable=False),
    Column("app", Text),
    Column("service_name", Text),
    Column("url", Text),
    Column("status", Text, nullable=False, server_default="deploying"),
    Column("verified", Integer, nullable=False, server_default="0"),
    Column("ts", Float, nullable=False),
)

tickets = Table(
    "tickets", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("project_id", Text, nullable=False),
    Column("title", Text, nullable=False),
    Column("acceptance", Text, nullable=False),
    Column("dod", Text, nullable=False),
    Column("wave", Integer, nullable=False),
    Column("status", Text, nullable=False, server_default="open"),
    Column("agent", Text),
    Column("provenance", Text),
    Column("provenance_type", Text),
    Column("diff_lines", Integer, nullable=False, server_default="0"),
    Column("app", Text),
    Column("description", Text, nullable=False, server_default=""),
)

agents = Table(
    "agents", metadata,
    Column("agent_id", Text, primary_key=True),
    Column("project_id", Text, primary_key=True),
    Column("ticket_id", Integer),
    Column("role", Text, nullable=False),
    Column("model", Text, nullable=False),
    Column("phase", Text),
    Column("status", Text, nullable=False, server_default="running"),
    Column("outcome", Text),
    Column("cost_usd", Float, nullable=False, server_default="0"),
    Column("input_tokens", Integer, nullable=False, server_default="0"),
    Column("cached_tokens", Integer, nullable=False, server_default="0"),
    Column("output_tokens", Integer, nullable=False, server_default="0"),
    Column("reasoning_tokens", Integer, nullable=False, server_default="0"),
    Column("provenance", Text),
    Column("provenance_type", Text),
    Column("diff_lines", Integer, nullable=False, server_default="0"),
    Column("started_at", Float, nullable=False),
    Column("ended_at", Float),
)

# ---- global directory tables (one row-set, not per-project) ------------------------------
organizations = Table(
    "organizations", metadata,
    Column("id", Text, primary_key=True),
    Column("name", Text, nullable=False),
    Column("industry", Text),
    Column("sub_focus", Text),                 # JSON-encoded list
    Column("headcount", Text),                 # band label, e.g. "51–200"
    Column("revenue", Text),                   # band label, e.g. "$10M–$50M"
    Column("location", Text),
    Column("website", Text),
    Column("connected_systems", Text),         # JSON-encoded list
    Column("plan", Text),                       # billing plan label, e.g. "Team"
    Column("monthly_budget_cap", Float),        # USD/month cap shown in Usage & billing
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("created_by", Text),
)

# ---- RBAC: roles + permissions (the access model) ----------------------------------------
# A role is a named bucket; one row per role. `role_permissions` maps roles to permission
# strings (the future privileges feature, as a proper relation rather than a parsed column).
roles = Table(
    "roles", metadata,
    Column("id", _UUID, primary_key=True, server_default=text("gen_random_uuid()")),
    Column("name", Text, nullable=False, unique=True),       # 'admin' | 'member'
    Column("description", Text),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

role_permissions = Table(
    "role_permissions", metadata,
    Column("role_id", _UUID, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission", Text, primary_key=True),            # e.g. 'projects.delete'
)

# Canonical identity AND the allowlist — the single source of truth for "who can access".
#   - id          internal stable key; FK target for everything (never join on email)
#   - google_sub  Google's permanent user id; NULL until first sign-in, then the match key
#   - email       set at invite time; the allowlist match before google_sub is known
#   - role_id     single FK (invite assigns exactly one role); → user_roles join if multi ever needed
#   - is_internal internal staff vs external collaborator (was the `tenexity` flag)
#   - status      invited (on allowlist, not signed in) | active (signed in) | disabled (revoked)
#   - token_version  bump to revoke this user's existing signed cookies before they expire
#   - metadata    jsonb extensibility; NEVER anything security-relevant or filtered/joined on
#   - invited_by  audit trail (nullable self-FK)
#   - onboarded_at  one-time fact of first sign-in (current-login is session state, never stored)
# org_id/designation/role_description are kept (Org Admin + onboarding join/filter on them, so
# they are real columns per the metadata rule — they are NOT auth-relevant).
users = Table(
    "users", metadata,
    Column("id", _UUID, primary_key=True, server_default=text("gen_random_uuid()")),
    Column("google_sub", Text, unique=True),
    Column("email", Text, nullable=False, unique=True),
    Column("role_id", _UUID, ForeignKey("roles.id"), nullable=False),
    Column("is_internal", Boolean, nullable=False, server_default=text("false")),
    Column("status", Text, nullable=False, server_default="invited"),
    Column("token_version", Integer, nullable=False, server_default="0"),
    Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("invited_by", _UUID, ForeignKey("users.id")),
    Column("onboarded_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    # kept for Org Admin / onboarding (join/filter attrs → real columns, not metadata)
    Column("org_id", Text),
    Column("designation", Text),
    Column("role_description", Text),
    # user-management (first-class columns, NOT metadata): display name, sign-in method, activity,
    # and the scrypt password hash for email+password sign-in (NULL = no password set).
    Column("name", Text),
    Column("sign_in_method", Text, nullable=False, server_default="google"),  # google|microsoft|password|sso
    Column("last_active", DateTime(timezone=True)),
    Column("password_hash", Text),
    CheckConstraint("status in ('invited', 'active', 'disabled')", name="users_status_check"),
)

blobs = Table(
    "blobs", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("scope", Text, nullable=False),     # 'project' | 'org'
    Column("scope_id", Text, nullable=False),
    Column("kind", Text),
    Column("name", Text),                       # display filename, e.g. "standard-pricing.xlsx"
    Column("tag", Text),                        # category label, e.g. "Price book"
    Column("storage_key", Text, nullable=False),
    Column("content_type", Text),
    Column("size_bytes", Integer),
    Column("sha256", Text),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

# A project (run) drawing on an org-scoped knowledge-base doc. One row per (blob, run); the
# knowledge-base "used by N projects" count is COUNT(DISTINCT project_id) over these rows.
blob_uses = Table(
    "blob_uses", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("blob_id", Integer, nullable=False),
    Column("project_id", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

# Editable agent system prompts (Tenexity OS §3.4). One row per agent callsign; live orchestrator
# overrides are applied, while role-agent prompts remain stored until subagent prompt wiring exists.
agent_prompts = Table(
    "agent_prompts", metadata,
    Column("callsign", Text, primary_key=True),     # e.g. "ATLAS"
    Column("prompt", Text, nullable=False),
    Column("version", Integer, nullable=False, server_default="1"),
    Column("updated_by", Text),
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
)

# Tools / MCP registry (Tenexity OS §3.5) — real datastore (seeded with the factory's tools), no
# hardcoded response. `used` is derived (not stored).
mcp_tools = Table(
    "mcp_tools", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", Text, nullable=False),
    Column("type", Text),                       # MCP | API | native | HTTP
    Column("provider", Text),
    Column("scope", Text),
    Column("status", Text, nullable=False, server_default="available"),  # connected | available
    Column("auth", Text),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

# Agent registry (Tenexity OS §3.4 identity) — seeded from the canonical roster; live cost/success
# are merged from `public.agents` at read time. Editable here so it's real datastore, not a constant.
agent_registry = Table(
    "agent_registry", metadata,
    Column("callsign", Text, primary_key=True),
    Column("name", Text, nullable=False),
    Column("role", Text),
    Column("model", Text),
    Column("cost_tier", Integer, nullable=False, server_default="1"),
    Column("descr", Text),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

sow = Table(
    "sow", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("title", Text, nullable=False),
    Column("org", Text),
    Column("project", Text),
    Column("value", Text),
    Column("file", Text),
    Column("version", Integer, nullable=False, server_default="1"),
    Column("status", Text, nullable=False, server_default="Draft"),
    Column("body", Text),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
    CheckConstraint(
        "status in ('Template','Draft','In review','Sent','Signed')",
        name="sow_status_check",
    ),
)

checkpoint = Table(
    "checkpoint", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("project_id", Text, nullable=False),
    Column("node", Text, nullable=False),          # pipeline node name or "ticket:<id>"
    Column("output", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("stamped_at", Float, nullable=False),
    UniqueConstraint("project_id", "node", name="uq_checkpoint_project_node"),
)

# Groupings: the flat per-project tables, the global directory tables, and everything (Alembic + tests).
PROJECTDB = (projectstate, phases, artifacts, blockers, gates, verifications, deployments)
FLAT_TABLES = PROJECTDB + (tickets, agents, checkpoint)
GLOBAL_TABLES = (roles, role_permissions, organizations, users, blobs, blob_uses,
                 agent_prompts, mcp_tools, agent_registry, sow)
ALL_TABLES = FLAT_TABLES + GLOBAL_TABLES
