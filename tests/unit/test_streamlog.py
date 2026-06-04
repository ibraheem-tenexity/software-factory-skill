"""Parse the headless claude stream-json (captured in run.log) into the two things the
dashboard needs but the wandering orchestration doesn't self-report: live COST and the
AGENT GRAPH (orchestrator + the subagents it spawned via the Task tool).

Deriving these from the real claude stream makes the dashboard truthful regardless of
whether the skill code records anything.
"""
from software_factory.streamlog import cost_usd, agents, summary


# A few representative stream-json lines (one JSON object per line, as claude -p emits).
def stream(*lines):
    return "\n".join(lines) + "\n"


ASSIST_USAGE = '{"type":"assistant","message":{"model":"claude-sonnet-4-6","content":[{"type":"text","text":"working"}],"usage":{"input_tokens":1000,"output_tokens":500,"cache_read_input_tokens":200}}}'
TASK_SPAWN = '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"toolu_a","name":"Task","input":{"description":"build guestbook form","subagent_type":"general-purpose"}}]}}'
TASK_RESULT = '{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"toolu_a","content":"done"}]}}'
TASK_SPAWN_2 = '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"toolu_b","name":"Task","input":{"description":"write API","subagent_type":"general-purpose"}}]}}'
BASH = '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"toolu_c","name":"Bash","input":{"command":"ls"}}]}}'
RESULT = '{"type":"result","subtype":"success","total_cost_usd":0.0731,"usage":{"input_tokens":1000,"output_tokens":500}}'


def test_cost_uses_result_total_when_present():
    # The final result event carries claude's own authoritative cost.
    assert cost_usd(stream(ASSIST_USAGE, RESULT)) == 0.0731


def test_cost_falls_back_to_summing_usage_via_price_table():
    # No result event yet (run in progress) -> sum assistant usage with the model's prices.
    c = cost_usd(stream(ASSIST_USAGE))
    assert c > 0  # 1000 in + 500 out + 200 cached on sonnet, all priced


def test_empty_or_garbage_stream_is_zero_cost():
    assert cost_usd("") == 0.0
    assert cost_usd("not json\n{bad}\n") == 0.0


def test_agents_are_the_task_subagents_with_status():
    a = agents(stream(ASSIST_USAGE, TASK_SPAWN, TASK_RESULT, TASK_SPAWN_2))
    by_id = {x["id"]: x for x in a}
    assert set(by_id) == {"toolu_a", "toolu_b"}
    assert by_id["toolu_a"]["label"] == "build guestbook form"
    assert by_id["toolu_a"]["status"] == "done"      # had a tool_result
    assert by_id["toolu_b"]["status"] == "running"   # no result yet


def test_non_task_tools_are_not_agents():
    # Bash/Edit etc. are orchestrator actions, not separate agents/nodes.
    assert agents(stream(BASH)) == []


def test_summary_bundles_cost_and_agents_for_the_graph():
    s = summary(stream(ASSIST_USAGE, TASK_SPAWN, TASK_RESULT, RESULT))
    assert s["cost_usd"] == 0.0731
    assert len(s["agents"]) == 1
    assert s["agents"][0]["status"] == "done"
