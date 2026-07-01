"""SOF-51: the composed promote trust gate — brief.enough() (required-section coverage) AND
SOF-37's reflection-questions check, both enforced at POST /api/projects/{pid}/promote, composed
into ONE 409 when either or both fail.
"""
import importlib
import os
import sys

import pytest
from fastapi.testclient import TestClient


def _load_app(tmp_path, monkeypatch, **env):
    monkeypatch.setenv("SF_PROJECTS_DIR", str(tmp_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    for k, val in env.items():
        monkeypatch.setenv(k, val)
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    import console.app as app_mod
    importlib.reload(app_mod)
    return app_mod


@pytest.fixture()
def auth_mod(tmp_path, monkeypatch):
    mod = _load_app(tmp_path, monkeypatch,
                    SF_GOOGLE_CLIENT_ID="cid-123.apps.googleusercontent.com",
                    SF_SESSION_SECRET="test-secret")
    mod.users.upsert("op@tenexity.ai", "member")
    return mod


@pytest.fixture()
def auth_client(auth_mod):
    return TestClient(auth_mod.app, base_url="https://testserver")


def _login(mod, client, monkeypatch, email="op@tenexity.ai"):
    from software_factory import auth as a
    monkeypatch.setattr(a, "verify_google_id_token",
                        lambda tok: {"sub": "sub-" + email, "email": email, "email_verified": True})
    return client.post("/api/auth/google", json={"credential": "t"})


class _FakeState:
    def __init__(self, brief=None, reflection_questions=None):
        self.brief = brief or {}
        self.reflection_questions = reflection_questions or []


_COMPLETE_BRIEF = {"goals": "Automate quoting for our distribution business end to end.",
                   "success_metrics": "Cut quote turnaround from 2 days to under 1 hour.",
                   "definition_of_done": "Sales can generate and send a quote without IT help."}


def _wire(mod, monkeypatch, *, is_draft=True, brief=None, reflection_questions=None, owner="op@tenexity.ai"):
    c = mod.console
    monkeypatch.setattr(c, "is_draft", lambda pid: is_draft)
    monkeypatch.setattr(c, "_load_state", lambda pid: _FakeState(brief, reflection_questions))
    monkeypatch.setattr(c, "project_exists", lambda rid: True)
    monkeypatch.setattr(c, "project_owner", lambda rid: owner)


def test_promote_409s_when_brief_incomplete_and_no_open_questions(auth_mod, auth_client, monkeypatch):
    _login(auth_mod, auth_client, monkeypatch)
    _wire(auth_mod, monkeypatch, brief={}, reflection_questions=[])
    r = auth_client.post("/api/projects/project-abc/promote", json={})
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert set(detail["missing_sections"]) == {"goals", "success_metrics", "definition_of_done"}
    assert "open_questions" not in detail


def test_promote_409s_when_only_reflection_questions_are_open(auth_mod, auth_client, monkeypatch):
    _login(auth_mod, auth_client, monkeypatch)
    open_q = [{"id": "q1", "status": "open", "fact": "x", "document_blob_id": 1,
              "section_path_claimed": None, "answer": None, "created_at": 1.0}]
    _wire(auth_mod, monkeypatch, brief=_COMPLETE_BRIEF, reflection_questions=open_q)
    r = auth_client.post("/api/projects/project-abc/promote", json={})
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert "missing_sections" not in detail
    assert detail["open_questions"] == open_q


def test_promote_409s_with_both_pieces_when_both_fail(auth_mod, auth_client, monkeypatch):
    # Composed gate — a user fixing only one problem must be told about the other on the SAME
    # response, not discover it on a second failed resubmit.
    _login(auth_mod, auth_client, monkeypatch)
    open_q = [{"id": "q1", "status": "open", "fact": "x", "document_blob_id": 1,
              "section_path_claimed": None, "answer": None, "created_at": 1.0}]
    _wire(auth_mod, monkeypatch, brief={}, reflection_questions=open_q)
    r = auth_client.post("/api/projects/project-abc/promote", json={})
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert set(detail["missing_sections"]) == {"goals", "success_metrics", "definition_of_done"}
    assert detail["open_questions"] == open_q


def test_promote_ignores_answered_and_dismissed_questions(auth_mod, auth_client, monkeypatch):
    _login(auth_mod, auth_client, monkeypatch)
    resolved = [{"id": "q1", "status": "answered", "fact": "x", "document_blob_id": 1,
                "section_path_claimed": None, "answer": "yes", "created_at": 1.0},
               {"id": "q2", "status": "dismissed", "fact": "y", "document_blob_id": 1,
                "section_path_claimed": None, "answer": None, "created_at": 1.0}]
    _wire(auth_mod, monkeypatch, brief=_COMPLETE_BRIEF, reflection_questions=resolved)
    monkeypatch.setattr(auth_mod.console, "promote_draft", lambda pid, **kw: "project-real-id")
    r = auth_client.post("/api/projects/project-abc/promote", json={})
    assert r.status_code == 200
    assert r.json() == {"project_id": "project-real-id", "status": "started"}


def test_promote_succeeds_when_both_gates_pass(auth_mod, auth_client, monkeypatch):
    _login(auth_mod, auth_client, monkeypatch)
    _wire(auth_mod, monkeypatch, brief=_COMPLETE_BRIEF, reflection_questions=[])
    monkeypatch.setattr(auth_mod.console, "promote_draft", lambda pid, **kw: "project-real-id")
    r = auth_client.post("/api/projects/project-abc/promote", json={})
    assert r.status_code == 200
    assert r.json() == {"project_id": "project-real-id", "status": "started"}


def test_promote_409s_when_not_a_draft(auth_mod, auth_client, monkeypatch):
    _login(auth_mod, auth_client, monkeypatch)
    _wire(auth_mod, monkeypatch, is_draft=False, brief=_COMPLETE_BRIEF, reflection_questions=[])
    r = auth_client.post("/api/projects/project-abc/promote", json={})
    assert r.status_code == 409
    assert r.json()["detail"] == "not a draft (already promoted)"
