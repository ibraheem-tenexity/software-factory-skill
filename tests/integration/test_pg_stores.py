"""Live-Postgres integration: full store round-trips through dbshim against a REAL
database (the Supabase pooler). Skipped unless SF_TEST_DATABASE_URL is set:

    SF_TEST_DATABASE_URL=postgresql://... python3 -m pytest tests/integration/test_pg_stores.py
"""
import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("SF_TEST_DATABASE_URL"),
    reason="SF_TEST_DATABASE_URL not set (live pg integration)")


@pytest.fixture()
def pg_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SF_ENVIRONMENT", "test")
    monkeypatch.setenv("SF_DB", "postgres")
    monkeypatch.setenv("DATABASE_URL", os.environ["SF_TEST_DATABASE_URL"])
    rid = "run-it" + uuid.uuid4().hex[:8]
    yield str(tmp_path), rid
    # drop the test schema + registry row
    from software_factory import dbshim
    conn = dbshim._pg_connect(os.environ["SF_TEST_DATABASE_URL"])
    with conn.transaction():
        cur = conn.cursor()
        cur.execute(f'DROP SCHEMA IF EXISTS "{dbshim.schema_for(rid)}" CASCADE')
        cur.execute("DELETE FROM public.sf_runs WHERE run_id = %s", (rid,))
    conn.close()


def test_full_store_round_trip_on_live_pg(pg_env):
    runs_dir, rid = pg_env
    db_path = os.path.join(runs_dir, rid, "run.db")
    from software_factory.agents import AgentRegistry
    from software_factory.budget import Usage
    from software_factory.db import RunDB
    from software_factory.runstate import RunState
    from software_factory.tickets import TicketStore
    from software_factory import dbshim

    db = RunDB(db_path)
    st = RunState.load(rid, db)
    st.phase = "build"
    st.spent_usd = 3.5
    st.save()
    assert RunState.load(rid, RunDB(db_path)).spent_usd == 3.5

    db.set_phase("build", "active", stage=3)
    db.record_artifact("PRD", "PRD.md", kind="doc")
    db.add_blocker("budget cap", blocks="budget")
    db.set_gate("stage1", "passed")
    db.record_verification("https://x", True, "{}")
    assert db.phases()[0]["name"] == "build"
    assert db.artifacts()[0]["title"] == "PRD"
    assert db.blockers()[0]["blocks"] == "budget"

    ts = TicketStore(db_path)
    tid = ts.create_ticket("t1", "a", "d", 1)
    assert isinstance(tid, int) and ts.get(tid).title == "t1"

    reg = AgentRegistry(db_path)
    reg.spawn("a1", rid, tid, "build", "claude-sonnet-4-6")
    reg.record("a1", outcome="real_diff", usage=Usage("claude-sonnet-4-6"), cost_usd=0.1,
               provenance=1, diff_lines=5)
    assert reg.counts(rid)["done"] == 1

    assert rid in {r["run_id"] for r in dbshim.registry_runs()}


def test_backfill_copies_a_sqlite_run_and_preserves_ids(pg_env, monkeypatch):
    runs_dir, rid = pg_env
    db_path = os.path.join(runs_dir, rid, "run.db")
    # author the run in sqlite first
    monkeypatch.setenv("SF_DB", "sqlite")
    from software_factory.db import RunDB
    from software_factory.tickets import TicketStore
    sdb = RunDB(db_path)
    sdb.set_phase("research", "done", stage=1)
    sts = TicketStore(db_path)
    t1 = sts.create_ticket("first", "a", "d", 1)
    # backfill into pg
    monkeypatch.setenv("SF_DB", "postgres")
    from software_factory.backfill import backfill_run
    assert backfill_run(runs_dir, rid).startswith("copied")
    assert backfill_run(runs_dir, rid) == "skip"            # idempotent
    pts = TicketStore(db_path)
    assert pts.get(t1).title == "first"                     # id preserved
    t2 = pts.create_ticket("post-flip", "a", "d", 1)
    assert t2 > t1                                          # sequence cleared the backfill
