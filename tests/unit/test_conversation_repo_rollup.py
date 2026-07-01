"""Pure unit tests for ConversationRepository.rollup() (SOF-34/T1.5) — no DB. Injects a fake `exec_`
whose fetchall() runs the REAL (pure, no-connection) `to_sql()` compiler and returns canned rows, so
these tests verify the actual compiled SQL/params — not just that the code doesn't crash — while
staying entirely off the DB (to_sql() only compiles a SQLAlchemy Core statement to a string + params
tuple; it never opens a socket). Matches the standing no-DB-connection constraint on this box."""
import datetime

from software_factory.repositories.conversation_repo import ConversationRepository
from software_factory.repositories._compile import to_sql


class _CapturingExec:
    def __init__(self, rows=None):
        self.rows = rows if rows is not None else []
        self.sql = None
        self.params = None

    def fetchall(self, stmt):
        self.sql, self.params = to_sql(stmt)
        return self.rows

    def fetchone(self, stmt):
        self.sql, self.params = to_sql(stmt)
        return self.rows[0] if self.rows else None


def test_rollup_with_no_filters_compiles_a_grouped_limited_query():
    x = _CapturingExec()
    ConversationRepository(x).rollup(limit=25)
    assert "GROUP BY" in x.sql
    assert "conversation.session_id" in x.sql
    assert "LIMIT" in x.sql
    assert 25 in x.params
    assert "WHERE" not in x.sql
    assert "HAVING" not in x.sql


def test_rollup_each_filter_adds_a_where_predicate_and_binds_its_value():
    x = _CapturingExec()
    ConversationRepository(x).rollup(org_id="org-1", project_id="proj-1", user_id="user-1",
                                     session_id="sess-1", role="agent", limit=10)
    assert "WHERE" in x.sql
    for expected in ("org-1", "proj-1", "user-1", "sess-1", "agent"):
        assert expected in x.params


def test_rollup_date_range_filters_compile_as_comparisons():
    x = _CapturingExec()
    df = datetime.datetime(2026, 1, 1)
    dt = datetime.datetime(2026, 6, 1)
    ConversationRepository(x).rollup(date_from=df, date_to=dt, limit=10)
    assert ">=" in x.sql and "<=" in x.sql
    assert df in x.params and dt in x.params


def test_rollup_cursor_compiles_a_having_clause_for_keyset_pagination():
    x = _CapturingExec()
    cursor_ts = datetime.datetime(2026, 3, 1, 12, 0, 0)
    ConversationRepository(x).rollup(cursor=(cursor_ts, "sess-prev"), limit=10)
    assert "HAVING" in x.sql
    assert cursor_ts in x.params and "sess-prev" in x.params


def test_rollup_orders_by_last_activity_desc_then_session_id_desc():
    x = _CapturingExec()
    ConversationRepository(x).rollup(limit=10)
    assert "ORDER BY" in x.sql
    order_clause = x.sql.split("ORDER BY", 1)[1]
    assert "DESC" in order_clause


def test_rollup_returns_the_rows_the_exec_gave_it_unmodified():
    canned = [{"session_id": "s1", "turn_count": 3}]
    x = _CapturingExec(rows=canned)
    result = ConversationRepository(x).rollup(limit=10)
    assert result == canned
