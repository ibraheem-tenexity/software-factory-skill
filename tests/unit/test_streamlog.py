"""Parse the headless claude stream-json (captured in project.log) into the two things the
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


def test_cost_sums_result_totals_across_appended_stages():
    # project.log APPENDS each stage's claude -p session; each stage is a DISTINCT real session_id
    # (a fresh, non-resumed `claude -p` invocation) and emits its own authoritative result line.
    # True run cost = SUM of every DISTINCT session's total_cost_usd, not just the last one (the
    # old "last result wins" lost Stage 1's cost the moment Stage 2 finished).
    usage1 = '{"type":"assistant","session_id":"stage1","message":{"model":"claude-sonnet-4-6","content":[],"usage":{"input_tokens":1000,"output_tokens":500}}}'
    stage1 = '{"type":"result","subtype":"success","total_cost_usd":0.0731,"session_id":"stage1"}'
    usage2 = '{"type":"assistant","session_id":"stage2","message":{"model":"claude-sonnet-4-6","content":[],"usage":{"input_tokens":1000,"output_tokens":500}}}'
    stage2 = '{"type":"result","subtype":"success","total_cost_usd":0.0731,"session_id":"stage2"}'
    two_stages = stream(usage1, stage1, usage2, stage2)
    assert cost_usd(two_stages) == round(0.0731 * 2, 6)


def test_cost_takes_max_not_sum_across_resumes_of_the_same_session():
    # SOF-87 live incident: `claude -p --resume <session>` resends the full prior conversation, so
    # a resumed session's total_cost_usd is CUMULATIVE — a later result already includes every
    # earlier turn. A stage retried/resumed N times under the SAME session_id therefore emits N
    # monotonically-increasing result lines; summing them double/triple/N-x counts the earliest
    # turns. Confirmed live: project-8394d197a111467f's session emitted 15 results
    # ($0.94..$12.59, non-monotonic num_turns/duration_ms proving separate invocations) whose SUM
    # was $83.83 against the true $12.59 — inflating that project's total spend from ~$19 to
    # $100.64. The parser must take the MAX per session, never sum a single session's results.
    same_session = stream(
        '{"type":"result","subtype":"success","total_cost_usd":0.94,"session_id":"resumed"}',
        '{"type":"result","subtype":"success","total_cost_usd":1.74,"session_id":"resumed"}',
        '{"type":"result","subtype":"success","total_cost_usd":12.59,"session_id":"resumed"}',
    )
    assert cost_usd(same_session) == 12.59


def test_cost_max_within_session_still_sums_across_distinct_sessions():
    # Combine both real-world shapes in one log: one session resumed 3x (max, not sum) plus one
    # fresh, distinct session (added on top) — mirrors project-8394d197a111467f's actual log shape.
    mixed = stream(
        '{"type":"result","subtype":"success","total_cost_usd":0.94,"session_id":"resumed"}',
        '{"type":"result","subtype":"success","total_cost_usd":12.59,"session_id":"resumed"}',
        '{"type":"result","subtype":"success","total_cost_usd":4.16,"session_id":"other"}',
    )
    assert cost_usd(mixed) == round(12.59 + 4.16, 6)


def test_cost_adds_inflight_stage_after_last_result():
    # A finished stage (result line) plus an in-flight stage (usage, no result yet): the total is
    # the finished session's authoritative cost PLUS the running session's token estimate.
    c = cost_usd(stream(RESULT, ASSIST_USAGE))
    assert c > 0.0731                      # 0.0731 (finished) + estimate of the in-flight usage


def test_cost_keeps_a_killed_sessions_estimate_when_a_later_session_finishes():
    # project-d329e57c scar: the OOM-killed S3 session never emitted a result line; when the RETRY
    # session's result landed, the killed session's ~$12 estimate was discarded (tail reset) and
    # the run under-reported $28.37 as $16.31 — under-counting the budget guard. Cost must be
    # session-aware: per session, a result is authoritative; without one, the estimate COUNTS.
    s1 = '{"type":"result","subtype":"success","total_cost_usd":1.0,"session_id":"s1"}'
    killed_usage = '{"type":"assistant","session_id":"killed","message":{"model":"claude-sonnet-4-6","content":[],"usage":{"input_tokens":100000,"output_tokens":50000}}}'
    retry_result = '{"type":"result","subtype":"success","total_cost_usd":2.0,"session_id":"retry"}'
    c = cost_usd(stream(s1, killed_usage, retry_result))
    assert c > 3.0                      # 1.0 + 2.0 + the killed session's token estimate


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
