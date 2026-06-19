"""Alembic environment for the console's GLOBAL public tables.

Connects to $DATABASE_URL (the console's Postgres). Online mode only — we always have a live DB
when migrating. Raw SQL migrations (op.execute) so no SQLAlchemy models are required.
"""
from __future__ import annotations

import os
from alembic import context
from sqlalchemy import create_engine, pool


def _url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set — Alembic migrations require Postgres.")
    # SQLAlchemy wants the psycopg3 driver name explicitly.
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    elif url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    return url


def run_migrations_online() -> None:
    # prepare_threshold=None: the Supabase transaction pooler (6543) multiplexes connections, so
    # server-side prepared statements break ("prepared statement _pg3_0 does not exist").
    engine = create_engine(_url(), poolclass=pool.NullPool, future=True,
                          connect_args={"prepare_threshold": None})
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None,
                          version_table="alembic_version", version_table_schema="public")
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    raise SystemExit("offline alembic mode is not supported for this project")
run_migrations_online()
