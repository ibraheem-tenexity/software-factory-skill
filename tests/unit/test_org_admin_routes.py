"""Org Admin backend routes (PRD §2.3): knowledge base, team & access, usage & billing.

Auth-enabled TestClient (org endpoints resolve the org from the session, so they need a real
logged-in user). The default user here is an ADMIN (seeded with role 'admin') so write routes are
exercised; a member-only fixture guards the admin gate.
"""
import base64
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
    mod.users.upsert("op@tenexity.ai", "admin")   # org-admin → write routes exercised
    return mod


@pytest.fixture()
def admin_client(admin_mod):
    return TestClient(admin_mod.app, base_url="https://testserver")


@pytest.fixture()
def member_mod(tmp_path, monkeypatch):
    mod = _load_app(tmp_path, monkeypatch, **_AUTH)
    mod.users.upsert("op@tenexity.ai", "member")   # op is a member
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
    return client.post("/api/org", json={"name": name}).json()["org"]["id"]


# ── knowledge base ──────────────────────────────────────────────────────────────────────────
def test_docs_404_without_org(admin_mod, admin_client, monkeypatch):
    _login(admin_mod, admin_client, monkeypatch)
    assert admin_client.get("/api/org/docs").status_code == 404


def test_upload_list_use_delete_doc(admin_mod, admin_client, monkeypatch):
    _login(admin_mod, admin_client, monkeypatch)
    _make_org(admin_client)
    data = base64.b64encode(b"hello").decode()
    r = admin_client.post("/api/org/docs", json={
        "name": "pricing.xlsx", "tag": "Price book", "content_type": "text/plain",
        "data_b64": data})
    assert r.status_code == 200
    doc = r.json()["doc"]
    assert doc["name"] == "pricing.xlsx" and doc["tag"] == "Price book"
    assert doc["kind"] == "xlsx" and doc["size_bytes"] == 5 and doc["used_count"] == 0

    docs = admin_client.get("/api/org/docs").json()["docs"]
    assert [d["name"] for d in docs] == ["pricing.xlsx"]

    r2 = admin_client.post(f"/api/org/docs/{doc['id']}/use", json={"project_id": "project-1"})
    assert r2.status_code == 200 and r2.json()["used_count"] == 1

    assert admin_client.delete(f"/api/org/docs/{doc['id']}").status_code == 200
    assert admin_client.get("/api/org/docs").json()["docs"] == []


def test_upload_requires_name(admin_mod, admin_client, monkeypatch):
    _login(admin_mod, admin_client, monkeypatch)
    _make_org(admin_client)
    r = admin_client.post("/api/org/docs", json={"name": "  ", "data_b64": ""})
    assert r.status_code == 400


def test_member_cannot_upload_doc(member_mod, member_client, monkeypatch):
    _login(member_mod, member_client, monkeypatch)
    r = member_client.post("/api/org/docs", json={"name": "x.pdf", "data_b64": ""})
    assert r.status_code == 403          # admin-gated


# ── team & access ───────────────────────────────────────────────────────────────────────────
def test_members_list_invite_patch_remove(admin_mod, admin_client, monkeypatch):
    _login(admin_mod, admin_client, monkeypatch)
    _make_org(admin_client)
    members = admin_client.get("/api/org/members").json()["members"]
    assert any(m["email"] == "op@tenexity.ai" and m["you"] for m in members)

    r = admin_client.post("/api/org/members", json={
        "email": "maya@acme.com", "role": "member", "designation": "Operations"})
    assert r.status_code == 200
    assert "maya@acme.com" in [m["email"] for m in r.json()["members"]]

    r2 = admin_client.patch("/api/org/members/maya@acme.com", json={"designation": "Sales"})
    assert r2.status_code == 200
    maya = next(m for m in r2.json()["members"] if m["email"] == "maya@acme.com")
    assert maya["designation"] == "Sales" and not maya["you"]

    assert admin_client.delete("/api/org/members/maya@acme.com").status_code == 200
    assert "maya@acme.com" not in [
        m["email"] for m in admin_client.get("/api/org/members").json()["members"]]


def test_member_cannot_invite(member_mod, member_client, monkeypatch):
    _login(member_mod, member_client, monkeypatch)
    r = member_client.post("/api/org/members", json={"email": "x@y.com"})
    assert r.status_code == 403


# ── usage & billing ─────────────────────────────────────────────────────────────────────────
def test_billing_set_plan_then_usage_reads_it(admin_mod, admin_client, monkeypatch):
    _login(admin_mod, admin_client, monkeypatch)
    _make_org(admin_client)
    r = admin_client.patch("/api/org/billing", json={"plan": "Team", "monthly_budget_cap": 120.0})
    assert r.status_code == 200 and r.json() == {"plan": "Team", "monthly_budget_cap": 120.0}
    u = admin_client.get("/api/org/usage").json()
    assert u["plan"] == "Team" and u["monthly_budget_cap"] == 120.0
    assert u["total_projects"] == 0 and u["by_project"] == []


def test_usage_rolls_up_only_member_runs(admin_mod, admin_client, monkeypatch):
    _login(admin_mod, admin_client, monkeypatch)
    _make_org(admin_client)
    monkeypatch.setattr(admin_mod.console, "list_projects", lambda owner=None: [
        {"project_id": "r1", "name": "AP matching", "spent_usd": 5.0, "owner": "op@tenexity.ai",
         "budget_stopped": False, "held": False, "deploy_url": ""},
        {"project_id": "r2", "name": "Stranger's", "spent_usd": 9.0, "owner": "stranger@x.com",
         "budget_stopped": False, "held": False, "deploy_url": ""},
    ])
    u = admin_client.get("/api/org/usage").json()
    assert u["total_projects"] == 1                       # stranger's run excluded
    assert [p["name"] for p in u["by_project"]] == ["AP matching"]
    assert u["spent"] == 5.0


def test_member_cannot_set_billing(member_mod, member_client, monkeypatch):
    _login(member_mod, member_client, monkeypatch)
    r = member_client.patch("/api/org/billing", json={"plan": "Team"})
    assert r.status_code == 403
