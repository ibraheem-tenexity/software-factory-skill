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
             SF_SESSION_SECRET="test-secret")


@pytest.fixture()
def staff_mod(tmp_path, monkeypatch):
    # platform staff = role==admin AND is_internal; bootstrap seeds op as an internal admin.
    return _load_app(tmp_path, monkeypatch,
                     SF_BOOTSTRAP_ADMIN_EMAIL="op@tenexity.ai", **_AUTH)


@pytest.fixture()
def staff_client(staff_mod):
    return TestClient(staff_mod.app, base_url="https://testserver")


@pytest.fixture()
def member_mod(tmp_path, monkeypatch):
    mod = _load_app(tmp_path, monkeypatch, **_AUTH)
    mod.users.upsert("op@tenexity.ai", "member")   # op is a non-staff member
    return mod


@pytest.fixture()
def member_client(member_mod):
    return TestClient(member_mod.app, base_url="https://testserver")


@pytest.fixture()
def adminonly_mod(tmp_path, monkeypatch):
    # role==admin but is_internal NOT set → must NOT reach Tenexity OS.
    mod = _load_app(tmp_path, monkeypatch, **_AUTH)
    mod.users.upsert("op@tenexity.ai", "admin")
    return mod


@pytest.fixture()
def adminonly_client(adminonly_mod):
    return TestClient(adminonly_mod.app, base_url="https://testserver")


def _login(mod, client, monkeypatch, email="op@tenexity.ai"):
    from software_factory import auth as a
    monkeypatch.setattr(a, "verify_google_id_token",
                        lambda tok: {"sub": "sub-" + email, "email": email, "email_verified": True})
    return client.post("/api/auth/google", json={"credential": "t"})


def _enable_react(mod, monkeypatch):
    monkeypatch.setattr(mod.state, "_react_enabled", lambda: True)
    monkeypatch.setattr(mod.state, "_admin_html", lambda: b"<admin-spa>")


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
    _login(adminonly_mod, adminonly_client, monkeypatch)         # role admin, NO is_internal flag
    assert adminonly_client.get("/admin").status_code == 403


def test_admin_page_served_to_staff(staff_mod, staff_client, monkeypatch):
    _enable_react(staff_mod, monkeypatch)
    _login(staff_mod, staff_client, monkeypatch)                 # role admin AND is_internal
    r = staff_client.get("/admin")
    assert r.status_code == 200 and b"admin-spa" in r.content


def test_admin_api_forbidden_for_admin_without_tenexity(adminonly_mod, adminonly_client, monkeypatch):
    # require_staff strict bar: a plain admin (no is_internal) must NOT reach cross-tenant data.
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
def test_agents_roster_is_the_real_agents_not_fakes(staff_mod, staff_client, monkeypatch):
    _login(staff_mod, staff_client, monkeypatch)
    signs = {a["callsign"] for a in staff_client.get("/api/admin/agents").json()["agents"]}
    assert {"STAGE-1", "STAGE-2", "STAGE-3", "CONCIERGE"} <= signs       # the 4 REAL orchestrators
    assert not ({"ATLAS", "HORIZON", "CHROMA", "SIREN", "TENDER", "FORGE", "GARRISON", "MATRIX",
                 "LEDGER", "CONDUIT", "CARGO", "PROFIT"} & signs)         # the 12 fakes are GONE


def test_real_agent_purge_sticks_no_per_request_reseed(staff_mod, staff_client, monkeypatch):
    # The core fix: deleting a registry row must NOT be undone by the next read. Inject a legacy fake,
    # then confirm a plain .all() (what the dashboard GET calls) never reseeds it back.
    _login(staff_mod, staff_client, monkeypatch)
    mod = staff_mod
    mod.agent_store.create("ATLAS", "Orchestrator", role="orchestrator")  # simulate a stale fake row
    mod.agent_store.delete("ATLAS")
    assert mod.agent_store.get("ATLAS") is None
    mod.agent_store.all()                                                 # the read path — must NOT reseed
    assert mod.agent_store.get("ATLAS") is None                           # stays gone (was the bug)


def test_custom_agent_prompt_edit_is_saved_but_not_applied(staff_mod, staff_client, monkeypatch):
    # The role/custom-agent prompt path stays stored-not-applied (part-2b). Create a custom agent first
    # (the fakes are gone), then edit its prompt.
    _login(staff_mod, staff_client, monkeypatch)
    staff_client.post("/api/admin/agents", json={"callsign": "CUSTOM1", "name": "Custom One"})
    r = staff_client.patch("/api/admin/agents/CUSTOM1/prompt", json={"prompt": "be terse"})
    assert r.status_code == 200 and r.json()["version"] == 1 and r.json()["applied"] is False
    detail = staff_client.get("/api/admin/agents/CUSTOM1").json()
    assert detail["prompt"] == "be terse" and detail["prompt_applied"] is False


def test_structural_agents_cannot_be_deleted_but_custom_can(staff_mod, staff_client, monkeypatch):
    _login(staff_mod, staff_client, monkeypatch)
    for cs in ("STAGE-1", "STAGE-2", "STAGE-3", "CONCIERGE"):
        assert staff_client.delete(f"/api/admin/agents/{cs}").status_code == 409   # structural
    staff_client.post("/api/admin/agents", json={"callsign": "CUSTOM2", "name": "Custom Two"})
    assert staff_client.delete("/api/admin/agents/CUSTOM2").status_code == 200      # custom = deletable


def test_real_agents_carry_true_model_data(staff_mod, staff_client, monkeypatch):
    _login(staff_mod, staff_client, monkeypatch)
    monkeypatch.delenv("SF_MODEL", raising=False)
    monkeypatch.delenv("SF_CHAT_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    by_cs = {a["callsign"]: a for a in staff_client.get("/api/admin/agents").json()["agents"]}
    assert by_cs["STAGE-1"]["model"] == "claude-opus-4-8"      # from console._STAGE_MODEL (live config)
    assert by_cs["STAGE-3"]["model"] == "claude-sonnet-4-6"
    assert by_cs["CONCIERGE"]["model"] == "gpt-5.4"            # from chat_model_label (live config)
    # each real agent appears exactly ONCE (no registry-row + live-card duplicate)
    signs = [a["callsign"] for a in staff_client.get("/api/admin/agents").json()["agents"]]
    assert signs.count("STAGE-1") == 1 and signs.count("CONCIERGE") == 1


def test_agent_detail_unknown_404(staff_mod, staff_client, monkeypatch):
    _login(staff_mod, staff_client, monkeypatch)
    assert staff_client.get("/api/admin/agents/NOPE").status_code == 404


def test_stage_skill_cards_appear_in_roster(staff_mod, staff_client, monkeypatch):
    _login(staff_mod, staff_client, monkeypatch)
    agents = staff_client.get("/api/admin/agents").json()["agents"]
    stage = {a["callsign"]: a for a in agents if a.get("kind") == "stage_skill"}
    assert set(stage) == {"STAGE-1", "STAGE-2", "STAGE-3"}
    assert stage["STAGE-1"]["stage"] == 1 and stage["STAGE-3"]["model"] == "claude-sonnet-4-6"
    assert stage["STAGE-1"]["runtimes"] == ["claude", "opencode"]
    assert "CONCIERGE" in {a["callsign"] for a in agents}        # the concierge coexists; no fakes


def test_stage_skill_detail_serves_real_skill_md(staff_mod, staff_client, monkeypatch):
    _login(staff_mod, staff_client, monkeypatch)
    d = staff_client.get("/api/admin/agents/STAGE-1").json()
    assert d["prompt_source"] == "skill_file" and d["prompt_applied"] is True   # live, file-backed
    assert d["editable"] is True and d["runtime"] == "claude"    # now editable (Part 2)
    assert d["is_default"] is True and d["overridden"] is False and d["version"] == 0
    assert "research orchestrator" in d["prompt"].lower()        # the REAL SKILL.md body
    assert d["skill_path"] == "skills/stage-1-research/SKILL.md"
    # the opencode variant is served on request and differs from the claude one
    oc = staff_client.get("/api/admin/agents/STAGE-3?runtime=opencode").json()
    assert oc["runtime"] == "opencode" and oc["skill_path"].endswith("SKILL.opencode.md")
    assert oc["prompt"] != staff_client.get("/api/admin/agents/STAGE-3").json()["prompt"]


def test_concierge_card_is_code_backed_and_live(staff_mod, staff_client, monkeypatch):
    _login(staff_mod, staff_client, monkeypatch)
    monkeypatch.delenv("SF_CHAT_MODEL", raising=False)        # make the model label deterministic
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)   # (no kimi fallback)
    agents = staff_client.get("/api/admin/agents").json()["agents"]
    card = next(a for a in agents if a["callsign"] == "CONCIERGE")
    assert card["kind"] == "concierge" and card["name"] == "Factory Concierge"
    d = staff_client.get("/api/admin/agents/CONCIERGE").json()
    assert d["prompt_source"] == "code" and d["prompt_applied"] is True and d["editable"] is True
    assert "Factory Concierge" in d["prompt"]                 # the REAL CONCIERGE_INSTRUCTIONS
    assert d["model"] == "gpt-5.4"                             # default concierge model
    assert d["source_ref"].endswith("CONCIERGE_INSTRUCTIONS")


def test_stage_prompt_edit_applies_per_runtime_and_reverts(staff_mod, staff_client, monkeypatch):
    _login(staff_mod, staff_client, monkeypatch)
    # edit STAGE-1's CLAUDE prompt → applied (drives next run), GET reflects the override
    r = staff_client.patch("/api/admin/agents/STAGE-1/prompt",
                           json={"prompt": "EDITED claude S1", "runtime": "claude"})
    assert r.status_code == 200 and r.json()["applied"] is True and r.json()["is_default"] is False
    assert r.json()["runtime"] == "claude" and r.json()["version"] == 1
    d = staff_client.get("/api/admin/agents/STAGE-1?runtime=claude").json()
    assert d["prompt"] == "EDITED claude S1" and d["overridden"] is True and d["is_default"] is False
    # the OPENCODE variant is a SEPARATE override — still the default
    oc = staff_client.get("/api/admin/agents/STAGE-1?runtime=opencode").json()
    assert oc["is_default"] is True and oc["prompt"] != "EDITED claude S1"
    # stage edit WITHOUT runtime → 400
    assert staff_client.patch("/api/admin/agents/STAGE-1/prompt",
                              json={"prompt": "x"}).status_code == 400
    # revert (DELETE) → back to default
    assert staff_client.delete("/api/admin/agents/STAGE-1/prompt?runtime=claude").json()["is_default"] is True
    back = staff_client.get("/api/admin/agents/STAGE-1?runtime=claude").json()
    assert back["is_default"] is True and "research orchestrator" in back["prompt"].lower()


def test_concierge_prompt_edit_applies_without_runtime(staff_mod, staff_client, monkeypatch):
    _login(staff_mod, staff_client, monkeypatch)
    r = staff_client.patch("/api/admin/agents/CONCIERGE/prompt", json={"prompt": "EDITED concierge"})
    assert r.status_code == 200 and r.json()["applied"] is True and r.json()["runtime"] is None
    d = staff_client.get("/api/admin/agents/CONCIERGE").json()
    assert d["prompt"] == "EDITED concierge" and d["overridden"] is True
    staff_client.delete("/api/admin/agents/CONCIERGE/prompt")
    assert staff_client.get("/api/admin/agents/CONCIERGE").json()["is_default"] is True


def test_role_agent_prompt_edit_stays_unapplied(staff_mod, staff_client, monkeypatch):
    _login(staff_mod, staff_client, monkeypatch)
    r = staff_client.patch("/api/admin/agents/ATLAS/prompt", json={"prompt": "be terse"})
    assert r.status_code == 200 and r.json()["applied"] is False   # role cards = part-2b, NOT applied
    assert staff_client.delete("/api/admin/agents/ATLAS/prompt").status_code == 404  # not an orchestrator


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


# ── staff-admin toggle (role + is_internal, with strand-the-platform guards) ──────────────────
def test_make_and_revoke_tenexity_admin(staff_mod, staff_client, monkeypatch):
    _login(staff_mod, staff_client, monkeypatch)
    staff_client.post("/api/admin/access", json={"email": "m@acme.com", "access_type": "org",
                                                 "org_name": "Acme"})        # plain org member
    r = staff_client.patch("/api/admin/access/m@acme.com",
                           json={"role": "admin", "is_internal": True})       # Make Tenexity admin
    assert r.status_code == 200
    u = staff_mod.users.get_user("m@acme.com")
    assert u["role"] == "admin" and u["is_internal"] in (1, True)
    # revoke staff — op is still a staff admin, so this is allowed (not the last)
    r2 = staff_client.patch("/api/admin/access/m@acme.com", json={"is_internal": False})
    assert r2.status_code == 200 and staff_mod.users.get_user("m@acme.com")["is_internal"] in (0, False)


def test_cannot_demote_own_staff_session(staff_mod, staff_client, monkeypatch):
    _login(staff_mod, staff_client, monkeypatch)                # op = staff admin AND the requester
    assert staff_client.patch("/api/admin/access/op@tenexity.ai",
                              json={"is_internal": False}).status_code == 409
    assert staff_client.patch("/api/admin/access/op@tenexity.ai",
                              json={"role": "member"}).status_code == 409
    assert staff_mod.users.get_user("op@tenexity.ai")["is_internal"] in (1, True)   # unchanged


def test_cannot_remove_last_staff_admin(tmp_path, monkeypatch):
    from software_factory import auth
    mod = _load_app(tmp_path, monkeypatch, SF_BOOTSTRAP_ADMIN_EMAIL="op@tenexity.ai",
                    SF_SERVICE_TOKEN="svc-secret-token", **_AUTH)
    c = TestClient(mod.app, base_url="https://testserver")
    # service-token session (viewer email=None) → not "your own session", so guard (a) is reachable:
    # op is the LONE staff admin, de-staffing it would strand the platform → 409.
    r = c.patch("/api/admin/access/op@tenexity.ai", json={"is_internal": False},
                headers={auth.SERVICE_HEADER: "svc-secret-token"})
    assert r.status_code == 409
    assert mod.users.get_user("op@tenexity.ai")["is_internal"] in (1, True)   # refused, unchanged


# ── POST /api/admin/agents/sync ───────────────────────────────────────────────────────────────
def test_agents_sync_returns_4_canonical_agents_for_staff(staff_mod, staff_client, monkeypatch):
    _login(staff_mod, staff_client, monkeypatch)
    r = staff_client.post("/api/admin/agents/sync")
    assert r.status_code == 200
    body = r.json()
    assert body["synced"] == 4
    callsigns = {a["callsign"] for a in body["agents"]}
    assert callsigns == {"STAGE-1", "STAGE-2", "STAGE-3", "CONCIERGE"}


def test_agents_sync_forbidden_for_non_staff(member_mod, member_client, monkeypatch):
    _login(member_mod, member_client, monkeypatch)
    assert member_client.post("/api/admin/agents/sync").status_code == 403


def test_agents_sync_forbidden_for_admin_without_is_internal(adminonly_mod, adminonly_client,
                                                               monkeypatch):
    _login(adminonly_mod, adminonly_client, monkeypatch)
    assert adminonly_client.post("/api/admin/agents/sync").status_code == 403


def test_agents_sync_upserts_stale_name(staff_mod, staff_client, monkeypatch):
    # If a canonical agent's name was drifted (e.g. via PATCH), sync must restore the canonical value.
    _login(staff_mod, staff_client, monkeypatch)
    staff_mod.agent_store.update("STAGE-1", {"name": "STALE NAME"})
    assert staff_mod.agent_store.get("STAGE-1")["name"] == "STALE NAME"
    r = staff_client.post("/api/admin/agents/sync")
    assert r.status_code == 200
    s1 = next(a for a in r.json()["agents"] if a["callsign"] == "STAGE-1")
    assert s1["name"] == "Stage 1 · Research"                    # restored by upsert


def test_agents_sync_is_idempotent(staff_mod, staff_client, monkeypatch):
    _login(staff_mod, staff_client, monkeypatch)
    r1 = staff_client.post("/api/admin/agents/sync").json()
    r2 = staff_client.post("/api/admin/agents/sync").json()
    assert r1["synced"] == r2["synced"] == 4
    assert {a["callsign"] for a in r1["agents"]} == {a["callsign"] for a in r2["agents"]}


def test_agents_sync_does_not_touch_custom_agents(staff_mod, staff_client, monkeypatch):
    _login(staff_mod, staff_client, monkeypatch)
    staff_client.post("/api/admin/agents", json={"callsign": "CUSTOM3", "name": "Custom Three"})
    staff_client.post("/api/admin/agents/sync")
    # custom agent must still exist after sync
    assert staff_mod.agent_store.get("CUSTOM3") is not None


# ── POST /api/admin/access/{email}/resend ────────────────────────────────────────────────────────
def test_resend_returns_link_for_invited_user(staff_mod, staff_client, monkeypatch):
    _login(staff_mod, staff_client, monkeypatch)
    staff_client.post("/api/admin/access", json={
        "email": "pending@acme.com", "access_type": "org", "org_name": "Acme Co"})
    r = staff_client.post("/api/admin/access/pending@acme.com/resend")
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "pending@acme.com"
    assert body["status"] == "invited"
    assert "link" in body   # platform sign-in URL


def test_resend_forbidden_for_non_staff(member_mod, member_client, monkeypatch):
    _login(member_mod, member_client, monkeypatch)
    assert member_client.post("/api/admin/access/any@acme.com/resend").status_code == 403


def test_resend_404_for_unknown_user(staff_mod, staff_client, monkeypatch):
    _login(staff_mod, staff_client, monkeypatch)
    assert staff_client.post("/api/admin/access/nobody@ghost.com/resend").status_code == 404


def test_resend_409_for_active_user(staff_mod, staff_client, monkeypatch):
    _login(staff_mod, staff_client, monkeypatch)
    # op@tenexity.ai is already active (logged in above)
    assert staff_client.post("/api/admin/access/op@tenexity.ai/resend").status_code == 409


def test_resend_link_includes_sf_app_url(staff_mod, staff_client, monkeypatch):
    monkeypatch.setenv("SF_APP_URL", "https://app.tenexity.ai")
    _login(staff_mod, staff_client, monkeypatch)
    staff_client.post("/api/admin/access", json={
        "email": "link@acme.com", "access_type": "org", "org_name": "Acme"})
    r = staff_client.post("/api/admin/access/link@acme.com/resend")
    assert r.status_code == 200
    assert r.json()["link"] == "https://app.tenexity.ai/"
