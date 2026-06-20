"""DB migration entrypoint — Alembic against the single `public` schema.

A no-op when DATABASE_URL is unset so tests and bare local runs are unaffected. Idempotent and safe
to run on every deploy (wired into entrypoint.sh before uvicorn, and the console lifespan calls it
defensively). With the flat schema there is no per-project fan-out: Alembic owns every table directly.

    python3 -m software_factory.migrate            # alembic upgrade head
    python3 -m software_factory.migrate --check     # report state, change nothing
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]   # .../<repo> (holds alembic.ini + migrations/)


def _is_pg() -> bool:
    return bool(os.environ.get("DATABASE_URL"))


def _alembic_cfg():
    from alembic.config import Config
    cfg = Config(str(_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_ROOT / "migrations"))
    return cfg


def _wipe_if_stale(cfg) -> None:
    """The big-bang run->project transition: if the DB carries a PRE-RENAME stamp (a revision not in
    the current script chain — the old 0001-0004), DROP the whole public schema so the fresh
    0001_project_baseline rebuilds it from scratch (operator: no data, no migration, no back-compat).
    The drop is done HERE, before Alembic resolves revisions, because doing it inside the baseline
    would also drop Alembic's own alembic_version table mid-run and break the version stamp.
    No-op on a fresh DB (nothing stamped) or one already on the current chain (idempotent re-deploy)."""
    from alembic.script import ScriptDirectory
    import psycopg
    known = {r.revision for r in ScriptDirectory.from_config(cfg).walk_revisions()}
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as conn:
        if conn.execute("SELECT to_regclass('public.alembic_version')").fetchone()[0] is None:
            return  # fresh DB — nothing to wipe
        row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        if row and row[0] not in known:
            conn.execute("DROP SCHEMA public CASCADE")
            conn.execute("CREATE SCHEMA public")
            print(f"[migrate] wiped pre-rename schema (stale stamp {row[0]}) — rebuilding from baseline", flush=True)


def upgrade_global() -> None:
    """Run Alembic to head against `public` — the fresh project baseline builds every table
    (the flat project_id-keyed tables + the global directory tables) directly from models.metadata."""
    from alembic import command
    cfg = _alembic_cfg()
    _wipe_if_stale(cfg)
    command.upgrade(cfg, "head")
    print("[migrate] alembic upgrade head OK", flush=True)


def run(check: bool = False) -> int:
    if not _is_pg():
        print("[migrate] no DATABASE_URL — skipping.", flush=True)
        return 0
    if check:
        from alembic import command
        command.current(_alembic_cfg())
        return 0
    upgrade_global()
    return 0


if __name__ == "__main__":
    sys.exit(run(check="--check" in sys.argv))
