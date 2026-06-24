"""SOW CRUD routes: GET/POST /api/admin/sow, PATCH /api/admin/sow/{id}."""
import importlib
import os
import sys
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


def _load_app(tmp_path, monkeypatch, **env):
    monkeypatch.setenv("SF_PROJECTS_DIR", str(tmp_path))
    monkeypatch.setenv("SF_RUNS_DIR", str(tmp_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    for k, val in env.items():
        monkeypatch.setenv(k, val)
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    import console.app as app_mod
    importlib.reload(app_mod)
    return app_mod


_AUTH = dict(SF_GOOGLE_CLIENT_ID="cid-123.apps.googleusercontent.com",
             SF_SESSION_SECRET="test-secret")


@pytest.fixture()
def staff_mod(tmp_path, monkeypatch):
    return _load_app(tmp_path, monkeypatch, SF_BOOTSTRAP_ADMIN_EMAIL="op@tenexity.ai", **_AUTH)


@pytest.fixture()
def staff_client(staff_mod):
    return TestClient(staff_mod.app, base_url="https://testserver")


@pytest.fixture()
def member_mod(tmp_path, monkeypatch):
    mod = _load_app(tmp_path, monkeypatch, **_AUTH)
    mod.users.upsert("op@tenexity.ai", "member")
    return mod


@pytest.fixture()
def member_client(member_mod):
    return TestClient(member_mod.app, base_url="https://testserver")


def _login(mod, client, monkeypatch, email="op@tenexity.ai"):
    from software_factory import auth as a
    monkeypatch.setattr(a, "verify_google_id_token",
                        lambda tok: {"sub": "sub-" + email, "email": email, "email_verified": True})
    return client.post("/api/auth/google", json={"credential": "t"})


_SOW_ROW = {
    "id": 1, "title": "Acme SOW Q3", "org": "Acme", "project": "project-abc12345",
    "value": "$50,000", "file": None, "version": 1, "status": "Draft",
    "body": "## Scope\nBuild a thing.", "created_at": "2026-06-24T00:00:00Z",
    "updated_at": "2026-06-24T00:00:00Z",
}


def _mock_sow(mod, monkeypatch):
    m = MagicMock()
    m.list_all.return_value = [_SOW_ROW]
    m.get.return_value = _SOW_ROW
    m.create.return_value = _SOW_ROW
    m.update.return_value = dict(_SOW_ROW, title="Updated Title")
    import console.state as st
    monkeypatch.setattr(st, "sow_store", m)
    return m


def test_sow_list_returns_all(staff_mod, staff_client, monkeypatch):
    _login(staff_mod, staff_client, monkeypatch)
    _mock_sow(staff_mod, monkeypatch)
    j = staff_client.get("/api/admin/sow").json()
    assert j["sows"][0]["title"] == "Acme SOW Q3"
    assert j["sows"][0]["status"] == "Draft"


def test_sow_create_returns_row(staff_mod, staff_client, monkeypatch):
    _login(staff_mod, staff_client, monkeypatch)
    _mock_sow(staff_mod, monkeypatch)
    j = staff_client.post("/api/admin/sow", json={
        "title": "Acme SOW Q3", "org": "Acme", "status": "Draft",
        "body": "## Scope\nBuild a thing."
    }).json()
    assert j["id"] == 1 and j["title"] == "Acme SOW Q3"


def test_sow_patch_updates_title(staff_mod, staff_client, monkeypatch):
    _login(staff_mod, staff_client, monkeypatch)
    _mock_sow(staff_mod, monkeypatch)
    j = staff_client.patch("/api/admin/sow/1", json={"title": "Updated Title"}).json()
    assert j["title"] == "Updated Title"


def test_sow_patch_404_for_unknown(staff_mod, staff_client, monkeypatch):
    _login(staff_mod, staff_client, monkeypatch)
    m = _mock_sow(staff_mod, monkeypatch)
    m.get.return_value = None
    assert staff_client.patch("/api/admin/sow/999", json={"title": "X"}).status_code == 404


def test_sow_requires_staff(member_mod, member_client, monkeypatch):
    _login(member_mod, member_client, monkeypatch)
    assert member_client.get("/api/admin/sow").status_code == 403


def test_sow_requires_session(staff_client):
    assert staff_client.get("/api/admin/sow").status_code == 401


def test_sow_create_invalid_status(staff_mod, staff_client, monkeypatch):
    _login(staff_mod, staff_client, monkeypatch)
    m = _mock_sow(staff_mod, monkeypatch)
    m.create.side_effect = ValueError("invalid status 'Bogus'")
    r = staff_client.post("/api/admin/sow", json={"title": "X", "status": "Bogus"})
    assert r.status_code == 422


def test_sow_get_returns_row(staff_mod, staff_client, monkeypatch):
    _login(staff_mod, staff_client, monkeypatch)
    _mock_sow(staff_mod, monkeypatch)
    j = staff_client.get("/api/admin/sow/1").json()
    assert j["id"] == 1 and j["title"] == "Acme SOW Q3"


def test_sow_get_404_for_unknown(staff_mod, staff_client, monkeypatch):
    _login(staff_mod, staff_client, monkeypatch)
    m = _mock_sow(staff_mod, monkeypatch)
    m.get.return_value = None
    assert staff_client.get("/api/admin/sow/999").status_code == 404


def test_sow_get_requires_staff(member_mod, member_client, monkeypatch):
    _login(member_mod, member_client, monkeypatch)
    assert member_client.get("/api/admin/sow/1").status_code == 403
