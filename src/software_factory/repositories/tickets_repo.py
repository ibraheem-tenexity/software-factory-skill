"""Pure CRUD for the `tickets` table (SQLAlchemy Core). Per-project: constructed with a `PathExec`
lane + the run's `project_id`, and every query is auto-scoped to that project. No lifecycle rules,
no dataclass mapping, no Python folds — those stay in `TicketStore`. All `tickets` queries live here
(same-table access in one module)."""
from __future__ import annotations

from sqlalchemy import select, insert, update

from ..models import tickets

# The columns TicketStore maps into its `Ticket` dataclass (excludes the project_id scoping column).
_TCOLS = (tickets.c.id, tickets.c.title, tickets.c.acceptance, tickets.c.dod, tickets.c.wave,
          tickets.c.status, tickets.c.agent, tickets.c.provenance, tickets.c.provenance_type,
          tickets.c.diff_lines, tickets.c.app, tickets.c.description)


class TicketRepository:
    def __init__(self, exec_, project_id):
        """`project_id` is a zero-arg callable returning the owning store's CURRENT project_id, read
        LIVE on every query. `_project_id` is the store's scoping source of truth and callers may
        reassign it (e.g. tests point one store at another run in a shared DB), so the repo must not
        capture a stale snapshot."""
        self._x = exec_
        self._pid = project_id

    def _scoped(self):
        return tickets.c.project_id == self._pid()

    # -- writes -------------------------------------------------------------------------
    def insert(self, **vals) -> int:
        stmt = insert(tickets).values(project_id=self._pid(), **vals).returning(tickets.c.id)
        return self._x.execute(stmt).fetchone()["id"]

    def update(self, ticket_id: int, **vals) -> int:
        stmt = update(tickets).where(tickets.c.id == ticket_id, self._scoped()).values(**vals)
        return self._x.execute(stmt).rowcount

    def bulk_reset_in_progress(self) -> int:
        stmt = (update(tickets)
                .where(self._scoped(), tickets.c.status == "in_progress")
                .values(status="open", agent=None))
        return self._x.execute(stmt).rowcount

    # -- reads --------------------------------------------------------------------------
    def by_id(self, ticket_id: int):
        return self._x.fetchone(select(*_TCOLS).where(tickets.c.id == ticket_id, self._scoped()))

    def rows_by_status(self, statuses: tuple, *, order_by_wave: bool = False) -> list:
        order = (tickets.c.wave, tickets.c.id) if order_by_wave else (tickets.c.id,)
        return self._x.fetchall(select(*_TCOLS)
                                .where(self._scoped(), tickets.c.status.in_(statuses))
                                .order_by(*order))

    def rows_in_wave(self, wave: int, statuses: tuple) -> list:
        return self._x.fetchall(select(*_TCOLS)
                                .where(self._scoped(), tickets.c.wave == wave,
                                       tickets.c.status.in_(statuses))
                                .order_by(tickets.c.id))

    def all_rows(self) -> list:
        return self._x.fetchall(select(*_TCOLS).where(self._scoped())
                                .order_by(tickets.c.wave, tickets.c.id))

    def distinct_waves(self, statuses: tuple) -> list:
        return self._x.fetchall(select(tickets.c.wave)
                                .where(self._scoped(), tickets.c.status.in_(statuses))
                                .distinct().order_by(tickets.c.wave))

    def acceptance_dod_rows(self) -> list:
        return self._x.fetchall(select(tickets.c.acceptance, tickets.c.dod).where(self._scoped()))

    def status_rows(self) -> list:
        return self._x.fetchall(select(tickets.c.status).where(self._scoped()))
