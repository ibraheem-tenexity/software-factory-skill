"""Agent telemetry registry — visibility into how many agents ran and how they performed.

Postgres source of truth (queryable, resumable). Every lifecycle event
is also pushed to a pluggable sink so an external dashboard can render the run in real time.
The headline health metric is the no-op rate: agents that produced no real change.

DATA ACCESS: all `agents` SQL lives in `repositories.agents_repo.AgentRepository` (SQLAlchemy Core);
this store keeps only the outcome-status mapping and the markdown rendering.
"""
from __future__ import annotations


from .db import project_id_from_path
from .repositories._exec import PathExec
from .repositories.agents_repo import AgentRepository
import time
from dataclasses import dataclass
from typing import Callable, Optional, Protocol

from .budget import Usage


class Sink(Protocol):
    def emit(self, event: dict) -> None: ...


class NullSink:
    """Default sink: visibility stays in the database, nothing is pushed out."""

    def emit(self, event: dict) -> None:
        pass


# outcome -> terminal status. A no-op produced nothing, so it is NOT 'done'.
_STATUS_FOR = {"real_diff": "done", "success": "done", "no_op": "failed", "blocked": "blocked", "failed": "failed"}


@dataclass
class AgentRecord:
    agent_id: str
    project_id: str
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
    provenance: Optional[str]
    provenance_type: Optional[str]
    diff_lines: int
    started_at: float
    ended_at: Optional[float]


class AgentRegistry:
    def __init__(self, path: str, sink: Sink = NullSink(), clock: Callable[[], float] = time.time):
        self._project_id = project_id_from_path(path)
        # Postgres; schema owned by Alembic (prod) / tests. All SQL is in AgentRepository.
        self._repo = AgentRepository(PathExec(path))
        self._sink = sink
        self._clock = clock

    def spawn(self, agent_id: str, project_id: str, ticket_id: Optional[int], role: str,
              model: str, phase: Optional[str] = None) -> None:
        now = self._clock()
        self._repo.insert(agent_id, project_id, ticket_id, role, model, phase, now)
        self._sink.emit(
            {"event": "spawn", "agent_id": agent_id, "project_id": project_id,
             "ticket_id": ticket_id, "role": role, "model": model, "phase": phase, "at": now}
        )

    def agents_for(self, project_id: str) -> list[AgentRecord]:
        return [AgentRecord(**dict(r)) for r in self._repo.all_for_project(project_id)]

    def finalize_orphans(self, project_id: str, stage_ok: bool) -> int:
        """SPEC §5 (no phantom agents): when a stage exits, close any still-running rows the
        orchestrator forgot to finish — outcome 'unreported'; status done if the stage's gate
        passed (its work evidently materialized), failed otherwise. Returns rows closed."""
        return self._repo.finalize_orphans(project_id, "done" if stage_ok else "failed", self._clock())

    def record(
        self,
        agent_id: str,
        outcome: str,
        usage: Optional[Usage] = None,
        cost_usd: float = 0.0,
        provenance: Optional[str] = None,
        provenance_type: Optional[str] = None,
        diff_lines: int = 0,
    ) -> None:
        u = usage or Usage(model="")
        now = self._clock()
        if provenance is not None and provenance_type is None:
            provenance_type = "pr" if str(provenance).isdigit() else "commit"
        self._repo.set_outcome(
            agent_id, self._project_id, status=_STATUS_FOR.get(outcome, "failed"), outcome=outcome,
            cost_usd=cost_usd, input_tokens=u.input_tokens, cached_tokens=u.cached_tokens,
            output_tokens=u.output_tokens, reasoning_tokens=u.reasoning_tokens, provenance=provenance,
            provenance_type=provenance_type, diff_lines=diff_lines, ended_at=now)
        self._sink.emit(
            {"event": "record", "agent_id": agent_id, "outcome": outcome, "cost_usd": cost_usd,
             "provenance": provenance, "provenance_type": provenance_type, "diff_lines": diff_lines, "at": now}
        )

    def get(self, agent_id: str) -> AgentRecord:
        row = self._repo.by_agent_id(agent_id, self._project_id)
        if row is None:
            raise KeyError(agent_id)
        return AgentRecord(**dict(row))

    def active(self) -> list[AgentRecord]:
        return [AgentRecord(**dict(r)) for r in self._repo.running_for_project(self._project_id)]

    def counts(self, project_id: str) -> dict:
        rows = self._repo.status_outcome_rows(project_id)
        c = {"spawned": len(rows), "running": 0, "done": 0, "failed": 0, "blocked": 0, "no_op": 0}
        for r in rows:
            c[r["status"]] = c.get(r["status"], 0) + 1
            if r["outcome"] == "no_op":
                c["no_op"] += 1
        return c

    def no_op_rate(self, project_id: str) -> float:
        rows = self._repo.outcome_rows(project_id)
        if not rows:
            return 0.0
        no_ops = sum(1 for r in rows if r["outcome"] == "no_op")
        return no_ops / len(rows)

    def cost_by_ticket(self, project_id: str) -> dict:
        rows = self._repo.cost_sum_by_ticket(project_id)
        return {r["ticket_id"]: r["c"] for r in rows}

    def render_markdown(self, project_id: str) -> str:
        rows = self._repo.all_for_project(project_id)
        c = self.counts(project_id)
        lines = [
            f"# Agents — run `{project_id}`",
            "",
            f"spawned {c['spawned']} · running {c['running']} · done {c['done']} · "
            f"no-op {c['no_op']} · blocked {c['blocked']} · no-op rate {self.no_op_rate(project_id):.0%}",
            "",
            "| agent | ticket | role | status | outcome | $ | provenance |",
            "|---|---|---|---|---|---|---|",
        ]
        for r in rows:
            lines.append(
                f"| {r['agent_id']} | {r['ticket_id']} | {r['role']} | {r['status']} | "
                f"{r['outcome'] or ''} | {r['cost_usd']:.2f} | {r['provenance'] or ''} |"
            )
        return "\n".join(lines) + "\n"
