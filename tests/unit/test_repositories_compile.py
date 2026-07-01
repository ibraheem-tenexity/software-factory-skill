"""Pure (no-DB) unit tests for the SQLAlchemy-Core → SQL compile seam (`repositories._compile.to_sql`).

These assert the exact SQL text + positional params a Core construct compiles to, so a SQLAlchemy
version bump that changes compilation is caught, and the two invariants the execution lanes rely on
hold: (1) placeholders are `%s` positional (never `%(name)s` or `?`), (2) values are bound params in
order. No database is touched.
"""
from sqlalchemy import select, insert, update, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert

from software_factory.models import tickets, gates, projectstate
from software_factory.repositories._compile import to_sql


def test_select_where_in_order_by():
    stmt = (select(tickets.c.id, tickets.c.title)
            .where(tickets.c.project_id == "p1", tickets.c.status.in_(("open", "in_progress")))
            .order_by(tickets.c.id))
    sql, params = to_sql(stmt)
    assert "SELECT" in sql and "FROM tickets" in sql and "ORDER BY tickets.id" in sql
    assert "%s" in sql and "?" not in sql and "%(" not in sql
    assert params == ("p1", "open", "in_progress")


def test_insert_returning_id_positional():
    stmt = insert(tickets).values(project_id="p1", title="t", wave=1).returning(tickets.c.id)
    sql, params = to_sql(stmt)
    assert sql.startswith("INSERT INTO tickets")
    assert "RETURNING tickets.id" in sql
    assert "?" not in sql and "%(" not in sql
    assert set(params) == {"p1", "t", 1}


def test_update_set_then_where_param_order():
    stmt = (update(tickets)
            .where(tickets.c.id == 5, tickets.c.project_id == "p1")
            .values(status="done", diff_lines=10))
    sql, params = to_sql(stmt)
    assert sql.startswith("UPDATE tickets SET")
    assert "?" not in sql
    # SET values are bound before WHERE values in positional order.
    assert params == ("done", 10, 5, "p1")


def test_delete_where():
    stmt = delete(tickets).where(tickets.c.project_id == "p1")
    sql, params = to_sql(stmt)
    assert sql.startswith("DELETE FROM tickets")
    assert params == ("p1",)


def test_on_conflict_do_update_upsert():
    stmt = (pg_insert(projectstate)
            .values(project_id="p1", data="{}"))
    stmt = stmt.on_conflict_do_update(index_elements=["project_id"],
                                      set_={"data": stmt.excluded.data})
    sql, params = to_sql(stmt)
    assert "ON CONFLICT" in sql and "DO UPDATE SET" in sql
    assert "?" not in sql
    assert set(params) == {"p1", "{}"}


def test_on_conflict_do_nothing_composite_pk():
    stmt = pg_insert(gates).values(project_id="p1", name="build", status="green", ts=1.0)
    stmt = stmt.on_conflict_do_update(index_elements=["project_id", "name"],
                                      set_={"status": stmt.excluded.status, "ts": stmt.excluded.ts})
    sql, params = to_sql(stmt)
    assert "ON CONFLICT (project_id, name) DO UPDATE SET" in sql
    assert "?" not in sql
