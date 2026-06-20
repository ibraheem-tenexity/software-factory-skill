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


# Provision the private DB + schema AT IMPORT — before any app code reads DATABASE_URL (the console
# singletons hit Postgres the moment they're constructed during collection) — then point the whole
# process at it.
_create_private_db()
os.environ["DATABASE_URL"] = _PRIVATE_URL


def _build_schema() -> None:
    from sqlalchemy import create_engine
    from software_factory import models
    engine = create_engine(_sa_url(_PRIVATE_URL), connect_args={"prepare_threshold": None})
    models.metadata.create_all(engine)
    engine.dispose()


_build_schema()


def pytest_unconfigure(config):
    # Always runs at process exit (incl. --collect-only / the xdist controller) — guarantees the
    # throwaway database is removed even if the session fixture never ran.
    _drop_private_db()


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

    names = ", ".join(f'public."{t}"' for t in models.metadata.tables)
    conn = psycopg.connect(_db_schema, autocommit=True)
    try:
        conn.execute(f"TRUNCATE {names} RESTART IDENTITY CASCADE")
    finally:
        conn.close()
    yield
