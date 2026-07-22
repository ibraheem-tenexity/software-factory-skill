"""Durable project intake: drafts, attached materials, and repository access."""
from __future__ import annotations

import os
import time
from typing import Callable

from .. import storage, vault
from ..constants import IMPL_MODELS, OPENCODE_MODEL_IDS, PLANNING_MODELS
from ..db import ProjectStore, request_repo_access
from ..input_pipeline import persist_and_compose
from ..log import get_logger
from ..projectstate import ProjectState

logger = get_logger(__name__)


def project_paths(projects_dir: str, project_id: str) -> dict:
    """Return the durable filesystem and store locations for one project."""
    base = os.path.join(projects_dir, project_id)
    # The flat Postgres tables are the source of truth: projectstate + tickets + agents + the
    # canvas-projected tables (phases/artifacts/blockers/gates/verifications), all keyed by project_id.
    return {
        "base": base,
        "state_dir": base,
        "db": base,
        "agents_db": base,
        "tickets_db": base,
        "input_dir": os.path.join(base, "input"),
    }


def compose_description(goal: str, scope=None) -> str:
    """Compose the canonical project description from its goal and work scope."""
    goal = (goal or "").strip()
    items = [item.strip() for item in (scope or []) if item and item.strip()]
    if not items:
        return goal
    line = "Scope of work: " + ", ".join(items) + "."
    return f"{goal}\n\n{line}" if goal else line


class ProjectIntake:
    """Own the pre-run project record and the materials gathered during onboarding."""

    def __init__(
        self,
        projects_dir: str,
        *,
        new_id: Callable[[], str],
        extract: Callable[[str], str],
        skill_version: str,
    ):
        self._projects_dir = projects_dir
        self._new_id = new_id
        self._extract = extract
        self._skill_version = skill_version

    def _paths(self, project_id: str) -> dict:
        return project_paths(self._projects_dir, project_id)

    def _load_state(self, project_id: str) -> ProjectState:
        return ProjectState.load(project_id, ProjectStore(self._paths(project_id)["db"]))

    def create_draft(self, owner: str = "", name: str = "", runtime: str = "",
                     planning_model: str = "", impl_model: str = "", model: str = "",
                     budget: float | None = None, github_username: str = "") -> str:
        """Create a poller-invisible draft with the canonical project identifier."""
        project_id = self._new_id()
        paths = self._paths(project_id)
        os.makedirs(paths["base"], exist_ok=True)
        ProjectStore(paths["db"]).set_phase("draft", "active")
        state = self._load_state(project_id)
        state.phase = "draft"
        state.held = True
        state.skill = "software-factory"
        state.skill_version = self._skill_version
        state.name = name or ""
        state.owner = (owner or "").lower()
        state.owner_github_username = (github_username or "").strip().lstrip("@")
        if not state.created_by:
            state.created_by = (owner or "").lower()
            state.created_at = time.time()
        state.runtime = runtime or os.environ.get("SF_RUNTIME", "claude")
        state.planning_model = planning_model if planning_model in PLANNING_MODELS else ""
        state.impl_model = impl_model if impl_model in IMPL_MODELS else ""
        state.opencode_model = model if model in OPENCODE_MODEL_IDS else ""
        if budget is not None and float(budget) > 0:
            state.budget_ceiling = float(budget)
        state.save()
        return project_id

    def is_draft(self, project_id: str) -> bool:
        return self._load_state(project_id).phase == "draft"

    def product_brief(self, project_id: str) -> str | None:
        """Read the newest finalized product-brief artifact, if one exists."""
        paths = self._paths(project_id)
        rows = [artifact for artifact in ProjectStore(paths["db"]).artifacts()
                if (artifact.get("kind") or "") == "product_brief"]
        if not rows:
            return None
        row = rows[-1]
        content = row.get("content")
        if content:
            return content
        url = row.get("path") or ""
        if url:
            try:
                return storage.get_by_url(url).decode()
            except OSError:
                logger.exception("[intake] failed to read product brief for %s", project_id)
                return None
        return None

    def attach_to_draft(self, project_id: str, files: list) -> list[str]:
        """Persist + extract files attached during the interview into the draft's input/ (PDF/DOCX
        -> Markdown[+images], wireframes survive). Records .md extractions as context artifacts;
        original PDF/DOCX binaries are kept on disk for the caller to push to blob storage.
        The draft stays invisible to the poller (is_pipeline_project excludes drafts).
        Returns paths written (includes original binaries for PDF/DOCX so callers can blob-record).

        SOF-56: `tolerate_extract_failures=True` — a text-free/malformed attachment here must not
        500 the whole request (same failure-isolation principle SOF-32 applied to memory
        ingestion); unlike Stage-1 input, a mid-interview attachment failing to convert to Markdown
        does not mean the request itself failed — the original still gets blob-recorded and
        separately ingested (memory/ingest.py has its own graceful parse-failure handling)."""
        if not files:
            return []
        paths = self._paths(project_id)
        os.makedirs(paths["input_dir"], exist_ok=True)
        written = persist_and_compose(paths["input_dir"], "", files, extract=self._extract,
                                      tolerate_extract_failures=True)
        db = ProjectStore(paths["db"])
        for name in written:
            if name == "context.md":
                continue
            lowered = name.lower()
            if lowered.endswith(".pdf") or lowered.endswith(".docx"):
                continue
            db.record_artifact("input", "input/" + name, kind="context")
        return [name for name in written if name != "context.md"]

    def draft_project(self, project_id: str) -> dict:
        """Return the durable intake projection used to resume onboarding."""
        state = self._load_state(project_id)
        return {
            "name": state.name,
            "goal": state.goal or "",
            "scope": list(state.scope or []),
            "description": state.description or "",
            "budget": state.budget_ceiling,
            "runtime": state.runtime or "claude",
            "model": state.opencode_model or "kimi",
            "recipe_id": state.recipe_id or "",
            "github_username": state.owner_github_username or "",
        }

    def set_draft_project(self, project_id: str, name: str | None = None,
                          goal: str | None = None, scope: list | None = None,
                          runtime: str | None = None, model: str | None = None,
                          recipe_id: str | None = None, github_username: str | None = None) -> dict:
        """Update draft intake fields and recompute the canonical description."""
        state = self._load_state(project_id)
        if name is not None:
            state.name = name
        if runtime is not None:
            state.runtime = runtime
        if model is not None:
            state.opencode_model = model if model in OPENCODE_MODEL_IDS else ""
        if recipe_id is not None:
            state.recipe_id = recipe_id
        if github_username is not None:
            state.owner_github_username = github_username.strip().lstrip("@")
        if goal is not None:
            state.goal = goal
        if scope is not None:
            state.scope = list(scope)
        effective_goal = state.goal or ""
        effective_scope = state.scope or []
        if effective_goal or effective_scope:
            state.description = compose_description(effective_goal, effective_scope)
        state.save()
        return {
            "name": state.name,
            "goal": state.goal or "",
            "scope": list(state.scope or []),
            "description": state.description or "",
            "recipe_id": state.recipe_id or "",
            "github_username": state.owner_github_username or "",
        }

    def request_repo_access(self, project_id: str, github_username: str) -> dict:
        """Save a GitHub handle and invite it now when its repository exists."""
        return request_repo_access(self._projects_dir, project_id, github_username)

    def repo_access(self, project_id: str) -> dict:
        """Project the repository-access request and any recorded provider outcome."""
        state = self._load_state(project_id)
        db = ProjectStore(self._paths(project_id)["db"])
        username = (state.owner_github_username or "").strip()
        repo_url = state.repo_url or ""
        if any((artifact.get("kind") or "").lower() == "repo-shared" for artifact in db.artifacts()):
            return {"status": "invited", "detail": f"GitHub invited @{username} to this repository.",
                    "repo_url": repo_url, "github_username": username}
        failure = next((blocker for blocker in reversed(db.blockers())
                        if blocker.get("blocks") == "github-access" and not blocker.get("cleared")), None)
        if failure:
            return {"status": "failed", "detail": failure["what"].split(" failed: ", 1)[-1],
                    "repo_url": repo_url, "github_username": username}
        if not username:
            return {"status": "not_requested", "detail": "Add your GitHub username to receive repository access.",
                    "repo_url": repo_url, "github_username": ""}
        if not repo_url:
            return {"status": "waiting_for_repo", "detail": "The invitation will be sent when the repository is created.",
                    "repo_url": "", "github_username": username}
        return {"status": "ready", "detail": "Request the invitation to join this repository.",
                "repo_url": repo_url, "github_username": username}

    def store_draft_creds(self, project_id: str, credentials: dict) -> dict:
        """Vault-store onboarding credentials and persist only their names and vault IDs."""
        state = self._load_state(project_id)
        existing = dict(getattr(state, "creds_vault_ids", {}) or {})
        new_ids = {}
        for key_name, value in (credentials or {}).items():
            if not value:
                continue
            try:
                uid = vault.vault_store(f"byok-{project_id}-{key_name}", value)
                if uid:
                    new_ids[key_name] = uid
            except Exception:
                logger.exception(
                    "[vault] store failed for %s key %s; recording name only",
                    project_id,
                    key_name,
                )
        merged = {**existing, **new_ids}
        state.creds_vault_ids = merged
        state.creds_provided = sorted({*merged, *(key for key in credentials if credentials[key])})
        state.save()
        return {"creds_provided": state.creds_provided}
