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

from pgvector.sqlalchemy import HALFVEC
from sqlalchemy import (Boolean, CheckConstraint, Column, Computed, DateTime, Float,
                        ForeignKey, ForeignKeyConstraint, Index, Integer, MetaData, Table, Text,
                        UniqueConstraint, func, text)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID

metadata = MetaData()

_UUID = UUID(as_uuid=False)  # uuid columns surface as plain strings at the dbshim boundary

projectstate = Table(
    "projectstate", metadata,
    Column("project_id", Text, primary_key=True),
    Column("data", Text, nullable=False),
    # `name` and `summary` are promoted out of the JSON `data` blob into authoritative columns
    # (queryable; the dashboard card reads them). The store pops them from `data` on write and
    # merges them back on read, so the blob never carries duplicate copies.
    Column("name", Text),
    Column("summary", Text),
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
    # SOF-60: user-deposited documents live here too, distinguished from agent-produced
    # artifacts by `origin`. `content` holds the full converted markdown inline (text, not
    # binary — no storage round-trip needed to read a document whole); `source_blob_id`
    # links back to the uploaded document's blobs row.
    Column("content", Text),
    Column("source_blob_id", Integer, ForeignKey("blobs.id", ondelete="CASCADE")),
    Column("origin", Text, nullable=False, server_default="agent"),  # 'agent' | 'user'
    # SOF-78: the pipeline stage that produced this artifact (0=intake/concierge, 1/2/3=stages),
    # stamped at record_artifact() time from the run's current ProjectState.stage. Nullable —
    # pre-SOF-78 rows and any record path that can't resolve a stage stay NULL.
    Column("stage", Integer),
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
    Column("goal", Text, nullable=False, server_default=""),
    # SOF-100: JSON-encoded arrays. NULL means the writer never addressed the question (fails the
    # depth gate); '[]' means it explicitly decided "none apply" (an honest pass for e.g. a
    # backend-only ticket with no screen) — no server_default, so omission is distinguishable
    # from an explicit empty answer.
    Column("design_refs", Text),
    Column("dependencies", Text),
    Column("scope_genre", Text),
    Column("implementation_notes", Text, nullable=False, server_default=""),
    # SOF-118: JSON-encoded array of {type, statement, reason, affected_surface} decision-log
    # entries (assumptions made / shortcuts taken / known gaps left while building THIS ticket).
    # Same NULL-vs-'[]' convention as design_refs/dependencies: NULL = never addressed (mark_done
    # refuses to close it), '[]' = explicitly "nothing to declare" (an honest, gate-passing close).
    Column("decision_log", Text),
    # SOF-119: how many times the in-pipeline REVIEW agent has bounced this ticket back to `open`
    # (deployed -> open, before the QA loop ever starts). A real column, not derivable after the
    # fact — no per-ticket transition/event history exists elsewhere in this schema, and the bounce
    # loop spans separate agent processes (review -> rebuild -> redeploy -> review again), so this
    # must be persisted, not counted in-process.
    Column("review_bounce_count", Integer, nullable=False, server_default="0"),
    # SOF-163: how many times the host has reclaimed this ticket back to `open` because it was
    # `in_progress` with no live path forward (its claimed agent's runtime_agents row already
    # terminal, or running well past a generous staleness bound). Same shape as
    # review_bounce_count — persisted, not derivable, since the stall spans separate processes.
    Column("stall_count", Integer, nullable=False, server_default="0"),
)

runtime_agents = Table(
    "runtime_agents", metadata,
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
    # Provenance (SOF-26/T0.1): set when this blob is itself an asset extracted FROM another blob
    # (e.g. an image pulled out of a document page) — never set for an original upload.
    Column("source_blob_id", Integer, ForeignKey("blobs.id")),
    Column("source_page", Integer),             # 1-based source page/slide, when extracted
    Column("provenance", JSONB, server_default=text("'{}'::jsonb")),  # extractor, bbox, etc.
    # Files browser (SOF-251): the persisted source-directory this blob belongs to. NULL = unfiled
    # (a virtual/top-level position, or an extracted-child asset whose membership is provenance via
    # source_blob_id, not a directory). The composite FK below targets directories(id, scope,
    # scope_id) so a blob can only sit in a directory of its OWN scope/scope_id, and ON DELETE
    # RESTRICT means a directory that still owns source material cannot be silently dropped.
    Column("directory_id", _UUID),
    ForeignKeyConstraint(
        ["directory_id", "scope", "scope_id"],
        ["directories.id", "directories.scope", "directories.scope_id"],
        ondelete="RESTRICT", name="fk_blobs_directory_scope",
    ),
)

# Source-directory tree for the Files browser (SOF-251), owned by the source-material/memory
# capability. Roots (parent_id IS NULL) are per-scope; the top-level Files screen itself is virtual
# and mixed-scope, so it is NEVER a stored row. Database-enforced invariants:
#   * a directory's parent shares its scope/scope_id — the composite parent FK targets the
#     (id, scope, scope_id) unique key, so a mismatched-scope parent is impossible.
#   * sibling names are unique within their parent and scope, roots included — two partial unique
#     indexes (parent present vs. NULL root) because SQL treats NULL parents as distinct.
#   * a blob's directory shares the blob's scope/scope_id — enforced by the composite FK on `blobs`.
#   * ON DELETE RESTRICT on both the self-parent and blob FKs means deleting a directory with
#     descendants or member blobs is refused, never a silent cascade/orphan.
# `summary_*` back the truthful Files UI state: `summary_status` is one of summarizing|ready|
# needs_refresh|failed, `last_successful_summary_at` is the last time a rollup summary actually
# succeeded, and `summary_source_hash` detects drift of the summarized source set.
directories = Table(
    "directories", metadata,
    Column("id", _UUID, primary_key=True, server_default=text("gen_random_uuid()")),
    Column("scope", Text, nullable=False),            # 'project' | 'org' (mirrors blobs)
    Column("scope_id", Text, nullable=False),
    Column("parent_id", _UUID),                       # NULL => scope root
    Column("name", Text, nullable=False),
    Column("summary_md", Text),
    Column("summary_status", Text, nullable=False, server_default="needs_refresh"),
    Column("summary_source_hash", Text),
    Column("last_successful_summary_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("scope in ('project', 'org')", name="directories_scope_check"),
    CheckConstraint(
        "summary_status in ('summarizing', 'ready', 'needs_refresh', 'failed')",
        name="directories_summary_status_check",
    ),
    # Composite-FK target: lets `blobs` and child directories pin (id, scope, scope_id) together.
    UniqueConstraint("id", "scope", "scope_id", name="uq_directories_id_scope"),
    # Parent must live in the same scope/scope_id; use_alter defers this self-FK past table create.
    ForeignKeyConstraint(
        ["parent_id", "scope", "scope_id"],
        ["directories.id", "directories.scope", "directories.scope_id"],
        ondelete="RESTRICT", name="fk_directories_parent_scope", use_alter=True,
    ),
    # Unique sibling names: children keyed by parent; roots (NULL parent) keyed by scope alone.
    Index("uq_directories_sibling_name", "scope", "scope_id", "parent_id", "name",
          unique=True, postgresql_where=text("parent_id IS NOT NULL")),
    Index("uq_directories_root_name", "scope", "scope_id", "name",
          unique=True, postgresql_where=text("parent_id IS NULL")),
    # Traversal helpers: scope-root lookup, parent walk, and blob membership (on `blobs`).
    Index("ix_directories_scope_roots", "scope", "scope_id",
          postgresql_where=text("parent_id IS NULL")),
    Index("ix_directories_parent", "parent_id"),
)

Index("ix_blobs_directory_id", blobs.c.directory_id)

# Project Memory (SOF-26/T0.1): the per-document "2,000-ft view", keyed 1:1 on the document's
# `blobs` row. `scope`/`scope_id` mirror `blobs` so project- and org-scoped memory share one
# app-layer filter shape (this system isolates at the app layer + credential-scoped MCP, not
# Postgres RLS — see docs/ARCHITECTURE.md §7).
doc_summary = Table(
    "doc_summary", metadata,
    Column("blob_id", Integer, ForeignKey("blobs.id", ondelete="CASCADE"), primary_key=True),
    Column("scope", Text, nullable=False),          # 'project' | 'org'  (mirrors blobs)
    Column("scope_id", Text, nullable=False),
    Column("summary_md", Text),                     # map-reduce summary -> PRD "AI auto-summarize"
    Column("assumptions", JSONB, server_default=text("'{}'::jsonb")),  # -> "Let's confirm what I
    # learned"; each entry carries its own source reference (document_blob_id + section_path/page)
    # -- no confidence scores (product-spec decision): an unreferenced inference is never stored here.
    Column("outline", JSONB, server_default=text("'[]'::jsonb")),    # section titles + one-line gist
    Column("embedding", HALFVEC(3072)),
    Column("token_count", Integer),
    Column("content_sha256", Text),                 # staleness vs blobs.sha256
    Column("status", Text, nullable=False, server_default="pending"),  # pending|ready|failed
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
)

# The leaf level: one row per chunk of a document, hybrid-searchable (dense vector + Postgres
# native full-text as the sparse/keyword channel). A learned-
# sparse `sparse` column is intentionally NOT added here -- deferred, per SOF-26 scope.
chunk = Table(
    "chunk", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("blob_id", Integer, ForeignKey("blobs.id", ondelete="CASCADE"), nullable=False),
    Column("scope", Text, nullable=False),
    Column("scope_id", Text, nullable=False),
    Column("ordinal", Integer, nullable=False),      # position within the document
    Column("section_path", Text),                    # e.g. "2 / 2.3 Auth" -- hierarchical nav
    Column("content", Text, nullable=False),
    Column("dense", HALFVEC(3072)),                   # OpenRouter dense embedding
    # Generated in Postgres from `content` -- defined here (not just in the migration) so
    # `metadata.create_all` in tests builds the identical column the Alembic migration does;
    # otherwise prod and tests would drift on exactly this column.
    Column("fts", TSVECTOR, Computed("to_tsvector('english', content)", persisted=True)),
    Column("token_count", Integer),
)

# Durable, provider-agnostic conversation store (SOF-26/T0.1).
# One row per message/turn; `id` is the message_id returned to the FE. `json_blob` is the
# canonical content-block list (source of truth for provider replay); `input`/`tool_result` are
# denormalized conveniences for display/query, never the source of truth.
conversation = Table(
    "conversation", metadata,
    Column("id", _UUID, primary_key=True, server_default=text("gen_random_uuid()")),
    Column("session_id", _UUID, nullable=False),      # groups one conversation/thread
    Column("seq", Integer, nullable=False),           # monotonic order within session (replay key)
    Column("user_id", _UUID, ForeignKey("users.id")),  # who sent it; null for agent/tool/system
    Column("project_id", Text),                        # -> projectstate; null for org-level chat
    Column("org_id", Text),                             # -> organizations.id
    Column("role", Text, nullable=False),               # user | agent | tool | system
    Column("input", Text),                               # plaintext, denormalized from json_blob
    Column("json_blob", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("tool_name", Text),
    Column("tool_call_id", Text),                        # correlates tool_use <-> tool_result
    Column("tool_result", JSONB),                        # convenience mirror of the result block
    # Artifact references live as blocks inside json_blob (a turn may reference several) — there is
    # deliberately NO single referenced_artifact FK column: one prompt can cite many artifacts.
    Column("model", Text),
    Column("provider", Text),                            # 'openai' | 'anthropic' | 'openrouter' | ...
    Column("input_tokens", Integer, server_default="0"),
    Column("output_tokens", Integer, server_default="0"),
    Column("cost_usd", Float, server_default="0"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("session_id", "seq", name="uq_conversation_session_seq"),
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

# System agents (Tenexity OS): the operator-configurable agents — the Concierge + the three skill
# stages. One row per agent carrying its editable prompt AND the LLM it runs on. This table is the
# ONLY source for what the OS shows/edits; nothing is seeded from code. Merges the former
# agent_registry (identity) + agent_prompts (prompt) into one place.
system_agents = Table(
    "system_agents", metadata,
    Column("callsign", Text, primary_key=True),      # CONCIERGE | STAGE-1 | STAGE-2 | STAGE-3
    Column("name", Text, nullable=False),            # display name
    Column("prompt", Text, nullable=False, server_default=""),
    Column("model_id", Text),                        # the LLM this agent runs on
    Column("version", Integer, nullable=False, server_default="1"),
    Column("updated_by", Text),
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
)

# Tools / MCP registry (SOF-81) — the real, live tool set: `config` is the exact shape
# workspace_setup.py composes into a stage's .mcp.json (or, for non-MCP tools like `github`,
# {"kind": "api", "env_key": ...}). `attached_to` names which system_agents callsigns / pipeline
# nodes actually use the tool today — declarative, not enforced. Key material is NEVER stored
# here: key_vault_id points into Supabase Vault (see vault.py), key_last4 is display-only.
tools = Table(
    "tools", metadata,
    Column("name", Text, primary_key=True),
    Column("config", JSONB, nullable=False),
    Column("attached_to", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("key_vault_id", Text),
    Column("key_last4", Text),
    Column("updated_by", Text),
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
)


recipes = Table(
    "recipes", metadata,
    Column("id", _UUID, primary_key=True, server_default=text("gen_random_uuid()")),
    Column("name", Text, nullable=False, unique=True),
    Column("tagline", Text),
    Column("category", Text),
    Column("capabilities", JSONB, nullable=False, server_default=text("'[]'::jsonb")),  # customer-facing bullets
    Column("body_md", Text),          # recipe text — concierge/brief input
    Column("repo_url", Text),         # build-seed repo (nullable until connected)
    Column("images", JSONB, nullable=False, server_default=text("'[]'::jsonb")),  # [{url, public: bool}]
    Column("status", Text, nullable=False, server_default=text("'draft'")),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
    CheckConstraint("status IN ('draft','published','archived')", name="recipes_status_check"),
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

# Org secrets (SOF-45): metadata only — the plaintext lives in Supabase Vault (pgsodium), this row
# only holds `vault_id`, the pointer `vault.py`'s vault_store/vault_retrieve_many/vault_delete_many
# resolve against. Replaces the earlier in-memory `services/secrets.py` mock.
org_secrets = Table(
    "org_secrets", metadata,
    Column("id", _UUID, primary_key=True, server_default=text("gen_random_uuid()")),
    Column("org_id", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("kind", Text),
    Column("vault_id", Text, nullable=False),
    Column("last4", Text),
    Column("used_by", Integer, nullable=False, server_default="0"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("org_id", "name", name="uq_org_secrets_org_name"),
)

# Run autopsy (SOF-93): each benchmark run is autopsied AT MOST ONCE — `autopsy_processed_runs`
# is the per-run idempotency ledger (a re-scan of an already-processed project_id is a no-op),
# separate from `autopsy_signatures`, which is the cross-run dedup ledger (a repeated FAILURE
# SIGNATURE comments on its existing Linear ticket instead of filing a duplicate). Persisted in the
# DB, not process memory — SOF-116's lesson: a console/script restart must never re-file a known
# failure. `linear_issue_id`/`linear_issue_identifier` are NULL when filing degraded honestly
# (no LINEAR_API_KEY yet) — the signature is still recorded so dedup/occurrence-counting works the
# moment a key is provisioned, without re-processing already-seen runs.
autopsy_processed_runs = Table(
    "autopsy_processed_runs", metadata,
    Column("project_id", Text, primary_key=True),
    Column("signature", Text, nullable=False),
    Column("classification", Text, nullable=False),
    Column("processed_at", Float, nullable=False),
)

autopsy_signatures = Table(
    "autopsy_signatures", metadata,
    Column("signature", Text, primary_key=True),
    Column("classification", Text, nullable=False),
    Column("linear_issue_id", Text),
    Column("linear_issue_identifier", Text),
    Column("first_project_id", Text, nullable=False),
    Column("last_project_id", Text, nullable=False),
    Column("occurrences", Integer, nullable=False, server_default="1"),
    Column("first_seen_at", Float, nullable=False),
    Column("last_seen_at", Float, nullable=False),
)

# SOF-165 (Proposal 5) — first-class Recovery Action: the tier-2 recovery entity between the
# bounded auto-resume (tier 1) and the terminal Recovery-bar/Linear escalation (tier 3). One
# unified record that BOTH the production path (mark_stage_crashed) and the benchmark path
# (autopsy_and_file) + the SOF-164 silence seam write to. Global, like the autopsy ledgers.
# Idempotency: the partial unique index below allows at most ONE *open* (resolved_at IS NULL)
# action per (project_id, kind) — a repeated same-cause signal refreshes it instead of duplicating;
# a re-open after resolution is a fresh row. `evidence` JSONB carries the cause specifics
# (stage/idle/signature/linear_issue); `resolution` is the terminal outcome.
recovery_actions = Table(
    "recovery_actions", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("project_id", Text, nullable=False),
    Column("kind", Text, nullable=False),               # dead_stage | silent_run | budget_exhausted | ...
    Column("owner", Text, nullable=False, server_default="auto"),   # "auto" | operator email
    Column("cause", Text, nullable=False, server_default=""),
    Column("evidence", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("opened_at", Float, nullable=False),
    Column("resolved_at", Float),                        # NULL while open
    Column("resolution", Text),                          # restored|delegated|false_positive|blocked|escalated|cancelled
)
# At most one OPEN action per (project_id, kind) — the DB-enforced idempotency the open() upsert's
# ON CONFLICT arbiter must match EXACTLY (index_elements + this same predicate), or the upsert
# throws "no unique or exclusion constraint matching" on the first real conflict.
Index("uq_recovery_open_project_kind", recovery_actions.c.project_id, recovery_actions.c.kind,
      unique=True, postgresql_where=recovery_actions.c.resolved_at.is_(None))

# SOF-102 (B5) — eval-judge scores. One row per benchmark run (project_id PK); trends come from
# querying rows across runs (group by brief_title, order by scored_at). Global, like the autopsy
# ledgers. `by_stage`/`detail` are JSONB: by_stage = {stage bucket: miss count}, detail = the full
# scored criteria + screen diffs (the evidence behind the aggregate score).
eval_scores = Table(
    "eval_scores", metadata,
    Column("project_id", Text, primary_key=True),
    Column("brief_title", Text, nullable=False, server_default=""),
    Column("total", Integer, nullable=False, server_default="0"),
    Column("passed", Integer, nullable=False, server_default="0"),
    Column("score", Float, nullable=False, server_default="0"),
    Column("by_stage", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("detail", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("scored_at", Float, nullable=False),
)

# Groupings: the flat per-project tables, the global directory tables, and everything (Alembic + tests).
PROJECTDB = (projectstate, phases, artifacts, blockers, gates, verifications, deployments)
FLAT_TABLES = PROJECTDB + (tickets, runtime_agents, checkpoint)
GLOBAL_TABLES = (roles, role_permissions, organizations, users, blobs, blob_uses,
                 system_agents, tools, recipes,
                 doc_summary, chunk, conversation, org_secrets,
                 autopsy_processed_runs, autopsy_signatures, eval_scores, recovery_actions)
ALL_TABLES = FLAT_TABLES + GLOBAL_TABLES
