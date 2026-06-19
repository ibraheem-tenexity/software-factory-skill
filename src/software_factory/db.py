"""Per-run datastore — the source of truth the canvas projects from (Postgres, flat schema).

All runs share one set of tables keyed by ``run_id``: RunState (the ``runstate`` table) plus the
canvas-projected tables ``phases``, ``artifacts``, ``blockers``, ``gates``, ``verifications``,
``deployments``. ``tickets`` and ``agents`` are the same flat model (TicketStore / AgentRegistry).
The ``path`` argument names the run directory + the ``run_id`` to scope by; storage is Postgres.

The headless orchestrator records canvas state by calling the CLI
(``python3 -m software_factory.db <verb> <runs_dir> <run_id> ...``) instead of emitting
events. ``Console.graph()`` projects nodes/edges by SELECTing these tables — the DB is the
single source of truth, never a separate event stream.
"""
from __future__ import annotations

import json
import os
import re

from . import dbshim
import sys
import time
from typing import Optional

# Canonical factory run-id shape (the strict registry form dbshim._ensure uses).
_RUN_ID_RE = re.compile(r"run-[0-9a-f]{8}")


def db_path(runs_dir: str, run_id: str) -> str:
    return os.path.join(runs_dir, run_id, "run.db")


def run_id_from_path(path: str) -> str:
    """The run id a store at `path` belongs to — the run-dir name in
    `<runs_dir>/<run_id>/run.db`. In the flat schema every per-run table is scoped by this."""
    return os.path.basename(os.path.dirname(path))


class RunDB:
    """The run datastore (Postgres). In the flat schema all runs share one set of tables keyed
    by ``run_id``. Also implements the RunState ``Store`` protocol (``read``/``write``) via the
    ``runstate`` table."""

    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._run_id = run_id_from_path(path)
        self._conn = dbshim.connect(path)  # Postgres; schema owned by Alembic (prod) / tests

    # ---- RunState Store protocol (the runstate table) --------------------------------
    def read(self, run_id: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT data FROM runstate WHERE run_id = ?", (run_id,)
        ).fetchone()
        return json.loads(row["data"]) if row else None

    def write(self, run_id: str, data: dict) -> None:
        self._conn.execute(
            "INSERT INTO runstate (run_id, data) VALUES (?, ?) "
            "ON CONFLICT(run_id) DO UPDATE SET data = excluded.data",
            (run_id, json.dumps(data)),
        )
        self._conn.commit()

    # ---- canvas-state writes (used by the CLI the orchestrator calls) ----------------
    def set_phase(self, name: str, status: str = "active", stage: Optional[int] = None) -> None:
        self._conn.execute(
            "INSERT INTO phases (run_id, name, status, stage, ts) VALUES (?, ?, ?, ?, ?)",
            (self._run_id, name, status, stage, time.time()),
        )
        self._conn.commit()

    def record_artifact(self, title: str, path: str, kind: Optional[str] = None,
                        agent: Optional[str] = None) -> None:
        self._conn.execute(
            "INSERT INTO artifacts (run_id, title, path, kind, agent, ts) VALUES (?, ?, ?, ?, ?, ?)",
            (self._run_id, title, path, kind, agent, time.time()),
        )
        self._conn.commit()

    def add_blocker(self, what: str, blocks: Optional[str] = None) -> None:
        self._conn.execute(
            "INSERT INTO blockers (run_id, what, blocks, ts) VALUES (?, ?, ?, ?)",
            (self._run_id, what, blocks, time.time()),
        )
        self._conn.commit()

    def clear_blocker(self, what: str) -> None:
        self._conn.execute("UPDATE blockers SET cleared = 1 WHERE run_id = ? AND what = ?",
                           (self._run_id, what))
        self._conn.commit()

    def set_gate(self, name: str, status: str) -> None:
        self._conn.execute(
            "INSERT INTO gates (run_id, name, status, ts) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(run_id, name) DO UPDATE SET status = excluded.status, ts = excluded.ts",
            (self._run_id, name, status, time.time()),
        )
        self._conn.commit()

    def record_verification(self, url: str, passed: bool, result) -> None:
        self._conn.execute(
            "INSERT INTO verifications (run_id, url, passed, result, ts) VALUES (?, ?, ?, ?, ?)",
            (self._run_id, url, 1 if passed else 0,
             result if isinstance(result, str) else json.dumps(result), time.time()),
        )
        self._conn.commit()

    def record_deployment(self, app: str, url: str, status: str = "live",
                          service_name: Optional[str] = None, verified: bool = False) -> None:
        """Record one deliverable's deployment. A run ships 1..N deliverables (mobile-web/web/api),
        so deploy state is per-app, not a single run-level deploy_url."""
        self._conn.execute(
            "INSERT INTO deployments (run_id, app, service_name, url, status, verified, ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (self._run_id, app, service_name, url, status, 1 if verified else 0, time.time()),
        )
        self._conn.commit()

    # ---- projection reads (scoped to this run) ---------------------------------------
    def phase_status(self) -> dict:
        """Latest status per phase name (rows are append-only; last write wins)."""
        out: dict = {}
        for r in self._conn.execute(
                "SELECT name, status FROM phases WHERE run_id = ? ORDER BY ts, id",
                (self._run_id,)).fetchall():
            out[r["name"]] = r["status"]
        return out

    def phases(self) -> list[dict]:
        return [dict(r) for r in self._conn.execute(
            "SELECT * FROM phases WHERE run_id = ? ORDER BY ts, id", (self._run_id,)).fetchall()]

    def artifacts(self) -> list[dict]:
        return [dict(r) for r in self._conn.execute(
            "SELECT * FROM artifacts WHERE run_id = ? ORDER BY id", (self._run_id,)).fetchall()]

    def blockers(self) -> list[dict]:
        return [dict(r) for r in self._conn.execute(
            "SELECT * FROM blockers WHERE run_id = ? ORDER BY id", (self._run_id,)).fetchall()]

    def gate_status(self) -> dict:
        return {r["name"]: r["status"] for r in self._conn.execute(
            "SELECT name, status FROM gates WHERE run_id = ?", (self._run_id,)).fetchall()}

    def verifications(self) -> list[dict]:
        return [dict(r) for r in self._conn.execute(
            "SELECT * FROM verifications WHERE run_id = ? ORDER BY id", (self._run_id,)).fetchall()]

    def has_passing_verification(self) -> bool:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM verifications WHERE run_id = ? AND passed = 1",
            (self._run_id,)).fetchone()
        return row["n"] > 0

    def deployments(self) -> list[dict]:
        return [dict(r) for r in self._conn.execute(
            "SELECT * FROM deployments WHERE run_id = ? ORDER BY id", (self._run_id,)).fetchall()]


# --- CLI the headless orchestrator uses instead of emitting events --------------------
_USAGE = (
    "usage: python3 -m software_factory.db <verb> <runs_dir> <run_id> [args]\n"
    "  (<runs_dir> <run_id> ALWAYS come first, before the verb's own args)\n"
    "  set-phase <runs_dir> <run_id> <name> [status]\n"
    "  record-artifact <runs_dir> <run_id> <title> <path> [kind] [agent]\n"
    "  add-blocker <runs_dir> <run_id> <what> [blocks]\n"
    "  clear-blocker <runs_dir> <run_id> <what>\n"
    "  set-gate <runs_dir> <run_id> <name> <status>\n"
    "  record-verification <runs_dir> <run_id> <url> <passed:0|1> <result-json>\n"
    "  record-deployment <runs_dir> <run_id> <app> <url> [status] [service_name] [verified:0|1]\n"
    "  spawn-agent <runs_dir> <run_id> <agent_id> <role> <model> [phase] [ticket_id]\n"
    "  finish-agent <runs_dir> <run_id> <agent_id> <outcome> [cost_usd] [provenance] [diff_lines]\n"
    "                         provenance = PR number or commit SHA; type inferred (digits='pr', else='commit')\n"
    "  claim <runs_dir> <run_id> <ticket_id> <agent>\n"
    "  mark-done <runs_dir> <run_id> <ticket_id> <provenance> <diff_lines>\n"
    "  mark-deployed <runs_dir> <run_id> <ticket_id>\n"
    "  start-qa <runs_dir> <run_id> <ticket_id>\n"
    "  qa-approve <runs_dir> <run_id> <ticket_id>\n"
    "  qa-reject <runs_dir> <run_id> <ticket_id> <bug_markdown>   (ticket → open, carries the bug report)\n"
)


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        sys.stderr.write(_USAGE)
        return 2
    verb, runs_dir, run_id, rest = argv[0], argv[1], argv[2], argv[3:]
    # Reject malformed run ids BEFORE constructing RunDB — connecting has a side effect
    # (dbshim._ensure runs CREATE SCHEMA in pg mode). A wrong arg order (e.g. junk landing
    # in the run_id slot) must never create a prod schema.
    if not _RUN_ID_RE.fullmatch(run_id):
        sys.stderr.write(
            f"error: run_id {run_id!r} is not a valid factory run id (run-XXXXXXXX); "
            "args go <verb> <runs_dir> <run_id> [args]\n"
        )
        sys.stderr.write(_USAGE)
        return 2
    db = RunDB(db_path(runs_dir, run_id))
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
        AgentRegistry(db_path(runs_dir, run_id)).spawn(agent_id, run_id, ticket_id, role, model, phase=phase)
    elif verb == "finish-agent":
        from .agents import AgentRegistry
        agent_id, outcome = rest[0], rest[1]
        cost = float(rest[2]) if len(rest) > 2 and rest[2] not in ("", "-") else 0.0
        provenance = rest[3] if len(rest) > 3 and rest[3] not in ("", "-") else None
        diff_lines = int(rest[4]) if len(rest) > 4 and rest[4] not in ("", "-") else 0
        AgentRegistry(db_path(runs_dir, run_id)).record(agent_id, outcome, cost_usd=cost,
                                                        provenance=provenance,
                                                        diff_lines=diff_lines)
    elif verb in ("claim", "mark-done", "mark-deployed", "start-qa", "qa-approve", "qa-reject"):
        from .tickets import TicketStore
        ts = TicketStore(db_path(runs_dir, run_id))
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
