"""Langfuse exporter: env-gated no-op, event mapping from both runtimes' log vocabularies,
incremental offsets, deterministic ids (re-export dedupes instead of duplicating)."""
import json

import pytest

from software_factory import tracing


CLAUDE_LINE = json.dumps({"type": "assistant", "session_id": "s1", "message": {
    "model": "claude-sonnet-4-6",
    "usage": {"input_tokens": 100, "output_tokens": 20},
    "content": [{"type": "text", "text": "hello"},
                {"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}]}})
OPENCODE_LINE = json.dumps({"type": "step_finish", "sessionID": "s2", "part": {
    "type": "step-finish", "cost": 0.01, "tokens": {"input": 50, "output": 5}}})


@pytest.fixture()
def sink(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    batches = []
    monkeypatch.setattr(tracing, "_post", lambda b: batches.append(b))
    return batches


def test_noop_when_unconfigured(tmp_path, monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    p = tmp_path / "run.log"
    p.write_text(CLAUDE_LINE + "\n")
    assert tracing.Tracer().tick("run-x", str(p)) == 0
    assert not tracing.enabled()


def test_maps_both_runtimes_and_ships_incrementally(tmp_path, sink):
    p = tmp_path / "run.log"
    p.write_text(CLAUDE_LINE + "\n")
    tr = tracing.Tracer()
    n1 = tr.tick("run-x", str(p), meta={"runtime": "claude"})
    flat = [e for b in sink for e in b]
    assert any(e["type"] == "trace-create" and e["body"]["id"] == "run-x" for e in flat)
    gen = next(e for e in flat if e["type"] == "generation-create")
    assert gen["body"]["usage"] == {"input": 100, "output": 20}
    assert any(e["type"] == "event-create" and e["body"]["name"] == "tool:Bash" for e in flat)
    assert n1 == len(flat)

    # append an opencode step -> only the NEW line ships, with a kimi generation
    with open(p, "a") as f:
        f.write(OPENCODE_LINE + "\n")
    before = len(flat)
    tr.tick("run-x", str(p))
    flat2 = [e for b in sink for e in b]
    new = flat2[before:]
    assert all(e["type"] != "trace-create" for e in new)          # trace only once
    assert any(e["body"].get("model") == "kimi-k2.7-code" for e in new
               if e["type"] == "generation-create")


def test_ids_are_deterministic_for_dedup(tmp_path, sink):
    p = tmp_path / "run.log"
    p.write_text(CLAUDE_LINE + "\n")
    tracing.Tracer().tick("run-x", str(p))
    first = [e["id"] for b in sink for e in b]
    sink.clear()
    tracing.Tracer().tick("run-x", str(p))                         # fresh tracer = restart
    assert [e["id"] for b in sink for e in b] == first
