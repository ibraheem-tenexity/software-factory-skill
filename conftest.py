import fcntl
import os
import sys
from urllib.parse import urlsplit, urlunsplit

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import pytest

# Postgres everywhere. The suite runs against a PG SERVER (the dev container by default); override
# DATABASE_URL to point at a different server. The db NAME in that URL is ignored — each pytest
# PROCESS (and each pytest-xdist worker) mints its OWN throwaway database below, so two concurrent
# runs NEVER share the `public` schema. This is the permanent fix for the cross-run TRUNCATE/DROP
# contamination that made the suite flaky under any concurrency.
os.environ.setdefault("SF_ENVIRONMENT", "test")
os.environ.setdefault("SF_DB", "postgres")

# #197: per-process DB naming (below) already prevents cross-run schema collisions — that part was
# never broken. The REAL fleet-wide hang was concurrent pytest processes each loading the full app
# into RAM at once, exhausting machine memory (observed: 7 procs swap-thrashing at ~79% CPU for up
# to 4.7h). Fix: a machine-wide, blocking flock so only ONE pytest process runs at a time, fleet-wide
# — later invocations queue instead of piling up. The lock path is FIXED under /tmp, not repo/worktree
# -relative: different worktrees are different directories, so a repo-local lock would never see each
# other. xdist workers (PYTEST_XDIST_WORKER set) skip it — the invoking/controller process already
# holds it for the whole session, so xdist's OWN internal parallelism isn't defeated if ever used.
_FLEET_LOCK_PATH = "/tmp/sf-pytest-fleet.lock"
_fleet_lock_fh = None


def _acquire_fleet_lock() -> None:
    global _fleet_lock_fh
    if os.environ.get("PYTEST_XDIST_WORKER"):
        return
    _fleet_lock_fh = open(_FLEET_LOCK_PATH, "w")
    fcntl.flock(_fleet_lock_fh, fcntl.LOCK_EX)   # blocks here until the previous run releases it


def _release_fleet_lock() -> None:
    global _fleet_lock_fh
    if _fleet_lock_fh is not None:
        fcntl.flock(_fleet_lock_fh, fcntl.LOCK_UN)
        _fleet_lock_fh.close()
        _fleet_lock_fh = None


_acquire_fleet_lock()

_SERVER_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5434/postgres")
# Unique per process: xdist worker id (gw0/gw1/… or "main") + PID isolates both xdist workers and
# independent `pytest` invocations.
_WORKER = os.environ.get("PYTEST_XDIST_WORKER", "main")
_PRIVATE_DB = f"sftest_{_WORKER}_{os.getpid()}"


def _with_db(url: str, dbname: str) -> str:
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, "/" + dbname, p.query, p.fragment))


_PRIVATE_URL = _with_db(_SERVER_URL, _PRIVATE_DB)


def _sa_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    return url


def _maintenance():
    """A connection to the server's default `postgres` db — CREATE/DROP DATABASE cannot run against
    the database you're connected to."""
    import psycopg
    return psycopg.connect(_with_db(_SERVER_URL, "postgres"), autocommit=True)


def _drop_private_db() -> None:
    """Terminate any lingering backends, then drop — version-agnostic (no DROP … WITH FORCE needed)."""
    try:
        conn = _maintenance()
        try:
            conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()", (_PRIVATE_DB,))
            conn.execute(f'DROP DATABASE IF EXISTS "{_PRIVATE_DB}"')
        finally:
            conn.close()
    except Exception:
        pass


def _create_private_db() -> None:
    _drop_private_db()                       # clear a stale leftover from a crashed prior run
    conn = _maintenance()
    try:
        conn.execute(f'CREATE DATABASE "{_PRIVATE_DB}"')
    finally:
        conn.close()


def _sweep_orphaned_dbs() -> None:
    """Drop every OTHER sftest_* database. Only ever runs while this process holds the fleet lock
    (see _acquire_fleet_lock above) — no other pytest process can be legitimately alive without
    holding that same lock, so any sftest_* db found here is provably orphaned (a crashed/killed
    prior run that never reached its own _drop_private_db). Best-effort per-db: one failure must
    not block the sweep or this run's own setup."""
    try:
        conn = _maintenance()
    except Exception:
        return
    try:
        rows = conn.execute(
            "SELECT datname FROM pg_database WHERE datname LIKE 'sftest\\_%'").fetchall()
        for (name,) in rows:
            if name == _PRIVATE_DB:
                continue
            try:
                conn.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()", (name,))
                conn.execute(f'DROP DATABASE IF EXISTS "{name}"')
            except Exception:
                pass
    except Exception:
        pass
    finally:
        conn.close()


# Provision the private DB + schema AT IMPORT — before any app code reads DATABASE_URL (the console
# singletons hit Postgres the moment they're constructed during collection) — then point the whole
# process at it. The orphan sweep runs first (see its docstring for why it's safe here specifically).
_sweep_orphaned_dbs()
_create_private_db()
os.environ["DATABASE_URL"] = _PRIVATE_URL


def _build_schema() -> None:
    from sqlalchemy import create_engine
    from software_factory import models
    engine = create_engine(_sa_url(_PRIVATE_URL), connect_args={"prepare_threshold": None})
    # SOF-26: doc_summary.embedding / chunk.dense are pgvector Vector columns — the extension
    # must exist before create_all issues their CREATE TABLE, or those two tables fail to build.
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
    models.metadata.create_all(engine)
    engine.dispose()


_build_schema()


def pytest_unconfigure(config):
    # Always runs at process exit (incl. --collect-only / the xdist controller) — guarantees the
    # throwaway database is removed even if the session fixture never ran. Release the fleet lock
    # LAST so the next queued run's sweep+create only starts once our own db is fully gone. A
    # SIGKILL'd run releases the lock automatically (flock is tied to the fd/process) even though
    # this function never gets to run — a hung/killed run can never deadlock the fleet.
    _drop_private_db()
    _release_fleet_lock()


@pytest.fixture(scope="session", autouse=True)
def _db_schema():
    """The private database is built at import; this just exposes its URL to per-test cleanup."""
    yield _PRIVATE_URL


@pytest.fixture(autouse=True)
def _clean_db(_db_schema):
    """Empty every table + reset identity sequences before each test — deterministic ids (first
    insert id=1), now within this process's PRIVATE database, so it can never clobber another run."""
    import psycopg
    from software_factory import models

    # roles/role_permissions are migration-seeded REFERENCE data (the RBAC buckets), not per-test
    # state — like a lookup table they persist for the session (and users.role_id FKs them). Truncating
    # them would wipe the seed and break every user insert, so they're excluded here.
    _seed = {"roles", "role_permissions"}
    names = ", ".join(f'public."{t}"' for t in models.metadata.tables if t not in _seed)
    conn = psycopg.connect(_db_schema, autocommit=True)
    try:
        conn.execute(f"TRUNCATE {names} RESTART IDENTITY CASCADE")
    finally:
        conn.close()
    yield
