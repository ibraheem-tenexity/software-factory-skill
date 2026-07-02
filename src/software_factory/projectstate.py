"""Resumable run state.

The orchestrator is a `/loop` session: each re-entry loads state, does a slice of work,
and saves. A crash or loop tick therefore resumes instead of restarting. The store is a
small pluggable interface — JSON on disk for tests, the per-project project store (ProjectStore) in real runs.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields
from typing import Optional, Protocol


class Store(Protocol):
    def read(self, project_id: str) -> Optional[dict]: ...
    def write(self, project_id: str, data: dict) -> None: ...


class JsonFileStore:
    """One JSON file per run, under `dir`."""

    def __init__(self, dir: str):
        self._dir = dir
        os.makedirs(dir, exist_ok=True)

    def _path(self, project_id: str) -> str:
        return os.path.join(self._dir, f"{project_id}.json")

    def read(self, project_id: str) -> Optional[dict]:
        try:
            with open(self._path(project_id)) as f:
                return json.load(f)
        except FileNotFoundError:
            return None

    def write(self, project_id: str, data: dict) -> None:
        with open(self._path(project_id), "w") as f:
            json.dump(data, f, indent=2)


_PERSISTED = {
    "project_id", "phase", "spent_usd", "repo_url", "deploy_url",
    "skill", "skill_version", "description", "name", "deploy_target", "creds_provided",
    "stage", "stage1_done", "stage2_done", "runtime",
    "planning_model", "impl_model", "opencode_model",
    "deps_required", "deps_provided", "deps_satisfied", "deps_disposition",
    "budget_ceiling", "deploy_db_attempts", "deploy_db_service_id", "deploy_db_volume_id", "held", "owner",
    "goal", "scope", "is_demo", "archived",
    "summary",
    "created_by", "created_at",
    "creds_vault_ids",
    "paused_at_node", "crashed_at_node",
    "relaunched_from",
    "log_url",
    "owner_github_username",
    "launch_attempted",
    "ingestion_spent_usd",
    "memory_overview",
    "reflection_questions",
    "concierge_notes",
}


@dataclass
class ProjectState:
    project_id: str
    phase: str = "provision"
    spent_usd: float = 0.0
    # SOF-27: console-side ingestion spend (embedding/summarization/extraction), accumulated
    # separately from spent_usd. It must NOT live in spent_usd: Console._cost() overwrites
    # spent_usd wholesale from project.log's own cost every time it reparses the log, which
    # would silently clobber any ingestion charge folded in there. See Console._project_spend.
    ingestion_spent_usd: float = 0.0
    # SOF-32: the cached project-overview rollup (coarse "2,000-ft view" over this project's
    # ready doc_summary rows) — no third table, per the locked decision (build-plan §7 #4).
    # T3.1's MemoryStore.overview() reads this same key directly off the raw projectstate.data
    # JSON blob (not through ProjectState) — both paths agree because ProjectState.save() writes
    # this field into that same blob.
    memory_overview: str = ""
    # SOF-37/SOF-60: interview questions the Concierge raises from its own analysis (the
    # trust gate) — [{id, fact, document_blob_id, section_path_claimed,
    # status: "open"|"answered"|"dismissed", answer, created_at}]. promote_draft
    # refuses to hand off while any entry here has status="open".
    reflection_questions: list = field(default_factory=list)
    # Durable facts the Concierge saves during the interview via its write_to_project_memory tool
    # (concierge-agent-spec.md §5). Persisted into the same projectstate.data JSON blob as
    # memory_overview — the "no third table" pattern — and read back by get_from_project_memory.
    concierge_notes: list = field(default_factory=list)
    # SOF-63 NOTE: the Concierge's finalized product brief is NOT state — it's the
    # kind='product_brief' ARTIFACT (markdown in artifacts.content, newest row wins; written by
    # finalize_product_brief, read by Console.product_brief). At promote it supersedes
    # make_prompt's raw composition as the Stage-1 context.md (input_pipeline.persist_and_compose).
    repo_url: Optional[str] = None
    deploy_url: Optional[str] = None
    # Proof marker — stamped at provision so the run carries a receipt of which skill drove it.
    skill: Optional[str] = None
    skill_version: Optional[str] = None
    description: Optional[str] = None
    name: str = ""  # operator-chosen project name (display label; project_id stays the key)
    summary: Optional[str] = None  # customer-facing project summary (populated externally; see CRUD)
    deploy_target: Optional[str] = None
    creds_provided: list = field(default_factory=list)  # cred NAMES only, never values
    creds_vault_ids: dict = field(default_factory=dict)  # {name: vault_uuid} — never plaintext
    stage: int = 1
    stage1_done: bool = False
    stage2_done: bool = False
    # SOF-23: set True the first time _launch_stage actually runs for this project (even if the
    # launch is then refused by a guard, e.g. a transient MCP health hiccup) — distinguishes a
    # real pipeline run from a project row seeded directly for a test/verify fixture, which never
    # goes through _launch_stage at all. See Console.auto_resume_dead_stage.
    launch_attempted: bool = False
    runtime: str = "claude"  # agent runtime for this run: claude | opencode; pinned at start_project
    # Operator-picked models, pinned at start_project (claude runtime; empty = stage defaults):
    # planning drives the S1/S2 orchestrators, impl drives S3.
    planning_model: str = ""
    impl_model: str = ""
    opencode_model: str = ""  # short alias for the opencode runtime model: "kimi" | "glm"; empty = default (kimi)
    deps_required: list = field(default_factory=list)
    deps_provided: list = field(default_factory=list)  # dep NAMES only, never values
    deps_satisfied: bool = False
    deps_disposition: dict = field(default_factory=dict)  # name -> provide|mock|mcp|env (metadata, safe on disk)
    budget_ceiling: Optional[float] = None  # per-project override of SF_COST_CEILING (SPEC §4, recoverable kill)
    deploy_db_attempts: int = 0  # provision-attempt counter — hard cap so a failure can't spawn unbounded DBs
    deploy_db_service_id: str = ""  # captured Railway Postgres serviceId — the durable teardown handle
    deploy_db_volume_id: str = ""   # captured Railway volume ID — must be deleted explicitly (service delete does NOT cascade)
    # Crash/pause recovery — set by the console when it halts a stage.
    # Operator-driven recovery (Recovery bar) resumes from these; auto-resume is suppressed.
    paused_at_node: str = ""   # pipeline node where pause was requested
    crashed_at_node: str = ""  # pipeline node where an unexpected process exit was detected
    held: bool = False  # gated hold: created but NOT launched until released (survives restarts)
    owner: str = ""  # email of the creating user; members see only their own runs (admins see all)
    # SOF-3: the owner's GitHub handle — self-declared, unverified (GitHub's own collaborator-invite
    # accept, via the owner's real GitHub login, is the verification). Populated upstream of this
    # ticket's scope; empty means "no username on file" (Stage 1 records a blocker, does not skip).
    # Whether the invite succeeded is NOT mirrored here — like demo-creds, it's a recorded
    # 'repo-shared' artifact (see console.repo_shared_with_owner), the single source of truth.
    owner_github_username: str = ""
    # The plain project goal (one prose answer from intake). The structured brief is the
    # Concierge-authored product_brief ARTIFACT (kind='product_brief'), not state.
    goal: str = ""
    # Option C "scope of work" selections (e.g. ["Quoting / RFQ", ...]) — the structured backing
    # for the project description: description = compose(goal, scope), recomposed idempotently
    # whenever goal or scope changes via Console.set_draft_project.
    scope: list = field(default_factory=list)

    # Tenexity OS REAL/DEMO toggle (§3.3). False = real customer project; True = demo/internal.
    is_demo: bool = False

    # Soft-delete: archived projects are hidden from every listing (DELETE /api/runs/{id}).
    archived: bool = False
    # IMMUTABLE creator attribution — set ONCE at creation, NEVER mutated (unlike `owner`, which is the
    # reassignable current owner). created_by = the email that created the project; created_at = epoch.
    created_by: str = ""
    created_at: float = 0.0
    relaunched_from: str = ""  # source project_id if this run was minted via /relaunch
    log_url: Optional[str] = None  # Supabase Storage URL of the latest uploaded project.log snapshot
    _store: Optional[Store] = field(default=None, repr=False, compare=False)

    @classmethod
    def from_data(cls, project_id: str, data: dict) -> "ProjectState":
        """Hydrate a ProjectState from a plain dict (used by batch loaders).

        The returned instance has no backing ``_store``, so it is read-only: any code that
        needs to save must go through ``ProjectState.load(store)`` instead.
        """
        known = {k: v for k, v in data.items() if k in _PERSISTED}
        known["project_id"] = project_id
        return cls(_store=None, **known)

    @classmethod
    def load(cls, project_id: str, store: Store) -> "ProjectState":
        data = store.read(project_id) or {}
        known = {k: v for k, v in data.items() if k in _PERSISTED}
        known["project_id"] = project_id  # the id is authoritative from the caller, not the file
        return cls(_store=store, **known)

    def save(self) -> None:
        if self._store is None:
            raise RuntimeError("ProjectState has no store to save to")
        payload = {f.name: getattr(self, f.name) for f in fields(self) if f.name in _PERSISTED}
        self._store.write(self.project_id, payload)
