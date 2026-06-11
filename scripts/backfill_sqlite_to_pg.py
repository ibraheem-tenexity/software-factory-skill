#!/usr/bin/env python3
"""CLI for software_factory.backfill — copy per-run sqlite state into Postgres.

    SF_DB=postgres DATABASE_URL=... python3 scripts/backfill_sqlite_to_pg.py <runs_dir> [--force]

Idempotent (registered runs skip; row copies are ON CONFLICT DO NOTHING)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from software_factory.backfill import backfill_all  # noqa: E402

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--force"]
    if not args:
        sys.exit("usage: backfill_sqlite_to_pg.py <runs_dir> [--force]")
    results = backfill_all(args[0], force="--force" in sys.argv)
    if not results:
        sys.exit("SF_DB is not postgres — nothing to do")
    bad = 0
    for rid, res in results.items():
        print(f"{rid}: {res}")
        bad += res.startswith("ERROR")
    sys.exit(1 if bad else 0)
