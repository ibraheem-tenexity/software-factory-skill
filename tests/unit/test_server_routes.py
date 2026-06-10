"""HTTP routing of the console server — the page must serve regardless of query string.

Scar: '/?run=run-1e17ea6a' (the state-restore link the UI itself writes into the address bar)
returned the JSON 404 because do_GET matched self.path verbatim, query string included.
"""
import importlib
import os
import sys
import threading
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
