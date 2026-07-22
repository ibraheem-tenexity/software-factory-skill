"""Per-run datastore — the source of truth the canvas projects from (Postgres, flat schema).

All runs share one set of tables keyed by ``project_id``: ProjectState (the ``projectstate`` table) plus the
canvas-projected tables ``phases``, ``artifacts``, ``blockers``, ``gates``, ``verifications``,
``deployments``. ``tickets`` and ``agents`` are the same flat model (TicketStore / AgentRegistry).
The ``path`` argument names the run directory + the ``project_id`` to scope by; storage is Postgres.

The headless orchestrator records canvas state by calling the CLI
(``python3 -m software_factory.db <verb> <projects_dir> <project_id> ...``) instead of emitting
events. ``Console.graph()`` projects nodes/edges by SELECTing these tables — the DB is the
single source of truth, never a separate event stream.
"""
from __future__ import annotations

import json
import logging
import os

import sys
import time
import weakref
from typing import Optional

from sqlalchemy import delete as _sa_delete

from .constants import PROJECT_ID_RE as _PROJECT_ID_RE
from .constants import PROJECT_ID_STRICT_RE as _PROJECT_ID_STRICT_RE
from .repositories._exec import PathExec
from .repositories.canvas import (ProjectStateRepository, PhaseRepository, ArtifactRepository,
                                       BlockerRepository, GateRepository, VerificationRepository,
                                       DeploymentRepository)

logger = logging.getLogger(__name__)


def db_path(projects_dir: str, project_id: str) -> str:
    return os.path.join(projects_dir, project_id)


def project_id_from_path(path: str) -> str:
    """The run id a store at `path` belongs to — normally the basename of `<projects_dir>/<project_id>`.

    If an agent passes a file path (e.g. `.../<project_id>/project.db`), derive the id from the
    parent directory instead. In that file-like case the parent *must* be a valid project id,
    so `project.db` can never become a project_id and leak across runs.
    """
    normalized = path.rstrip("/")
    leaf = os.path.basename(normalized)
    if _PROJECT_ID_RE.fullmatch(leaf):
        return leaf
    # File-like leaf (e.g. project.db) — derive from the containing run directory and validate it.
    if "." in leaf and not leaf.startswith("."):
        parent = os.path.basename(os.path.dirname(normalized))
        if _PROJECT_ID_RE.fullmatch(parent):
            return parent
        raise ValueError(
            f"could not derive a valid project_id from path {path!r} "
            f"(file-like leaf={leaf!r}, parent={parent!r})"
        )
    return leaf


class ProjectStore:
    """The run datastore (Postgres). In the flat schema all runs share one set of tables keyed
    by ``project_id``. Also implements the ProjectState ``Store`` protocol (``read``/``write``) via the
    ``projectstate`` table."""

    def __init__(self, path: str):
        os.makedirs(path or ".", exist_ok=True)
        self._project_id = project_id_from_path(path)
        # Postgres; schema owned by Alembic (prod) / tests. All SQL is in repositories/canvas.py.
        self._exec = PathExec(path)  # per-call checkout — nothing is held between statements
        # Live getter via a WEAKREF, not a closure over `self` directly: a closure capturing `self`
        # and stored on an attribute `self` owns (self._phase_repo, etc.) is a reference CYCLE — CPython
        # won't return the pooled connection to dbshim's pool until the cyclic GC eventually runs,
        # which exhausts the pool under any call site that constructs many short-lived ProjectStores
        # (e.g. gates.py's per-call `_db_for()`). weakref.ref breaks the cycle; the store always
        # outlives its own repos, so the ref is never dead when the getter is actually called.
        _self_ref = weakref.ref(self)
        get_pid = lambda: _self_ref()._project_id
        self._projectstate_repo = ProjectStateRepository(self._exec)
        self._phase_repo = PhaseRepository(self._exec, get_pid)
        self._artifact_repo = ArtifactRepository(self._exec, get_pid)
        self._blocker_repo = BlockerRepository(self._exec, get_pid)
        self._gate_repo = GateRepository(self._exec, get_pid)
        self._verification_repo = VerificationRepository(self._exec, get_pid)
        self._deployment_repo = DeploymentRepository(self._exec, get_pid)

    # ---- ProjectState Store protocol (the projectstate table) --------------------------------
    def read(self, project_id: str) -> Optional[dict]:
        row = self._projectstate_repo.by_project(project_id)
        if not row:
            return None
        data = json.loads(row["data"])
        data["name"] = row["name"]
        data["summary"] = row["summary"]
        return data

    def write(self, project_id: str, data: dict) -> None:
        # name/summary live in dedicated columns, not the JSON blob — pop them off a copy so the
        # persisted `data` never carries duplicates; the columns are the source of truth.
        blob = dict(data)
        name = blob.pop("name", None)
        summary = blob.pop("summary", None)
        self._projectstate_repo.upsert(project_id, json.dumps(blob), name, summary)

    def delete_project(self, project_id: str) -> None:
        """Permanently remove every flat-schema row for this run (projectstate + the per-project
        tables). Dropping the projectstate row is what stops the run reappearing from the registry
        (dbshim.registry_projects reads that table). Idempotent — deleting a gone run is a no-op."""
        from .models import FLAT_TABLES
        for table in FLAT_TABLES:
            self._exec.execute(_sa_delete(table).where(table.c.project_id == project_id))

    # ---- canvas-state writes (used by the CLI the orchestrator calls) ----------------
    def set_phase(self, name: str, status: str = "active", stage: Optional[int] = None) -> None:
        self._phase_repo.insert(name, status, stage, time.time())

    def record_artifact(self, title: str, path: str, kind: Optional[str] = None,
                        agent: Optional[str] = None, *, content: Optional[str] = None,
                        source_blob_id: Optional[int] = None, origin: Optional[str] = None) -> None:
        self._artifact_repo.insert(title, path, kind, agent, time.time(),
                                   content=content, source_blob_id=source_blob_id, origin=origin)

    def add_blocker(self, what: str, blocks: Optional[str] = None) -> None:
        self._blocker_repo.insert(what, blocks, time.time())

    def clear_blocker(self, what: str) -> None:
        self._blocker_repo.clear(what)

    def set_gate(self, name: str, status: str) -> None:
        self._gate_repo.upsert(name, status, time.time())

    def record_verification(self, url: str, passed: bool, result) -> None:
        self._verification_repo.insert(
            url, 1 if passed else 0, result if isinstance(result, str) else json.dumps(result),
            time.time())

    def record_deployment(self, app: str, url: str, status: str = "live",
                          service_name: Optional[str] = None, verified: bool = False) -> None:
        """Record one deliverable's deployment. A run ships 1..N deliverables (mobile-web/web/api),
        so deploy state is per-app, not a single run-level deploy_url. The deploy step and the later
        verify step both call this for the SAME (app, url) — update that row in place rather than
        inserting a sibling (SOF-219: the verify call was inserting a duplicate row differing only
        in `verified`)."""
        ts = time.time()
        if self._deployment_repo.find(app, url) is not None:
            self._deployment_repo.update_existing(app, url, service_name, status, 1 if verified else 0, ts)
        else:
            self._deployment_repo.insert(app, service_name, url, status, 1 if verified else 0, ts)

    # ---- projection reads (scoped to this run) ---------------------------------------
    def phase_status(self) -> dict:
        """Latest status per phase name (rows are append-only; last write wins)."""
        out: dict = {}
        for r in self._phase_repo.all_for_project():
            out[r["name"]] = r["status"]
        return out

    def phases(self) -> list[dict]:
        return [dict(r) for r in self._phase_repo.all_for_project()]

    def artifacts(self) -> list[dict]:
        return [dict(r) for r in self._artifact_repo.all_for_project()]

    def artifact_by_path(self, path: str) -> Optional[dict]:
        """The artifact row recorded at `path` (or None). SOF-138: the read path prefers the inline
        `content` column here over the workspace file, so a produced artifact survives teardown."""
        row = self._artifact_repo.by_path(path)
        return dict(row) if row else None

    def delete_artifacts_by_paths(self, paths: list[str]) -> None:
        self._artifact_repo.delete_paths(paths)

    def blockers(self) -> list[dict]:
        return [dict(r) for r in self._blocker_repo.all_for_project()]

    def gate_status(self) -> dict:
        return {r["name"]: r["status"] for r in self._gate_repo.all_for_project()}

    def verifications(self) -> list[dict]:
        return [dict(r) for r in self._verification_repo.all_for_project()]

    def has_passing_verification(self) -> bool:
        return self._verification_repo.passing_count() > 0

    def deployments(self) -> list[dict]:
        return [dict(r) for r in self._deployment_repo.all_for_project()]


def artifact_by_id(artifact_id: int) -> Optional[dict]:
    """Look up a single artifact row by its primary-key id (cross-project).
    Returns None when the id is unknown. Used by GET /api/artifacts/{id}."""
    repo = ArtifactRepository(PathExec(os.environ["SF_RUNS_DIR"]), lambda: None)  # id lookup, unscoped
    row = repo.by_id_global(artifact_id)
    return dict(row) if row else None


# --- CLI the headless orchestrator uses instead of emitting events --------------------
# SOF-138 follow-up: cap how much artifact text we inline into the DB `content` column at record
# time. Produced docs are KB; this is a sanity ceiling so a pathologically large file falls back to
# path-only rather than bloating the row (the read side already caps its own output at 200k chars).
_MAX_INLINE_ARTIFACT_BYTES = 1_000_000

_USAGE = (
    "usage: python3 -m software_factory.db <verb> <projects_dir> <project_id> [args]\n"
    "  (<projects_dir> <project_id> ALWAYS come first, before the verb's own args)\n"
    "  set-phase <projects_dir> <project_id> <name> [status]\n"
    "  record-artifact <projects_dir> <project_id> <title> <path> [kind] [agent]\n"
    "  add-blocker <projects_dir> <project_id> <what> [blocks]\n"
    "  clear-blocker <projects_dir> <project_id> <what>\n"
    "  record-verification <projects_dir> <project_id> <url> <passed:0|1> <result-json>\n"
    "  record-deployment <projects_dir> <project_id> <app> <url> [status] [service_name] [verified:0|1]\n"
    "  spawn-agent <projects_dir> <project_id> <agent_id> <role> <model> [phase] [ticket_id]\n"
    "  finish-agent <projects_dir> <project_id> <agent_id> <outcome> [cost_usd] [provenance] [diff_lines]\n"
    "                         provenance = PR number or commit SHA; type inferred (digits='pr', else='commit')\n"
    "  claim <projects_dir> <project_id> <ticket_id> <agent>\n"
    "  mark-done <projects_dir> <project_id> <ticket_id> <provenance> <diff_lines> <decision_log_json>\n"
    "                         decision_log_json = a JSON array of {type, statement, reason,\n"
    "                         affected_surface} objects, or '[]' for an honest 'nothing to declare'\n"
    "                         — REQUIRED, mark-done refuses a hollow close without it (SOF-118)\n"
    "  mark-deployed <projects_dir> <project_id> <ticket_id>\n"
    "  start-qa <projects_dir> <project_id> <ticket_id>\n"
    "  qa-approve <projects_dir> <project_id> <ticket_id>\n"
    "  qa-reject <projects_dir> <project_id> <ticket_id> <bug_markdown>   (ticket → open, carries the bug report)\n"
    "  provision-db <projects_dir> <project_id>   (stage-3: create this run's Railway Postgres; writes context/deploy-db.json)\n"
    "  provision-repo <projects_dir> <project_id> <slug>   (stage-1/stage-3: create-or-reuse this project's ONE canonical GitHub repo)\n"
)


def _provision_db(projects_dir: str, project_id: str) -> int:
    """Provision (or resume) this run's deploy database and persist its teardown handles to
    ProjectState — the stage-3 agent calls this exactly once. Wraps the proven
    ``deploy_db.provision()`` (railway add → DATABASE_URL → context/deploy-db.json); does NOT
    reimplement it. On success: persist ``deploy_db_service_id`` (+ ``deploy_db_volume_id`` if
    present) so the reaper can tear the DB down later, and record the "Deploy DB" artifact. On
    failure: salvage any partial serviceId provision() wrote to disk before raising (so the reaper
    still finds it), print the error, and return non-zero so the agent can add-blocker + STOP."""
    from . import deploy_db
    from .projectstate import ProjectState
    base = db_path(projects_dir, project_id)
    # Resolve the run's context/ dir: the stage workspace's context/ holds deploy-db.json, the same
    # file the agent then reads for DATABASE_URL. The verb runs in the agent's cwd (the workspace),
    # so context/ is relative to it.
    ctx = os.path.join(os.getcwd(), "context")
    info_path = os.path.join(ctx, deploy_db.DEPLOY_DB_FILE)
    db = ProjectStore(base)
    state = ProjectState.load(project_id, db)
    # SOF-159: a marker still set from a prior attempt with no captured handle means that attempt was
    # killed mid-`railway add` (Railway created the Postgres, the CLI never returned an id) — surface
    # it so the reconciliation reporter/operator can reclaim that orphan. This attempt still proceeds.
    if state.deploy_db_pending and not state.deploy_db_service_id:
        sys.stderr.write(
            f"provision-db: WARNING prior provision (attempt {state.deploy_db_pending.get('attempt')}, "
            f"started {state.deploy_db_pending.get('started_at')}) left a pending marker with no serviceId "
            f"— it may have orphaned a Postgres; flag for reconciliation.\n")
    # Durable breadcrumb written BEFORE the create call: if this process is SIGKILLed during
    # `railway add` (SOF-116 console-deploy kill / OOM / timeout — none catchable by the except
    # below), this marker is the ONLY durable record that a DB may have been created for this
    # project. deploy-db.json is workspace-local and, in the kill-mid-add case, never gets written.
    state.deploy_db_pending = {"started_at": time.time(), "attempt": state.deploy_db_attempts + 1}
    state.save()
    try:
        info = deploy_db.provision(project_id, ctx)
        # Persist the captured serviceId as the DURABLE teardown handle: the reaper needs it even
        # after this run's context dir (which also holds it) is gone.
        if info.get("service_id"):
            state.deploy_db_service_id = info["service_id"]
        if info.get("volume_id"):
            state.deploy_db_volume_id = info["volume_id"]
        state.deploy_db_pending = {}  # SOF-159: handle captured → clear the in-flight breadcrumb
        state.save()
        db.record_artifact("Deploy DB", "context/" + deploy_db.DEPLOY_DB_FILE, kind="deploy-db")
        return 0
    except Exception as e:
        # Salvage the serviceId if provision() wrote it to disk before failing (created-but-not-
        # URL-fetched), so the reaper can still tear it down.
        try:
            with open(info_path) as _pf:
                _partial = json.load(_pf)
            if _partial.get("service_id") and not state.deploy_db_service_id:
                state.deploy_db_service_id = _partial["service_id"]
            if state.deploy_db_service_id:
                state.deploy_db_pending = {}  # SOF-159: salvaged a handle → clear the breadcrumb
            state.save()  # else the pending marker STAYS set — the breadcrumb for reconciliation
        except Exception:
            logger.exception("[provision-db] failed to salvage partial serviceId for project %s",
                             project_id)
        logger.exception("[provision-db] provision failed for project %s", project_id)
        sys.stderr.write(f"provision-db failed: {e}\n")
        return 1


def _provision_repo(projects_dir: str, project_id: str, slug: str) -> int:
    """Create-or-reuse this project's ONE canonical GitHub repo (SOF-22). Both stage-1 and
    stage-3 call this exact same verb — idempotent, so a run never ends up with two repos
    from two independent SKILL-driven creation paths.

    First call: compute the canonical name as "<slug>-<first 8 hex chars of the project_id>"
    (HOST-computed, not left to the agent, so the hex suffix github_repo_reaper's suffix-fallback
    depends on can never be dropped or mistyped), create it, persist ``state.repo_url``, and
    record the "GitHub Repo" artifact exactly once — in Python, so the SKILL instruction on
    either stage can never double-record it.

    A later call (a retry, or stage-3 running after stage-1 already provisioned): repo_url is
    already set — no second repo, no second artifact row. Clone it into the caller's cwd if it
    isn't already checked out there (create_repo's own --clone only benefited the FIRST caller's
    workspace; a later stage's fresh workspace needs its own clone of the same repo)."""
    from .repo import GitHub
    from .projectstate import ProjectState
    base = db_path(projects_dir, project_id)
    db = ProjectStore(base)
    state = ProjectState.load(project_id, db)
    if state.repo_url:
        # SOF-44: both create_repo's own --clone and clone_repo() (`gh repo clone <url>`) clone
        # into a NEW ./<repo-name>/ subdirectory, never into cwd itself — checking os.path.isdir
        # (".git") was always False after a real clone, so a retry from an already-cloned
        # workspace re-attempted clone_repo unnecessarily every time (harmless — clone_repo
        # doesn't check/raise on failure — but wasted work). Derive the actual clone target from
        # the recorded repo_url instead of assuming cwd.
        repo_name = state.repo_url.rstrip("/").rsplit("/", 1)[-1]
        if not os.path.isdir(os.path.join(repo_name, ".git")):
            GitHub().clone_repo(state.repo_url)
        print(state.repo_url)
        return 0
    hex_part = project_id[len("project-"):]
    name = f"{slug}-{hex_part[:8]}"
    url = GitHub().create_repo(name)
    if not url:
        sys.stderr.write(f"provision-repo failed: gh repo create returned no url for {name!r}\n")
        return 1
    state.repo_url = url
    state.save()
    db.record_artifact("GitHub Repo", url, kind="repo")
    _invite_repo_owner(db, state)
    print(url)
    return 0


def _clear_repo_access_blockers(db: ProjectStore) -> None:
    for blocker in db.blockers():
        if blocker.get("blocks") == "github-access" and not blocker.get("cleared"):
            db.clear_blocker(blocker["what"])


def _invite_repo_owner(db: ProjectStore, state) -> dict:
    """Invite the saved owner handle and record only facts GitHub has confirmed.

    A repository is still usable by the factory when this fails, so `github-access` is visible
    without becoming a lifecycle stop. `repo-shared` remains the reaper's durable proof that the
    owner received access.
    """
    username = (state.owner_github_username or "").strip().lstrip("@")
    if not username:
        return {"status": "not_requested", "detail": "No GitHub username has been provided."}
    if not state.repo_url:
        return {"status": "waiting_for_repo", "detail": "The invitation will be sent when the repository is created."}

    from .repo import GitHub
    parts = state.repo_url.rstrip("/").rsplit("/", 2)
    if len(parts) < 3:
        detail = f"Repository URL is not valid: {state.repo_url}"
        _clear_repo_access_blockers(db)
        db.add_blocker(f"GitHub Access: invite to @{username} failed: {detail}", "github-access")
        return {"status": "failed", "detail": detail, "repo_url": state.repo_url,
                "github_username": username}
    repo = "/".join(parts[-2:])
    result = GitHub().invite_collaborator(repo, username)
    if result.returncode == 0:
        _clear_repo_access_blockers(db)
        if not any((a.get("kind") or "").lower() == "repo-shared" for a in db.artifacts()):
            db.record_artifact("Owner Repo Access", state.repo_url, kind="repo-shared")
        return {"status": "invited", "detail": f"GitHub invited @{username} to this repository.",
                "repo_url": state.repo_url, "github_username": username}

    detail = (result.stderr or result.stdout or f"gh exited with status {result.returncode}").strip()
    _clear_repo_access_blockers(db)
    db.add_blocker(f"GitHub Access: invite to @{username} failed: {detail}", "github-access")
    return {"status": "failed", "detail": detail, "repo_url": state.repo_url,
            "github_username": username}


def request_repo_access(projects_dir: str, project_id: str, github_username: str) -> dict:
    """Save an owner's GitHub handle and issue its invite now when a repository exists."""
    from .projectstate import ProjectState
    db = ProjectStore(db_path(projects_dir, project_id))
    state = ProjectState.load(project_id, db)
    state.owner_github_username = (github_username or "").strip().lstrip("@")
    state.save()
    return _invite_repo_owner(db, state)


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        sys.stderr.write(_USAGE)
        return 2
    verb, projects_dir, project_id, rest = argv[0], argv[1], argv[2], argv[3:]
    # Reject malformed run ids BEFORE constructing ProjectStore — connecting has a side effect
    # (dbshim._ensure runs CREATE SCHEMA in pg mode). A wrong arg order (e.g. junk landing
    # in the project_id slot) must never create a prod schema.
    if not _PROJECT_ID_STRICT_RE.fullmatch(project_id):
        sys.stderr.write(
            f"error: project_id {project_id!r} is not a valid factory run id (project-XXXXXXXX); "
            "args go <verb> <projects_dir> <project_id> [args]\n"
        )
        sys.stderr.write(_USAGE)
        return 2
    if verb == "provision-db":
        return _provision_db(projects_dir, project_id)
    if verb == "provision-repo":
        return _provision_repo(projects_dir, project_id, rest[0])
    db = ProjectStore(db_path(projects_dir, project_id))
    if verb == "set-phase":
        db.set_phase(rest[0], rest[1] if len(rest) > 1 else "active")
    elif verb == "record-artifact":
        _path = rest[1]
        _content = None
        if not _path.startswith("http://") and not _path.startswith("https://"):
            if not os.path.exists(_path):
                sys.stderr.write(f"error: record-artifact: file not found: {_path!r}\n")
                return 1
            # SOF-138: persist the artifact's CONTENT inline at record time, so a produced document
            # survives workspace teardown (the read path no longer depends on the file still being
            # on disk). Follow-up guards: skip BINARY files (a NUL byte → storing a decoded blob
            # would be mojibake; leave content NULL and fall back to the path) and skip files over
            # the inline cap (path-only). Text is decoded utf-8 with errors="replace".
            try:
                if os.path.getsize(_path) <= _MAX_INLINE_ARTIFACT_BYTES:
                    with open(_path, "rb") as f:
                        raw = f.read()
                    if b"\x00" not in raw:
                        _content = raw.decode("utf-8", errors="replace")
            except OSError:
                # Best-effort inline content: on a read error the artifact still records path-only.
                # Log the traceback so a read failure isn't invisible behind the fallback.
                logger.exception("[record-artifact] could not inline content of %r (recording path-only)",
                                 _path)
                _content = None
        db.record_artifact(rest[0], _path,
                           rest[2] if len(rest) > 2 else None,
                           rest[3] if len(rest) > 3 else None,
                           content=_content)
    elif verb == "add-blocker":
        db.add_blocker(rest[0], rest[1] if len(rest) > 1 else None)
    elif verb == "clear-blocker":
        db.clear_blocker(rest[0])
    elif verb == "record-verification":
        db.record_verification(rest[0], rest[1] in ("1", "true", "True"), rest[2])
    elif verb == "record-deployment":
        db.record_deployment(
            rest[0], rest[1],
            status=rest[2] if len(rest) > 2 else "live",
            service_name=rest[3] if len(rest) > 3 else None,
            verified=(len(rest) > 4 and rest[4] in ("1", "true", "True")),
        )
    elif verb == "spawn-agent":
        from .runtime_agents import AgentRegistry
        agent_id, role, model = rest[0], rest[1], rest[2]
        phase = rest[3] if len(rest) > 3 and rest[3] not in ("", "-") else None
        ticket_id = int(rest[4]) if len(rest) > 4 and rest[4] not in ("", "-") else None
        AgentRegistry(db_path(projects_dir, project_id)).spawn(agent_id, project_id, ticket_id, role, model, phase=phase)
    elif verb == "finish-agent":
        from .runtime_agents import AgentRegistry
        agent_id, outcome = rest[0], rest[1]
        cost = float(rest[2]) if len(rest) > 2 and rest[2] not in ("", "-") else 0.0
        provenance = rest[3] if len(rest) > 3 and rest[3] not in ("", "-") else None
        diff_lines = int(rest[4]) if len(rest) > 4 and rest[4] not in ("", "-") else 0
        AgentRegistry(db_path(projects_dir, project_id)).record(agent_id, outcome, cost_usd=cost,
                                                        provenance=provenance,
                                                        diff_lines=diff_lines)
    elif verb in ("claim", "mark-done", "mark-deployed", "start-qa", "qa-approve", "qa-reject"):
        from .tickets import TicketStore
        ts = TicketStore(db_path(projects_dir, project_id))
        tid = int(rest[0])
        if verb == "claim":
            ts.claim(tid, rest[1])
        elif verb == "mark-done":
            decision_log = json.loads(rest[3]) if len(rest) > 3 and rest[3] not in ("", "-") else None
            ts.mark_done(tid, rest[1], int(rest[2]), decision_log=decision_log)
        elif verb == "mark-deployed":
            ts.mark_deployed(tid)
        elif verb == "start-qa":
            ts.start_qa(tid)
        elif verb == "qa-approve":
            ts.qa_approve(tid)
        elif verb == "qa-reject":
            ts.qa_reject(tid, rest[1])
    else:
        sys.stderr.write(_USAGE)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
