"""Pure CRUD for `recovery_actions` (SQLAlchemy Core, Postgres). Global table — the tier-2 recovery
entity (SOF-165). Mirrors the run_autopsy/eval_scores Store→Repository→GlobalExec pattern."""
from __future__ import annotations

from sqlalchemy import desc, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..models import recovery_actions
from ._compile import serialize_jsonb


class RecoveryActionRepository:
    def __init__(self, exec_):
        self._x = exec_

    def open(self, project_id: str, kind: str, cause: str, evidence: dict, owner: str,
             opened_at: float) -> None:
        """Open (or refresh) the single OPEN action for (project_id, kind). The ON CONFLICT arbiter
        MUST name both the index_elements AND the partial index's predicate (resolved_at IS NULL) —
        otherwise Postgres can't match the partial unique index and throws "no unique or exclusion
        constraint matching". On a live duplicate we refresh cause/evidence/owner + bump opened_at;
        a re-open after the prior action resolved inserts a fresh row (the partial index ignores
        resolved rows)."""
        stmt = pg_insert(recovery_actions).values(
            project_id=project_id, kind=kind, owner=owner, cause=cause,
            evidence=serialize_jsonb(evidence, default={}), opened_at=opened_at,
        ).on_conflict_do_update(
            index_elements=["project_id", "kind"],
            index_where=recovery_actions.c.resolved_at.is_(None),   # match the PARTIAL index predicate
            set_={"cause": cause, "evidence": serialize_jsonb(evidence, default={}),
                  "owner": owner, "opened_at": opened_at},
        )
        self._x.execute(stmt)

    def resolve_open(self, project_id: str, resolution: str, resolved_at: float,
                     kind: str | None = None) -> None:
        """Resolve this run's OPEN action(s) (optionally only one kind). Idempotent — a run with no
        open action is a no-op, so callers can fire it freely on done/resume/archive."""
        q = update(recovery_actions).where(
            recovery_actions.c.project_id == project_id,
            recovery_actions.c.resolved_at.is_(None),
        )
        if kind is not None:
            q = q.where(recovery_actions.c.kind == kind)
        self._x.execute(q.values(resolved_at=resolved_at, resolution=resolution))

    def open_for(self, project_id: str) -> list[dict]:
        return self._x.fetchall(
            select(recovery_actions).where(
                recovery_actions.c.project_id == project_id,
                recovery_actions.c.resolved_at.is_(None),
            ).order_by(desc(recovery_actions.c.opened_at)))

    def by_project(self, project_id: str, limit: int = 50) -> list[dict]:
        return self._x.fetchall(
            select(recovery_actions).where(recovery_actions.c.project_id == project_id)
            .order_by(desc(recovery_actions.c.opened_at)).limit(limit))

    def open_count(self, project_id: str) -> int:
        """COUNT of this run's OPEN actions — cheap (partial-index-covered), for status()'s per-tick
        open-count signal. Fetches an int, not rows. GlobalExec returns a dict row; take its single
        value key-agnostically (count(*) column name varies)."""
        row = self._x.fetchone(
            select(func.count().label("n")).select_from(recovery_actions).where(
                recovery_actions.c.project_id == project_id,
                recovery_actions.c.resolved_at.is_(None)))
        return int(next(iter((row or {}).values()), 0) or 0)
