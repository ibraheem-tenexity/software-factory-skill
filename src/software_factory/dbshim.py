"""The Postgres connection seam the run stores use.

`connect(path)` returns a `PgConn` over psycopg3
against the factory state DB (Supabase transaction pooler on 6543 in prod; a local Postgres in dev/test).
The URL is read from ``SF_STATE_DB_URL`` (preferred) or ``DATABASE_URL`` (fallback).  Stage subprocesses
receive ``SF_STATE_DB_URL`` from ``stage_env_baseline`` but NOT ``DATABASE_URL``, so the CLI can write
run-state without the factory DB URL leaking into the customer app's environment.
The `path` only names the run directory (project.log/chat.jsonl still live on the volume) and the run id
the stores scope by; no per-project schema or database file is created.

`PgConn` presents a minimal DB-API connection surface over psycopg3:
  - `?`->`%s` placeholder translation (the stores' SQL uses `?`);
  - `.lastrowid` via an appended `RETURNING id` on inserts into the surrogate-id tables;
  - `prepare_threshold=None` — the 6543 pooler multiplexes backends, so server-side prepares break;
  - each statement in its own transaction; 3x retry with backoff on transient pooler/network errors.

CONNECTION POOL: a single module-level `_StatePool` reuses warm psycopg3 connections across requests
instead of opening a fresh TCP+TLS+auth handshake per call (the old `psycopg.connect()`-per-statement
path cost ~20-50ms/connection against the 6543 pooler + connection-storm risk under load). The pool is
sized min_size=1 / max_size=10 (single-process Railway console) with a 5-min idle reaper. Connections
are checked out in `_pg_connect` and returned on `close()` (the existing call sites all `try/finally
conn.close()`, so the swap is transparent). `prepare_threshold=None` + autocommit are set once at
checkout. Schema is owned by the SQLAlchemy models (Alembic in prod, `metadata.create_all` in tests),
never by dbshim. Run discovery (`registry_projects`) reads the flat `projectstate` table.
"""
from __future__ import annotations

import os
import re
import threading
import time

_RETRY_SLEEP = 0.5
_TRIES = 3
# Tables with an `id` identity column — INSERTs get RETURNING id so `.lastrowid` keeps working
# (projectstate/gates/agents key on natural/composite PKs instead).
_ID_TABLES = ("tickets", "phases", "artifacts", "blockers", "verifications", "deployments", "blobs")

# Pool sizing (single-process Railway console). Min 1 warm conn; grow on demand to max; reap idle
# connections older than 5min so a quiet console doesn't hold backends on the 6543 pooler.
_POOL_MIN = 1
_POOL_MAX = 10
_POOL_IDLE_TIMEOUT = 300.0


def _db_url() -> str:
    # SF_STATE_DB_URL is the dedicated factory-state URL injected by stage_env_baseline;
    # DATABASE_URL is the legacy name used outside stage contexts.
    return os.environ.get("SF_STATE_DB_URL") or os.environ["DATABASE_URL"]


class _StatePool:
    """Thread-safe pool of warm psycopg3 connections for the factory state DB.

    Grows lazily up to `_POOL_MAX`; idle connections are returned to the queue and reaped either
    on the next checkout or by a background daemon thread (_idle_reaper). A bad (closed/stale)
    connection is discarded and another is tried. `close_all()` drains the pool (called at process
    shutdown via atexit)."""

    def __init__(self):
        self._url: str | None = None
        self._pool: list = []  # [(conn, last_used_ts)]
        self._out = 0
        # Condition wraps a Lock; `with self._lock:` is identical to the old Lock usage, but
        # `.wait()` / `.notify_all()` let getconn() block (and yield the lock) when at cap
        # instead of silently overflowing past _POOL_MAX.
        self._lock = threading.Condition()
        t = threading.Thread(target=self._idle_reaper, daemon=True, name="dbshim-idle-reaper")
        t.start()

    def _configure(self, conn):
        conn.prepare_threshold = None
        # SOF-26/SOF-29: psycopg3 has no built-in adapter for pgvector's `vector` type. Without
        # this, a `vector` column reads back as a plain string (confirmed empirically against a
        # real pgvector DB during #237's review: "[0,0,0,...]", the STRING, not a 1024-length
        # array) — inserts work either way, only reads are silently wrong. Registered once per
        # real connection (here, at creation), not per-checkout, since it's a property of the
        # psycopg connection object itself. Best-effort: a codebase with no pgvector columns in
        # use yet must never fail to connect over this.
        try:
            from pgvector.psycopg import register_vector
            register_vector(conn)
        except Exception:
            pass
        return conn

    def _new_conn(self):
        import psycopg
        from psycopg.rows import dict_row
        conn = psycopg.connect(self._url, row_factory=dict_row, autocommit=True)
        return self._configure(conn)

    def _idle_reaper(self):
        """Background daemon: close connections that have been idle past _POOL_IDLE_TIMEOUT.
        Without this, quiet periods left stale connections holding Supabase pooler sessions open
        indefinitely (the lazy in-getconn reaper only ran when a new caller arrived)."""
        while True:
            time.sleep(_POOL_IDLE_TIMEOUT / 2)
            to_close = []
            with self._lock:
                now = time.monotonic()
                fresh = [(c, ts) for c, ts in self._pool if now - ts <= _POOL_IDLE_TIMEOUT]
                to_close = [(c, ts) for c, ts in self._pool if now - ts > _POOL_IDLE_TIMEOUT]
                self._pool[:] = fresh
            for conn, _ in to_close:
                try:
                    conn._hard_close()
                except Exception:
                    pass

    def getconn(self):
        url = _db_url()
        with self._lock:
            if self._url is None:
                self._url = url
            elif self._url != url:
                # URL changed (env swap / test reset) — drain + rebind rather than mix pools.
                self._drain_locked()
                self._url = url
            # try a warm idle conn (lazy idle-reap on the way through)
            while self._pool:
                conn, last_used = self._pool.pop()
                if (time.monotonic() - last_used) > _POOL_IDLE_TIMEOUT:
                    try: conn._hard_close()
                    except Exception: pass
                    continue
                self._out += 1
                return self._wrap(conn)
            # No idle conn available — if at cap, wait for putconn() to signal a return.
            # Previously this was a bare `pass` that fell through to _new_conn(), silently
            # growing the pool past _POOL_MAX and accumulating Supabase pooler sessions (#126).
            deadline = time.monotonic() + 5.0
            while self._out >= _POOL_MAX:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError(
                        f"DB pool exhausted: {_POOL_MAX} connections already checked out"
                    )
                self._lock.wait(timeout=min(remaining, 0.5))
                # A putconn() may have returned an idle conn — check before creating a new one.
                while self._pool:
                    conn, last_used = self._pool.pop()
                    if (time.monotonic() - last_used) > _POOL_IDLE_TIMEOUT:
                        try: conn._hard_close()
                        except Exception: pass
                        continue
                    self._out += 1
                    return self._wrap(conn)
            conn = self._new_conn()
            self._out += 1
            return self._wrap(conn)

    def _wrap(self, conn):
        # The raw psycopg3 Connection.close() tears down the TCP+TLS+auth we want to reuse. Swap it
        # for a return-to-pool so the existing call sites (blobs.py / _exec.py / PgConn all do
        # `try/finally conn.close()`) recycle the connection transparently. Original close preserved
        # as `_hard_close` for the idle-reaper / close_all path.
        #
        # IDEMPOTENT: getconn() calls _wrap() on EVERY checkout, including a warm connection being
        # reused for the 2nd/3rd/... time — at that point `conn.close` is ALREADY `_return_to_pool`
        # from the previous wrap. Capturing `original_close = conn.close` unconditionally would
        # capture that stale `_return_to_pool` as the new `_hard_close`, corrupting the true-close
        # escape hatch. The next `_drain_locked()` (close_all() at atexit, or a URL-change drain)
        # then calls this corrupted `_hard_close()`, which calls `putconn()`, which RE-APPENDS the
        # connection into `self._pool` — so `_drain_locked`'s `while self._pool:` loop never empties,
        # spinning at ~100% CPU forever. Only capture the TRUE original close on the FIRST wrap.
        if not hasattr(conn, "_hard_close"):
            conn._hard_close = conn.close
        pool = self
        def _return_to_pool(*_a, **_kw):
            pool.putconn(conn)
        conn.close = _return_to_pool
        return conn

    def putconn(self, conn):
        with self._lock:
            self._out = max(0, self._out - 1)
            try:
                if conn.closed:
                    self._lock.notify_all()
                    return
            except Exception:
                self._lock.notify_all()
                return
            self._pool.append((conn, time.monotonic()))
            self._lock.notify_all()  # wake any getconn() caller blocked at the cap

    def _drain_locked(self):
        while self._pool:
            conn, _ = self._pool.pop()
            try: conn._hard_close()
            except Exception: pass

    def close_all(self):
        with self._lock:
            self._drain_locked()
            self._url = None
            self._lock.notify_all()  # unblock any blocked getconn() callers


_POOL = _StatePool()


def _close_at_shutdown():
    try:
        _POOL.close_all()
    except Exception:
        pass

# Best-effort drain on interpreter exit (uvicorn worker recycle / `railway` restarts).
import atexit
atexit.register(_close_at_shutdown)


def execute(sql: str, params: tuple = ()) -> list:
    """One-shot statement against the factory state DB — used by the checkpoint store which is not
    scoped to a per-project path. Checks out a pooled connection, runs the statement in a single
    transaction, returns the conn. Returns rows (list of dicts) or empty list."""
    conn = _pg_connect(_db_url())
    try:
        cur = conn.execute(sql, params)
        return cur.fetchall() if cur else []
    finally:
        conn.close()


def connect(path: str):
    os.makedirs(path or ".", exist_ok=True)  # project.log/chat.jsonl live here
    return PgConn(_pg_connect(_db_url()))


def _pg_connect(url: str):
    """Check out a warm psycopg3 connection from the pool (opening a new one on cold start / under
    growth). The caller MUST `.close()` it (all call sites do, in a finally) — that returns it to
    the pool rather than tearing down the TCP+TLS+auth handshake."""
    return _POOL.getconn()


def registry_projects() -> list:
    """Runs known to the flat `public.projectstate` table: [{project_id, created}]. `created` is 0
    (projectstate carries no timestamp; the console falls back to volume mtime for sorting). [] on any
    pg error so the run listing keeps working even if the DB is briefly unreachable."""
    try:
        conn = _pg_connect(_db_url())
        try:
            with conn.transaction():
                cur = conn.cursor()
                cur.execute("SELECT project_id FROM public.projectstate")
                return [{"project_id": r["project_id"], "created": 0} for r in cur.fetchall()]
        finally:
            conn.close()
    except Exception:
        return []


def project_in_registry(project_id: str) -> bool:
    """True if this project_id has a row in the projectstate table. False on miss or any pg error."""
    try:
        conn = _pg_connect(_db_url())
        try:
            with conn.transaction():
                cur = conn.cursor()
                cur.execute("SELECT 1 FROM public.projectstate WHERE project_id = %s LIMIT 1",
                            (project_id,))
                return cur.fetchone() is not None
        finally:
            conn.close()
    except Exception:
        return False


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
        self._closed = False

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

    def commit(self):  # every statement is its own transaction
        pass

    def close(self):
        if not self._closed:
            self._closed = True
            self._conn.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

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
