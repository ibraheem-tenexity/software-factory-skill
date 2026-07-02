"""Two execution lanes for repositories, both over the existing `dbshim` pool — no new SQLAlchemy
Engine, so the tuned pool/retry/idle-reaper and Supabase-pooler settings are preserved.

- `PathExec`: per-project stores (constructed with a run `path`). Checks out a pooled `PgConn` per
  CALL (`dbshim.connect(path)`) and returns it in a finally; every statement is its own autocommit
  transaction (matching today's per-project stores).
- `GlobalExec`: global singleton stores. Checks out a pooled connection per call, runs the statement
  in its own transaction, and returns it (matching today's `users.py`/`blobs.py`/`registries.py`).

Both take SQLAlchemy Core constructs and route them through `to_sql` → `%s` + positional params.
"""
from __future__ import annotations

import os

from .. import dbshim
from ._compile import to_sql


class PathExec:
    """Per-project lane over a `PgConn` (dbshim.connect(path)) — one checkout PER CALL.

    Construction used to check out a PgConn and hold it for the object's whole lifetime. The store
    objects built on this lane (ProjectStore/TicketStore/…) are constructed per-request all over
    the console, and several are alive at once inside a single call (e.g. `Console.status`), so
    each in-flight request pinned 3-4 of the pool's `_POOL_MAX=10` slots even while idle — a
    page-load burst of parallel GETs plus the 3s background poller saturated the pool, and every
    `getconn()` waiter then held its own already-checked-out conns for the full 5s wait before
    raising "DB pool exhausted" (#126's no-silent-growth cap, kept intact). Checking out per call,
    like `GlobalExec`, means a slot is held only while a statement actually runs. Semantics are
    unchanged: every statement was already its own autocommit transaction on PgConn, and the
    cursor buffers rows client-side so it stays valid after the conn returns to the pool."""

    def __init__(self, path: str):
        self._path = path

    def fetchall(self, stmt) -> list:
        sql, params = to_sql(stmt)
        conn = dbshim.connect(self._path)
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def fetchone(self, stmt):
        sql, params = to_sql(stmt)
        conn = dbshim.connect(self._path)
        try:
            return conn.execute(sql, params).fetchone()
        finally:
            conn.close()

    def execute(self, stmt):
        """Run a write; returns the cursor (`.rowcount`, `.lastrowid`, or a RETURNING row via
        `.fetchone()`). No commit needed: every statement is its own autocommit transaction."""
        sql, params = to_sql(stmt)
        conn = dbshim.connect(self._path)
        try:
            return conn.execute(sql, params)
        finally:
            conn.close()

    def close(self) -> None:
        pass  # nothing held between calls; kept for the existing `try/finally exec_.close()` sites


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
