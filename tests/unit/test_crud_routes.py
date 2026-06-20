"""CRUD endpoints (no-mock-data pass): admin tools/agents/clients/access CRUD + KB doc PATCH +
project rename/archive + run materials upload."""
import base64
import importlib
import os
import sys

import pytest
from fastapi.testclient import TestClient


def _load_app(tmp_path, monkeypatch, **env):
    monkeypatch.setenv("SF_RUNS_DIR", str(tmp_path))
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
             SF_AUTH_EMAILS="op@tenexity.ai", SF_AUTH_SECRET="test-secret")


@pytest.fixture()
def mod(tmp_path, monkeypatch):
    # op is staff (SF_ADMIN_EMAILS) AND can act as an org-admin for the org it creates.
    return _load_app(tmp_path, monkeypatch, SF_ADMIN_EMAILS="op@tenexity.ai", **_AUTH)


@pytest.fixture()
def client(mod):
    return TestClient(mod.app)


def _login(mod, client, monkeypatch, email="op@tenexity.ai"):
    from software_factory import auth as a
    monkeypatch.setattr(a, "_fetch_claims", lambda tok: {
        "aud": "cid-123.apps.googleusercontent.com", "email": email, "email_verified": "true"})
    return client.post("/api/auth/google", json={"credential": "t"})


# ── tools CRUD ───────────────────────────────────────────────────────────────────────────────
def test_tools_crud(mod, client, monkeypatch):
    _login(mod, client, monkeypatch)
    seeded = client.get("/api/admin/tools").json()["tools"]
    assert any(t["name"] == "Playwright MCP" for t in seeded)        # real datastore, seeded
    tid = client.post("/api/admin/tools", json={"name": "Custom", "type": "MCP"}).json()["tool"]["id"]
    assert client.patch(f"/api/admin/tools/{tid}",
                        json={"status": "connected"}).json()["tool"]["status"] == "connected"
    assert client.delete(f"/api/admin/tools/{tid}").status_code == 200
    assert not any(t.get("id") == tid for t in client.get("/api/admin/tools").json()["tools"])


# ── agents CRUD ──────────────────────────────────────────────────────────────────────────────
def test_agents_crud(mod, client, monkeypatch):
    _login(mod, client, monkeypatch)
    assert any(a["callsign"] == "ATLAS" for a in client.get("/api/admin/agents").json()["agents"])
    r = client.post("/api/admin/agents", json={"callsign": "nova", "name": "Novelist",
                                               "role": "nova", "model": "m"})
    assert r.status_code == 200 and r.json()["agent"]["callsign"] == "NOVA"
    assert client.post("/api/admin/agents", json={"callsign": "nova", "name": "dup"}).status_code == 409
    assert client.patch("/api/admin/agents/NOVA",
                        json={"model": "m2"}).json()["agent"]["model"] == "m2"
    assert client.delete("/api/admin/agents/NOVA").status_code == 200
    assert client.get("/api/admin/agents/NOVA").status_code == 404


# ── clients CRUD ─────────────────────────────────────────────────────────────────────────────
def test_clients_crud(mod, client, monkeypatch):
    _login(mod, client, monkeypatch)
    oid = client.post("/api/admin/clients", json={"name": "Northwind"}).json()["client"]["id"]
    assert client.patch(f"/api/admin/clients/{oid}",
                        json={"industry": "Distribution"}).json()["client"]["industry"] == "Distribution"
    assert client.delete(f"/api/admin/clients/{oid}").status_code == 200
    assert client.patch(f"/api/admin/clients/{oid}", json={"name": "x"}).status_code == 404


# ── access PATCH/DELETE ──────────────────────────────────────────────────────────────────────
def test_access_update_and_revoke(mod, client, monkeypatch):
    _login(mod, client, monkeypatch)
    client.post("/api/admin/access", json={"email": "u@x.com", "access_type": "org",
                                           "org_name": "X Co"})
    rows = client.patch("/api/admin/access/u@x.com", json={"status": "active"}).json()["users"]
    assert next(u for u in rows if u["email"] == "u@x.com")["status"] == "active"
    rows = client.delete("/api/admin/access/u@x.com").json()["users"]
    assert not any(u["email"] == "u@x.com" for u in rows)


# ── KB doc PATCH (rename/retag) ──────────────────────────────────────────────────────────────
def test_kb_doc_patch(mod, client, monkeypatch):
    _login(mod, client, monkeypatch)
    client.post("/api/org", json={"name": "Acme"})
    doc = client.post("/api/org/docs", json={"name": "a.pdf", "tag": "Old",
                                             "data_b64": base64.b64encode(b"x").decode()}).json()["doc"]
    upd = client.patch(f"/api/org/docs/{doc['id']}", json={"tag": "New"}).json()["doc"]
    assert upd["tag"] == "New" and upd["name"] == "a.pdf"


# ── project rename / archive / materials ─────────────────────────────────────────────────────
def test_project_rename_and_archive(mod, client, monkeypatch):
    _login(mod, client, monkeypatch)
    monkeypatch.setattr(mod.console, "project_owner", lambda rid: "op@tenexity.ai")
    monkeypatch.setattr(mod.console, "rename_project",
                        lambda rid, name=None, description=None, scope=None: {"project_id": rid, "name": name})
    monkeypatch.setattr(mod.console, "set_archived", lambda rid, a: a)
    assert client.patch("/api/projects/project-x", json={"name": "Renamed"}).json()["name"] == "Renamed"
    assert client.delete("/api/projects/project-x").json() == {"project_id": "project-x", "archived": True}


def test_run_material_upload(mod, client, monkeypatch):
    _login(mod, client, monkeypatch)
    monkeypatch.setattr(mod.console, "project_owner", lambda rid: "op@tenexity.ai")
    monkeypatch.setattr(mod.console, "artifacts", lambda rid: [])
    r = client.post("/api/projects/project-z/materials", json={
        "name": "spec.pdf", "data_b64": base64.b64encode(b"hello").decode()})
    assert r.status_code == 200
    up = r.json()["uploaded"]
    assert any(m["name"] == "spec.pdf" and m["kind"] == "pdf" for m in up)
    assert all(m.get("id") for m in up)        # stable id for the scope-toggle


def test_project_scope_edit_wires_through(mod, client, monkeypatch):
    _login(mod, client, monkeypatch)
    monkeypatch.setattr(mod.console, "project_owner", lambda pid: "op@tenexity.ai")
    monkeypatch.setattr(mod.console, "rename_project",
                        lambda pid, name=None, description=None, scope=None: {
                            "project_id": pid, "scope": scope or []})
    r = client.patch("/api/projects/project-x", json={"scope": ["Quoting", "Pricing"]})
    assert r.status_code == 200 and r.json()["scope"] == ["Quoting", "Pricing"]


def test_material_scope_toggle_moves_to_org_kb(mod, client, monkeypatch):
    _login(mod, client, monkeypatch)
    client.post("/api/org", json={"name": "Acme"})        # op gets an org
    monkeypatch.setattr(mod.console, "project_owner", lambda pid: "op@tenexity.ai")
    monkeypatch.setattr(mod.console, "artifacts", lambda pid: [])
    up = client.post("/api/projects/project-z/materials", json={
        "name": "spec.pdf", "data_b64": base64.b64encode(b"x").decode()}).json()["uploaded"]
    mid = up[0]["id"]
    docs = client.patch(f"/api/projects/project-z/materials/{mid}", json={"scope": "org"}).json()
    assert all(m["id"] != mid for m in docs["uploaded"])          # gone from the project
    assert any(d["id"] == mid for d in client.get("/api/org/docs").json()["docs"])  # now in org KB
