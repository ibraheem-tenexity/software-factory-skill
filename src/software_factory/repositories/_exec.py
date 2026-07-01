"""Two execution lanes for repositories, both over the existing `dbshim` pool — no new SQLAlchemy
Engine, so the tuned pool/retry/idle-reaper and Supabase-pooler settings are preserved.

- `PathExec`: per-project stores (constructed with a run `path`). Wraps a `dbshim.connect(path)`
  `PgConn`; every statement is its own autocommit transaction (matching today's per-project stores).
- `GlobalExec`: global singleton stores. Checks out a pooled connection per call, runs the statement
  in its own transaction, and returns it (matching today's `users.py`/`blobs.py`/`registries.py`).

Both take SQLAlchemy Core constructs and route them through `to_sql` → `%s` + positional params.
"""
from __future__ import annotations

import os

from .. import dbshim
from ._compile import to_sql


class PathExec:
    """Per-project lane over a `PgConn` (dbshim.connect(path))."""

    def __init__(self, path: str):
        self._conn = dbshim.connect(path)

    def fetchall(self, stmt) -> list:
        sql, params = to_sql(stmt)
        return self._conn.execute(sql, params).fetchall()

    def fetchone(self, stmt):
        sql, params = to_sql(stmt)
        return self._conn.execute(sql, params).fetchone()

    def execute(self, stmt):
        """Run a write; returns the cursor (`.rowcount`, `.lastrowid`, or a RETURNING row via
        `.fetchone()`). Commit is a no-op on PgConn (per-statement autocommit) but called for parity."""
        sql, params = to_sql(stmt)
        cur = self._conn.execute(sql, params)
        self._conn.commit()
        return cur

    def close(self) -> None:
        self._conn.close()


class GlobalExec:
    """Global lane: a fresh pooled connection per call, each in its own transaction."""

    def _run(self, stmt, want_rows: bool):
        sql, params = to_sql(stmt)
        conn = dbshim._pg_connect(os.environ["DATABASE_URL"])
        try:
            with conn.transaction():
                cur = conn.cursor()
                cur.execute(sql, params)
                return [dict(r) for r in cur.fetchall()] if want_rows else None
        finally:
            conn.close()

    def fetchall(self, stmt) -> list:
        return self._run(stmt, want_rows=True)

    def fetchone(self, stmt):
        rows = self._run(stmt, want_rows=True)
        return rows[0] if rows else None

    def execute(self, stmt) -> None:
        self._run(stmt, want_rows=False)
