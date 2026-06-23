"""The Postgres connection seam the run stores use.

`connect(path)` returns a `PgConn` over psycopg3
against `DATABASE_URL` (the Supabase transaction pooler on 6543 in prod; a local Postgres in dev/test).
The `path` only names the run directory (project.log/chat.jsonl still live on the volume) and the run id
the stores scope by; no per-project schema or database file is created.

`PgConn` presents a minimal DB-API connection surface over psycopg3:
  - `?`->`%s` placeholder translation (the stores' SQL uses `?`);
  - `.lastrowid` via an appended `RETURNING id` on inserts into the surrogate-id tables;
  - `prepare_threshold=None` — the 6543 pooler multiplexes backends, so server-side prepares break;
  - each statement in its own transaction; 3x retry with backoff on transient pooler/network errors.

Schema is owned by the SQLAlchemy models (Alembic in prod, `metadata.create_all` in tests), never by
dbshim. Run discovery (`registry_projects`) reads the flat `projectstate` table.
"""
from __future__ import annotations

import os
import re
import time

_RETRY_SLEEP = 0.5
_TRIES = 3
# Tables with an `id` identity column — INSERTs get RETURNING id so `.lastrowid` keeps working
# (projectstate/gates/agents key on natural/composite PKs instead).
_ID_TABLES = ("tickets", "phases", "artifacts", "blockers", "verifications", "deployments", "blobs")


def connect(path: str):
    os.makedirs(path or ".", exist_ok=True)  # project.log/chat.jsonl live here
    return PgConn(_pg_connect(os.environ["DATABASE_URL"]))


def _pg_connect(url: str):
    import psycopg
    from psycopg.rows import dict_row

    conn = psycopg.connect(url, row_factory=dict_row, autocommit=True)
    # psycopg3 auto-prepare breaks under transaction pooling (prepared stmts are
    # per-backend; the pooler swaps backends under us).
    conn.prepare_threshold = None
    return conn


def registry_projects() -> list:
    """Runs known to the flat `public.projectstate` table: [{project_id, created}]. `created` is 0
    (projectstate carries no timestamp; the console falls back to volume mtime for sorting). [] on any
    pg error so the run listing keeps working even if the DB is briefly unreachable."""
    try:
        conn = _pg_connect(os.environ["DATABASE_URL"])
        try:
            with conn.transaction():
                cur = conn.cursor()
                cur.execute("SELECT project_id FROM public.projectstate")
                return [{"project_id": r["project_id"], "created": 0} for r in cur.fetchall()]
        finally:
            conn.close()
    except Exception:
        return []


def _translate(sql: str) -> str:
    return sql.replace("?", "%s")


class _Cursor:
    """Result holder: psycopg buffers rows client-side at execute, so fetches stay
    valid after the statement's transaction closes."""

    def __init__(self, rows, rowcount, lastrowid):
        self._rows = list(rows)
        self.rowcount = rowcount
        self.lastrowid = lastrowid

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class PgConn:
    """Minimal DB-API connection layer over psycopg3 against the flat `public` schema."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql: str, params=()):
        tsql = _translate(sql)
        head = tsql.lstrip().upper()
        returning = None
        if head.startswith("INSERT") and "RETURNING" not in head:
            m = re.match(r"\s*INSERT\s+INTO\s+(\w+)", tsql, re.I)
            if m and m.group(1).lower() in _ID_TABLES:
                tsql += " RETURNING id"
                returning = "id"
        wants_rows = returning or head.startswith("SELECT") or " RETURNING " in head
        return self._tx(tsql, tuple(params), wants_rows, returning)

    def executescript(self, script: str):
        stmts = [s.strip() for s in script.split(";") if s.strip()]
        last = None
        for s in stmts:
            last = self._tx(_translate(s), (), False, None)
        return last

    def commit(self):  # every statement is its own transaction
        pass

    def close(self):
        self._conn.close()

    def _tx(self, sql: str, params: tuple, wants_rows: bool, returning):
        last_err = None
        for attempt in range(_TRIES):
            try:
                with self._conn.transaction():
                    cur = self._conn.cursor()
                    cur.execute(sql, params)
                    rows = cur.fetchall() if wants_rows else []
                    lastrowid = (rows[0] or {}).get("id") if returning and rows else None
                    return _Cursor(rows, cur.rowcount, lastrowid)
            except Exception as e:  # pooler hiccup / transient network — retry, then surface
                last_err = e
                time.sleep(_RETRY_SLEEP * (attempt + 1))
        raise last_err
