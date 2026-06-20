"""SQLAlchemy models — the SINGLE, object-oriented definition of every table.

Postgres everywhere (no sqlite): the schema is owned by Alembic in prod and by `metadata.create_all`
against the test Postgres in the suite — both build from THIS `metadata`, so they cannot drift.
Query routing goes through `dbshim` (the Postgres connection wrapper that handles the Supabase 6543
transaction pooler) — the recorded "hybrid": ORM for schema definition, `dbshim` for DML.

Flat schema: one set of tables, every per-project table keyed by `project_id`. `gates`/`agents` use composite
`(project_id, …)` PKs since their natural keys are only unique within a run. The global directory tables
(organizations, users, blobs) are single row-sets, not per-project.
"""
from __future__ import annotations

from sqlalchemy import (Column, DateTime, Float, Integer, MetaData, Table, Text, func)

metadata = MetaData()

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

users = Table(
    "users", metadata,
    Column("email", Text, primary_key=True),
    Column("role", Text, nullable=False, server_default="member"),
    Column("org_id", Text),
    Column("designation", Text),
    Column("role_description", Text),
    Column("tenexity", Integer),
    Column("status", Text, nullable=False, server_default="active"),  # 'active' | 'invited' (§3.6)
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("created_by", Text),
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

# Editable agent system prompts (Tenexity OS §3.4). One row per agent callsign; the live pipeline
# does NOT yet read these (operator-editable + versioned here; wiring into agents is a follow-up).
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

# Groupings: the flat per-project tables, the global directory tables, and everything (Alembic + tests).
PROJECTDB = (projectstate, phases, artifacts, blockers, gates, verifications, deployments)
FLAT_TABLES = PROJECTDB + (tickets, agents)
GLOBAL_TABLES = (organizations, users, blobs, blob_uses, agent_prompts, mcp_tools, agent_registry)
ALL_TABLES = FLAT_TABLES + GLOBAL_TABLES
