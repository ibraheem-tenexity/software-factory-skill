"""Pure CRUD for `autopsy_processed_runs` + `autopsy_signatures` (SQLAlchemy Core). Global tables —
see models.py's comment on the two tables for why they're separate ledgers."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..models import autopsy_processed_runs, autopsy_signatures


class RunAutopsyRepository:
    def __init__(self, exec_):
        self._x = exec_

    def already_processed(self, project_id: str) -> bool:
        row = self._x.fetchone(
            select(autopsy_processed_runs.c.project_id)
            .where(autopsy_processed_runs.c.project_id == project_id))
        return row is not None

    def mark_processed(self, project_id: str, signature: str, classification: str, ts: float) -> None:
        stmt = pg_insert(autopsy_processed_runs).values(
            project_id=project_id, signature=signature, classification=classification, processed_at=ts
        ).on_conflict_do_nothing(index_elements=["project_id"])
        self._x.execute(stmt)

    def get_signature(self, signature: str):
        return self._x.fetchone(
            select(autopsy_signatures).where(autopsy_signatures.c.signature == signature))

    def upsert_signature(self, signature: str, classification: str, project_id: str, ts: float,
                         linear_issue_id: str | None, linear_issue_identifier: str | None) -> None:
        """First sighting of `signature` inserts a fresh row (occurrences=1, the given issue ids —
        possibly both None if filing degraded). A repeat sighting bumps occurrences and last_seen.
        linear_issue_id/identifier use COALESCE(existing, incoming) on conflict — an existing
        filed ticket is NEVER overwritten (once filed, always that ticket), but a signature that
        first degraded (no key yet) and is later retried with a real id — because a key was
        provisioned since — correctly ATTACHES it instead of silently discarding it."""
        stmt = pg_insert(autopsy_signatures).values(
            signature=signature, classification=classification,
            linear_issue_id=linear_issue_id, linear_issue_identifier=linear_issue_identifier,
            first_project_id=project_id, last_project_id=project_id,
            occurrences=1, first_seen_at=ts, last_seen_at=ts,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["signature"],
            set_={
                "last_project_id": stmt.excluded.last_project_id,
                "last_seen_at": stmt.excluded.last_seen_at,
                "occurrences": autopsy_signatures.c.occurrences + 1,
                "linear_issue_id": func.coalesce(autopsy_signatures.c.linear_issue_id, stmt.excluded.linear_issue_id),
                "linear_issue_identifier": func.coalesce(
                    autopsy_signatures.c.linear_issue_identifier, stmt.excluded.linear_issue_identifier),
            },
        )
        self._x.execute(stmt)
