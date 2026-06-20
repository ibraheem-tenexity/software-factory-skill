"""opencode-swarm → factory bridge, written against the REAL captured fixture
(tests/fixtures/swarm-events.jsonl — a live 2-agent Kimi K2.6 ping-pong swarm against
opencode-swarm @ 881630e, schema ground truth)."""
import json
import os

from software_factory.agents import AgentRegistry
from software_factory.budget import PRICES
from software_factory.swarm_adapter import (
    agent_name_for,
    bridge_events,
    read_events,
    spend_usd,
    swarm_argv,
    swarm_config_for_tickets,
    swarm_env,
    ticket_id_for,
)
from software_factory.tickets import Ticket

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "swarm-events.jsonl")

KIMI = "openrouter/moonshotai/kimi-k2.7-code"
FIXTURE_MODEL = "openrouter/moonshotai/kimi-k2.6"


def _ticket(tid=7, title="Add login form", acceptance="form submits", dod="tests pass"):
    return Ticket(id=tid, title=title, acceptance=acceptance, dod=dod,
                  wave=1, status="open", agent=None, provenance=None,
                  provenance_type=None, diff_lines=0)


# ---- events parsing -------------------------------------------------------------------

def test_fixture_parses_and_spend_matches_swarm_done_total():
    events = read_events(FIXTURE)
    assert events, "fixture must load"
    done = [e for e in events if e["type"] == "swarm-done"]
    assert len(done) == 1
    turned = sum(e["costUsd"] for e in events if e["type"] == "agent-turn-done")
    assert turned > 0, "fixture must carry real non-zero costs"
    assert abs(spend_usd(events) - done[0]["totalCostUsd"]) < 1e-9
    assert abs(spend_usd(events) - turned) < 1e-9


def test_spend_survives_truncation_without_swarm_done():
    events = [e for e in read_events(FIXTURE) if e["type"] != "swarm-done"]
    full = spend_usd(read_events(FIXTURE))
    assert spend_usd(events) == full  # turn-done fold alone carries the truth


def test_costless_turn_prices_tokens_at_the_event_model_rate():
    ev = {"type": "agent-turn-done", "agent": "a", "round": 0, "model": KIMI,
          "costUsd": 0,
          "tokens": {"input": 1_000_000, "output": 500_000, "reasoning": 500_000,
                     "cache": {"read": 1_000_000, "write": 0}},
          "totalCostUsd": 0}
    rate = PRICES[KIMI]
    expected = 1_000_000 * rate["input"] + 1_000_000 * rate["cached"] + 1_000_000 * rate["output"]
    assert abs(spend_usd([ev]) - expected) < 1e-9


def test_costless_turn_with_unknown_model_never_bills_free():
    ev = {"type": "agent-turn-done", "agent": "a", "round": 0, "model": "mystery/model",
          "costUsd": 0, "tokens": {"input": 10, "output": 5, "reasoning": 0,
                                   "cache": {"read": 0, "write": 0}},
          "totalCostUsd": 0}
    try:
        spend_usd([ev])
        assert False, "un-priced spend must raise, not bill as free"
    except KeyError:
        pass


def test_read_events_skips_garbage_and_half_written_tail(tmp_path):
    p = tmp_path / "events.jsonl"
    good = json.dumps({"type": "agent-spawned", "agent": "a", "sessionId": "s"})
    p.write_text(good + "\nnot json\n" + '{"type": "agent-turn-d')
    events = read_events(str(p))
    assert len(events) == 1 and events[0]["type"] == "agent-spawned"


def test_read_events_missing_file_is_empty_not_fatal(tmp_path):
    assert read_events(str(tmp_path / "nope.jsonl")) == []


# ---- swarm config generation ----------------------------------------------------------

def test_config_one_agent_per_ticket_with_contract_and_tools_cap():
    t = _ticket()
    cfg = swarm_config_for_tickets([t], model=KIMI, project_db_path="/runs/r1",
                                   budget_usd=12.5, max_concurrent=3)
    assert cfg["model"] == KIMI
    assert cfg["budgetUsd"] == 12.5
    assert cfg["maxConcurrent"] == 3
    (agent,) = cfg["agents"]
    assert agent["name"] == "ticket-7"
    # the explicit tools map is the 128-tool-cap guard: default-deny, work tools only
    assert agent["tools"]["*"] is False
    for tool in ("read", "edit", "write", "bash", "glob", "grep"):
        assert agent["tools"][tool] is True
    task = agent["task"]
    assert "Add login form" in task and "form submits" in task and "tests pass" in task
    # claim id == agent name (detect_stage3_done traceability), concrete db path
    assert "claim(7, 'ticket-7')" in task
    assert "/runs/r1" in task
    assert "mark_done(7" in task
    # host owns lifecycle records — the agent must not double-record
    assert "spawn-agent" in task and "host records" in task


def test_agent_name_round_trip():
    assert agent_name_for(42) == "ticket-42"
    assert ticket_id_for("ticket-42") == 42
    assert ticket_id_for("oracle") is None
    assert ticket_id_for("ticket-x") is None


# ---- launch hygiene (every rule here broke a real run — SPEC §9) ------------------------

def test_argv_uses_sf_swarm_bin_and_carries_no_secrets(monkeypatch):
    monkeypatch.setenv("SF_SWARM_BIN", "/opt/swarm/swarm")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-secret")
    argv = swarm_argv("/ws/swarm.json", "/ws", "/ws/.swarm/swarm.db", "/ws/events.jsonl")
    assert argv[0] == "/opt/swarm/swarm"
    assert argv[1] == "run"
    assert "--events" in argv and "--json" in argv and "--db" in argv
    assert not any("sk-secret" in a for a in argv)


def test_env_sets_pwd_xdg_isolation_and_db_inside_workspace():
    env = swarm_env("/ws", base_env={"PATH": "/bin", "PWD": "/somewhere/else"})
    assert env["PWD"] == "/ws"
    assert env["XDG_CONFIG_HOME"] == "/ws/.oc-config"
    assert env["XDG_DATA_HOME"] == "/ws/.oc-data"   # hides global auth.json (spend-limited key)
    assert env["OPENCODE_DISABLE_CLAUDE_CODE_SKILLS"] == "1"
    assert env["OPENCODE_DISABLE_EXTERNAL_SKILLS"] == "1"
    assert env["OPENCODE_SWARM_DB"] == "/ws/.swarm/swarm.db"
    assert env["PATH"] == "/bin"  # base env preserved


# ---- event bridge ---------------------------------------------------------------------

def test_bridge_records_spawn_and_final_costs_from_fixture(tmp_path):
    reg = AgentRegistry(str(tmp_path / "project-x"))
    events = read_events(FIXTURE)
    folded = bridge_events(events, reg, "project-x", KIMI)
    rows = {r.agent_id: r for r in reg.agents_for("project-x")}
    assert set(rows) == {"asker", "oracle"}
    # agent-done.costUsd is NOT final (sweep turns land after it); the bridge must fold
    # ALL turn-done events. Fixture truth: oracle $0.00478 at agent-done, $0.00964 final.
    assert abs(rows["oracle"].cost_usd - 0.00964201) < 1e-6
    assert abs(folded["asker"] - rows["asker"].cost_usd) < 1e-9
    assert rows["asker"].status == "done" and rows["asker"].outcome == "success"
    assert rows["oracle"].input_tokens > 0
    assert rows["oracle"].model == FIXTURE_MODEL


def test_bridge_is_idempotent_over_a_growing_file(tmp_path):
    reg = AgentRegistry(str(tmp_path / "project-x"))
    events = read_events(FIXTURE)
    bridge_events(events[:4], reg, "project-x", KIMI)   # mid-run poll: spawned, no outcomes yet
    running = {r.agent_id: r for r in reg.agents_for("project-x")}
    assert running["asker"].status == "running"
    bridge_events(events, reg, "project-x", KIMI)       # full file later
    bridge_events(events, reg, "project-x", KIMI)       # and again — no dup rows, same totals
    rows = {r.agent_id: r for r in reg.agents_for("project-x")}
    assert len(reg.agents_for("project-x")) == 2
    assert abs(rows["oracle"].cost_usd - 0.00964201) < 1e-6


def test_bridge_maps_ticket_agents_to_ticket_ids_and_failures(tmp_path):
    reg = AgentRegistry(str(tmp_path / "project-x"))
    events = [
        {"type": "agent-spawned", "agent": "ticket-3", "sessionId": "s1"},
        {"type": "agent-turn-done", "agent": "ticket-3", "round": 0, "model": KIMI,
         "costUsd": 0.01, "tokens": {"input": 100, "output": 10, "reasoning": 0,
                                     "cache": {"read": 0, "write": 0}},
         "totalCostUsd": 0.01},
        {"type": "agent-failed", "agent": "ticket-3", "error": "boom"},
    ]
    bridge_events(events, reg, "project-x", KIMI)
    (row,) = reg.agents_for("project-x")
    assert row.ticket_id == 3
    assert row.role == "swarm-ticket"
    assert row.status == "failed" and row.outcome == "failed"
    assert abs(row.cost_usd - 0.01) < 1e-9


def test_bridge_agent_settled_supersedes_agent_done(tmp_path):
    # opencode-swarm >= df0a10d emits agent-settled AFTER the sweep with the true final
    # cost/status; agent-done remains the realtime (pre-sweep) signal.
    reg = AgentRegistry(str(tmp_path / "project-x"))
    tok = {"input": 100, "output": 10, "reasoning": 0, "cache": {"read": 0, "write": 0}}
    events = [
        {"type": "agent-spawned", "agent": "ticket-9", "sessionId": "s"},
        {"type": "agent-turn-done", "agent": "ticket-9", "round": 0, "model": KIMI,
         "costUsd": 0.01, "tokens": tok, "totalCostUsd": 0.01},
        {"type": "agent-done", "agent": "ticket-9", "result": "ok", "costUsd": 0.01},
        {"type": "agent-turn-done", "agent": "ticket-9", "round": 1, "model": KIMI,
         "costUsd": 0.005, "tokens": tok, "totalCostUsd": 0.015},  # sweep turn
        {"type": "agent-settled", "agent": "ticket-9", "status": "done",
         "costUsd": 0.015, "result": "ok"},
    ]
    bridge_events(events, reg, "project-x", KIMI)
    (row,) = reg.agents_for("project-x")
    assert abs(row.cost_usd - 0.015) < 1e-9      # settled cost, not agent-done's 0.01
    assert row.status == "done" and row.outcome == "success"


def test_bridge_settled_failure_wins_over_earlier_done(tmp_path):
    reg = AgentRegistry(str(tmp_path / "project-x"))
    events = [
        {"type": "agent-spawned", "agent": "a", "sessionId": "s"},
        {"type": "agent-done", "agent": "a", "result": "ok", "costUsd": 0.01},
        {"type": "agent-settled", "agent": "a", "status": "failed", "costUsd": 0.01,
         "result": "boom"},
    ]
    bridge_events(events, reg, "project-x", KIMI)
    (row,) = reg.agents_for("project-x")
    assert row.status == "failed" and row.outcome == "failed"


# ---- v0.2.0 release-binary fixture (agent-settled + monotonic ordinals) -----------------

FIXTURE_V020 = os.path.join(os.path.dirname(__file__), "..", "fixtures",
                            "swarm-events-v020.jsonl")


def test_v020_fixture_settled_costs_match_turn_sums_and_swarm_total():
    events = read_events(FIXTURE_V020)
    settled = {e["agent"]: e["costUsd"] for e in events if e["type"] == "agent-settled"}
    assert settled, "v0.2.0 fixture must carry agent-settled events"
    for agent, cost in settled.items():
        turns = sum(e["costUsd"] for e in events
                    if e["type"] == "agent-turn-done" and e["agent"] == agent)
        assert abs(cost - turns) < 1e-9
    total = next(e["totalCostUsd"] for e in events if e["type"] == "swarm-done")
    assert abs(sum(settled.values()) - total) < 1e-9
    assert abs(spend_usd(events) - total) < 1e-9


def test_v020_fixture_rounds_are_monotonic_ordinals():
    events = read_events(FIXTURE_V020)
    per_agent: dict = {}
    for e in events:
        if e["type"] == "agent-turn-done":
            per_agent.setdefault(e["agent"], []).append(e["round"])
    for rounds in per_agent.values():
        assert rounds == sorted(rounds) and -1 not in rounds


def test_v020_fixture_bridge_settles_to_the_settled_costs(tmp_path):
    reg = AgentRegistry(str(tmp_path / "project-x"))
    events = read_events(FIXTURE_V020)
    bridge_events(events, reg, "project-x", KIMI)
    settled = {e["agent"]: e["costUsd"] for e in events if e["type"] == "agent-settled"}
    rows = {r.agent_id: r for r in reg.agents_for("project-x")}
    for agent, cost in settled.items():
        assert abs(rows[agent].cost_usd - cost) < 1e-9
        assert rows[agent].status == "done"
