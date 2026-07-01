"""Compile a SQLAlchemy Core construct to a parameterized SQL string + ordered params, plus a
handful of column-expression/value-serialize helpers repeated across repos for the SAME
GlobalExec raw-SQL type-decode gotchas (SOF-55/SOF-46c) — psycopg3's own default adapters run
instead of SQLAlchemy's bind/result processors, so UUID/epoch/JSONB columns each need an explicit
cast or pre-serialize at every call site. Kept byte-identical to what each replaced (verified via
str(stmt.compile()) diffs) — these are wrappers around the exact same expressions, not a behavior
change.

We compile with the PostgreSQL dialect in **positional** paramstyle (`format` → `%s`, not `%(name)s`),
because both execution lanes want positional params:
  - the `dbshim.PgConn` lane calls `tuple(params)` internally, so it requires a positional sequence;
  - a direct psycopg3 cursor accepts `%s` + a sequence just as happily.

`literal_binds` is left OFF — values stay bound parameters (no injection, no quoting bugs). The compiled
SQL contains `%s`, never `?`, so `PgConn._translate`'s `?`→`%s` pass is a no-op on it.
"""
from __future__ import annotations

import json

from sqlalchemy import Float, Text, cast, func
from sqlalchemy.dialects import postgresql

_DIALECT = postgresql.dialect(paramstyle="format")


def epoch_cast(col):
    """DateTime column -> epoch float. A bare `func.extract("epoch", col)` returns Postgres
    `numeric`, which psycopg3 decodes to `decimal.Decimal`, not `float` (SOF-55) -- `cast(...,
    Float)` on top forces the real double-precision result the rest of the app expects. Callers
    still apply their own `.label(...)`."""
    return cast(func.extract("epoch", col), Float)


def uuid_str_cast(col):
    """UUID column -> plain string. GlobalExec's raw-SQL path bypasses SQLAlchemy's own
    UUID(as_uuid=False) coercion, so psycopg3's native UUID adapter decodes a bare UUID column to
    a Python `uuid.UUID` object on SELECT/RETURNING output, not the string the rest of the app
    expects (SOF-55). Bind parameters (WHERE/INSERT VALUES) don't need this — Postgres infers the
    type from the typed column there."""
    return cast(col, Text)


def serialize_jsonb(value, default=None):
    """JSON-encode `value` for a JSONB column -- GlobalExec's raw-SQL path bypasses SQLAlchemy's
    own bind processor, so a bare dict/list is never auto-serialized on the way in. `default`
    substitutes for a None `value` before encoding; leave it None (the default) to pass a bare
    None straight through as SQL NULL instead of encoding it."""
    if value is None:
        return json.dumps(default) if default is not None else None
    return json.dumps(value)


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
