"""Pure (no-DB) checks that TicketRepository builds the intended SQL via a fake exec lane that just
captures `to_sql(stmt)`. Confirms auto project-scoping, %s-positional params, RETURNING on insert, and
the status/order clauses — without touching Postgres. The behavior-equivalence round-trip is covered
by the existing DB tests (test_tickets.py / test_pg_stores.py), run in a serialized slot."""
from software_factory.repositories._compile import to_sql
from software_factory.repositories.tickets_repo import TicketRepository


class _Cur:
    rowcount = 1
    def fetchone(self):
        return {"id": 1}


class FakeExec:
    def __init__(self):
        self.sql = None
        self.params = None

    def _cap(self, stmt):
        self.sql, self.params = to_sql(stmt)

    def fetchall(self, stmt):
        self._cap(stmt)
        return []

    def fetchone(self, stmt):
        self._cap(stmt)
        return {"id": 1}

    def execute(self, stmt):
        self._cap(stmt)
        return _Cur()


def _repo():
    fx = FakeExec()
    return TicketRepository(fx, lambda: "p1"), fx


def _no_bad_placeholders(sql):
    assert "?" not in sql and "%(" not in sql


def test_insert_scopes_project_and_returns_id():
    r, fx = _repo()
    assert r.insert(title="t", acceptance="a", dod="d", wave=1, app=None, description="") == 1
    assert fx.sql.startswith("INSERT INTO tickets")
    assert "RETURNING tickets.id" in fx.sql
    _no_bad_placeholders(fx.sql)
    assert "p1" in fx.params           # project_id auto-injected


def test_by_id_scoped():
    r, fx = _repo()
    r.by_id(5)
    assert "FROM tickets" in fx.sql and "tickets.id = %s" in fx.sql and "tickets.project_id = %s" in fx.sql
    assert fx.params == (5, "p1")


def test_update_set_then_where_params():
    r, fx = _repo()
    r.update(5, status="done", agent=None)
    assert fx.sql.startswith("UPDATE tickets SET")
    _no_bad_placeholders(fx.sql)
    assert fx.params == ("done", None, 5, "p1")   # SET values, then WHERE (id, project_id)


def test_rows_by_status_in_and_order():
    r, fx = _repo()
    r.rows_by_status(("done", "deployed", "qa_testing", "approved"))
    assert "tickets.status IN (%s, %s, %s, %s)" in fx.sql
    assert "ORDER BY tickets.id" in fx.sql
    assert fx.params == ("p1", "done", "deployed", "qa_testing", "approved")


def test_rows_by_status_order_by_wave():
    r, fx = _repo()
    r.rows_by_status(("approved",), order_by_wave=True)
    assert "ORDER BY tickets.wave, tickets.id" in fx.sql


def test_rows_in_wave():
    r, fx = _repo()
    r.rows_in_wave(2, ("open", "in_progress"))
    assert "tickets.wave = %s" in fx.sql and "tickets.status IN (%s, %s)" in fx.sql
    assert fx.params == ("p1", 2, "open", "in_progress")


def test_distinct_waves():
    r, fx = _repo()
    r.distinct_waves(("open", "in_progress"))
    assert "DISTINCT" in fx.sql and "tickets.wave" in fx.sql and "ORDER BY tickets.wave" in fx.sql


def test_all_rows_order():
    r, fx = _repo()
    r.all_rows()
    assert "ORDER BY tickets.wave, tickets.id" in fx.sql
    assert fx.params == ("p1",)


def test_bulk_reset_in_progress():
    r, fx = _repo()
    r.bulk_reset_in_progress()
    assert fx.sql.startswith("UPDATE tickets SET")
    assert "tickets.status = %s" in fx.sql        # WHERE status = 'in_progress'
    assert fx.params == ("open", None, "p1", "in_progress")   # SET status,agent ; WHERE project_id,status
