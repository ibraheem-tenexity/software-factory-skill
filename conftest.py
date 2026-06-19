import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import pytest

# Postgres everywhere — the suite runs against a local/throwaway Postgres (the dev container by
# default). Override DATABASE_URL to point elsewhere. These are defaults, so an env already set
# (CI, a different container) wins.
os.environ.setdefault("SF_ENVIRONMENT", "test")
os.environ.setdefault("SF_DB", "postgres")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5434/postgres")


def _sa_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    return url


@pytest.fixture(scope="session", autouse=True)
def _db_schema():
    """Build the whole schema from the SQLAlchemy models on the test Postgres, once per session.
    Yields the (raw) DATABASE_URL so per-test cleanup uses the session's known-good connection even
    if a test monkeypatches the env."""
    from sqlalchemy import create_engine
    from software_factory import models

    url = os.environ["DATABASE_URL"]
    engine = create_engine(_sa_url(url), connect_args={"prepare_threshold": None})
    models.metadata.drop_all(engine)      # clean slate (a prior run may have left tables)
    models.metadata.create_all(engine)
    engine.dispose()
    yield url


@pytest.fixture(autouse=True)
def _clean_db(_db_schema):
    """Empty every table + reset identity sequences before each test — gives deterministic ids
    (first insert is id=1, as the old sqlite-per-file tests expected) and isolates tests that share
    the flat tables."""
    import psycopg
    from software_factory import models

    names = ", ".join(f'public."{t}"' for t in models.metadata.tables)
    conn = psycopg.connect(_db_schema, autocommit=True)
    try:
        conn.execute(f"TRUNCATE {names} RESTART IDENTITY CASCADE")
    finally:
        conn.close()
    yield
