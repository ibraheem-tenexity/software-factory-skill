"""HTTP routing of the console server (FastAPI app in console/app.py).

Ported from the stdlib-server tests to FastAPI's TestClient. Originals preserved:
- the page must serve regardless of query string (scar: '/?run=run-1e17ea6a' returned a JSON 404
  when do_GET matched self.path verbatim, query string included);
- auth gate (login page vs console, 401 without session, Google login cookie, unallowed email 403).
Added: run-scoped ownership 403 + an SSE stream smoke.
"""
import importlib
import os
import sys

import pytest
from fastapi.testclient import TestClient


def _load_app(tmp_path, monkeypatch, **env):
    monkeypatch.setenv("SF_RUNS_DIR", str(tmp_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    import console.app as app_mod
    importlib.reload(app_mod)
    return app_mod


@pytest.fixture()
def app_mod(tmp_path, monkeypatch):
    return _load_app(tmp_path, monkeypatch)


@pytest.fixture()
def client(app_mod):
    # No `with` → lifespan (and the background poller) does not run, matching the old tests.
    return TestClient(app_mod.app)


def test_root_serves_console_html(client):
    r = client.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]


def test_run_restore_link_serves_console_html_not_404(client):
    # the exact URL attach() writes via history.replaceState — reload must restore the run view
    r = client.get("/?run=run-1e17ea6a")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert "Software Factory" in r.text


@pytest.fixture()
def auth_mod(tmp_path, monkeypatch):
    return _load_app(
        tmp_path, monkeypatch,
        SF_GOOGLE_CLIENT_ID="cid-123.apps.googleusercontent.com",
        SF_AUTH_EMAILS="op@tenexity.ai",
        SF_AUTH_SECRET="test-secret",
    )


@pytest.fixture()
def auth_client(auth_mod):
    return TestClient(auth_mod.app)


def test_auth_enabled_root_serves_login_not_console(auth_client):
    r = auth_client.get("/")
    assert r.status_code == 200
    assert "accounts.google.com" in r.text          # the Google sign-in page
    assert "cid-123" in r.text                       # client id injected
    assert "Factory Concierge" not in r.text         # console NOT exposed


def test_auth_enabled_api_requires_session(auth_client):
    r = auth_client.get("/api/runs")
    assert r.status_code == 401


def _login(auth_mod, client, monkeypatch, email="op@tenexity.ai"):
    from software_factory import auth as auth_mod_
    monkeypatch.setattr(auth_mod_, "_fetch_claims", lambda tok: {
        "aud": "cid-123.apps.googleusercontent.com", "email": email,
        "email_verified": "true"})
    return client.post("/api/auth/google", json={"credential": "goog-token"})


def test_google_login_sets_cookie_and_opens_console(auth_mod, auth_client, monkeypatch):
    r = _login(auth_mod, auth_client, monkeypatch)
    assert r.status_code == 200
    cookie = r.headers.get("set-cookie", "")
    assert "sf_session=" in cookie and "HttpOnly" in cookie
    # TestClient persists the cookie on its jar → subsequent requests are authed.
    r2 = auth_client.get("/")
    assert r2.status_code == 200 and "Factory Concierge" in r2.text
    r3 = auth_client.get("/api/runs")
    assert r3.status_code == 200


def test_google_login_rejected_for_unallowed_email(auth_mod, auth_client, monkeypatch):
    r = _login(auth_mod, auth_client, monkeypatch, email="evil@example.com")
    assert r.status_code == 403


def test_run_scoped_route_forbidden_for_non_owner(auth_mod, auth_client, monkeypatch):
    # op@tenexity.ai is a *member* here (no SF_ADMIN_EMAILS) → may only see runs it owns.
    _login(auth_mod, auth_client, monkeypatch)
    monkeypatch.setattr(auth_mod.console, "run_owner", lambda rid: "someone-else@tenexity.ai")
    r = auth_client.get("/api/runs/run-deadbeef")
    assert r.status_code == 403


def test_chat_threads_viewer_role_to_concierge(auth_mod, auth_client, monkeypatch):
    # A member's chat must carry role='member' (not the default 'admin') so the concierge's
    # run-scoped tools enforce ownership. Regression for the FastAPI port dropping role=.
    _login(auth_mod, auth_client, monkeypatch)          # op@tenexity.ai = member (no SF_ADMIN_EMAILS)
    captured = {}

    class _FakeRunner:
        async def handle_message(self, run_id, message, files, images, **kw):
            captured.update(kw)
            return ("run-abcdef12", [])

    monkeypatch.setattr(auth_mod, "_chat_runner", _FakeRunner())
    r = auth_client.post("/api/chat", json={"message": "build me an app"})
    assert r.status_code == 200
    assert captured.get("role") == "member"
    assert captured.get("owner") == "op@tenexity.ai"


def test_get_org_null_before_onboarding(auth_mod, auth_client, monkeypatch):
    # A freshly-logged-in user with no org on file → GET /api/org returns null (first-time path).
    _login(auth_mod, auth_client, monkeypatch)
    r = auth_client.get("/api/org")
    assert r.status_code == 200
    assert r.json() == {"org": None}


def test_post_then_get_org_roundtrip(auth_mod, auth_client, monkeypatch):
    # POST creates the org + links the user; GET then returns it (returning path thereafter).
    _login(auth_mod, auth_client, monkeypatch)
    r = auth_client.post("/api/org", json={
        "name": "Acme Industrial Supply", "industry": "Industrial Distribution",
        "sub_focus": ["MRO / maintenance"], "headcount": "51–200", "revenue": "$10M–$50M",
        "connected_systems": ["epicor"], "designation": "Ops Manager",
        "role_description": "runs quoting"})
    assert r.status_code == 200
    org = r.json()["org"]
    assert org["id"].startswith("org-")
    assert org["name"] == "Acme Industrial Supply"
    assert org["headcount"] == "51–200"            # band label verbatim, not a number
    assert org["connected_systems"] == ["epicor"]  # json list round-trips
    # The user is now linked → GET returns the same org, and the profile fields persisted.
    r2 = auth_client.get("/api/org")
    assert r2.json()["org"]["id"] == org["id"]
    u = auth_mod.users.get_user("op@tenexity.ai")
    assert u["org_id"] == org["id"] and u["designation"] == "Ops Manager"


def test_post_org_requires_name(auth_mod, auth_client, monkeypatch):
    _login(auth_mod, auth_client, monkeypatch)
    r = auth_client.post("/api/org", json={"name": "  "})
    assert r.status_code == 400


def test_patch_org_updates_fields(auth_mod, auth_client, monkeypatch):
    _login(auth_mod, auth_client, monkeypatch)
    auth_client.post("/api/org", json={"name": "Acme", "industry": "Distribution",
                                       "connected_systems": ["epicor"]})
    r = auth_client.patch("/api/org", json={"headcount": "201–1,000",
                                            "connected_systems": ["epicor", "salesforce"]})
    assert r.status_code == 200
    org = r.json()["org"]
    assert org["industry"] == "Distribution"        # untouched
    assert org["headcount"] == "201–1,000"           # patched
    assert org["connected_systems"] == ["epicor", "salesforce"]


def test_patch_org_404_without_org(auth_mod, auth_client, monkeypatch):
    _login(auth_mod, auth_client, monkeypatch)
    r = auth_client.patch("/api/org", json={"headcount": "11–50"})
    assert r.status_code == 404


def test_org_requires_session(auth_client):
    assert auth_client.get("/api/org").status_code == 401


def test_create_draft_then_patch_composes_description(client):
    # Option C onboarding: form eagerly creates a draft, then write-throughs project fields.
    rid = client.post("/api/drafts", json={"project_name": "Quote-to-Epicor"}).json()["run_id"]
    assert rid.startswith("run-")
    r = client.patch(f"/api/runs/{rid}/draft", json={
        "name": "Quote-to-Epicor", "goal": "Replace the manual quoting spreadsheet.",
        "scope": ["Quoting / RFQ", "Pricing & approvals"]})
    assert r.status_code == 200
    body = r.json()
    assert body["description"] == ("Replace the manual quoting spreadsheet.\n\n"
                                   "Scope of work: Quoting / RFQ, Pricing & approvals.")
    assert body["brief"]["goals"] == "Replace the manual quoting spreadsheet."


def test_attach_to_draft_endpoint(client):
    rid = client.post("/api/drafts", json={}).json()["run_id"]
    r = client.post(f"/api/runs/{rid}/attach", json={"files": []})
    assert r.status_code == 200 and r.json() == {"attached": []}


def test_draft_writethrough_409_on_non_draft(client):
    # PATCH/attach/promote refuse a non-draft (already promoted or nonexistent) run.
    for path, payload in [("/draft", {"goal": "x"}), ("/attach", {"files": []}), ("/promote", {})]:
        method = client.patch if path == "/draft" else client.post
        r = method(f"/api/runs/run-deadbeef{path}", json=payload)
        assert r.status_code == 409, path


def test_promote_endpoint_wires_to_console(client, app_mod, monkeypatch):
    # The handoff button calls POST /promote → console.promote_draft. Stub promote to avoid a real
    # Stage-1 launch; assert the endpoint shape.
    rid = client.post("/api/drafts", json={}).json()["run_id"]
    monkeypatch.setattr(app_mod.console, "promote_draft",
                        lambda r, description="", target="railway": r)
    res = client.post(f"/api/runs/{rid}/promote", json={"target": "railway"})
    assert res.status_code == 200 and res.json() == {"run_id": rid, "status": "started"}


def test_push_sse_delivers_to_registered_client(app_mod):
    # The SSE mechanic: _push_sse fans a message out to every queue registered for the run
    # (the stream endpoint registers one such queue; the poller + chat/deps handlers push).
    from software_factory.chat_store import ChatMessage
    q: list = []
    with app_mod._sse_lock:
        app_mod._sse_clients.setdefault("run-1e17ea6a", []).append(q)
    app_mod._push_sse("run-1e17ea6a", [ChatMessage(role="assistant", content="ping")])
    assert q and q[0].startswith("data: ") and "ping" in q[0] and q[0].endswith("\n\n")
