"""DB migration entrypoint: global (Alembic) + per-run schema fan-out.

Postgres-only — a no-op in sqlite/dev so tests and local runs are unaffected. Idempotent and safe
to run on every deploy (it's wired into entrypoint.sh before uvicorn, and the console lifespan calls
it defensively).

    python3 -m software_factory.migrate            # upgrade global + fan-out per-run
    python3 -m software_factory.migrate --check     # report state, change nothing
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]   # .../<repo> (holds alembic.ini + migrations/)


def _is_pg() -> bool:
    return (os.environ.get("SF_DB", "").strip().lower() == "postgres"
            and bool(os.environ.get("DATABASE_URL")))


def _alembic_cfg():
    from alembic.config import Config
    cfg = Config(str(_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_ROOT / "migrations"))
    return cfg


def upgrade_global() -> None:
    """Run Alembic to head against public (creates/updates sf_runs, users, version registry)."""
    from alembic import command
    command.upgrade(_alembic_cfg(), "head")
    print("[migrate] global: alembic upgrade head OK", flush=True)


def fanout_per_run(check: bool = False) -> dict:
    """Apply pending per-run revisions to every sf_run_<id> schema and stamp its version."""
    import psycopg
    from .schema_ddl import pending_per_run, per_run_head

    head = per_run_head()
    out = {"schemas": 0, "migrated": 0, "head": head}
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=30, autocommit=True) as c:
        c.prepare_threshold = None   # Supabase transaction pooler (6543) breaks server-side prepares
        c.execute("CREATE TABLE IF NOT EXISTS public.sf_run_schema_version ("
                  "run_id text PRIMARY KEY, version text NOT NULL, "
                  "updated_at timestamptz NOT NULL DEFAULT now())")
        runs = c.execute("SELECT run_id, schema_name FROM public.sf_runs").fetchall()
        out["schemas"] = len(runs)
        for run_id, schema in runs:
            row = c.execute("SELECT version FROM public.sf_run_schema_version WHERE run_id=%s",
                            (run_id,)).fetchone()
            cur_ver = row[0] if row else None
            if cur_ver == head:
                continue
            pending = pending_per_run(cur_ver)
            if check:
                if pending:
                    out["migrated"] += 1
                continue
            for _ver, stmts in pending:
                if not stmts:
                    continue
                with c.transaction():
                    c.execute(f'SET LOCAL search_path TO "{schema}", public')
                    for s in stmts:
                        c.execute(s)
            c.execute("INSERT INTO public.sf_run_schema_version (run_id, version) VALUES (%s,%s) "
                      "ON CONFLICT (run_id) DO UPDATE SET version=excluded.version, updated_at=now()",
                      (run_id, head))
            out["migrated"] += 1
    verb = "would migrate" if check else "migrated/stamped"
    print(f"[migrate] per-run: {out['schemas']} schemas, {verb} {out['migrated']} → head {head}", flush=True)
    return out


def stamp_new_schema(conn, run_id: str) -> None:
    """Stamp a freshly-created per-run schema at the current head (called by dbshim).
    `conn` is a live psycopg connection; best-effort (never block run creation)."""
    from .schema_ddl import per_run_head
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS public.sf_run_schema_version ("
                     "run_id text PRIMARY KEY, version text NOT NULL, "
                     "updated_at timestamptz NOT NULL DEFAULT now())")
        conn.execute("INSERT INTO public.sf_run_schema_version (run_id, version) VALUES (%s,%s) "
                     "ON CONFLICT (run_id) DO NOTHING", (run_id, per_run_head()))
    except Exception:
        pass


def run(check: bool = False) -> int:
    if not _is_pg():
        print("[migrate] SF_DB!=postgres or no DATABASE_URL — skipping (dev/sqlite).", flush=True)
        return 0
    if not check:
        upgrade_global()
    fanout_per_run(check=check)
    return 0


if __name__ == "__main__":
    sys.exit(run(check="--check" in sys.argv))
