"""Backfill per-run sqlite files into the Postgres backend (SF_DB=postgres).

Idempotent: a run already in public.sf_runs is skipped (force=True re-runs it; row
copies are ON CONFLICT DO NOTHING either way, so a partial earlier pass self-heals).
Ids are preserved and identity sequences bumped past MAX(id), so post-flip inserts
never collide with backfilled rows. Runs wherever the sqlite files live — in
production that is the console container (the /data volume).
"""
from __future__ import annotations

import os
import sqlite3

from . import dbshim

_TABLES = ("runstate", "phases", "artifacts", "blockers", "gates",
           "verifications", "tickets", "agents")
_ID_TABLES = ("phases", "artifacts", "blockers", "verifications", "tickets")


def backfill_run(runs_dir: str, run_id: str, force: bool = False,
                 registry: set | None = None) -> str:
    db_path = os.path.join(runs_dir, run_id, "run.db")
    if not os.path.exists(db_path):
        return "no-db"
    if registry is None:
        registry = {r["run_id"] for r in dbshim.registry_runs()}
    if run_id in registry and not force:
        return "skip"
    # The stores' constructors create the pg schema + tables for this run.
    from .agents import AgentRegistry
    from .db import RunDB
    from .tickets import TicketStore
    RunDB(db_path)
    TicketStore(db_path)
    AgentRegistry(db_path)

    src = sqlite3.connect(db_path)
    src.row_factory = sqlite3.Row
    dst = dbshim.connect(db_path)
    copied = 0
    for t in _TABLES:
        try:
            rows = src.execute(f"SELECT * FROM {t}").fetchall()
        except sqlite3.OperationalError:
            continue  # table never created in this run
        for row in rows:
            cols = list(row.keys())
            dst.execute(
                f"INSERT INTO {t} ({', '.join(cols)}) "
                f"VALUES ({', '.join('?' * len(cols))}) ON CONFLICT DO NOTHING",
                tuple(row))
            copied += 1
        if t in _ID_TABLES and rows:
            # Identity sequences must clear the preserved ids (resolved via search_path).
            dst.execute(
                f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), "
                f"(SELECT COALESCE(MAX(id), 1) FROM {t}))")
    src.close()
    return f"copied {copied} rows"


def backfill_all(runs_dir: str, force: bool = False) -> dict:
    """All runs under runs_dir. Safe to call at every boot: already-registered runs skip."""
    if (os.environ.get("SF_DB") or "sqlite").lower() != "postgres":
        return {}
    registry = {r["run_id"] for r in dbshim.registry_runs()}
    out = {}
    for name in sorted(os.listdir(runs_dir)):
        if os.path.isdir(os.path.join(runs_dir, name)):
            try:
                out[name] = backfill_run(runs_dir, name, force=force, registry=registry)
            except Exception as e:  # one bad run must not block the rest
                out[name] = f"ERROR {e}"
    return out
