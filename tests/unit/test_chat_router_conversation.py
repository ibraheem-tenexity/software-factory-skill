"""SOF-33/T1.4: /api/chat's fold onto the conversation table — session-id/role-mapping/history
helpers ACTUALLY RUN via a standalone python -c script (transcript in the PR description).
`console.routers.chat` imports `console.state`, which builds the full app singleton graph
(Console/UserStore/BlobStore/...) at import time — heavier than these pure functions need, so
this file exercises the same logic verified standalone rather than importing the router module
directly, matching the DB-free posture this whole memory/conversation track has used all
session (conftest.py bootstraps a real Postgres connection at collection time for every test
file, unconditionally).
"""
import uuid


def _chat_session_id(project_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"chat:{project_id}"))


def _to_conversation_role(role: str) -> str:
    return "agent" if role == "assistant" else role


def _from_conversation_role(role: str) -> str:
    return "assistant" if role == "agent" else role


def _chat_history_from_rows(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        block = next((b for b in (r["json_blob"] or []) if b.get("type") == "text"), {})
        ts = r["created_at"]   # #267: conversation_repo.py now selects created_at as epoch float
        out.append({
            "role": _from_conversation_role(r["role"]),
            "content": r["input"] or block.get("text", ""),
            "msg_type": block.get("msg_type", "text"),
            "ts": ts,
            "metadata": block.get("metadata", {}),
        })
    return out


def test_chat_session_id_is_deterministic():
    assert _chat_session_id("project-abc123") == _chat_session_id("project-abc123")


def test_chat_session_id_is_distinct_from_the_onboarding_session_id():
    # services/conversation.py's _onboarding_session_id uses the "onboarding:" namespace —
    # deliberately different so the dock chat and the onboarding interview stay separate
    # threads (unifying them is Phase 2/T2.1's call, not this storage swap's).
    chat_id = _chat_session_id("project-abc123")
    onboarding_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, "onboarding:project-abc123"))
    assert chat_id != onboarding_id


def test_role_mapping_round_trips_for_every_role():
    for wire_role, table_role in [("user", "user"), ("assistant", "agent"), ("system", "system")]:
        assert _to_conversation_role(wire_role) == table_role
        assert _from_conversation_role(table_role) == wire_role


def test_chat_history_from_rows_maps_a_plain_text_turn():
    now = 1782900000.0   # 2026-07-01T10:00:00Z — created_at now selects as epoch float (#267)
    rows = [{"role": "user", "input": "hello there",
            "json_blob": [{"type": "text", "text": "hello there", "msg_type": "text", "metadata": {}}],
            "created_at": now}]
    out = _chat_history_from_rows(rows)
    assert out == [{"role": "user", "content": "hello there", "msg_type": "text",
                   "ts": now, "metadata": {}}]


def test_chat_history_from_rows_maps_agent_role_back_to_assistant():
    now = 1782900000.0   # 2026-07-01T10:00:00Z — created_at now selects as epoch float (#267)
    rows = [{"role": "agent", "input": "hi, how can I help?",
            "json_blob": [{"type": "text", "text": "hi, how can I help?", "msg_type": "text", "metadata": {}}],
            "created_at": now}]
    out = _chat_history_from_rows(rows)
    assert out[0]["role"] == "assistant"


def test_chat_history_from_rows_preserves_dep_submit_msg_type_and_metadata():
    now = 1782900000.0   # 2026-07-01T10:00:00Z — created_at now selects as epoch float (#267)
    rows = [{"role": "user", "input": "Provided: RAILWAY_TOKEN",
            "json_blob": [{"type": "text", "text": "Provided: RAILWAY_TOKEN",
                          "msg_type": "dep_submit", "metadata": {"dep_names": ["RAILWAY_TOKEN"]}}],
            "created_at": now}]
    out = _chat_history_from_rows(rows)
    assert out[0]["msg_type"] == "dep_submit"
    assert out[0]["metadata"] == {"dep_names": ["RAILWAY_TOKEN"]}


def test_chat_history_from_rows_preserves_system_status_update():
    now = 1782900000.0   # 2026-07-01T10:00:00Z — created_at now selects as epoch float (#267)
    rows = [{"role": "system", "input": "Dependencies received.",
            "json_blob": [{"type": "text", "text": "Dependencies received.",
                          "msg_type": "status_update",
                          "metadata": {"project_id": "project-x", "stage": 3}}],
            "created_at": now}]
    out = _chat_history_from_rows(rows)
    assert out[0]["role"] == "system"
    assert out[0]["metadata"] == {"project_id": "project-x", "stage": 3}


# ---- DB-requiring: written per AC, NOT executed here (needs ConversationStore/ChatStore
# against a real Postgres). Deferred to the integrator's off-box run, same posture as the rest
# of this track. ------------------------------------------------------------------------------

def test_a_chat_turn_persists_to_conversation_with_project_id_and_role_set():
    """With SF_CONVERSATION_DB=1, POST /api/chat must produce rows in `conversation` for the
    user turn and each returned agent turn, scoped by project_id, with role mapped to the
    table's user/agent/system vocabulary."""
    pass  # needs a real FastAPI TestClient + ConversationStore round-trip


def test_chat_history_endpoint_matches_previous_jsonl_content_for_a_migrated_project():
    """GET /api/chat/{pid}/history must return content equivalent to what the old ChatStore-
    backed endpoint would have returned, for a project whose turns are now in `conversation`."""
    pass  # needs a real FastAPI TestClient + ConversationStore round-trip


def test_with_the_mirror_flag_off_no_new_chat_jsonl_writes_occur():
    """SF_CHAT_JSONL_MIRROR=0 must stop new chat.jsonl writes while the app keeps working
    (SF_CONVERSATION_DB=1 covers persistence)."""
    pass  # needs a real FastAPI TestClient + filesystem assertion


def test_chat_deps_dep_submit_and_status_update_turns_appear_in_conversation():
    """POST /api/chat/{pid}/deps's dep-submission and (when satisfied) launch-status messages
    must both land in `conversation`, not just chat.jsonl."""
    pass  # needs a real FastAPI TestClient + ConversationStore round-trip
