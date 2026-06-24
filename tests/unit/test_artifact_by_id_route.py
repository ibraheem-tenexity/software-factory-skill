"""Tests for GET /api/artifacts/{id} — cross-project artifact fetch."""
import importlib
import os
import sys
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


def _load_app(tmp_path, monkeypatch):
    monkeypatch.setenv("SF_PROJECTS_DIR", str(tmp_path))
    monkeypatch.setenv("SF_RUNS_DIR", str(tmp_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("SF_GOOGLE_CLIENT_ID", "cid-123.apps.googleusercontent.com")
    monkeypatch.setenv("SF_SESSION_SECRET", "test-secret")
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    import console.app as app_mod
    importlib.reload(app_mod)
    return app_mod


@pytest.fixture()
def auth_mod(tmp_path, monkeypatch):
    mod = _load_app(tmp_path, monkeypatch)
    mod.users.upsert("user@tenexity.ai", "member")
    return mod


@pytest.fixture()
def auth_client(auth_mod):
    return TestClient(auth_mod.app, base_url="https://testserver")


def _login(mod, client, monkeypatch, email="user@tenexity.ai"):
    from software_factory import auth as a
    monkeypatch.setattr(a, "verify_google_id_token",
                        lambda tok: {"sub": "sub-" + email, "email": email, "email_verified": True})
    return client.post("/api/auth/google", json={"credential": "t"})


_ARTIFACT_ROW = {
    "id": 42,
    "project_id": "project-abc12345",
    "title": "Architecture",
    "kind": "plan",
    "path": "architecture.md",
    "ts": 1718000000.0,
    "agent": "architect-01",
}


def test_artifact_detail_returns_full_shape(auth_mod, auth_client, monkeypatch):
    _login(auth_mod, auth_client, monkeypatch)
    import console.routers.projects as rmod
    monkeypatch.setattr(rmod, "artifact_by_id", lambda aid: dict(_ARTIFACT_ROW))
    monkeypatch.setattr(auth_mod.console, "artifact",
                        lambda pid, path: {"content": "# Architecture\n..."})
    monkeypatch.setattr(auth_mod.console, "project_owner", lambda pid: "user@tenexity.ai")
    j = auth_client.get("/api/artifacts/42").json()
    assert j["id"] == 42
    assert j["project_id"] == "project-abc12345"
    assert j["title"] == "Architecture"
    assert j["kind"] == "plan"
    assert j["path"] == "architecture.md"
    assert j["content"] == "# Architecture\n..."
    assert j["updated"] == 1718000000.0
    assert j["agent"] == "architect-01"


def test_artifact_detail_404_for_unknown_id(auth_mod, auth_client, monkeypatch):
    _login(auth_mod, auth_client, monkeypatch)
    import console.routers.projects as rmod
    monkeypatch.setattr(rmod, "artifact_by_id", lambda aid: None)
    assert auth_client.get("/api/artifacts/999").status_code == 404


def test_artifact_detail_requires_auth(auth_client):
    assert auth_client.get("/api/artifacts/42").status_code == 401


def test_artifact_detail_url_path_skips_content_read(auth_mod, auth_client, monkeypatch):
    _login(auth_mod, auth_client, monkeypatch)
    import console.routers.projects as rmod
    url_row = dict(_ARTIFACT_ROW, path="https://example.com/deploy")
    monkeypatch.setattr(rmod, "artifact_by_id", lambda aid: url_row)
    monkeypatch.setattr(auth_mod.console, "project_owner", lambda pid: "user@tenexity.ai")
    j = auth_client.get("/api/artifacts/42").json()
    assert j["path"] == "https://example.com/deploy"
    assert j["content"] is None


def test_artifact_detail_empty_path_returns_null_content(auth_mod, auth_client, monkeypatch):
    _login(auth_mod, auth_client, monkeypatch)
    import console.routers.projects as rmod
    row = dict(_ARTIFACT_ROW, path=None)
    monkeypatch.setattr(rmod, "artifact_by_id", lambda aid: row)
    monkeypatch.setattr(auth_mod.console, "project_owner", lambda pid: "user@tenexity.ai")
    j = auth_client.get("/api/artifacts/42").json()
    assert j["content"] is None
    assert j["path"] == ""


def test_artifact_detail_403_for_other_users_project(auth_mod, auth_client, monkeypatch):
    """IDOR guard: a member who doesn't own the artifact's project gets 403, not the artifact."""
    _login(auth_mod, auth_client, monkeypatch)
    import console.routers.projects as rmod
    monkeypatch.setattr(rmod, "artifact_by_id", lambda aid: dict(_ARTIFACT_ROW))
    # project owner is someone else; auth_mod user is a member (not admin)
    monkeypatch.setattr(auth_mod.console, "project_owner",
                        lambda pid: "other-user@elsewhere.com")
    assert auth_client.get("/api/artifacts/42").status_code == 403
