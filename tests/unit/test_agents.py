"""Agent telemetry registry: the source of truth for HOW MANY agents ran and HOW WELL.

SQLite-backed (like tickets.py), fully offline-testable. Every lifecycle event is also
pushed to a pluggable sink (the external dashboard in production; a fake here). The metric
that matters most is the no-op rate — agents that produced nothing — the same scar the
ticket/repo guards defend, now made observable.
"""
from software_factory.agents import AgentRegistry, NullSink
from software_factory.budget import Usage


class FakeSink:
    def __init__(self):
        self.events = []

    def emit(self, event):
        self.events.append(event)


def reg(tmp_path, sink=None, clock=None):
    ticks = iter(range(1, 10_000))
    return AgentRegistry(
        str(tmp_path / "agents.db"),
        sink=sink or NullSink(),
        clock=clock or (lambda: next(ticks)),
    )


def test_spawn_lists_agent_as_active_and_counts_it(tmp_path):
    r = reg(tmp_path)
    r.spawn("a1", run_id="run", ticket_id=1, role="build", model="claude-opus-4-8")
    assert [a.agent_id for a in r.active()] == ["a1"]
    assert r.counts("run")["spawned"] == 1
    assert r.counts("run")["running"] == 1


def test_record_real_diff_marks_done_and_captures_cost(tmp_path):
    r = reg(tmp_path)
    r.spawn("a1", "run", 1, "build", "claude-opus-4-8")
    r.record("a1", outcome="real_diff", usage=Usage("claude-opus-4-8", output_tokens=4000),
             cost_usd=0.30, pr=7, diff_lines=120)
    a = r.get("a1")
    assert a.status == "done"
    assert a.outcome == "real_diff"
    assert a.cost_usd == 0.30
    assert a.pr == 7
    assert r.active() == []  # no longer running


def test_no_op_turn_is_not_done_and_shows_in_no_op_rate(tmp_path):
    r = reg(tmp_path)
    r.spawn("a1", "run", 1, "build", "claude-opus-4-8")
    r.spawn("a2", "run", 2, "build", "claude-opus-4-8")
    r.record("a1", outcome="real_diff", cost_usd=0.30, pr=7, diff_lines=120)
    r.record("a2", outcome="no_op", cost_usd=0.05)
    assert r.get("a2").status != "done"
    c = r.counts("run")
    assert c["no_op"] == 1 and c["done"] == 1
    assert r.no_op_rate("run") == 0.5


def test_cost_aggregates_per_ticket(tmp_path):
    r = reg(tmp_path)
    r.spawn("a1", "run", 1, "build", "m"); r.record("a1", outcome="no_op", cost_usd=0.05)
    r.spawn("a2", "run", 1, "build", "m"); r.record("a2", outcome="real_diff", cost_usd=0.40, pr=7, diff_lines=80)
    r.spawn("a3", "run", 2, "build", "m"); r.record("a3", outcome="real_diff", cost_usd=0.20, pr=8, diff_lines=30)
    by = r.cost_by_ticket("run")
    assert round(by[1], 2) == 0.45
    assert round(by[2], 2) == 0.20


def test_attempts_per_ticket_visible_via_counts(tmp_path):
    r = reg(tmp_path)
    r.spawn("a1", "run", 1, "build", "m"); r.record("a1", outcome="no_op", cost_usd=0.05)
    r.spawn("a2", "run", 1, "build", "m"); r.record("a2", outcome="real_diff", cost_usd=0.4, pr=7, diff_lines=80)
    assert r.counts("run")["spawned"] == 2  # two attempts on the same ticket are both counted


def test_events_are_pushed_to_sink_on_spawn_and_record(tmp_path):
    sink = FakeSink()
    r = reg(tmp_path, sink=sink)
    r.spawn("a1", "run", 1, "build", "claude-opus-4-8")
    r.record("a1", outcome="real_diff", cost_usd=0.3, pr=7, diff_lines=120)
    kinds = [e["event"] for e in sink.events]
    assert kinds == ["spawn", "record"]
    assert sink.events[0]["agent_id"] == "a1"
    assert sink.events[1]["outcome"] == "real_diff"


def test_records_are_scoped_by_run(tmp_path):
    r = reg(tmp_path)
    r.spawn("a1", "runA", 1, "build", "m")
    r.spawn("b1", "runB", 1, "build", "m")
    assert r.counts("runA")["spawned"] == 1
    assert r.counts("runB")["spawned"] == 1


def test_state_survives_reopening_the_db(tmp_path):
    db = str(tmp_path / "agents.db")
    AgentRegistry(db).spawn("a1", "run", 1, "build", "m")
    assert AgentRegistry(db).counts("run")["spawned"] == 1


def test_render_markdown_shows_agents_and_outcomes(tmp_path):
    r = reg(tmp_path)
    r.spawn("a1", "run", 1, "build", "claude-opus-4-8")
    r.record("a1", outcome="real_diff", cost_usd=0.3, pr=7, diff_lines=120)
    md = r.render_markdown("run")
    assert "a1" in md and "real_diff" in md
