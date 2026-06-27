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
import os

from . import dbshim
import sys
import time
from typing import Optional

from .constants import PROJECT_ID_RE as _PROJECT_ID_RE
from .constants import PROJECT_ID_STRICT_RE as _PROJECT_ID_STRICT_RE


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
        self._conn = dbshim.connect(path)  # Postgres; schema owned by Alembic (prod) / tests

    # ---- ProjectState Store protocol (the projectstate table) --------------------------------
    def read(self, project_id: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT data FROM projectstate WHERE project_id = ?", (project_id,)
        ).fetchone()
        return json.loads(row["data"]) if row else None

    def write(self, project_id: str, data: dict) -> None:
        self._conn.execute(
            "INSERT INTO projectstate (project_id, data) VALUES (?, ?) "
            "ON CONFLICT(project_id) DO UPDATE SET data = excluded.data",
            (project_id, json.dumps(data)),
        )
        self._conn.commit()

    def delete_project(self, project_id: str) -> None:
        """Permanently remove every flat-schema row for this run (projectstate + the per-project
        tables). Dropping the projectstate row is what stops the run reappearing from the registry
        (dbshim.registry_projects reads that table). Idempotent — deleting a gone run is a no-op."""
        from .models import FLAT_TABLES
        for table in FLAT_TABLES:
            self._conn.execute(f"DELETE FROM {table.name} WHERE project_id = ?", (project_id,))
        self._conn.commit()

    # ---- canvas-state writes (used by the CLI the orchestrator calls) ----------------
    def set_phase(self, name: str, status: str = "active", stage: Optional[int] = None) -> None:
        self._conn.execute(
            "INSERT INTO phases (project_id, name, status, stage, ts) VALUES (?, ?, ?, ?, ?)",
            (self._project_id, name, status, stage, time.time()),
        )
        self._conn.commit()

    def record_artifact(self, title: str, path: str, kind: Optional[str] = None,
                        agent: Optional[str] = None) -> None:
        self._conn.execute(
            "INSERT INTO artifacts (project_id, title, path, kind, agent, ts) VALUES (?, ?, ?, ?, ?, ?)",
            (self._project_id, title, path, kind, agent, time.time()),
        )
        self._conn.commit()

    def add_blocker(self, what: str, blocks: Optional[str] = None) -> None:
        self._conn.execute(
            "INSERT INTO blockers (project_id, what, blocks, ts) VALUES (?, ?, ?, ?)",
            (self._project_id, what, blocks, time.time()),
        )
        self._conn.commit()

    def clear_blocker(self, what: str) -> None:
        self._conn.execute("UPDATE blockers SET cleared = 1 WHERE project_id = ? AND what = ?",
                           (self._project_id, what))
        self._conn.commit()

    def set_gate(self, name: str, status: str) -> None:
        self._conn.execute(
            "INSERT INTO gates (project_id, name, status, ts) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(project_id, name) DO UPDATE SET status = excluded.status, ts = excluded.ts",
            (self._project_id, name, status, time.time()),
        )
        self._conn.commit()

    def record_verification(self, url: str, passed: bool, result) -> None:
        self._conn.execute(
            "INSERT INTO verifications (project_id, url, passed, result, ts) VALUES (?, ?, ?, ?, ?)",
            (self._project_id, url, 1 if passed else 0,
             result if isinstance(result, str) else json.dumps(result), time.time()),
        )
        self._conn.commit()

    def record_deployment(self, app: str, url: str, status: str = "live",
                          service_name: Optional[str] = None, verified: bool = False) -> None:
        """Record one deliverable's deployment. A run ships 1..N deliverables (mobile-web/web/api),
        so deploy state is per-app, not a single run-level deploy_url."""
        self._conn.execute(
            "INSERT INTO deployments (project_id, app, service_name, url, status, verified, ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (self._project_id, app, service_name, url, status, 1 if verified else 0, time.time()),
        )
        self._conn.commit()

    # ---- projection reads (scoped to this run) ---------------------------------------
    def phase_status(self) -> dict:
        """Latest status per phase name (rows are append-only; last write wins)."""
        out: dict = {}
        for r in self._conn.execute(
                "SELECT name, status FROM phases WHERE project_id = ? ORDER BY ts, id",
                (self._project_id,)).fetchall():
            out[r["name"]] = r["status"]
        return out

    def phases(self) -> list[dict]:
        return [dict(r) for r in self._conn.execute(
            "SELECT * FROM phases WHERE project_id = ? ORDER BY ts, id", (self._project_id,)).fetchall()]

    def artifacts(self) -> list[dict]:
        return [dict(r) for r in self._conn.execute(
            "SELECT * FROM artifacts WHERE project_id = ? ORDER BY id", (self._project_id,)).fetchall()]

    def blockers(self) -> list[dict]:
        return [dict(r) for r in self._conn.execute(
            "SELECT * FROM blockers WHERE project_id = ? ORDER BY id", (self._project_id,)).fetchall()]

    def gate_status(self) -> dict:
        return {r["name"]: r["status"] for r in self._conn.execute(
            "SELECT name, status FROM gates WHERE project_id = ?", (self._project_id,)).fetchall()}

    def verifications(self) -> list[dict]:
        return [dict(r) for r in self._conn.execute(
            "SELECT * FROM verifications WHERE project_id = ? ORDER BY id", (self._project_id,)).fetchall()]

    def has_passing_verification(self) -> bool:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM verifications WHERE project_id = ? AND passed = 1",
            (self._project_id,)).fetchone()
        return row["n"] > 0

    def deployments(self) -> list[dict]:
        return [dict(r) for r in self._conn.execute(
            "SELECT * FROM deployments WHERE project_id = ? ORDER BY id", (self._project_id,)).fetchall()]


def artifact_by_id(artifact_id: int) -> Optional[dict]:
    """Look up a single artifact row by its primary-key id (cross-project).
    Returns None when the id is unknown. Used by GET /api/artifacts/{id}."""
    conn = dbshim.connect(os.environ["SF_RUNS_DIR"])
    rows = conn.execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,)).fetchall()
    return dict(rows[0]) if rows else None


# --- CLI the headless orchestrator uses instead of emitting events --------------------
_USAGE = (
    "usage: python3 -m software_factory.db <verb> <projects_dir> <project_id> [args]\n"
    "  (<projects_dir> <project_id> ALWAYS come first, before the verb's own args)\n"
    "  set-phase <projects_dir> <project_id> <name> [status]\n"
    "  record-artifact <projects_dir> <project_id> <title> <path> [kind] [agent]\n"
    "  add-blocker <projects_dir> <project_id> <what> [blocks]\n"
    "  clear-blocker <projects_dir> <project_id> <what>\n"
    "  set-gate <projects_dir> <project_id> <name> <status>\n"
    "  record-verification <projects_dir> <project_id> <url> <passed:0|1> <result-json>\n"
    "  record-deployment <projects_dir> <project_id> <app> <url> [status] [service_name] [verified:0|1]\n"
    "  spawn-agent <projects_dir> <project_id> <agent_id> <role> <model> [phase] [ticket_id]\n"
    "  finish-agent <projects_dir> <project_id> <agent_id> <outcome> [cost_usd] [provenance] [diff_lines]\n"
    "                         provenance = PR number or commit SHA; type inferred (digits='pr', else='commit')\n"
    "  claim <projects_dir> <project_id> <ticket_id> <agent>\n"
    "  mark-done <projects_dir> <project_id> <ticket_id> <provenance> <diff_lines>\n"
    "  mark-deployed <projects_dir> <project_id> <ticket_id>\n"
    "  start-qa <projects_dir> <project_id> <ticket_id>\n"
    "  qa-approve <projects_dir> <project_id> <ticket_id>\n"
    "  qa-reject <projects_dir> <project_id> <ticket_id> <bug_markdown>   (ticket → open, carries the bug report)\n"
    "  provision-db <projects_dir> <project_id>   (stage-3: create this run's Railway Postgres; writes context/deploy-db.json)\n"
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
    try:
        info = deploy_db.provision(project_id, ctx)
        # Persist the captured serviceId as the DURABLE teardown handle: the reaper needs it even
        # after this run's context dir (which also holds it) is gone.
        if info.get("service_id"):
            state.deploy_db_service_id = info["service_id"]
        if info.get("volume_id"):
            state.deploy_db_volume_id = info["volume_id"]
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
                state.save()
        except Exception:
            pass
        sys.stderr.write(f"provision-db failed: {e}\n")
        return 1


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
    db = ProjectStore(db_path(projects_dir, project_id))
    if verb == "set-phase":
        db.set_phase(rest[0], rest[1] if len(rest) > 1 else "active")
    elif verb == "record-artifact":
        db.record_artifact(rest[0], rest[1],
                           rest[2] if len(rest) > 2 else None,
                           rest[3] if len(rest) > 3 else None)
    elif verb == "add-blocker":
        db.add_blocker(rest[0], rest[1] if len(rest) > 1 else None)
    elif verb == "clear-blocker":
        db.clear_blocker(rest[0])
    elif verb == "set-gate":
        db.set_gate(rest[0], rest[1])
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
        from .agents import AgentRegistry
        agent_id, role, model = rest[0], rest[1], rest[2]
        phase = rest[3] if len(rest) > 3 and rest[3] not in ("", "-") else None
        ticket_id = int(rest[4]) if len(rest) > 4 and rest[4] not in ("", "-") else None
        AgentRegistry(db_path(projects_dir, project_id)).spawn(agent_id, project_id, ticket_id, role, model, phase=phase)
    elif verb == "finish-agent":
        from .agents import AgentRegistry
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
            ts.mark_done(tid, rest[1], int(rest[2]))
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
