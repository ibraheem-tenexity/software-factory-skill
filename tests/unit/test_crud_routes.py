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
             SF_SESSION_SECRET="test-secret")


@pytest.fixture()
def mod(tmp_path, monkeypatch):
    # op is platform staff (role==admin AND is_internal via bootstrap) + org-admin of its own org.
    return _load_app(tmp_path, monkeypatch,
                     SF_BOOTSTRAP_ADMIN_EMAIL="op@tenexity.ai", **_AUTH)


@pytest.fixture()
def client(mod):
    return TestClient(mod.app, base_url="https://testserver")


@pytest.fixture(autouse=True)
def _fake_vault(monkeypatch):
    """SOF-81: tool keys are Vault-backed (Supabase pgsodium), which the local test Postgres
    doesn't have — mocked exactly like test_org_secrets_routes.py's _fake_vault. last4 is computed
    from the caller's own value in tools.py, so a deterministic fake UUID per call is enough."""
    import itertools
    from software_factory import tools as tools_mod
    counter = itertools.count(1)
    monkeypatch.setattr(tools_mod, "vault_store", lambda name, value: f"vault-uuid-{next(counter)}")
    monkeypatch.setattr(tools_mod, "vault_delete_many", lambda uuids: None)
    monkeypatch.setattr(tools_mod, "vault_retrieve_many", lambda vault_ids: {})


def _login(mod, client, monkeypatch, email="op@tenexity.ai"):
    from software_factory import auth as a
    monkeypatch.setattr(a, "verify_google_id_token",
                        lambda tok: {"sub": "sub-" + email, "email": email, "email_verified": True})
    return client.post("/api/auth/google", json={"credential": "t"})


# ── tools CRUD (SOF-81: name-keyed registry, config JSONB, vault-backed key) ───────────────────
def test_tools_crud(mod, client, monkeypatch):
    _login(mod, client, monkeypatch)
    # No code/create_all seeding — the real tool set only exists once migration 0013 has run
    # against this DB, which the test schema (create_all) never does. Empty is the honest baseline.
    assert client.get("/api/admin/tools").json()["tools"] == []

    created = client.post("/api/admin/tools", json={
        "name": "custom-tool", "config": {"kind": "api", "env_key": "CUSTOM_TOOL_KEY"},
        "attached_to": ["STAGE-1"],
    }).json()["tool"]
    assert created["name"] == "custom-tool"
    assert created["config"] == {"kind": "api", "env_key": "CUSTOM_TOOL_KEY"}
    assert created["attached_to"] == ["STAGE-1"]
    assert created["has_key"] is False and created["key_last4"] is None

    updated = client.patch("/api/admin/tools/custom-tool",
                           json={"config": {"kind": "api", "env_key": "CUSTOM_TOOL_KEY", "note": "v2"}}).json()["tool"]
    assert updated["config"]["note"] == "v2"

    keyed = client.put("/api/admin/tools/custom-tool/key", json={"value": "sk-test-abcd1234"}).json()["tool"]
    assert keyed["has_key"] is True and keyed["key_last4"] == "1234"

    unkeyed = client.delete("/api/admin/tools/custom-tool/key").json()["tool"]
    assert unkeyed["has_key"] is False and unkeyed["key_last4"] is None

    assert client.delete("/api/admin/tools/custom-tool").status_code == 200
    assert client.get("/api/admin/tools").json()["tools"] == []


# ── agents CRUD ──────────────────────────────────────────────────────────────────────────────
def test_agents_crud(mod, client, monkeypatch):
    _login(mod, client, monkeypatch)
    assert any(a["callsign"] == "STAGE-1" for a in client.get("/api/admin/agents").json()["agents"])
    r = client.post("/api/admin/agents", json={"callsign": "nova", "name": "Novelist",
                                               "role": "nova", "model": "m"})
    assert r.status_code == 200 and r.json()["agent"]["callsign"] == "NOVA"
    assert client.post("/api/admin/agents", json={"callsign": "nova", "name": "dup"}).status_code == 409
    # system_agents' real column is model_id (post agents/runtime_agents split) — the API mirrors
    # the column name verbatim, it doesn't alias back to the request body's `model` key.
    assert client.patch("/api/admin/agents/NOVA",
                        json={"model": "m2"}).json()["agent"]["model_id"] == "m2"
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
    # revoke = disable (status→disabled + token_version bump): the row stays as an audit record,
    # the user can no longer sign in and any live cookie is invalidated on its next request.
    rows = client.delete("/api/admin/access/u@x.com").json()["users"]
    assert next(u for u in rows if u["email"] == "u@x.com")["status"] == "disabled"


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
    monkeypatch.setattr(mod.console, "project_exists", lambda rid: True)
    monkeypatch.setattr(mod.console, "project_owner", lambda rid: "op@tenexity.ai")
    monkeypatch.setattr(mod.console, "rename_project",
                        lambda rid, name=None, description=None, scope=None, summary=None: {"project_id": rid, "name": name})
    monkeypatch.setattr(mod.console, "set_archived", lambda rid, a: a)
    assert client.patch("/api/projects/project-x", json={"name": "Renamed"}).json()["name"] == "Renamed"
    assert client.delete("/api/projects/project-x").json() == {"project_id": "project-x", "archived": True}


def test_run_material_upload(mod, client, monkeypatch, stub_maybe_ingest_async):
    _login(mod, client, monkeypatch)
    monkeypatch.setattr(mod.console, "project_exists", lambda rid: True)
    monkeypatch.setattr(mod.console, "project_owner", lambda rid: "op@tenexity.ai")
    monkeypatch.setattr(mod.console, "artifacts", lambda rid: [])
    r = client.post("/api/projects/project-z/materials", json={
        "name": "spec.pdf", "data_b64": base64.b64encode(b"hello").decode()})
    assert r.status_code == 200
    up = r.json()["uploaded"]
    assert any(m["name"] == "spec.pdf" and m["kind"] == "pdf" for m in up)
    assert all(m.get("id") for m in up)        # stable id for the scope-toggle
    # SOF-71: this route calls maybe_ingest_async with real content — confirms the conftest seam
    # actually intercepted it (real ingestion would otherwise spawn a genuine background thread).
    assert len(stub_maybe_ingest_async) == 1
    assert stub_maybe_ingest_async[0]["blob_id"] == up[0]["id"]


def test_project_scope_edit_wires_through(mod, client, monkeypatch):
    _login(mod, client, monkeypatch)
    monkeypatch.setattr(mod.console, "project_exists", lambda pid: True)
    monkeypatch.setattr(mod.console, "project_owner", lambda pid: "op@tenexity.ai")
    monkeypatch.setattr(mod.console, "rename_project",
                        lambda pid, name=None, description=None, scope=None, summary=None: {
                            "project_id": pid, "scope": scope or []})
    r = client.patch("/api/projects/project-x", json={"scope": ["Quoting", "Pricing"]})
    assert r.status_code == 200 and r.json()["scope"] == ["Quoting", "Pricing"]


def test_material_scope_toggle_moves_to_org_kb(mod, client, monkeypatch):
    _login(mod, client, monkeypatch)
    client.post("/api/org", json={"name": "Acme"})        # op gets an org
    monkeypatch.setattr(mod.console, "project_exists", lambda pid: True)
    monkeypatch.setattr(mod.console, "project_owner", lambda pid: "op@tenexity.ai")
    monkeypatch.setattr(mod.console, "artifacts", lambda pid: [])
    up = client.post("/api/projects/project-z/materials", json={
        "name": "spec.pdf", "data_b64": base64.b64encode(b"x").decode()}).json()["uploaded"]
    mid = up[0]["id"]
    docs = client.patch(f"/api/projects/project-z/materials/{mid}", json={"scope": "org"}).json()
    assert all(m["id"] != mid for m in docs["uploaded"])          # gone from the project
    assert any(d["id"] == mid for d in client.get("/api/org/docs").json()["docs"])  # now in org KB
