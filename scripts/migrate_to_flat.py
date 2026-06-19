#!/usr/bin/env python3
"""One-time, OPERATOR-GATED migration: schema-per-run (`sf_run_<id>`) → the flat `public` tables.

    # dry run — counts only, writes nothing:
    SF_DB=postgres DATABASE_URL=... python3 scripts/migrate_to_flat.py --dry-run
    # do it (idempotent: a run already present in public.runstate is skipped):
    SF_DB=postgres DATABASE_URL=... python3 scripts/migrate_to_flat.py --commit
    # after verifying the flat data, drop the old per-run schemas + retired registry:
    SF_DB=postgres DATABASE_URL=... python3 scripts/migrate_to_flat.py --drop-old

For each run in `public.sf_runs`, copies every per-run table's rows into the flat `public` table,
stamping `run_id`. The integer surrogate ids were per-schema (1..N) and would collide in the shared
flat tables, so they are NOT preserved: Postgres assigns fresh global ids, and `agents.ticket_id`
is remapped through the old→new ticket-id map. `status` is migrated `claimed → in_progress`
(the 3-state→6-state rename); everything else carries over.

This NEVER runs automatically. Run it by hand during the cutover, after `alembic upgrade head`
(0002_flat_schema) has created the flat tables. The old `software-factory-state` DB remains the
rollback until you have verified the flat data and chosen `--drop-old`.
"""
import os
import sys

# Append-only canvas/ticket tables whose integer id is reassigned by Postgres on insert.
_ID_TABLES = ("phases", "artifacts", "blockers", "verifications", "deployments")
_STATUS_REMAP = {"claimed": "in_progress"}   # 3-state → 6-state


def _connect():
    import psycopg
    conn = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)
    conn.prepare_threshold = None     # Supabase 6543 transaction pooler
    return conn


def _cols(cur, schema, table):
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position", (schema, table))
    return [r[0] for r in cur.fetchall()]


def _copy_table(cur, schema, table, run_id, *, remap_status=False, dry_run=False):
    """Copy <schema>.<table> rows → public.<table>, adding run_id. Returns rows copied."""
    cols = _cols(cur, schema, table)
    if not cols:
        return 0, {}
    cur.execute(f'SELECT {", ".join(cols)} FROM "{schema}".{table}')
    rows = cur.fetchall()
    if dry_run:
        return len(rows), {}
    id_map = {}
    has_id = "id" in cols
    si = cols.index("status") if (remap_status and "status" in cols) else None
    for row in rows:
        row = list(row)
        if si is not None:
            row[si] = _STATUS_REMAP.get(row[si], row[si])
        data = {c: v for c, v in zip(cols, row)}
        old_id = data.pop("id", None)                 # let pg assign a fresh global id
        data["run_id"] = run_id
        names = list(data.keys())
        placeholders = ", ".join(["%s"] * len(names))
        returning = " RETURNING id" if has_id else ""
        cur.execute(
            f"INSERT INTO public.{table} ({', '.join(names)}) VALUES ({placeholders})"
            f" ON CONFLICT DO NOTHING{returning}",
            [data[n] for n in names])
        if has_id:
            new = cur.fetchone()
            if new and old_id is not None:
                id_map[old_id] = new[0]
    return len(rows), id_map


def migrate(dry_run: bool = False) -> dict:
    out = {"runs": 0, "rows": 0}
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT run_id, schema_name FROM public.sf_runs ORDER BY run_id")
        runs = cur.fetchall()
        for run_id, schema in runs:
            # Idempotent: skip a run whose flat runstate row already exists.
            cur.execute("SELECT 1 FROM public.runstate WHERE run_id=%s", (run_id,))
            if cur.fetchone() and not dry_run:
                print(f"[migrate-flat] {run_id}: already flat — skip", flush=True)
                continue
            out["runs"] += 1
            # runstate (run_id PK) + gates (run_id,name PK) carry no surrogate id.
            for t in ("runstate", "gates"):
                n, _ = _copy_table(cur, schema, t, run_id, dry_run=dry_run)
                out["rows"] += n
            for t in _ID_TABLES:
                n, _ = _copy_table(cur, schema, t, run_id, dry_run=dry_run)
                out["rows"] += n
            # tickets first (build the old→new id map), then remap agents.ticket_id.
            n, ticket_map = _copy_table(cur, schema, "tickets", run_id,
                                        remap_status=True, dry_run=dry_run)
            out["rows"] += n
            n, _ = _copy_table(cur, schema, "agents", run_id, remap_status=True, dry_run=dry_run)
            out["rows"] += n
            if not dry_run and ticket_map:
                for old, new in ticket_map.items():
                    cur.execute("UPDATE public.agents SET ticket_id=%s WHERE run_id=%s AND ticket_id=%s",
                                (new, run_id, old))
            print(f"[migrate-flat] {run_id}: {'would copy' if dry_run else 'copied'} rows", flush=True)
    finally:
        conn.close()
    verb = "would migrate" if dry_run else "migrated"
    print(f"[migrate-flat] {verb} {out['runs']} runs, {out['rows']} rows", flush=True)
    return out


def drop_old() -> None:
    """Drop the per-run schemas + the retired registry tables. Destructive — run only after the
    flat data is verified."""
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT schema_name FROM public.sf_runs")
        schemas = [r[0] for r in cur.fetchall()]
        for s in schemas:
            cur.execute(f'DROP SCHEMA IF EXISTS "{s}" CASCADE')
            print(f"[migrate-flat] dropped schema {s}", flush=True)
        cur.execute("DROP TABLE IF EXISTS public.sf_run_schema_version")
        cur.execute("DROP TABLE IF EXISTS public.sf_runs")
        print(f"[migrate-flat] dropped {len(schemas)} schemas + retired registry", flush=True)
    finally:
        conn.close()


if __name__ == "__main__":
    if (os.environ.get("SF_DB", "").lower() != "postgres") or not os.environ.get("DATABASE_URL"):
        sys.exit("refusing to run: set SF_DB=postgres and DATABASE_URL (this only migrates Postgres).")
    if "--drop-old" in sys.argv:
        drop_old()
    elif "--commit" in sys.argv:
        migrate(dry_run=False)
    else:
        migrate(dry_run=True)   # default is the safe dry run
