"""Project View §2.5 aggregate endpoints: GET /api/projects/{rid}/overview + /documents.

Wiring tests — console reads are monkeypatched to fixtures so this asserts the endpoint assembles
the contract correctly and enforces the authorize_project ownership gate.
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


def _wire(mod, monkeypatch, owner="op@tenexity.ai"):
    c = mod.console
    monkeypatch.setattr(c, "project_exists", lambda rid: True)
    monkeypatch.setattr(c, "project_owner", lambda rid: owner)
    monkeypatch.setattr(c, "status", lambda rid: {
        "owner": owner, "phase": "Build · stage 3", "stage": 3, "done": False, "deploy_url": "",
        "spent_usd": 4.2, "budget_ceiling": 30.0, "agents": {"running": 2}, "name": "Quote",
        "description": "d", "impl_model": "claude-opus-4-8"})
    monkeypatch.setattr(c, "tickets", lambda rid: {"tickets": [
        {"id": 7, "title": "Discount workflow", "status": "done"},
        {"id": 8, "title": "Pricing", "status": "open"}]})
    monkeypatch.setattr(c, "deployments", lambda rid: {"deployments": [
        {"service_name": "sf-project-x", "app": "web", "url": "https://x", "status": "live",
         "verified": 1}]})
    monkeypatch.setattr(c, "agents", lambda rid: [
        {"agent_id": "a1", "role": "opus", "model": "m", "status": "running",
         "ticket_id": 7, "cost_usd": 1.1}])
    monkeypatch.setattr(c, "artifacts", lambda rid: [
        {"title": "Arch", "path": "p", "kind": "plan", "agent": "architect", "ts": 1.0}])
    monkeypatch.setattr(c, "draft_project", lambda rid: {
        "name": "Quote", "goal": "automate", "scope": ["Quoting"], "description": "d"})
    monkeypatch.setattr(c, "project_created", lambda rid: 1718000000.0)
    monkeypatch.setattr(mod.users, "org_for_user", lambda e: {
        "name": "Acme", "industry": "Distribution", "connected_systems": ["epicor"]})
    monkeypatch.setattr(mod.blobs, "list_for", lambda scope, sid: [
        {"storage_key": "project-x/inputs/rfq.pdf", "size_bytes": 10,
         "content_type": "application/pdf", "created_at": 1.0}])


def test_overview_assembles_contract(auth_mod, auth_client, monkeypatch):
    _login(auth_mod, auth_client, monkeypatch)
    _wire(auth_mod, monkeypatch)
    j = auth_client.get("/api/projects/project-abc/overview").json()
    assert j["brief"]["goal"] == "automate" and j["brief"]["scope"] == ["Quoting"]
    assert j["brief"]["owner"] == "op@tenexity.ai" and j["brief"]["created"] == 1718000000.0
    assert j["build"]["pct"] == 50 and j["build"]["tickets_done"] == 1
    assert j["build"]["agents_working"] == 2 and j["build"]["spent_usd"] == 4.2
    kinds = {(s["kind"], s["label"]): s for s in j["services"]}
    assert ("Integration", "epicor") in kinds
    assert kinds[("Hosting", "sf-project-x")]["url"] == "https://x"
    assert ("LLM", "claude-opus-4-8") in kinds
    assert kinds[("Testing", "Playwright")]["status"] == "passed"   # verified deployment
    assert j["agents"][0]["task"] == "Discount workflow"
    assert j["org"]["name"] == "Acme" and j["org"]["connected_systems"] == ["epicor"]
    assert j["materials_count"] == 1 and j["produced_count"] == 1


def test_documents_lists_uploaded_and_produced(auth_mod, auth_client, monkeypatch):
    _login(auth_mod, auth_client, monkeypatch)
    _wire(auth_mod, monkeypatch)
    j = auth_client.get("/api/projects/project-abc/documents").json()
    assert j["uploaded"][0]["name"] == "rfq.pdf" and j["uploaded"][0]["kind"] == "pdf"
    assert j["produced"][0]["title"] == "Arch" and j["produced"][0]["kind"] == "plan"


# ── SOF-36/T3.3: Auto-summarize / Regenerate ────────────────────────────────────────────────────
# SOF-71: memory is always on now — the "404s when disabled" case no longer exists, deleted.

def test_summarize_404s_on_unknown_blob(auth_mod, auth_client, monkeypatch):
    _login(auth_mod, auth_client, monkeypatch)
    _wire(auth_mod, monkeypatch)
    monkeypatch.setattr(auth_mod.blobs, "get_blob", lambda bid: None)
    r = auth_client.post("/api/projects/project-abc/documents/999/summarize")
    assert r.status_code == 404


def test_summarize_404s_when_blob_belongs_to_a_different_project(auth_mod, auth_client, monkeypatch):
    # The blob exists, but not under THIS project — authorize_project only checks the {pid} in the
    # URL owns the project; the blob_id itself could belong to anyone without this extra check.
    _login(auth_mod, auth_client, monkeypatch)
    _wire(auth_mod, monkeypatch)
    monkeypatch.setattr(auth_mod.blobs, "get_blob",
                        lambda bid: {"id": bid, "scope": "project", "scope_id": "some-other-project"})
    r = auth_client.post("/api/projects/project-abc/documents/1/summarize")
    assert r.status_code == 404


def test_summarize_calls_ingest_blob_with_force_and_returns_documents(auth_mod, auth_client, monkeypatch):
    _login(auth_mod, auth_client, monkeypatch)
    _wire(auth_mod, monkeypatch)
    monkeypatch.setattr(auth_mod.blobs, "get_blob",
                        lambda bid: {"id": bid, "scope": "project", "scope_id": "project-abc"})
    calls = {}

    def fake_ingest_blob(blob_id, *, console, force=False, push_progress=None):
        calls["blob_id"] = blob_id
        calls["force"] = force
        return {"blob_id": blob_id, "status": "ready"}

    from software_factory.memory import ingest as memory_ingest
    monkeypatch.setattr(memory_ingest, "ingest_blob", fake_ingest_blob)
    r = auth_client.post("/api/projects/project-abc/documents/1/summarize")
    assert r.status_code == 200
    assert calls == {"blob_id": 1, "force": True}
    assert r.json()["uploaded"][0]["name"] == "rfq.pdf"   # still the full documents() payload


def test_summarize_502s_when_ingest_reports_failed(auth_mod, auth_client, monkeypatch):
    _login(auth_mod, auth_client, monkeypatch)
    _wire(auth_mod, monkeypatch)
    monkeypatch.setattr(auth_mod.blobs, "get_blob",
                        lambda bid: {"id": bid, "scope": "project", "scope_id": "project-abc"})

    from software_factory.memory import ingest as memory_ingest
    monkeypatch.setattr(memory_ingest, "ingest_blob",
                        lambda blob_id, **kw: {"blob_id": blob_id, "status": "failed", "error": "parse boom"})
    r = auth_client.post("/api/projects/project-abc/documents/1/summarize")
    assert r.status_code == 502


def test_overview_requires_session(auth_client):
    assert auth_client.get("/api/projects/project-abc/overview").status_code == 401


def test_overview_forbidden_for_non_owner(auth_mod, auth_client, monkeypatch):
    _login(auth_mod, auth_client, monkeypatch)
    monkeypatch.setattr(auth_mod.console, "project_exists", lambda rid: True)
    monkeypatch.setattr(auth_mod.console, "project_owner", lambda rid: "someone@else.com")
    assert auth_client.get("/api/projects/project-abc/overview").status_code == 403
