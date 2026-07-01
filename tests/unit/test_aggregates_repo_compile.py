"""Pure (no-DB) checks for AggregatesRepository — pins the row-key contract (every aggregate must
keep its original `.label(...)` alias, or callers' `r["runs"]`/`r["cost_usd"]` etc. break silently)
and the `count(*) FILTER (WHERE ...)` rendering."""
from software_factory.repositories._compile import to_sql
from software_factory.repositories.aggregates_repo import AggregatesRepository


class FakeExec:
    def __init__(self):
        self.sql = None

    def fetchall(self, stmt):
        self.sql, _ = to_sql(stmt)
        return []

    def fetchone(self, stmt):
        self.sql, _ = to_sql(stmt)
        return None


def test_agent_rollups_labels_and_filter():
    fx = FakeExec()
    AggregatesRepository(fx).agent_rollups()
    for label in ("AS runs", "AS cost_usd", "AS total", "AS active", "AS successes", "AS model"):
        assert label in fx.sql, fx.sql
    assert "FILTER (WHERE agents.status = %s)" in fx.sql
    assert "FILTER (WHERE agents.outcome IN (%s, %s))" in fx.sql
    assert "GROUP BY agents.role" in fx.sql


def test_agents_active_count_label():
    fx = FakeExec()
    AggregatesRepository(fx).agents_active_count()
    assert "AS n" in fx.sql and "agents.status = %s" in fx.sql


def test_today_burn_coalesce_label():
    fx = FakeExec()
    AggregatesRepository(fx).today_burn(100.0)
    assert "coalesce(sum(agents.cost_usd), %s)" in fx.sql.lower() or "coalesce(sum" in fx.sql.lower()
    assert "AS burn" in fx.sql
    assert "agents.started_at >=" in fx.sql


def test_open_tickets_by_project_label_and_in():
    fx = FakeExec()
    AggregatesRepository(fx).open_tickets_by_project()
    assert "AS n" in fx.sql
    assert "tickets.status IN (%s, %s)" in fx.sql
    assert "GROUP BY tickets.project_id" in fx.sql


def test_ticket_counts_by_project_labels():
    fx = FakeExec()
    AggregatesRepository(fx).ticket_counts_by_project()
    assert "AS total" in fx.sql and "AS done" in fx.sql
    assert "FILTER (WHERE tickets.status IN (%s, %s, %s))" in fx.sql
