"""Live-Postgres integration: full store round-trips through dbshim against a REAL database
(e.g. the Supabase pooler). Skipped unless SF_TEST_DATABASE_URL is set:

    SF_TEST_DATABASE_URL=postgresql://... python3 -m pytest tests/integration/test_pg_stores.py

(The main unit suite already runs on Postgres against the local dev container; this is the extra
check against a real/remote pooler.)
"""
import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("SF_TEST_DATABASE_URL"),
    reason="SF_TEST_DATABASE_URL not set (live pg integration)")

_FLAT_TABLES = ("projectstate", "phases", "artifacts", "blockers", "gates",
                "verifications", "deployments", "tickets", "agents")


@pytest.fixture()
def pg_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SF_ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_URL", os.environ["SF_TEST_DATABASE_URL"])
    rid = "project-it" + uuid.uuid4().hex[:8]
    yield str(tmp_path), rid
    # flat schema: delete only this run's rows (no per-project schema to drop).
    from software_factory import dbshim
    conn = dbshim._pg_connect(os.environ["SF_TEST_DATABASE_URL"])
    with conn.transaction():
        cur = conn.cursor()
        for t in _FLAT_TABLES:
            cur.execute(f"DELETE FROM public.{t} WHERE project_id = %s", (rid,))
    conn.close()


def test_full_store_round_trip_on_live_pg(pg_env):
    projects_dir, rid = pg_env
    db_path = os.path.join(projects_dir, rid)
    from software_factory.agents import AgentRegistry
    from software_factory.budget import Usage
    from software_factory.db import ProjectStore
    from software_factory.projectstate import ProjectState
    from software_factory.tickets import TicketStore
    from software_factory import dbshim

    db = ProjectStore(db_path)
    st = ProjectState.load(rid, db)
    st.phase = "build"
    st.spent_usd = 3.5
    st.save()
    assert ProjectState.load(rid, ProjectStore(db_path)).spent_usd == 3.5

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

    assert rid in {r["project_id"] for r in dbshim.registry_projects()}
