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
    "budget_ceiling", "held", "owner",
    "brief", "interview_coverage", "scope", "is_demo", "archived",
    "created_by", "created_at",
}


@dataclass
class ProjectState:
    project_id: str
    phase: str = "provision"
    spent_usd: float = 0.0
    repo_url: Optional[str] = None
    deploy_url: Optional[str] = None
    # Proof marker — stamped at provision so the run carries a receipt of which skill drove it.
    skill: Optional[str] = None
    skill_version: Optional[str] = None
    description: Optional[str] = None
    name: str = ""  # operator-chosen project name (display label; project_id stays the key)
    deploy_target: Optional[str] = None
    creds_provided: list = field(default_factory=list)  # cred NAMES only, never values
    stage: int = 1
    stage1_done: bool = False
    stage2_done: bool = False
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
    held: bool = False  # gated hold: created but NOT launched until released (survives restarts)
    owner: str = ""  # email of the creating user; members see only their own runs (admins see all)
    # Structured onboarding brief (see brief.BRIEF_SECTIONS) + per-section covered flags. Accumulated
    # during the pre-run interview (phase == "draft") and injected into the Stage-1 PRD prompt.
    brief: dict = field(default_factory=dict)
    interview_coverage: dict = field(default_factory=dict)
    # Option C "scope of work" selections (e.g. ["Quoting / RFQ", ...]). NOT a brief section —
    # the structured backing for the project description: description = compose(brief.goals, scope),
    # recomposed idempotently whenever goal or scope changes via Console.set_draft_project.
    scope: list = field(default_factory=list)

    # Tenexity OS REAL/DEMO toggle (§3.3). False = real customer project; True = demo/internal.
    is_demo: bool = False

    # Soft-delete: archived projects are hidden from every listing (DELETE /api/runs/{id}).
    archived: bool = False
    # IMMUTABLE creator attribution — set ONCE at creation, NEVER mutated (unlike `owner`, which is the
    # reassignable current owner). created_by = the email that created the project; created_at = epoch.
    created_by: str = ""
    created_at: float = 0.0
    _store: Optional[Store] = field(default=None, repr=False, compare=False)

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
