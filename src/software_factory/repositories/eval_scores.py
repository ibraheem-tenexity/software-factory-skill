"""Pure CRUD for `eval_scores` (SQLAlchemy Core, Postgres). Global table — one row per benchmark
run, mirroring the run_autopsy repositories' Store→Repository→GlobalExec pattern (SOF-102)."""
from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..models import eval_scores
from ._compile import serialize_jsonb


class EvalScoreRepository:
    def __init__(self, exec_):
        self._x = exec_

    def upsert(self, project_id: str, brief_title: str, total: int, passed: int, score: float,
               by_stage: dict, detail: dict, scored_at: float) -> None:
        """Persist (or re-score) one run's eval. Re-judging a run overwrites its row — the latest
        judgment for a given run is the truth; trend history is across DIFFERENT runs, not versions
        of one."""
        # JSONB columns pass as json.dumps(...) strings (GlobalExec's raw-SQL path bypasses
        # SQLAlchemy's type processors; the jsonb assignment cast handles the string) — same as
        # checkpoint.py/conversation.py. Reads come back already-parsed.
        by_stage_j = serialize_jsonb(by_stage, default={})
        detail_j = serialize_jsonb(detail, default={})
        stmt = pg_insert(eval_scores).values(
            project_id=project_id, brief_title=brief_title, total=total, passed=passed,
            score=score, by_stage=by_stage_j, detail=detail_j, scored_at=scored_at,
        ).on_conflict_do_update(
            index_elements=["project_id"],
            set_={"brief_title": brief_title, "total": total, "passed": passed, "score": score,
                  "by_stage": by_stage_j, "detail": detail_j, "scored_at": scored_at},
        )
        self._x.execute(stmt)

    def by_project(self, project_id: str) -> dict | None:
        # GlobalExec.fetchone already returns a plain dict (or None) — JSONB columns come back parsed.
        return self._x.fetchone(select(eval_scores).where(eval_scores.c.project_id == project_id))

    def recent(self, limit: int = 50, brief_title: str | None = None) -> list[dict]:
        """Most-recent scores first — the trend feed. Optionally scoped to one brief so a scenario's
        capability curve is isolated from others."""
        q = select(eval_scores)
        if brief_title is not None:
            q = q.where(eval_scores.c.brief_title == brief_title)
        q = q.order_by(desc(eval_scores.c.scored_at)).limit(limit)
        return self._x.fetchall(q)
