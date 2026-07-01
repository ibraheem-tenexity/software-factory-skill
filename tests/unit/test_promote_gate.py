"""SOF-51/SOF-52: the composed promote trust gate — brief.enough() (required-section coverage)
AND SOF-37's reflection-questions check. Lives in console.promote_draft() itself (SOF-52) so
every caller is gated by construction (the HTTP route, the concierge's hand_off_to_factory tool,
any future one) — the route just lets the resulting services.errors.Conflict propagate to
app.py's global ServiceError handler, which serializes it to the same 409 shape SOF-51 originally
built inline at the router. No DB: Console(tmp_path, ...) is the local-filesystem JsonFileStore
harness, same as test_drafts.py.
"""
import pytest

from software_factory.console import Console
from software_factory.services.errors import Conflict


class FakeLauncher:
    def __init__(self):
        self.argv = None

    def __call__(self, argv, env=None, log_path=None, cwd=None):
        self.argv = argv
        return {"pid": 1234}


def _console(tmp_path, launcher=None):
    launcher = launcher or FakeLauncher()
    ids = iter([f"project-{i:08x}" for i in range(1, 50)])
    return Console(str(tmp_path), launch=launcher, new_id=lambda: next(ids), extract=lambda p: "# x")


_COMPLETE_BRIEF = {
    "goals": "A cargo screening prototype for ground handlers to log screening events.",
    "success_metrics": "A stakeholder cannot distinguish it from the hand-built demo.",
    "definition_of_done": "All V1 screens deployed and browser-verified.",
}


def _open_question(qid="q1"):
    return {"id": qid, "status": "open", "fact": "x", "document_blob_id": 1,
            "section_path_claimed": None, "answer": None, "created_at": 1.0}


def test_promote_draft_raises_conflict_when_brief_incomplete(tmp_path):
    c = _console(tmp_path)
    rid = c.create_draft(owner="op@tenexity.ai")
    with pytest.raises(Conflict) as exc_info:
        c.promote_draft(rid)
    detail = exc_info.value.detail
    assert set(detail["missing_sections"]) == {"goals", "success_metrics", "definition_of_done"}
    assert "open_questions" not in detail
    assert c.is_draft(rid) is True   # never provisioned — the gate fired before any state change


def test_promote_draft_raises_conflict_when_reflection_questions_open(tmp_path):
    c = _console(tmp_path)
    rid = c.create_draft(owner="op@tenexity.ai")
    c.update_draft_brief(rid, _COMPLETE_BRIEF)
    st = c._load_state(rid)
    st.reflection_questions = [_open_question()]
    st.save()
    with pytest.raises(Conflict) as exc_info:
        c.promote_draft(rid)
    detail = exc_info.value.detail
    assert "missing_sections" not in detail
    assert detail["open_questions"] == [_open_question()]
    assert c.is_draft(rid) is True


def test_promote_draft_raises_conflict_with_both_pieces_when_both_fail(tmp_path):
    # Composed gate — a user fixing only one problem must be told about the other on the SAME
    # exception, not discover it on a second failed attempt.
    c = _console(tmp_path)
    rid = c.create_draft(owner="op@tenexity.ai")
    st = c._load_state(rid)
    st.reflection_questions = [_open_question()]
    st.save()
    with pytest.raises(Conflict) as exc_info:
        c.promote_draft(rid)
    detail = exc_info.value.detail
    assert set(detail["missing_sections"]) == {"goals", "success_metrics", "definition_of_done"}
    assert detail["open_questions"] == [_open_question()]


def test_promote_draft_ignores_answered_and_dismissed_questions(tmp_path):
    c = _console(tmp_path)
    rid = c.create_draft(owner="op@tenexity.ai", name="Cargo", runtime="claude")
    c.update_draft_brief(rid, _COMPLETE_BRIEF)
    st = c._load_state(rid)
    st.reflection_questions = [
        {"id": "q1", "status": "answered", "fact": "x", "document_blob_id": 1,
         "section_path_claimed": None, "answer": "yes", "created_at": 1.0},
        {"id": "q2", "status": "dismissed", "fact": "y", "document_blob_id": 1,
         "section_path_claimed": None, "answer": None, "created_at": 1.0},
    ]
    st.save()
    out = c.promote_draft(rid, interview_md="transcript")
    assert out == rid
    assert c.is_draft(rid) is False


def test_promote_draft_succeeds_when_both_gates_pass(tmp_path):
    # The anchor for this ticket: proves the new gate doesn't false-positive-block a genuinely
    # ready draft (test_drafts.py's own promote test covers the brief-threading behavior itself).
    c = _console(tmp_path)
    rid = c.create_draft(owner="op@tenexity.ai", name="Cargo", runtime="claude")
    c.update_draft_brief(rid, _COMPLETE_BRIEF)
    out = c.promote_draft(rid, interview_md="transcript")
    assert out == rid
    assert c.is_draft(rid) is False


# ---- Router-level: confirm a Conflict from console.promote_draft propagates through app.py's
# global ServiceError handler into the exact 409 shape the FE expects (SOF-51's original
# contract, now produced automatically instead of built inline at the router). ------------------

def test_promote_route_returns_409_with_the_conflict_detail_verbatim(monkeypatch):
    import importlib
    import os
    import sys
    import tempfile
    from fastapi.testclient import TestClient

    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("SF_PROJECTS_DIR", tmp)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("SF_GOOGLE_CLIENT_ID", "cid-123.apps.googleusercontent.com")
    monkeypatch.setenv("SF_SESSION_SECRET", "test-secret")
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    import console.app as mod
    importlib.reload(mod)
    mod.users.upsert("op@tenexity.ai", "member")
    client = TestClient(mod.app, base_url="https://testserver")

    from software_factory import auth as a
    monkeypatch.setattr(a, "verify_google_id_token", lambda tok: {
        "sub": "sub-op@tenexity.ai", "email": "op@tenexity.ai", "email_verified": True})
    client.post("/api/auth/google", json={"credential": "t"})

    monkeypatch.setattr(mod.console, "is_draft", lambda pid: True)
    monkeypatch.setattr(mod.console, "project_exists", lambda rid: True)
    monkeypatch.setattr(mod.console, "project_owner", lambda rid: "op@tenexity.ai")

    def fake_promote_draft(pid, **kw):
        raise Conflict({"error": "project is not ready to promote", "missing_sections": ["goals"]})
    monkeypatch.setattr(mod.console, "promote_draft", fake_promote_draft)

    r = client.post("/api/projects/project-abc/promote", json={})
    assert r.status_code == 409
    assert r.json()["detail"] == {"error": "project is not ready to promote",
                                  "missing_sections": ["goals"]}
