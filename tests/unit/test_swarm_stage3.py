"""Stage-3 swarm driver: synthesized run.log lines, fold watermark, wave serialization.
Event shapes come from the captured fixture (tests/fixtures/swarm-events.jsonl)."""
import io
import json
import os

from software_factory.agents import AgentRegistry
from software_factory.console import Console
from software_factory.streamlog import cost_usd
from software_factory.swarm_adapter import read_events, spend_usd
from software_factory.swarm_stage3 import fold_once, main, run_swarm_waves, synth_step_finish
from software_factory.tickets import TicketStore

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "swarm-events.jsonl")
KIMI = "openrouter/moonshotai/kimi-k2.6"


# ---- synthesized step_finish lines ------------------------------------------------------

def test_synth_lines_sum_via_streamlog_to_the_swarm_spend():
    # the whole point: ONE spend stream — streamlog over the synthesized lines must equal
    # the adapter's authoritative fold over the raw events.
    events = read_events(FIXTURE)
    text = "\n".join(filter(None, (synth_step_finish(e) for e in events)))
    assert abs(cost_usd(text) - spend_usd(events)) < 1e-6


def test_synth_zero_cost_omits_the_key_so_tokens_price_fallback_fires():
    ev = {"type": "agent-turn-done", "agent": "a", "costUsd": 0,
          "tokens": {"input": 10, "output": 1, "reasoning": 0,
                     "cache": {"read": 0, "write": 0}}}
    line = json.loads(synth_step_finish(ev))
    assert "cost" not in line["part"]          # part.cost=0 would bill as authoritative-free
    assert line["part"]["tokens"]["input"] == 10
    assert line["sessionID"] == "swarm:a"


def test_synth_lines_never_read_as_a_finished_session(tmp_path):
    # the zombie detector treats `step_finish reason=stop` + idle as session-complete;
    # a mid-swarm log must never satisfy it (it would launch a concurrent stage — §1 race).
    log = tmp_path / "run.log"
    events = read_events(FIXTURE)
    log.write_text("\n".join(filter(None, (synth_step_finish(e) for e in events))) + "\n")
    assert Console._log_session_completed(str(log)) is False


def test_synth_ignores_non_turn_events():
    assert synth_step_finish({"type": "agent-done", "agent": "a", "costUsd": 1}) is None
    assert synth_step_finish({"type": "swarm-done", "totalCostUsd": 1}) is None


# ---- fold loop --------------------------------------------------------------------------

def test_fold_once_watermark_emits_each_turn_exactly_once(tmp_path):
    reg = AgentRegistry(str(tmp_path / "run.db"))
    out = io.StringIO()
    with open(FIXTURE) as f:
        lines = [l for l in f if l.strip()]
    ep = tmp_path / "ev.jsonl"
    ep.write_text("".join(lines[:6]))                       # mid-run poll
    n1 = fold_once(str(ep), 0, reg, "r", KIMI, out=out)
    ep.write_text("".join(lines))                           # file grew
    n2 = fold_once(str(ep), n1, reg, "r", KIMI, out=out)
    fold_once(str(ep), n2, reg, "r", KIMI, out=out)         # idempotent settle pass
    turns = sum(1 for e in read_events(FIXTURE) if e["type"] == "agent-turn-done")
    assert out.getvalue().count('"step_finish"') == turns   # no duplicates, none missed
    assert {r.agent_id for r in reg.agents_for("r")} == {"asker", "oracle"}


# ---- wave serialization -----------------------------------------------------------------

def test_run_swarm_waves_serializes_waves_and_decrements_budget(tmp_path):
    base, ws = str(tmp_path / "base"), str(tmp_path / "ws")
    os.makedirs(base), os.makedirs(ws)
    store = TicketStore(os.path.join(base, "run.db"))
    t1 = store.create_ticket("a", "acc", "dod", 1)
    t2 = store.create_ticket("b", "acc", "dod", 1)
    t3 = store.create_ticket("c", "acc", "dod", 2)
    fixture_text = open(FIXTURE).read()

    calls = []

    class DoneProc:
        def poll(self):
            return 0

    def spawn(argv, env=None, cwd=None, stdout=None, stderr=None):
        calls.append((argv, env, cwd))
        with open(argv[argv.index("--events") + 1], "w") as f:
            f.write(fixture_text)                            # the swarm "ran"
        return DoneProc()

    out = io.StringIO()
    spent = run_swarm_waves(base, "r", ws, KIMI, 10.0, spawn=spawn, poll_s=0, out=out)

    assert len(calls) == 2                                   # one swarm per open wave
    cfg1 = json.load(open(os.path.join(ws, "swarm-wave1.json")))
    cfg2 = json.load(open(os.path.join(ws, "swarm-wave2.json")))
    assert [a["name"] for a in cfg1["agents"]] == [f"ticket-{t1}", f"ticket-{t2}"]
    assert [a["name"] for a in cfg2["agents"]] == [f"ticket-{t3}"]
    wave_cost = spend_usd(read_events(FIXTURE))
    assert abs(cfg1["budgetUsd"] - 10.0) < 1e-6
    assert abs(cfg2["budgetUsd"] - (10.0 - wave_cost)) < 1e-4   # wave 2 sees what's left
    assert abs(spent - 2 * wave_cost) < 1e-6
    assert os.path.exists(os.path.join(base, "swarm-wave1.events.jsonl"))  # evidence survives ws teardown
    assert calls[0][1]["PWD"] == ws                          # §9 hygiene rode along
    # per-WAVE dbs: a shared swarm.db let a dying prior-wave serve take the live wave down
    assert calls[0][1]["OPENCODE_SWARM_DB"] == os.path.join(ws, ".swarm", "swarm-wave1.db")
    assert calls[1][1]["OPENCODE_SWARM_DB"] == os.path.join(ws, ".swarm", "swarm-wave2.db")
    assert calls[0][0][calls[0][0].index("--db") + 1] != calls[1][0][calls[1][0].index("--db") + 1]
    assert '"step_finish"' in out.getvalue()                 # spend reached run.log


def test_run_swarm_waves_skips_swarm_when_budget_is_exhausted(tmp_path):
    base, ws = str(tmp_path / "base"), str(tmp_path / "ws")
    os.makedirs(base), os.makedirs(ws)
    TicketStore(os.path.join(base, "run.db")).create_ticket("a", "acc", "dod", 1)
    spawned = []
    spent = run_swarm_waves(base, "r", ws, KIMI, 0.10,
                            spawn=lambda *a, **k: spawned.append(a), poll_s=0)
    assert spawned == [] and spent == 0.0    # the monolithic agent gets to triage instead


def test_main_without_separator_is_a_usage_error():
    assert main(["runs", "r", "/ws"]) == 2


def test_lingering_swarm_cli_is_terminated_after_swarm_done(tmp_path):
    # live scar (run-5b7aef7a wave 2): the swarm CLI never exited after swarm-done; the
    # wave loop must terminate a ledger-finished swarm whose process outlives the grace.
    base, ws = str(tmp_path / "base"), str(tmp_path / "ws")
    os.makedirs(base), os.makedirs(ws)
    TicketStore(os.path.join(base, "run.db")).create_ticket("a", "acc", "dod", 1)
    fixture_text = open(FIXTURE).read()   # ends with swarm-done

    class LingeringProc:
        def __init__(self):
            self.terminated = False
        def poll(self):
            return 143 if self.terminated else None   # never exits on its own
        def terminate(self):
            self.terminated = True
        def wait(self, timeout=None):
            return 143

    procs = []
    def spawn(argv, env=None, cwd=None, stdout=None, stderr=None):
        with open(argv[argv.index("--events") + 1], "w") as f:
            f.write(fixture_text)
        p = LingeringProc()
        procs.append(p)
        return p

    spent = run_swarm_waves(base, "r", ws, KIMI, 10.0, spawn=spawn,
                            poll_s=0.01, settle_grace_s=0.05)
    (p,) = procs
    assert p.terminated, "ledger-finished lingering swarm must be terminated"
    assert spent > 0   # the wave's spend still folded
