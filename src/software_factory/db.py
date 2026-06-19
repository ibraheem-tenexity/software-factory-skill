"""Single per-run SQLite datastore — the source of truth the canvas projects from.

One file per run: ``<base>/run.db``. It holds RunState (the ``runstate`` table) plus the
canvas-projected tables: ``phases``, ``artifacts``, ``blockers``, ``gates``, ``verifications``.
``tickets`` and ``agents`` live in the SAME file (created by TicketStore / AgentRegistry).

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


class RunDB:
    """The per-run datastore. Also implements the RunState ``Store`` protocol
    (``read``/``write``) so RunState persists into the ``runstate`` table."""

    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._conn = dbshim.connect(path)  # sqlite today, pg when SF_DB=postgres
        self._init()

    def _init(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runstate (
                run_id TEXT PRIMARY KEY,
                data   TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS phases (
                id     INTEGER PRIMARY KEY AUTOINCREMENT,
                name   TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                stage  INTEGER,
                ts     REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS artifacts (
                id     INTEGER PRIMARY KEY AUTOINCREMENT,
                title  TEXT,
                path   TEXT,
                kind   TEXT,
                agent  TEXT,
                ts     REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS blockers (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                what    TEXT,
                blocks  TEXT,
                cleared INTEGER NOT NULL DEFAULT 0,
                ts      REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS gates (
                name   TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                ts     REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS verifications (
                id     INTEGER PRIMARY KEY AUTOINCREMENT,
                url    TEXT,
                passed INTEGER NOT NULL,
                result TEXT,
                ts     REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS deployments (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                app          TEXT,
                service_name TEXT,
                url          TEXT,
                status       TEXT NOT NULL DEFAULT 'deploying',
                verified     INTEGER NOT NULL DEFAULT 0,
                ts           REAL NOT NULL
            );
            """
        )
        self._conn.commit()

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
            "INSERT INTO phases (name, status, stage, ts) VALUES (?, ?, ?, ?)",
            (name, status, stage, time.time()),
        )
        self._conn.commit()

    def record_artifact(self, title: str, path: str, kind: Optional[str] = None,
                        agent: Optional[str] = None) -> None:
        self._conn.execute(
            "INSERT INTO artifacts (title, path, kind, agent, ts) VALUES (?, ?, ?, ?, ?)",
            (title, path, kind, agent, time.time()),
        )
        self._conn.commit()

    def add_blocker(self, what: str, blocks: Optional[str] = None) -> None:
        self._conn.execute(
            "INSERT INTO blockers (what, blocks, ts) VALUES (?, ?, ?)",
            (what, blocks, time.time()),
        )
        self._conn.commit()

    def clear_blocker(self, what: str) -> None:
        self._conn.execute("UPDATE blockers SET cleared = 1 WHERE what = ?", (what,))
        self._conn.commit()

    def set_gate(self, name: str, status: str) -> None:
        self._conn.execute(
            "INSERT INTO gates (name, status, ts) VALUES (?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET status = excluded.status, ts = excluded.ts",
            (name, status, time.time()),
        )
        self._conn.commit()

    def record_verification(self, url: str, passed: bool, result) -> None:
        self._conn.execute(
            "INSERT INTO verifications (url, passed, result, ts) VALUES (?, ?, ?, ?)",
            (url, 1 if passed else 0,
             result if isinstance(result, str) else json.dumps(result), time.time()),
        )
        self._conn.commit()

    def record_deployment(self, app: str, url: str, status: str = "live",
                          service_name: Optional[str] = None, verified: bool = False) -> None:
        """Record one deliverable's deployment. A run ships 1..N deliverables (mobile-web/web/api),
        so deploy state is per-app, not a single run-level deploy_url."""
        self._conn.execute(
            "INSERT INTO deployments (app, service_name, url, status, verified, ts) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (app, service_name, url, status, 1 if verified else 0, time.time()),
        )
        self._conn.commit()

    # ---- projection reads (used by Console.graph / status) ---------------------------
    def phase_status(self) -> dict:
        """Latest status per phase name (rows are append-only; last write wins)."""
        out: dict = {}
        for r in self._conn.execute("SELECT name, status FROM phases ORDER BY ts, id").fetchall():
            out[r["name"]] = r["status"]
        return out

    def phases(self) -> list[dict]:
        return [dict(r) for r in self._conn.execute(
            "SELECT * FROM phases ORDER BY ts, id").fetchall()]

    def artifacts(self) -> list[dict]:
        return [dict(r) for r in self._conn.execute(
            "SELECT * FROM artifacts ORDER BY id").fetchall()]

    def blockers(self) -> list[dict]:
        return [dict(r) for r in self._conn.execute(
            "SELECT * FROM blockers ORDER BY id").fetchall()]

    def gate_status(self) -> dict:
        return {r["name"]: r["status"] for r in self._conn.execute(
            "SELECT name, status FROM gates").fetchall()}

    def verifications(self) -> list[dict]:
        return [dict(r) for r in self._conn.execute(
            "SELECT * FROM verifications ORDER BY id").fetchall()]

    def has_passing_verification(self) -> bool:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM verifications WHERE passed = 1").fetchone()
        return row["n"] > 0

    def deployments(self) -> list[dict]:
        return [dict(r) for r in self._conn.execute(
            "SELECT * FROM deployments ORDER BY id").fetchall()]


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
