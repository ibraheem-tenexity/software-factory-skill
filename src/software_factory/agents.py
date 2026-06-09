"""Agent telemetry registry — visibility into how many agents ran and how they performed.

SQLite source of truth (queryable, resumable, unit-testable offline). Every lifecycle event
is also pushed to a pluggable sink so an external dashboard can render the run in real time.
The headline health metric is the no-op rate: agents that produced no real change.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from typing import Callable, Optional, Protocol

from .budget import Usage


class Sink(Protocol):
    def emit(self, event: dict) -> None: ...


class NullSink:
    """Default sink: visibility stays local in SQLite, nothing is pushed out."""

    def emit(self, event: dict) -> None:
        pass


# outcome -> terminal status. A no-op produced nothing, so it is NOT 'done'.
_STATUS_FOR = {"real_diff": "done", "success": "done", "no_op": "failed", "blocked": "blocked", "failed": "failed"}


@dataclass
class AgentRecord:
    agent_id: str
    run_id: str
    ticket_id: Optional[int]
    role: str
    model: str
    phase: Optional[str]
    status: str
    outcome: Optional[str]
    cost_usd: float
    input_tokens: int
    cached_tokens: int
    output_tokens: int
    reasoning_tokens: int
    pr: Optional[int]
    diff_lines: int
    started_at: float
    ended_at: Optional[float]


class AgentRegistry:
    def __init__(self, path: str, sink: Sink = NullSink(), clock: Callable[[], float] = time.time):
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._sink = sink
        self._clock = clock
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agents (
                agent_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                ticket_id INTEGER,
                role TEXT NOT NULL,
                model TEXT NOT NULL,
                phase TEXT,
                status TEXT NOT NULL DEFAULT 'running',
                outcome TEXT,
                cost_usd REAL NOT NULL DEFAULT 0,
                input_tokens INTEGER NOT NULL DEFAULT 0,
                cached_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                reasoning_tokens INTEGER NOT NULL DEFAULT 0,
                pr INTEGER,
                diff_lines INTEGER NOT NULL DEFAULT 0,
                started_at REAL NOT NULL,
                ended_at REAL
            )
            """
        )
        self._conn.commit()

    def spawn(self, agent_id: str, run_id: str, ticket_id: Optional[int], role: str,
              model: str, phase: Optional[str] = None) -> None:
        now = self._clock()
        self._conn.execute(
            "INSERT INTO agents (agent_id, run_id, ticket_id, role, model, phase, started_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (agent_id, run_id, ticket_id, role, model, phase, now),
        )
        self._conn.commit()
        self._sink.emit(
            {"event": "spawn", "agent_id": agent_id, "run_id": run_id,
             "ticket_id": ticket_id, "role": role, "model": model, "phase": phase, "at": now}
        )

    def agents_for(self, run_id: str) -> list[AgentRecord]:
        rows = self._conn.execute(
            "SELECT * FROM agents WHERE run_id=? ORDER BY started_at, agent_id", (run_id,)
        ).fetchall()
        return [AgentRecord(**dict(r)) for r in rows]

    def finalize_orphans(self, run_id: str, stage_ok: bool) -> int:
        """SPEC §5 (no phantom agents): when a stage exits, close any still-running rows the
        orchestrator forgot to finish — outcome 'unreported'; status done if the stage's gate
        passed (its work evidently materialized), failed otherwise. Returns rows closed."""
        cur = self._conn.execute(
            "UPDATE agents SET status=?, outcome='unreported', ended_at=? "
            "WHERE run_id=? AND status='running'",
            ("done" if stage_ok else "failed", self._clock(), run_id),
        )
        self._conn.commit()
        return cur.rowcount

    def record(
        self,
        agent_id: str,
        outcome: str,
        usage: Optional[Usage] = None,
        cost_usd: float = 0.0,
        pr: Optional[int] = None,
        diff_lines: int = 0,
    ) -> None:
        u = usage or Usage(model="")
        now = self._clock()
        self._conn.execute(
            "UPDATE agents SET status=?, outcome=?, cost_usd=?, input_tokens=?, cached_tokens=?, "
            "output_tokens=?, reasoning_tokens=?, pr=?, diff_lines=?, ended_at=? WHERE agent_id=?",
            (_STATUS_FOR.get(outcome, "failed"), outcome, cost_usd, u.input_tokens, u.cached_tokens,
             u.output_tokens, u.reasoning_tokens, pr, diff_lines, now, agent_id),
        )
        self._conn.commit()
        self._sink.emit(
            {"event": "record", "agent_id": agent_id, "outcome": outcome, "cost_usd": cost_usd,
             "pr": pr, "diff_lines": diff_lines, "at": now}
        )

    def get(self, agent_id: str) -> AgentRecord:
        row = self._conn.execute("SELECT * FROM agents WHERE agent_id=?", (agent_id,)).fetchone()
        if row is None:
            raise KeyError(agent_id)
        return AgentRecord(**dict(row))

    def active(self) -> list[AgentRecord]:
        rows = self._conn.execute("SELECT * FROM agents WHERE status='running' ORDER BY started_at").fetchall()
        return [AgentRecord(**dict(r)) for r in rows]

    def counts(self, run_id: str) -> dict:
        rows = self._conn.execute(
            "SELECT status, outcome FROM agents WHERE run_id=?", (run_id,)
        ).fetchall()
        c = {"spawned": len(rows), "running": 0, "done": 0, "failed": 0, "blocked": 0, "no_op": 0}
        for r in rows:
            c[r["status"]] = c.get(r["status"], 0) + 1
            if r["outcome"] == "no_op":
                c["no_op"] += 1
        return c

    def no_op_rate(self, run_id: str) -> float:
        rows = self._conn.execute(
            "SELECT outcome FROM agents WHERE run_id=? AND outcome IS NOT NULL", (run_id,)
        ).fetchall()
        if not rows:
            return 0.0
        no_ops = sum(1 for r in rows if r["outcome"] == "no_op")
        return no_ops / len(rows)

    def cost_by_ticket(self, run_id: str) -> dict:
        rows = self._conn.execute(
            "SELECT ticket_id, SUM(cost_usd) AS c FROM agents WHERE run_id=? GROUP BY ticket_id",
            (run_id,),
        ).fetchall()
        return {r["ticket_id"]: r["c"] for r in rows}

    def render_markdown(self, run_id: str) -> str:
        rows = self._conn.execute(
            "SELECT * FROM agents WHERE run_id=? ORDER BY started_at", (run_id,)
        ).fetchall()
        c = self.counts(run_id)
        lines = [
            f"# Agents — run `{run_id}`",
            "",
            f"spawned {c['spawned']} · running {c['running']} · done {c['done']} · "
            f"no-op {c['no_op']} · blocked {c['blocked']} · no-op rate {self.no_op_rate(run_id):.0%}",
            "",
            "| agent | ticket | role | status | outcome | $ | PR |",
            "|---|---|---|---|---|---|---|",
        ]
        for r in rows:
            lines.append(
                f"| {r['agent_id']} | {r['ticket_id']} | {r['role']} | {r['status']} | "
                f"{r['outcome'] or ''} | {r['cost_usd']:.2f} | {r['pr'] or ''} |"
            )
        return "\n".join(lines) + "\n"
