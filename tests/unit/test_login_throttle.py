"""Brute-force/DoS throttle for POST /api/auth/password: the LoginThrottle primitive (deterministic,
explicit clock) and the route integration (429 + Retry-After, fired BEFORE the scrypt verify)."""
import importlib
import os
import sys

import pytest
from fastapi.testclient import TestClient

from console.throttle import LoginThrottle


# ── primitive ────────────────────────────────────────────────────────────────────────────────
def test_free_tier_then_exponential_backoff():
    t = LoginThrottle(free_email=5, base=2.0, cap=900.0)
    keys = ["email:a@b.com"]
    for _ in range(5):                       # first 5 failures are free — no lock
        assert t.retry_after(keys, now=0) == 0
        t.record_failure(keys, now=0)
    t.record_failure(keys, now=0)            # 6th failure arms the lock
    assert t.retry_after(keys, now=0) == 2   # base * 2^0
    t.record_failure(keys, now=0)            # 7th
    assert t.retry_after(keys, now=0) == 4   # base * 2^1
    t.record_failure(keys, now=0)            # 8th
    assert t.retry_after(keys, now=0) == 8


def test_backoff_is_capped():
    t = LoginThrottle(free_email=0, base=2.0, cap=10.0)
    for _ in range(20):
        t.record_failure(["email:x@y.com"], now=0)
    assert t.retry_after(["email:x@y.com"], now=0) == 10   # clamped to cap, not 2^20


def test_lock_expires_as_clock_advances():
    t = LoginThrottle(free_email=0, base=2.0, cap=900.0)
    t.record_failure(["email:a@b.com"], now=100)     # locked until 102
    assert t.retry_after(["email:a@b.com"], now=101) == 1
    assert t.retry_after(["email:a@b.com"], now=102) == 0   # lock elapsed


def test_idle_window_resets_the_counter():
    t = LoginThrottle(free_email=2, base=2.0, window=60.0)
    t.record_failure(["email:a@b.com"], now=0)
    t.record_failure(["email:a@b.com"], now=0)       # count=2 (still free)
    t.record_failure(["email:a@b.com"], now=1000)    # >window since last → counter reset to 1, free
    assert t.retry_after(["email:a@b.com"], now=1000) == 0


def test_success_reset_clears_counter():
    t = LoginThrottle(free_email=1, base=2.0)
    t.record_failure(["email:a@b.com"], now=0)
    t.record_failure(["email:a@b.com"], now=0)       # locked
    assert t.retry_after(["email:a@b.com"], now=0) > 0
    t.reset(["email:a@b.com"])
    assert t.retry_after(["email:a@b.com"], now=0) == 0


def test_ip_tier_is_looser_than_email():
    t = LoginThrottle(free_email=5, free_ip=20, base=2.0)
    for _ in range(10):
        t.record_failure(["ip:1.2.3.4"], now=0)      # 10 ≤ 20 free for IP
    assert t.retry_after(["ip:1.2.3.4"], now=0) == 0
    for _ in range(6):
        t.record_failure(["email:a@b.com"], now=0)   # 6 > 5 free for email
    assert t.retry_after(["email:a@b.com"], now=0) > 0


def test_max_wait_across_keys():
    t = LoginThrottle(free_email=0, free_ip=0, base=2.0)
    t.record_failure(["email:a@b.com"], now=0)       # email locked 2s
    t.record_failure(["ip:1.2.3.4"], now=0)
    t.record_failure(["ip:1.2.3.4"], now=0)          # ip locked 4s
    assert t.retry_after(["email:a@b.com", "ip:1.2.3.4"], now=0) == 4   # the larger of the two


# ── route integration ──────────────────────────────────────────────────────────────────────
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


def test_repeated_failures_get_429_with_retry_after(mod, client):
    # 6 wrong attempts on one email (free_email=5) → the 7th is throttled. Works even for an unknown
    # email — the failure is counted before authenticate_password resolves anything.
    last = None
    for _ in range(6):
        last = client.post("/api/auth/password", json={"email": "ghost@x.com", "password": "x"})
        assert last.status_code == 401
    blocked = client.post("/api/auth/password", json={"email": "ghost@x.com", "password": "x"})
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1


def test_throttle_fires_before_verify_even_with_correct_password(mod, client, monkeypatch):
    # Provision a real password user, burn the email through the lock with wrong tries, then confirm the
    # CORRECT password is ALSO 429 — proving the guard runs before the scrypt verify (closes the DoS).
    from software_factory import auth as a
    monkeypatch.setattr(a, "verify_google_id_token",
                        lambda tok: {"sub": "s", "email": "op@tenexity.ai", "email_verified": True})
    client.post("/api/auth/google", json={"credential": "t"})       # op = staff admin
    client.post("/api/admin/access", json={"email": "pw@acme.com", "access_type": "org",
                                           "org_name": "Acme", "method": "password",
                                           "password": "right-pw-123"})
    for _ in range(6):
        client.post("/api/auth/password", json={"email": "pw@acme.com", "password": "WRONG"})
    blocked = client.post("/api/auth/password", json={"email": "pw@acme.com", "password": "right-pw-123"})
    assert blocked.status_code == 429


def test_forged_leftmost_xff_does_not_evade_the_ip_lock(mod):
    # The IP layer must key on the TRUSTED (proxy-appended) hop, not the client-controlled leftmost.
    # Simulate one real attacker (rightmost 5.5.5.5, what our edge would append) rotating a forged
    # leftmost XFF + a distinct email each request (so the email counter never trips — isolates IP).
    # free_ip=20 → 21 failures arm the lock → the 22nd request is 429. If the code keyed on the
    # leftmost, every request would be its own bucket (count=1) and the 22nd would be a plain 401.
    c = TestClient(mod.app, base_url="https://testserver")
    last = None
    for i in range(21):
        last = c.post("/api/auth/password",
                      headers={"X-Forwarded-For": f"9.9.9.{i}, 5.5.5.5"},
                      json={"email": f"spray{i}@x.com", "password": "x"})
        assert last.status_code == 401          # under the IP cap, each distinct email = its own 401
    blocked = c.post("/api/auth/password",
                     headers={"X-Forwarded-For": "9.9.9.99, 5.5.5.5"},
                     json={"email": "spray-final@x.com", "password": "x"})
    assert blocked.status_code == 429            # IP counter held across the rotating forged leftmost


def test_envoy_external_address_is_preferred_over_xff(mod):
    # Railway's Envoy sets X-Envoy-External-Address to the real (non-spoofable) client; it wins over a
    # forged XFF. Same real client (7.7.7.7) behind two different forged XFFs shares one IP counter.
    c = TestClient(mod.app, base_url="https://testserver")
    last = None
    for i in range(21):
        last = c.post("/api/auth/password",
                      headers={"X-Envoy-External-Address": "7.7.7.7",
                               "X-Forwarded-For": f"{i}.{i}.{i}.{i}"},
                      json={"email": f"ev{i}@x.com", "password": "x"})
        assert last.status_code == 401
    assert c.post("/api/auth/password",
                  headers={"X-Envoy-External-Address": "7.7.7.7", "X-Forwarded-For": "1.2.3.4"},
                  json={"email": "ev-final@x.com", "password": "x"}).status_code == 429


def test_under_threshold_does_not_block_a_good_login(mod, client, monkeypatch):
    from software_factory import auth as a
    monkeypatch.setattr(a, "verify_google_id_token",
                        lambda tok: {"sub": "s", "email": "op@tenexity.ai", "email_verified": True})
    client.post("/api/auth/google", json={"credential": "t"})
    client.post("/api/admin/access", json={"email": "pw2@acme.com", "access_type": "org",
                                           "org_name": "Acme2", "method": "password",
                                           "password": "good-pw-456"})
    c2 = TestClient(mod.app, base_url="https://testserver")
    for _ in range(3):                                              # 3 < 5 free → no lock
        assert c2.post("/api/auth/password",
                       json={"email": "pw2@acme.com", "password": "no"}).status_code == 401
    ok = c2.post("/api/auth/password", json={"email": "pw2@acme.com", "password": "good-pw-456"})
    assert ok.status_code == 200 and ok.json() == {"ok": True}
