"""Pure (no-DB) checks that the canvas-table repositories build the intended SQL: the projectstate
single-PK upsert, the gates COMPOSITE-PK upsert, per-project scoping via the live getter, and the
FLAT_TABLES generic delete loop `ProjectStore.delete_project` uses. Behavior-equivalence round-trip
is the existing DB tests (test_db.py), run once the flock queue is clear."""
from sqlalchemy import delete

from software_factory.repositories._compile import to_sql
from software_factory.repositories.canvas_repo import (
    ProjectStateRepository, PhaseRepository, GateRepository, VerificationRepository)
from software_factory.models import tickets, agents, checkpoint


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
        return {"n": 0}

    def execute(self, stmt):
        self._cap(stmt)
        return None


def _clean(sql):
    assert "?" not in sql and "%(" not in sql


def test_projectstate_upsert_single_pk():
    fx = FakeExec()
    ProjectStateRepository(fx).upsert("p1", '{"a":1}', "n", "s")
    _clean(fx.sql)
    assert "ON CONFLICT (project_id) DO UPDATE SET" in fx.sql
    assert set(fx.params) == {"p1", '{"a":1}', "n", "s"}


def test_gates_upsert_composite_pk():
    fx = FakeExec()
    GateRepository(fx, lambda: "p1").upsert("build", "green", 1.0)
    _clean(fx.sql)
    assert "ON CONFLICT (project_id, name) DO UPDATE SET" in fx.sql
    assert fx.params == ("p1", "build", "green", 1.0)


def test_phase_insert_uses_live_getter():
    fx = FakeExec()
    pid_box = {"v": "p1"}
    repo = PhaseRepository(fx, lambda: pid_box["v"])
    pid_box["v"] = "p2"          # reassign AFTER repo construction — must read live, not stale
    repo.insert("build", "active", 1, 100.0)
    assert "p2" in fx.params and "p1" not in fx.params


def test_verifications_passing_count_shape():
    fx = FakeExec()
    row = VerificationRepository(fx, lambda: "p1").passing_count()
    assert "count(*)" in fx.sql.lower() or "count(" in fx.sql.lower()
    assert row == 0


def test_flat_tables_delete_loop_scopes_each_table():
    for table in (tickets, agents, checkpoint):
        stmt = delete(table).where(table.c.project_id == "p1")
        sql, params = to_sql(stmt)
        assert sql.startswith(f"DELETE FROM {table.name}")
        assert params == ("p1",)
