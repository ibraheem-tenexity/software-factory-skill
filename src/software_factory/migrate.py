"""DB migration entrypoint — Alembic against the single `public` schema.

A no-op when DATABASE_URL is unset so tests and bare local runs are unaffected. Idempotent and safe
to run on every deploy (wired into entrypoint.sh before uvicorn, and the console lifespan calls it
defensively). With the flat schema there is no per-run fan-out: Alembic owns every table directly.

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


def upgrade_global() -> None:
    """Run Alembic to head against `public` — creates/updates every table (the flat run tables
    from `schema.py` + the global directory tables)."""
    from alembic import command
    command.upgrade(_alembic_cfg(), "head")
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
