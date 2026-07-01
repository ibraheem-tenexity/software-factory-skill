"""SOF-27: memory/cost.py — console-side ingestion spend charged to the project cap.

These tests go through the same real-Postgres-backed Console fixtures as test_console.py (no
pgvector/new schema involved — this ticket only touches ProjectState/console.py/memory/cost.py),
so they run in this sandbox exactly like the rest of that file does.
"""
from software_factory.console import Console, ProjectRequest
from software_factory.memory.cost import record_ingestion_cost


class FakeLauncher:
    def __init__(self):
        self.argv = None

    def __call__(self, argv, env=None, log_path=None, cwd=None):
        self.argv = argv
        return None  # no live process — start_project ignores the return value


def _console(tmp_path, launcher):
    ids = iter(["project-cost1"])
    return Console(str(tmp_path), launch=launcher, new_id=lambda: next(ids))


def test_record_ingestion_cost_increments_state_and_project_spend(tmp_path):
    c = _console(tmp_path, FakeLauncher())
    rid = c.start_project(ProjectRequest(description="x"))
    delta = record_ingestion_cost(c, rid, model="google/gemini-embedding-2",
                                  provider="openrouter", usd=1.23)
    assert delta == 1.23
    assert c._load_state(rid).ingestion_spent_usd == 1.23
    assert c._project_spend(rid) >= 1.23


def test_record_ingestion_cost_accumulates_across_calls(tmp_path):
    c = _console(tmp_path, FakeLauncher())
    rid = c.start_project(ProjectRequest(description="x"))
    record_ingestion_cost(c, rid, model="m", provider="openrouter", usd=0.50)
    record_ingestion_cost(c, rid, model="m", provider="openrouter", usd=0.75)
    assert c._load_state(rid).ingestion_spent_usd == 1.25


def test_record_ingestion_cost_falls_back_to_price_table_when_usd_not_given(tmp_path):
    c = _console(tmp_path, FakeLauncher())
    rid = c.start_project(ProjectRequest(description="x"))
    delta = record_ingestion_cost(c, rid, model="claude-sonnet-4-6", provider="anthropic",
                                  input_tokens=1_000_000, output_tokens=0)
    assert delta == 3.0  # budget.PRICES["claude-sonnet-4-6"]["input"] = 3.0 / 1_000_000
    assert c._load_state(rid).ingestion_spent_usd == 3.0


def test_ingestion_cost_alone_trips_the_budget_blocker(tmp_path):
    # SOF-27 AC: a project whose cap is exceeded BY INGESTION ALONE (no stage spend at all)
    # still trips the existing budget blocker.
    c = _console(tmp_path, FakeLauncher())
    rid = c.start_project(ProjectRequest(description="x"))
    st = c._load_state(rid)
    st.budget_ceiling = 1.0
    st.save()
    record_ingestion_cost(c, rid, model="m", provider="openrouter", usd=5.0)
    assert c.enforce_budget(rid) is True
    from software_factory.db import ProjectStore, db_path
    blockers = ProjectStore(db_path(str(tmp_path), rid)).blockers()
    assert any(b.get("blocks") == "budget" and not b["cleared"] for b in blockers)


def test_ingestion_spent_usd_is_not_clobbered_when_cost_recomputes_from_the_log(tmp_path):
    # The trap this design specifically avoids: Console._cost() overwrites state.spent_usd
    # wholesale from project.log every time it reparses — ingestion_spent_usd must be immune.
    c = _console(tmp_path, FakeLauncher())
    rid = c.start_project(ProjectRequest(description="x"))
    record_ingestion_cost(c, rid, model="m", provider="openrouter", usd=2.0)
    import os
    log_path = os.path.join(c._paths(rid)["base"], "project.log")
    with open(log_path, "w") as f:
        f.write('{"type":"result","total_cost_usd":0.10,"session_id":"s1"}\n')
    c._cost(rid)  # triggers the self-healing state.spent_usd overwrite
    assert c._load_state(rid).ingestion_spent_usd == 2.0  # untouched by the log-driven overwrite
    assert c._project_spend(rid) >= 2.10  # both sources counted


def test_langfuse_span_emission_is_a_noop_without_langfuse_configured(tmp_path, monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    c = _console(tmp_path, FakeLauncher())
    rid = c.start_project(ProjectRequest(description="x"))
    # Must not raise even though Langfuse isn't configured.
    record_ingestion_cost(c, rid, model="m", provider="openrouter", usd=0.01)
    assert c._load_state(rid).ingestion_spent_usd == 0.01
