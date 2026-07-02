"""HTTP routing of the console server (FastAPI app in console/app.py).

Ported from the stdlib-server tests to FastAPI's TestClient. Originals preserved:
- the page must serve regardless of query string (scar: '/?run=project-1e17ea6a' returned a JSON 404
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
    monkeypatch.setenv("SF_PROJECTS_DIR", str(tmp_path))
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
    return TestClient(app_mod.app, base_url="https://testserver")


def test_root_serves_console_html(client):
    r = client.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]


def test_run_restore_link_serves_console_html_not_404(client):
    # the exact URL attach() writes via history.replaceState — reload must restore the run view
    r = client.get("/?run=project-1e17ea6a")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert "Software Factory" in r.text


def test_api_version_open_and_reports_sha(client, monkeypatch):
    # /api/version is open (no auth) and returns the running build's git SHA (TEN-151).
    monkeypatch.setenv("SF_GIT_SHA", "a1b2c3d4e5f60718293a4b5c6d7e8f9001122334")
    r = client.get("/api/version")
    assert r.status_code == 200
    body = r.json()
    assert body["sha"] == "a1b2c3d4e5f60718293a4b5c6d7e8f9001122334"
    assert body["short"] == "a1b2c3d"
    assert set(body) >= {"sha", "short", "dirty"}


@pytest.fixture()
def auth_mod(tmp_path, monkeypatch):
    mod = _load_app(
        tmp_path, monkeypatch,
        SF_GOOGLE_CLIENT_ID="cid-123.apps.googleusercontent.com",
        SF_SESSION_SECRET="test-secret",
    )
    mod.users.upsert("op@tenexity.ai", "member")   # op is a member (no platform-admin role)
    return mod


@pytest.fixture()
def auth_client(auth_mod):
    return TestClient(auth_mod.app, base_url="https://testserver")


def test_auth_enabled_root_serves_spa_to_unauthed(auth_mod, auth_client, monkeypatch):
    # React-only: root always serves the SPA bundle, even auth-on + unauthed — the React app gates
    # login itself (via /api/auth/config + /api/me, rendering its own LoginScreen on 401). There is
    # no server-rendered login page anymore.
    monkeypatch.setattr(auth_mod.state, "_index_html", lambda: b"<div id='root'></div><!--SPA-->")
    r = auth_client.get("/")
    assert r.status_code == 200
    assert "SPA" in r.text
    assert "accounts.google.com" not in r.text       # no server-rendered Google sign-in page


def test_auth_enabled_api_requires_session(auth_client):
    r = auth_client.get("/api/projects")
    assert r.status_code == 401


def _login(auth_mod, client, monkeypatch, email="op@tenexity.ai"):
    from software_factory import auth as auth_mod_
    monkeypatch.setattr(auth_mod_, "verify_google_id_token",
                        lambda tok: {"sub": "sub-" + email, "email": email, "email_verified": True})
    return client.post("/api/auth/google", json={"credential": "goog-token"})


def test_google_login_sets_cookie_and_opens_console(auth_mod, auth_client, monkeypatch):
    monkeypatch.setattr(auth_mod.state, "_index_html", lambda: b"<div id='root'></div><!--SPA-->")
    r = _login(auth_mod, auth_client, monkeypatch)
    assert r.status_code == 200
    cookie = r.headers.get("set-cookie", "")
    assert "sf_session=" in cookie and "HttpOnly" in cookie
    # TestClient persists the cookie on its jar → subsequent requests are authed.
    r2 = auth_client.get("/")
    assert r2.status_code == 200 and "SPA" in r2.text
    r3 = auth_client.get("/api/projects")
    assert r3.status_code == 200


def test_google_login_rejected_for_unallowed_email(auth_mod, auth_client, monkeypatch):
    r = _login(auth_mod, auth_client, monkeypatch, email="evil@example.com")
    assert r.status_code == 403


def test_run_scoped_route_forbidden_for_non_owner(auth_mod, auth_client, monkeypatch):
    # op@tenexity.ai is a *member* here (seeded with role 'member') → may only see runs it owns.
    _login(auth_mod, auth_client, monkeypatch)
    monkeypatch.setattr(auth_mod.console, "project_exists", lambda rid: True)
    monkeypatch.setattr(auth_mod.console, "project_owner", lambda rid: "someone-else@tenexity.ai")
    r = auth_client.get("/api/projects/project-deadbeef")
    assert r.status_code == 403


def test_chat_threads_viewer_role_to_concierge(auth_mod, auth_client, monkeypatch):
    # A member's chat must carry role='member' (not the default 'admin') so the concierge's
    # run-scoped tools enforce ownership. Regression for the FastAPI port dropping role=.
    import json as _json
    _login(auth_mod, auth_client, monkeypatch)          # op@tenexity.ai = member (seeded role 'member')
    captured = {}

    class _FakeRunner:
        async def handle_message_streamed(self, project_id, message, files, images, **kw):
            captured.update(kw)
            yield _json.dumps({"type": "done", "project_id": "project-abcdef12", "messages": []}) + "\n"

    monkeypatch.setattr(auth_mod.state, "_chat_runner", _FakeRunner())
    r = auth_client.post("/api/chat", json={"message": "build me an app"})
    assert r.status_code == 200
    assert captured.get("role") == "member"
    assert captured.get("owner") == "op@tenexity.ai"


def test_chat_timeout_yields_error_event(auth_mod, auth_client, monkeypatch):
    # If handle_message_streamed stalls past the deadline the stream emits a NDJSON error event.
    # The HTTP status stays 200 (streaming started); the error is in the body.
    import asyncio, json as _json
    _login(auth_mod, auth_client, monkeypatch)

    class _StallingRunner:
        async def handle_message_streamed(self, *a, **kw):
            await asyncio.sleep(9999)
            yield ""  # unreachable; marks this as an async generator

    monkeypatch.setattr(auth_mod.state, "_chat_runner", _StallingRunner())
    import console.routers.chat as _chat_mod
    monkeypatch.setattr(_chat_mod, "_CHAT_TIMEOUT", 0.01)
    r = auth_client.post("/api/chat", json={"message": "stall"})
    assert r.status_code == 200
    lines = [l for l in r.text.split("\n") if l.strip()]
    assert lines, "expected at least one NDJSON line"
    evt = _json.loads(lines[-1])
    assert evt["type"] == "error"
    assert "timed out" in evt["detail"]


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


def test_auth_config_public_when_disabled(client):
    # The SPA reads /api/auth/config on boot to decide whether to gate. Auth off (dev/test) →
    # enabled false, empty client id, and the route is reachable without a session.
    r = client.get("/api/auth/config")
    assert r.status_code == 200
    assert r.json() == {"enabled": False, "client_id": ""}


def test_auth_config_public_and_returns_client_id_when_enabled(auth_client):
    # Public (no session) so the static bundle can render the Google button; returns the
    # OAuth web client id (already public — it's in the GIS button) and enabled=true.
    r = auth_client.get("/api/auth/config")
    assert r.status_code == 200
    assert r.json() == {"enabled": True, "client_id": "cid-123.apps.googleusercontent.com"}


def test_me_open_when_auth_disabled(client):
    # Backs the SPA's disabled-path: auth off ⇒ /api/me is 200 admin ⇒ LoginScreen never shows.
    # No user row when auth is off (email None) → name None, is_internal True (admin operator).
    r = client.get("/api/me")
    assert r.status_code == 200
    assert r.json() == {"email": None, "role": "admin", "name": None, "is_internal": True, "auth": False}


def test_artifact_viewer_served_to_authed_user(auth_mod, auth_client, monkeypatch):
    from software_factory import auth as a
    monkeypatch.setattr(a, "verify_google_id_token",
                        lambda tok: {"sub": "sub-op", "email": "op@tenexity.ai",
                                     "email_verified": True})
    auth_client.post("/api/auth/google", json={"credential": "t"})
    monkeypatch.setattr(auth_mod.state, "_artifact_viewer_html",
                        lambda: b"<artifact-viewer-spa>")
    r = auth_client.get("/ArtifactViewer.html")
    assert r.status_code == 200
    assert b"artifact-viewer-spa" in r.content


def test_artifact_viewer_redirects_unauthenticated(auth_mod, auth_client, monkeypatch):
    r = auth_client.get("/ArtifactViewer.html", follow_redirects=False)
    assert r.status_code == 303


def test_create_draft_rejects_empty_name(client):
    assert client.post("/api/drafts", json={}).status_code == 400
    assert client.post("/api/drafts", json={"project_name": ""}).status_code == 400
    assert client.post("/api/drafts", json={"project_name": "   "}).status_code == 400


def test_create_draft_requires_real_name(client):
    r = client.post("/api/drafts", json={"project_name": "Quote-to-Epicor"})
    assert r.status_code == 200 and r.json()["project_id"].startswith("project-")


def test_create_draft_then_patch_composes_description(client):
    # Option C onboarding: form eagerly creates a draft, then write-throughs project fields.
    rid = client.post("/api/drafts", json={"project_name": "Quote-to-Epicor"}).json()["project_id"]
    assert rid.startswith("project-")
    r = client.patch(f"/api/projects/{rid}/draft", json={
        "name": "Quote-to-Epicor", "goal": "Replace the manual quoting spreadsheet.",
        "scope": ["Quoting / RFQ", "Pricing & approvals"]})
    assert r.status_code == 200
    body = r.json()
    assert body["description"] == ("Replace the manual quoting spreadsheet.\n\n"
                                   "Scope of work: Quoting / RFQ, Pricing & approvals.")
    assert body["brief"]["goals"] == "Replace the manual quoting spreadsheet."


def test_get_draft_rehydrates_intake_fields(client):
    # Resume an existing draft: GET /draft returns the fields to refill the onboarding form (read
    # counterpart to PATCH /draft) — no new draft minted.
    rid = client.post("/api/drafts", json={"project_name": "Quote-to-Epicor"}).json()["project_id"]
    client.patch(f"/api/projects/{rid}/draft", json={
        "name": "Quote-to-Epicor", "goal": "Replace the manual quoting spreadsheet.",
        "scope": ["Quoting / RFQ"]})
    d = client.get(f"/api/projects/{rid}/draft").json()
    assert d["name"] == "Quote-to-Epicor" and d["goal"] == "Replace the manual quoting spreadsheet."
    assert d["scope"] == ["Quoting / RFQ"] and "description" in d and "brief" in d and "coverage" in d


def test_get_draft_404_on_unknown_pid(client):
    assert client.get("/api/projects/project-deadbeef/draft").status_code == 404


def test_attach_to_draft_endpoint(client):
    rid = client.post("/api/drafts", json={"project_name": "Attach Test"}).json()["project_id"]
    r = client.post(f"/api/projects/{rid}/attach", json={"files": []})
    assert r.status_code == 200 and r.json() == {"attached": []}


def test_draft_writethrough_404_on_unknown_pid(client):
    # Unknown pid → 404 at authorize_project (never materializes a dir).
    for path, payload in [("/draft", {"goal": "x"}), ("/attach", {"files": []}), ("/promote", {})]:
        method = client.patch if path == "/draft" else client.post
        r = method(f"/api/projects/project-deadbeef{path}", json=payload)
        assert r.status_code == 404, path


def test_promote_endpoint_wires_to_console(client, app_mod, monkeypatch):
    # The handoff button calls POST /promote → console.promote_draft. Stub promote to avoid a real
    # Stage-1 launch; assert the endpoint shape.
    rid = client.post("/api/drafts", json={"project_name": "Promote Test"}).json()["project_id"]
    monkeypatch.setattr(app_mod.console, "promote_draft",
                        lambda r, description="", target="railway": r)
    res = client.post(f"/api/projects/{rid}/promote", json={"target": "railway"})
    assert res.status_code == 200 and res.json() == {"project_id": rid, "status": "started"}


def test_stop_endpoint_wires_to_console(client, app_mod, monkeypatch):
    # POST /stop → console.stop_project; stub it to avoid a real run, assert the endpoint shape.
    monkeypatch.setattr(app_mod.console, "project_exists", lambda pid: True)
    monkeypatch.setattr(app_mod.console, "stop_project",
                        lambda pid: {"project_id": pid, "phase": "stopped", "killed": False})
    res = client.post("/api/projects/project-1e17ea6a/stop")
    assert res.status_code == 200 and res.json()["phase"] == "stopped"


# ── local .env loading (console startup) ──────────────────────────────────────────────────────
def test_load_local_env_fills_gaps_but_does_not_override(tmp_path, monkeypatch):
    import console.app as app_mod
    envf = tmp_path / ".env"
    envf.write_text("SF_GAP_KEY=from_dotenv\nSF_EXISTING_KEY=from_dotenv\n")
    monkeypatch.setenv("SF_ENVIRONMENT", "dev")            # not 'test' → the loader runs
    monkeypatch.delenv("SF_GAP_KEY", raising=False)
    monkeypatch.setenv("SF_EXISTING_KEY", "from_process")
    app_mod._load_local_env(str(envf))
    assert os.environ["SF_GAP_KEY"] == "from_dotenv"       # absent var → filled from .env
    assert os.environ["SF_EXISTING_KEY"] == "from_process"  # override=False → process env wins


def test_load_local_env_skipped_under_test_suite(tmp_path, monkeypatch):
    import console.app as app_mod
    envf = tmp_path / ".env"
    envf.write_text("SF_SHOULD_NOT_LOAD=nope\n")
    monkeypatch.setenv("SF_ENVIRONMENT", "test")           # the suite guard
    monkeypatch.delenv("SF_SHOULD_NOT_LOAD", raising=False)
    app_mod._load_local_env(str(envf))
    assert "SF_SHOULD_NOT_LOAD" not in os.environ          # guard skipped the load entirely
