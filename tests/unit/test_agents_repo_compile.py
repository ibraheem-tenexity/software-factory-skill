"""Pure (no-DB) checks for AgentRepository — explicit project_id on every call (no getter/closure,
so there's nothing to form a reference cycle)."""
from software_factory.repositories._compile import to_sql
from software_factory.repositories.agents import AgentRepository


class FakeExec:
    def __init__(self):
        self.sql = None
        self.params = None

    def _cap(self, stmt):
        self.sql, self.params = to_sql(stmt)

    def fetchall(self, stmt):
        self._cap(stmt); return []

    def fetchone(self, stmt):
        self._cap(stmt); return None

    def execute(self, stmt):
        self._cap(stmt)
        class _Cur:
            rowcount = 2
        return _Cur()


def _clean(sql):
    assert "?" not in sql and "%(" not in sql


def test_insert_explicit_project_id():
    fx = FakeExec()
    r = AgentRepository(fx)
    r.insert("a1", "p1", 5, "build", "sonnet", "build", 100.0)
    _clean(fx.sql)
    assert fx.sql.startswith("INSERT INTO agents")
    assert "p1" in fx.params


def test_finalize_orphans_scopes_project_and_status():
    fx = FakeExec()
    n = AgentRepository(fx).finalize_orphans("p1", "done", 200.0)
    assert n == 2
    assert fx.sql.startswith("UPDATE agents SET")
    assert "agents.status = %s" in fx.sql   # WHERE status='running'
    assert fx.params == ("done", "unreported", 200.0, "p1", "running")


def test_set_outcome_all_columns():
    fx = FakeExec()
    AgentRepository(fx).set_outcome(
        "a1", "p1", status="done", outcome="success", cost_usd=1.5, input_tokens=10,
        cached_tokens=0, output_tokens=20, reasoning_tokens=0, provenance="42",
        provenance_type="pr", diff_lines=5, ended_at=300.0)
    _clean(fx.sql)
    assert fx.sql.startswith("UPDATE agents SET")
    assert fx.params[-2:] == ("a1", "p1")   # WHERE agent_id, project_id last


def test_cost_sum_by_ticket_groups():
    fx = FakeExec()
    AgentRepository(fx).cost_sum_by_ticket("p1")
    assert "sum(agents.cost_usd)" in fx.sql.lower()
    assert "GROUP BY agents.ticket_id" in fx.sql


def test_batch_roles_in_clause_and_order():
    fx = FakeExec()
    AgentRepository(fx).batch_roles(["p1", "p2"])
    _clean(fx.sql)
    assert "agents.project_id IN (%s, %s)" in fx.sql
    assert "ORDER BY agents.started_at, agents.agent_id" in fx.sql
