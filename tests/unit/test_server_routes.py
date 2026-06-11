"""HTTP routing of the console server — the page must serve regardless of query string.

Scar: '/?run=run-1e17ea6a' (the state-restore link the UI itself writes into the address bar)
returned the JSON 404 because do_GET matched self.path verbatim, query string included.
"""
import importlib
import json
import os
import sys
import threading
import urllib.error
import urllib.request

import pytest


@pytest.fixture()
def live_server(tmp_path, monkeypatch):
    monkeypatch.setenv("SF_RUNS_DIR", str(tmp_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "console"))
    import server as server_mod
    importlib.reload(server_mod)
    from http.server import ThreadingHTTPServer
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server_mod.Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def _get(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read()


def test_root_serves_console_html(live_server):
    status, ctype, body = _get(live_server + "/")
    assert status == 200 and "text/html" in ctype


def test_run_restore_link_serves_console_html_not_404(live_server):
    # the exact URL attach() writes via history.replaceState — reload must restore the run view
    status, ctype, body = _get(live_server + "/?run=run-1e17ea6a")
    assert status == 200 and "text/html" in ctype
    assert b"Software Factory" in body


@pytest.fixture()
def auth_server(tmp_path, monkeypatch):
    monkeypatch.setenv("SF_RUNS_DIR", str(tmp_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("SF_GOOGLE_CLIENT_ID", "cid-123.apps.googleusercontent.com")
    monkeypatch.setenv("SF_AUTH_EMAILS", "op@tenexity.ai")
    monkeypatch.setenv("SF_AUTH_SECRET", "test-secret")
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "console"))
    import server as server_mod
    importlib.reload(server_mod)
    from http.server import ThreadingHTTPServer
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server_mod.Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def _get_raw(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_auth_enabled_root_serves_login_not_console(auth_server):
    status, body = _get_raw(auth_server + "/")
    assert status == 200
    assert b"accounts.google.com" in body          # the Google sign-in page
    assert b"cid-123" in body                       # client id injected
    assert b"Factory Concierge" not in body         # console NOT exposed


def test_auth_enabled_api_requires_session(auth_server):
    status, body = _get_raw(auth_server + "/api/runs")
    assert status == 401


def test_google_login_sets_cookie_and_opens_console(auth_server, monkeypatch):
    from software_factory import auth as auth_mod
    monkeypatch.setattr(auth_mod, "_fetch_claims", lambda tok: {
        "aud": "cid-123.apps.googleusercontent.com", "email": "op@tenexity.ai",
        "email_verified": "true"})
    req = urllib.request.Request(
        auth_server + "/api/auth/google",
        data=json.dumps({"credential": "goog-token"}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        assert r.status == 200
        cookie = r.headers.get("Set-Cookie", "")
    assert "sf_session=" in cookie and "HttpOnly" in cookie
    session = cookie.split("sf_session=")[1].split(";")[0]
    status, body = _get_raw(auth_server + "/", headers={"Cookie": f"sf_session={session}"})
    assert status == 200 and b"Factory Concierge" in body
    status, _ = _get_raw(auth_server + "/api/runs", headers={"Cookie": f"sf_session={session}"})
    assert status == 200


def test_google_login_rejected_for_unallowed_email(auth_server, monkeypatch):
    from software_factory import auth as auth_mod
    monkeypatch.setattr(auth_mod, "_fetch_claims", lambda tok: {
        "aud": "cid-123.apps.googleusercontent.com", "email": "evil@example.com",
        "email_verified": "true"})
    req = urllib.request.Request(
        auth_server + "/api/auth/google",
        data=json.dumps({"credential": "goog-token"}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            status = r.status
    except urllib.error.HTTPError as e:
        status = e.code
    assert status == 403
