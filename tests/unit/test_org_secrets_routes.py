"""Tests for /api/org/secrets CRUD + ref endpoint (PR #195)."""
import importlib
import os
import sys

import pytest
from fastapi.testclient import TestClient


def _load_app(tmp_path, monkeypatch, **env):
    monkeypatch.setenv("SF_PROJECTS_DIR", str(tmp_path))
    monkeypatch.setenv("SF_BLOB_DIR", str(tmp_path / "blobs"))
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
def admin_mod(tmp_path, monkeypatch):
    mod = _load_app(tmp_path, monkeypatch, **_AUTH)
    mod.users.upsert("op@tenexity.ai", "admin")
    return mod


@pytest.fixture()
def admin_client(admin_mod):
    return TestClient(admin_mod.app, base_url="https://testserver")


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


def _make_org(client, name="Acme"):
    client.post("/api/org", json={"name": name})


# ── list ──────────────────────────────────────────────────────────────────────────────────────
def test_list_empty(admin_mod, admin_client, monkeypatch):
    _login(admin_mod, admin_client, monkeypatch)
    _make_org(admin_client)
    r = admin_client.get("/api/org/secrets")
    assert r.status_code == 200
    assert r.json()["secrets"] == []


def test_list_requires_admin(member_mod, member_client, monkeypatch):
    _login(member_mod, member_client, monkeypatch)
    assert member_client.get("/api/org/secrets").status_code == 403


# ── create ────────────────────────────────────────────────────────────────────────────────────
def test_create_secret(admin_mod, admin_client, monkeypatch):
    _login(admin_mod, admin_client, monkeypatch)
    _make_org(admin_client)
    r = admin_client.post("/api/org/secrets", json={"name": "MY_KEY", "value": "supersecret1234", "kind": "api_key"})
    assert r.status_code == 201
    s = r.json()["secret"]
    assert s["name"] == "MY_KEY"
    assert s["last4"] == "1234"
    assert s["kind"] == "api_key"
    assert "supersecret" not in str(r.json())   # plaintext never leaks


def test_create_appears_in_list(admin_mod, admin_client, monkeypatch):
    _login(admin_mod, admin_client, monkeypatch)
    _make_org(admin_client)
    admin_client.post("/api/org/secrets", json={"name": "TOKEN_A", "value": "abcdefgh", "kind": "token"})
    secrets = admin_client.get("/api/org/secrets").json()["secrets"]
    assert len(secrets) == 1
    assert secrets[0]["name"] == "TOKEN_A" and secrets[0]["last4"] == "efgh"


def test_create_duplicate_is_400(admin_mod, admin_client, monkeypatch):
    _login(admin_mod, admin_client, monkeypatch)
    _make_org(admin_client)
    admin_client.post("/api/org/secrets", json={"name": "DUPE", "value": "val1", "kind": "api_key"})
    r = admin_client.post("/api/org/secrets", json={"name": "DUPE", "value": "val2", "kind": "api_key"})
    assert r.status_code == 400


def test_create_invalid_name_422(admin_mod, admin_client, monkeypatch):
    _login(admin_mod, admin_client, monkeypatch)
    _make_org(admin_client)
    r = admin_client.post("/api/org/secrets", json={"name": "lower_case", "value": "x", "kind": "api_key"})
    assert r.status_code == 422


def test_create_requires_admin(member_mod, member_client, monkeypatch):
    _login(member_mod, member_client, monkeypatch)
    r = member_client.post("/api/org/secrets", json={"name": "MY_KEY", "value": "x", "kind": "api_key"})
    assert r.status_code == 403


# ── rotate ────────────────────────────────────────────────────────────────────────────────────
def test_rotate_updates_last4(admin_mod, admin_client, monkeypatch):
    _login(admin_mod, admin_client, monkeypatch)
    _make_org(admin_client)
    admin_client.post("/api/org/secrets", json={"name": "MY_KEY", "value": "oldvalue0000", "kind": "api_key"})
    r = admin_client.patch("/api/org/secrets/MY_KEY", json={"value": "newvalueABCD"})
    assert r.status_code == 200
    assert r.json()["secret"]["last4"] == "ABCD"


def test_rotate_unknown_404(admin_mod, admin_client, monkeypatch):
    _login(admin_mod, admin_client, monkeypatch)
    _make_org(admin_client)
    r = admin_client.patch("/api/org/secrets/GHOST", json={"value": "x"})
    assert r.status_code == 404


# ── delete ────────────────────────────────────────────────────────────────────────────────────
def test_delete_removes_secret(admin_mod, admin_client, monkeypatch):
    _login(admin_mod, admin_client, monkeypatch)
    _make_org(admin_client)
    admin_client.post("/api/org/secrets", json={"name": "TO_DEL", "value": "abcd1234", "kind": "api_key"})
    r = admin_client.delete("/api/org/secrets/TO_DEL")
    assert r.status_code == 204
    assert admin_client.get("/api/org/secrets").json()["secrets"] == []


def test_delete_unknown_404(admin_mod, admin_client, monkeypatch):
    _login(admin_mod, admin_client, monkeypatch)
    _make_org(admin_client)
    r = admin_client.delete("/api/org/secrets/GHOST")
    assert r.status_code == 404


# ── ref ──────────────────────────────────────────────────────────────────────────────────────
def test_ref_returns_name_and_kind(admin_mod, admin_client, monkeypatch):
    _login(admin_mod, admin_client, monkeypatch)
    _make_org(admin_client)
    admin_client.post("/api/org/secrets", json={"name": "DB_PASS", "value": "p@ssword99", "kind": "password"})
    r = admin_client.get("/api/org/secrets/DB_PASS/ref")
    assert r.status_code == 200
    assert r.json() == {"name": "DB_PASS", "kind": "password"}


def test_ref_accessible_to_member(member_mod, member_client, admin_mod, admin_client, monkeypatch):
    # Admin creates the secret; member can read its ref (used by project runners)
    _login(admin_mod, admin_client, monkeypatch)
    _make_org(admin_client)
    admin_client.post("/api/org/secrets", json={"name": "API_KEY", "value": "zzzz9999", "kind": "api_key"})
    _login(member_mod, member_client, monkeypatch)
    r = member_client.get("/api/org/secrets/API_KEY/ref")
    assert r.status_code == 200


def test_ref_unknown_404(admin_mod, admin_client, monkeypatch):
    _login(admin_mod, admin_client, monkeypatch)
    _make_org(admin_client)
    assert admin_client.get("/api/org/secrets/NOEXIST/ref").status_code == 404
