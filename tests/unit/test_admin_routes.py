"""Tenexity OS admin routes (PRD §3): /api/admin/* — staff-gated, cross-tenant."""
import importlib
import os
import sys

import pytest
from fastapi.testclient import TestClient


def _load_app(tmp_path, monkeypatch, **env):
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
             SF_AUTH_EMAILS="op@tenexity.ai", SF_AUTH_SECRET="test-secret")


@pytest.fixture()
def staff_mod(tmp_path, monkeypatch):
    mod = _load_app(tmp_path, monkeypatch, SF_ADMIN_EMAILS="op@tenexity.ai", **_AUTH)
    mod.users.set_profile("op@tenexity.ai", tenexity=True)   # platform staff = role==admin AND tenexity
    return mod


@pytest.fixture()
def staff_client(staff_mod):
    return TestClient(staff_mod.app)


@pytest.fixture()
def member_mod(tmp_path, monkeypatch):
    return _load_app(tmp_path, monkeypatch, **_AUTH)   # no SF_ADMIN_EMAILS → op is a non-staff member


@pytest.fixture()
def member_client(member_mod):
    return TestClient(member_mod.app)


@pytest.fixture()
def adminonly_mod(tmp_path, monkeypatch):
    # role==admin (via SF_ADMIN_EMAILS) but tenexity NOT set → must NOT reach Tenexity OS.
    return _load_app(tmp_path, monkeypatch, SF_ADMIN_EMAILS="op@tenexity.ai", **_AUTH)


@pytest.fixture()
def adminonly_client(adminonly_mod):
    return TestClient(adminonly_mod.app)


def _login(mod, client, monkeypatch, email="op@tenexity.ai"):
    from software_factory import auth as a
    monkeypatch.setattr(a, "_fetch_claims", lambda tok: {
        "aud": "cid-123.apps.googleusercontent.com", "email": email, "email_verified": "true"})
    return client.post("/api/auth/google", json={"credential": "t"})


def _enable_react(mod, monkeypatch):
    monkeypatch.setattr(mod, "_react_enabled", lambda: True)
    monkeypatch.setattr(mod, "_admin_html", lambda: b"<admin-spa>")


# ── /admin PAGE route is hard-gated (the live-exposure fix) ─────────────────────────────────────
def test_admin_page_redirects_unauthenticated(staff_mod, staff_client, monkeypatch):
    _enable_react(staff_mod, monkeypatch)
    r = staff_client.get("/admin", follow_redirects=False)      # no session
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert b"admin-spa" not in r.content                         # portal HTML NOT served


def test_admin_page_forbidden_for_member(member_mod, member_client, monkeypatch):
    _enable_react(member_mod, monkeypatch)
    _login(member_mod, member_client, monkeypatch)               # op = plain member here
    assert member_client.get("/admin").status_code == 403


def test_admin_page_forbidden_for_admin_without_tenexity(adminonly_mod, adminonly_client, monkeypatch):
    _enable_react(adminonly_mod, monkeypatch)
    _login(adminonly_mod, adminonly_client, monkeypatch)         # role admin, NO tenexity flag
    assert adminonly_client.get("/admin").status_code == 403


def test_admin_page_served_to_staff(staff_mod, staff_client, monkeypatch):
    _enable_react(staff_mod, monkeypatch)
    _login(staff_mod, staff_client, monkeypatch)                 # role admin AND tenexity
    r = staff_client.get("/admin")
    assert r.status_code == 200 and b"admin-spa" in r.content


def test_admin_api_forbidden_for_admin_without_tenexity(adminonly_mod, adminonly_client, monkeypatch):
    # require_staff strict bar: env-admin alone (no tenexity) must NOT reach cross-tenant data.
    _login(adminonly_mod, adminonly_client, monkeypatch)
    assert adminonly_client.get("/api/admin/overview").status_code == 403


# ── staff gate ────────────────────────────────────────────────────────────────────────────────
def test_admin_requires_session(staff_client):
    assert staff_client.get("/api/admin/overview").status_code == 401


def test_admin_forbidden_for_non_staff_member(member_mod, member_client, monkeypatch):
    _login(member_mod, member_client, monkeypatch)        # op is a member here, not staff
    assert member_client.get("/api/admin/overview").status_code == 403


def test_overview_ok_for_staff(staff_mod, staff_client, monkeypatch):
    _login(staff_mod, staff_client, monkeypatch)
    j = staff_client.get("/api/admin/overview").json()
    assert set(j) == {"pulse", "active_projects", "agents"}
    assert j["pulse"]["avg_friction"] is None           # not tracked — never fabricated
    assert "tenants" in j["pulse"] and "today_burn" in j["pulse"]


# ── clients / projects ──────────────────────────────────────────────────────────────────────────
def test_clients_rolls_up_org(staff_mod, staff_client, monkeypatch):
    _login(staff_mod, staff_client, monkeypatch)
    oid = staff_mod.users.create_org("Acme Industrial", by="op@tenexity.ai")
    staff_mod.users.invite_member("m@acme.com", oid, role="member", by="op@tenexity.ai")
    monkeypatch.setattr(staff_mod.console, "list_projects", lambda owner=None: [
        {"project_id": "r1", "owner": "m@acme.com", "spent_usd": 3.0, "updated": 5}])
    clients = staff_client.get("/api/admin/clients").json()["clients"]
    acme = next(c for c in clients if c["name"] == "Acme Industrial")
    assert acme["projects"] == 1 and acme["spend"] == 3.0 and acme["initials"] == "AI"


def test_projects_mode_filter(staff_mod, staff_client, monkeypatch):
    _login(staff_mod, staff_client, monkeypatch)
    monkeypatch.setattr(staff_mod.console, "list_projects", lambda owner=None: [
        {"project_id": "r1", "name": "Real", "owner": "a@x.com", "spent_usd": 1.0, "updated": 1,
         "stage": 3, "phase": "build", "runtime": "claude", "is_demo": False},
        {"project_id": "r2", "name": "Demo", "owner": "a@x.com", "spent_usd": 0.0, "updated": 2,
         "stage": 1, "phase": "draft", "runtime": "opencode", "is_demo": True}])
    real = staff_client.get("/api/admin/projects?mode=real").json()["projects"]
    assert [p["name"] for p in real] == ["Real"]


def test_set_demo_toggle(staff_mod, staff_client, monkeypatch):
    _login(staff_mod, staff_client, monkeypatch)
    monkeypatch.setattr(staff_mod.console, "set_demo", lambda rid, d: d)
    r = staff_client.patch("/api/admin/projects/project-x", json={"is_demo": True})
    assert r.status_code == 200 and r.json() == {"project_id": "project-x", "is_demo": True}


# ── agents + editable prompt ────────────────────────────────────────────────────────────────────
def test_agents_roster_has_curated_callsigns(staff_mod, staff_client, monkeypatch):
    _login(staff_mod, staff_client, monkeypatch)
    agents = staff_client.get("/api/admin/agents").json()["agents"]
    signs = {a["callsign"] for a in agents}
    assert {"ATLAS", "HORIZON", "CHROMA"} <= signs


def test_agent_prompt_edit_is_saved_but_not_applied(staff_mod, staff_client, monkeypatch):
    _login(staff_mod, staff_client, monkeypatch)
    r = staff_client.patch("/api/admin/agents/ATLAS/prompt", json={"prompt": "be terse"})
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == 1 and body["applied"] is False     # honest: stored, not applied
    detail = staff_client.get("/api/admin/agents/ATLAS").json()
    assert detail["prompt"] == "be terse" and detail["prompt_applied"] is False
    assert detail["prompt_version"] == 1


def test_agent_detail_unknown_404(staff_mod, staff_client, monkeypatch):
    _login(staff_mod, staff_client, monkeypatch)
    assert staff_client.get("/api/admin/agents/NOPE").status_code == 404


def test_tools_registry(staff_mod, staff_client, monkeypatch):
    _login(staff_mod, staff_client, monkeypatch)
    tools = staff_client.get("/api/admin/tools").json()["tools"]
    assert any(t["name"] == "Playwright MCP" for t in tools)
    assert all("used" in t for t in tools)


# ── access (allow-list + invites) ───────────────────────────────────────────────────────────────
def test_invite_org_admin_sets_invited_status(staff_mod, staff_client, monkeypatch):
    _login(staff_mod, staff_client, monkeypatch)
    r = staff_client.post("/api/admin/access", json={
        "email": "new@acme.com", "access_type": "org", "org_name": "Acme Co"})
    assert r.status_code == 200
    row = next(u for u in r.json()["users"] if u["email"] == "new@acme.com")
    assert row["status"] == "invited" and row["type"] == "New org"
    assert row["role"] == "admin" and row["org"] == "Acme Co"


def test_invite_tenexity_staff(staff_mod, staff_client, monkeypatch):
    _login(staff_mod, staff_client, monkeypatch)
    r = staff_client.post("/api/admin/access", json={
        "email": "intern@tenexity.ai", "access_type": "tenexity"})
    row = next(u for u in r.json()["users"] if u["email"] == "intern@tenexity.ai")
    assert row["type"] == "Tenexity" and row["status"] == "invited"


def test_invite_org_requires_name(staff_mod, staff_client, monkeypatch):
    _login(staff_mod, staff_client, monkeypatch)
    r = staff_client.post("/api/admin/access", json={"email": "x@y.com", "access_type": "org"})
    assert r.status_code == 400


def test_login_flips_invited_to_active(staff_mod, staff_client, monkeypatch):
    _login(staff_mod, staff_client, monkeypatch)
    staff_client.post("/api/admin/access", json={
        "email": "newbie@acme.com", "access_type": "org", "org_name": "Acme Co"})
    # the invited user signs in → status flips to active (login is open to allow-listed emails)
    _login(staff_mod, staff_client, monkeypatch, email="newbie@acme.com")
    # newbie isn't staff, so re-auth as op to read the allow-list back
    _login(staff_mod, staff_client, monkeypatch)
    rows = staff_client.get("/api/admin/access").json()["users"]
    newbie = next(u for u in rows if u["email"] == "newbie@acme.com")
    assert newbie["status"] == "active"
