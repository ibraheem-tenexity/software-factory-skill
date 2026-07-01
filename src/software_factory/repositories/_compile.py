"""Compile a SQLAlchemy Core construct to a parameterized SQL string + ordered params.

We compile with the PostgreSQL dialect in **positional** paramstyle (`format` → `%s`, not `%(name)s`),
because both execution lanes want positional params:
  - the `dbshim.PgConn` lane calls `tuple(params)` internally, so it requires a positional sequence;
  - a direct psycopg3 cursor accepts `%s` + a sequence just as happily.

`literal_binds` is left OFF — values stay bound parameters (no injection, no quoting bugs). The compiled
SQL contains `%s`, never `?`, so `PgConn._translate`'s `?`→`%s` pass is a no-op on it.
"""
from __future__ import annotations

from sqlalchemy.dialects import postgresql

_DIALECT = postgresql.dialect(paramstyle="format")


def to_sql(stmt) -> tuple[str, tuple]:
    """Return (sql, params) for a Core statement: `sql` uses `%s` placeholders, `params` is the
    values in positional order.

    `render_postcompile=True` expands "expanding" bind params (e.g. `col.in_([...])`) into real
    per-element `%s` placeholders AT COMPILE TIME. Without it SQLAlchemy leaves an `IN (__[POSTCOMPILE])`
    marker it would expand itself at execution — but we hand the SQL to psycopg directly, so we must
    expand here or the IN clause breaks."""
    compiled = stmt.compile(dialect=_DIALECT, compile_kwargs={"render_postcompile": True})
    params = tuple(compiled.params[k] for k in compiled.positiontup)
    return str(compiled), params
