"""Pure unit tests for AdminService.conversations()/conversation_transcript() (SOF-34/T1.5) — no DB.
Injects fake console/users/conversation_repo (mirrors ConversationStore's own fake-repo tests), so
the cursor encode/decode, date parsing, name-enrichment, and next_cursor logic are all verified
without a real Postgres. Matches the standing no-DB-connection constraint on this box."""
import datetime

import pytest

from software_factory.services.admin_service import (
    AdminService, _encode_cursor, _decode_cursor, _parse_date,
)
from software_factory.services.errors import Invalid


# ── Pure helpers ─────────────────────────────────────────────────────────────────────────────

def test_encode_decode_cursor_round_trips():
    ts = datetime.datetime(2026, 3, 1, 12, 30, 0)
    token = _encode_cursor(ts, "sess-42")
    assert _decode_cursor(token) == (ts, "sess-42")


def test_decode_cursor_rejects_garbage():
    with pytest.raises(Invalid):
        _decode_cursor("not-a-real-cursor")


def test_parse_date_accepts_iso_and_none():
    assert _parse_date("date_from", None) is None
    assert _parse_date("date_from", "2026-01-01") == datetime.datetime(2026, 1, 1)


def test_parse_date_rejects_bad_format():
    with pytest.raises(Invalid, match="date_from"):
        _parse_date("date_from", "not-a-date")


# ── AdminService.conversations() / conversation_transcript() ───────────────────────────────────

class _FakeConversationRepo:
    def __init__(self, rows):
        self._rows = rows
        self.rollup_calls = []
        self.transcript_calls = []

    def rollup(self, **kwargs):
        self.rollup_calls.append(kwargs)
        return self._rows

    def all_for_session(self, session_id):
        self.transcript_calls.append(session_id)
        return [{"session_id": session_id, "role": "user", "input": "hi"}]


class _FakeConsole:
    def list_projects(self, owner=None):
        return [{"project_id": "proj-1", "name": "Widget Factory"}]


class _FakeUsers:
    def list_orgs(self):
        return [{"id": "org-1", "name": "Acme Co"}]

    def list_org_members(self, org_id):
        return []

    def list_users(self):
        return [{"id": "user-1", "email": "alice@acme.co"}]


def _service(rows):
    repo = _FakeConversationRepo(rows)
    svc = AdminService(_FakeConsole(), _FakeUsers(), agent_store=None, tool_store=None,
                       conversation_repo=repo)
    return svc, repo


def test_conversations_enriches_rows_with_names_and_emits_no_next_cursor_below_limit():
    rows = [{"session_id": "sess-1", "org_id": "org-1", "project_id": "proj-1",
             "user_id": "user-1", "turn_count": 4,
             "last_activity": datetime.datetime(2026, 3, 1), "total_cost": 1.5}]
    svc, repo = _service(rows)
    out = svc.conversations(limit=50)
    assert out["sessions"] == [{
        "session_id": "sess-1", "org_id": "org-1", "org_name": "Acme Co",
        "project_id": "proj-1", "project_name": "Widget Factory",
        "user_id": "user-1", "user_email": "alice@acme.co",
        "turn_count": 4, "last_activity": datetime.datetime(2026, 3, 1), "total_cost": 1.5,
    }]
    assert out["next_cursor"] is None


def test_conversations_emits_next_cursor_when_page_is_full():
    ts = datetime.datetime(2026, 3, 1)
    rows = [{"session_id": f"sess-{i}", "org_id": None, "project_id": None, "user_id": None,
             "turn_count": 1, "last_activity": ts, "total_cost": 0} for i in range(3)]
    svc, repo = _service(rows)
    out = svc.conversations(limit=3)
    assert out["next_cursor"] == _encode_cursor(ts, "sess-2")


def test_conversations_decodes_the_cursor_and_passes_it_to_the_repo():
    svc, repo = _service([])
    token = _encode_cursor(datetime.datetime(2026, 1, 1), "sess-prev")
    svc.conversations(cursor=token, limit=10)
    assert repo.rollup_calls[0]["cursor"] == (datetime.datetime(2026, 1, 1), "sess-prev")


def test_conversations_parses_date_filters_before_hitting_the_repo():
    svc, repo = _service([])
    svc.conversations(date_from="2026-01-01", date_to="2026-02-01")
    assert repo.rollup_calls[0]["date_from"] == datetime.datetime(2026, 1, 1)
    assert repo.rollup_calls[0]["date_to"] == datetime.datetime(2026, 2, 1)


def test_conversations_rejects_a_malformed_date_before_hitting_the_repo():
    svc, repo = _service([])
    with pytest.raises(Invalid):
        svc.conversations(date_from="garbage")
    assert repo.rollup_calls == []


def test_conversation_transcript_delegates_to_the_repo_for_one_session():
    svc, repo = _service([])
    out = svc.conversation_transcript("sess-9")
    assert out["session_id"] == "sess-9"
    assert out["messages"][0]["role"] == "user"
    assert repo.transcript_calls == ["sess-9"]
