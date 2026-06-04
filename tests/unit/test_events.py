"""Append-only event bus: the orchestrator/agents emit events (phase started, artifact created,
agent spawned, blocker raised, awaiting review) so the API server/canvas can see what's happening
without the orchestration cooperating beyond a one-line shell emit. Lives in the run dir (on the
volume), so events survive redeploys.
"""
from software_factory import events


def test_emit_then_read_roundtrip(tmp_path):
    events.emit(str(tmp_path), "run-1", "artifact", {"title": "PRD", "path": "PRD.md"})
    evs = events.read_events(str(tmp_path), "run-1")
    assert len(evs) == 1
    assert evs[0]["type"] == "artifact"
    assert evs[0]["payload"]["title"] == "PRD"
    assert "ts" in evs[0]


def test_events_preserve_emit_order(tmp_path):
    for t in ["phase", "artifact", "awaiting_review"]:
        events.emit(str(tmp_path), "run-1", t)
    assert [e["type"] for e in events.read_events(str(tmp_path), "run-1")] == ["phase", "artifact", "awaiting_review"]


def test_reading_an_unknown_run_is_empty(tmp_path):
    assert events.read_events(str(tmp_path), "nope") == []


def test_garbage_lines_are_skipped(tmp_path):
    events.emit(str(tmp_path), "run-1", "phase", {"name": "provision"})
    # a torn/garbage line should not break reading
    with open(tmp_path / "run-1" / "events.jsonl", "a") as f:
        f.write("not json\n")
    evs = events.read_events(str(tmp_path), "run-1")
    assert len(evs) == 1 and evs[0]["payload"]["name"] == "provision"


def test_cli_emit_appends_an_event(tmp_path):
    # The orchestrator emits from a shell: python -m software_factory.events emit <dir> <run> <type> <json>
    events.main(["emit", str(tmp_path), "run-1", "blocker", '{"what":"missing RAILWAY_TOKEN","blocks":"deploy"}'])
    evs = events.read_events(str(tmp_path), "run-1")
    assert evs[0]["type"] == "blocker"
    assert evs[0]["payload"]["blocks"] == "deploy"
