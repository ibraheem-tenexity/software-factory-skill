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
    # Flat schema: the registry scopes by the run id in its path (<runs_dir>/<run_id>/…), and these
    # tests spawn under run_id="run" — so the db lives in a "run" dir to match (as it does in prod).
    return AgentRegistry(
        str(tmp_path / "run" / "agents.db"),
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
             cost_usd=0.30, provenance="7", diff_lines=120)
    a = r.get("a1")
    assert a.status == "done"
    assert a.outcome == "real_diff"
    assert a.cost_usd == 0.30
    assert a.provenance == "7"
    assert a.provenance_type == "pr"
    assert r.active() == []  # no longer running


def test_finalize_orphans_closes_running_agents(tmp_path):
    # SPEC §5: no phantom agents — when a stage exits, still-running rows are finalized:
    # outcome 'unreported'; status done if the stage's gate passed, failed otherwise.
    r = reg(tmp_path)
    r.spawn("a1", "run", 1, "build", "m")
    r.spawn("a2", "run", 2, "build", "m")
    r.record("a1", outcome="real_diff", cost_usd=0.1, provenance="1", diff_lines=10)   # properly finished
    n = r.finalize_orphans("run", stage_ok=True)
    assert n == 1                                            # only a2 was orphaned
    a2 = r.get("a2")
    assert a2.status == "done" and a2.outcome == "unreported"
    assert r.get("a1").outcome == "real_diff"                # untouched

    r.spawn("a3", "run", 3, "build", "m")
    r.finalize_orphans("run", stage_ok=False)                # e.g. budget kill
    assert r.get("a3").status == "failed"


def test_success_outcome_is_a_done_synonym_not_failed(tmp_path):
    # run-ce47692e scar: the Stage-3 orchestrator reported `finish-agent <id> success`; "success"
    # wasn't in the outcome vocabulary so the .get(..., "failed") default mislabeled a SUCCESSFUL
    # agent as failed (red on the canvas). "success" maps to done.
    r = reg(tmp_path)
    r.spawn("pm-lead", "run", None, "pm-lead", "claude-sonnet-4-6")
    r.record("pm-lead", outcome="success", cost_usd=0.1)
    assert r.get("pm-lead").status == "done"


def test_no_op_turn_is_not_done_and_shows_in_no_op_rate(tmp_path):
    r = reg(tmp_path)
    r.spawn("a1", "run", 1, "build", "claude-opus-4-8")
    r.spawn("a2", "run", 2, "build", "claude-opus-4-8")
    r.record("a1", outcome="real_diff", cost_usd=0.30, provenance="7", diff_lines=120)
    r.record("a2", outcome="no_op", cost_usd=0.05)
    assert r.get("a2").status != "done"
    c = r.counts("run")
    assert c["no_op"] == 1 and c["done"] == 1
    assert r.no_op_rate("run") == 0.5


def test_cost_aggregates_per_ticket(tmp_path):
    r = reg(tmp_path)
    r.spawn("a1", "run", 1, "build", "m"); r.record("a1", outcome="no_op", cost_usd=0.05)
    r.spawn("a2", "run", 1, "build", "m"); r.record("a2", outcome="real_diff", cost_usd=0.40, provenance="7", diff_lines=80)
    r.spawn("a3", "run", 2, "build", "m"); r.record("a3", outcome="real_diff", cost_usd=0.20, provenance="8", diff_lines=30)
    by = r.cost_by_ticket("run")
    assert round(by[1], 2) == 0.45
    assert round(by[2], 2) == 0.20


def test_attempts_per_ticket_visible_via_counts(tmp_path):
    r = reg(tmp_path)
    r.spawn("a1", "run", 1, "build", "m"); r.record("a1", outcome="no_op", cost_usd=0.05)
    r.spawn("a2", "run", 1, "build", "m"); r.record("a2", outcome="real_diff", cost_usd=0.4, provenance="7", diff_lines=80)
    assert r.counts("run")["spawned"] == 2  # two attempts on the same ticket are both counted


def test_events_are_pushed_to_sink_on_spawn_and_record(tmp_path):
    sink = FakeSink()
    r = reg(tmp_path, sink=sink)
    r.spawn("a1", "run", 1, "build", "claude-opus-4-8")
    r.record("a1", outcome="real_diff", cost_usd=0.3, provenance="7", diff_lines=120)
    kinds = [e["event"] for e in sink.events]
    assert kinds == ["spawn", "record"]
    assert sink.events[0]["agent_id"] == "a1"
    assert sink.events[1]["outcome"] == "real_diff"


def test_render_markdown_shows_agents_and_outcomes(tmp_path):
    r = reg(tmp_path)
    r.spawn("a1", "run", 1, "build", "claude-opus-4-8")
    r.record("a1", outcome="real_diff", cost_usd=0.3, provenance="7", diff_lines=120)
    md = r.render_markdown("run")
    assert "a1" in md and "real_diff" in md
