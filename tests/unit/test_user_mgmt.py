"""User management: password hashing, email+password sign-in, access-row extensions, last_active,
and the canonical Tenexity-org bootstrap seed."""
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


_AUTH = dict(SF_GOOGLE_CLIENT_ID="cid-123.apps.googleusercontent.com", SF_SESSION_SECRET="test-secret")


@pytest.fixture()
def mod(tmp_path, monkeypatch):
    return _load_app(tmp_path, monkeypatch, SF_BOOTSTRAP_ADMIN_EMAIL="op@tenexity.ai", **_AUTH)


@pytest.fixture()
def client(mod):
    return TestClient(mod.app, base_url="https://testserver")


def _login_google(mod, client, monkeypatch, email="op@tenexity.ai"):
    from software_factory import auth as a
    monkeypatch.setattr(a, "verify_google_id_token",
                        lambda tok: {"sub": "sub-" + email, "email": email, "email_verified": True})
    return client.post("/api/auth/google", json={"credential": "t"})


# ── password hashing primitive ───────────────────────────────────────────────────────────────
def test_password_hash_roundtrip_and_reject():
    from software_factory import auth
    h = auth.hash_password("hunter2")
    assert h.startswith("scrypt$") and h != auth.hash_password("hunter2")   # salted (distinct hashes)
    assert auth.verify_password("hunter2", h) is True
    assert auth.verify_password("wrong", h) is False
    assert auth.verify_password("hunter2", "not-a-hash") is False


def test_touch_last_active_sets_timestamp(mod):
    op = mod.users.get_user("op@tenexity.ai")
    assert op["last_active"] is None
    mod.users.touch_last_active(op["id"])
    mod.users._cache = None                       # bust the 20s read cache
    assert mod.users.get_by_id(op["id"])["last_active"] is not None


# ── Tenexity-org bootstrap seed ───────────────────────────────────────────────────────────────
def test_bootstrap_admin_linked_to_tenexity_org(mod, client, monkeypatch):
    _login_google(mod, client, monkeypatch)       # op signs in → active
    org = client.get("/api/org").json()["org"]
    assert org and org["name"] == "Tenexity" and org["id"] == "org-tenexity"
    assert client.get("/api/me").json()["role"] == "admin"   # role preserved by the org-link set_profile


def test_ensure_tenexity_org_is_idempotent(mod):
    mod.users.ensure_tenexity_org()               # 2nd call must not dup-PK (create_org has no ON CONFLICT)
    mod.users.ensure_tenexity_org()
    assert mod.users.get_org("org-tenexity")["name"] == "Tenexity"


# ── email+password provisioning + sign-in ───────────────────────────────────────────────────
def test_provision_password_user_then_login(mod, client, monkeypatch):
    _login_google(mod, client, monkeypatch)       # op = staff admin
    r = client.post("/api/admin/access", json={
        "email": "pw@acme.com", "access_type": "org", "org_name": "Acme", "method": "password",
        "password": "s3cret-pw", "name": "PW User", "designation": "Ops", "role": "member"})
    assert r.status_code == 200
    row = next(u for u in r.json()["users"] if u["email"] == "pw@acme.com")
    assert row["status"] == "active" and row["sign_in_method"] == "password" and row["role"] == "member"
    assert row["name"] == "PW User" and row["designation"] == "Ops" and row["invited_by"] == "op@tenexity.ai"

    c2 = TestClient(mod.app, base_url="https://testserver")
    ok = c2.post("/api/auth/password", json={"email": "pw@acme.com", "password": "s3cret-pw"})
    assert ok.status_code == 200 and ok.json() == {"ok": True}
    assert "sf_session=" in ok.headers.get("set-cookie", "")
    assert c2.get("/api/me").json()["email"] == "pw@acme.com"   # the minted cookie authenticates
    assert c2.post("/api/auth/password",
                   json={"email": "pw@acme.com", "password": "WRONG"}).status_code == 401


def test_password_login_rejects_invited_unknown_and_disabled(mod, client, monkeypatch):
    _login_google(mod, client, monkeypatch)
    client.post("/api/admin/access", json={"email": "inv@acme.com", "access_type": "org",
                                           "org_name": "Acme2"})              # google method → no password
    client.post("/api/admin/access", json={"email": "d@acme.com", "access_type": "org",
                                           "org_name": "Acme3", "method": "password",
                                           "password": "pw123456"})
    client.patch("/api/admin/access/d@acme.com", json={"status": "disabled"})
    c2 = TestClient(mod.app, base_url="https://testserver")
    assert c2.post("/api/auth/password", json={"email": "inv@acme.com", "password": "x"}).status_code == 401
    assert c2.post("/api/auth/password", json={"email": "ghost@x.com", "password": "x"}).status_code == 401
    assert c2.post("/api/auth/password", json={"email": "d@acme.com", "password": "pw123456"}).status_code == 401


def test_invite_password_requires_password(mod, client, monkeypatch):
    _login_google(mod, client, monkeypatch)
    r = client.post("/api/admin/access", json={"email": "np@acme.com", "access_type": "org",
                                               "org_name": "Acme4", "method": "password"})
    assert r.status_code == 400


def test_access_rows_carry_new_columns(mod, client, monkeypatch):
    _login_google(mod, client, monkeypatch)
    op = next(u for u in client.get("/api/admin/access").json()["users"]
              if u["email"] == "op@tenexity.ai")
    assert {"name", "designation", "sign_in_method", "last_active", "invited_by"} <= set(op)
    assert op["type"] == "Tenexity" and op["org"] == "Tenexity"   # internal staff


# ── /api/me enrichment (AccountMenu) + logout ────────────────────────────────────────────────
def test_me_carries_name_and_is_internal(mod, client, monkeypatch):
    _login_google(mod, client, monkeypatch)                       # op = bootstrap staff admin
    me = client.get("/api/me").json()
    assert me["email"] == "op@tenexity.ai" and me["role"] == "admin"
    assert me["name"] == "op@tenexity.ai"        # no name set → falls back to email
    assert me["is_internal"] is True             # staff → OPERATOR badge

    # a named, non-staff org member: name surfaces, is_internal False
    client.post("/api/admin/access", json={"email": "mem@acme.com", "access_type": "org",
                                           "org_name": "Acme", "method": "password",
                                           "password": "pw-123456", "name": "Mem Ber", "role": "member"})
    c2 = TestClient(mod.app, base_url="https://testserver")
    c2.post("/api/auth/password", json={"email": "mem@acme.com", "password": "pw-123456"})
    me2 = c2.get("/api/me").json()
    assert me2["name"] == "Mem Ber" and me2["is_internal"] is False and me2["role"] == "member"


def test_logout_clears_cookie_and_deauthenticates(mod, client, monkeypatch):
    _login_google(mod, client, monkeypatch)
    assert client.get("/api/me").json()["email"] == "op@tenexity.ai"   # authed
    out = client.post("/api/auth/logout")
    assert out.status_code == 200 and out.json() == {"ok": True}
    cookie = out.headers.get("set-cookie", "")
    assert "sf_session=" in cookie and ("Max-Age=0" in cookie or "expires=" in cookie.lower())
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie   # same flags
    # the cleared cookie de-authenticates the next request on the same client
    assert client.get("/api/me").status_code == 401


def test_logout_is_idempotent_without_a_session(mod):
    c = TestClient(mod.app, base_url="https://testserver")   # never logged in
    r = c.post("/api/auth/logout")
    assert r.status_code == 200 and r.json() == {"ok": True}  # ungated — succeeds with no cookie
