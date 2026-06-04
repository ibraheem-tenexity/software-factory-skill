"""Thin stdlib HTTP shell around software_factory.console — no third-party deps.

Serves the operator page and a small JSON API:
  GET  /                       -> input + live view
  POST /api/runs               -> {description, context, budget, target} -> launches a run
  GET  /api/runs/<id>          -> live status (phase, agents, spend, deploy_url)
  GET  /api/runs/<id>/evidence -> proof-of-run bundle + verification verdict

Run:  python3 console/server.py   (then open http://localhost:8765)
Launching a run shells out to headless `claude`, so ANTHROPIC_API_KEY + gh/Railway creds must
be present for a real build; without them the run will hard-block at provision (by design).
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from software_factory.console import Console, RunRequest  # noqa: E402

RUNS_DIR = os.environ.get("SF_RUNS_DIR", os.path.join(os.path.dirname(__file__), "..", ".runs"))
HERE = os.path.dirname(__file__)
console = Console(RUNS_DIR)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                return self._send(200, f.read(), "text/html")
        if self.path in ("/api/runs", "/api/runs/"):
            return self._send(200, {"runs": console.list_runs()})  # spec 3: reconnect on reload
        if self.path.startswith("/api/runs/"):
            rest = self.path[len("/api/runs/"):]
            if rest.endswith("/evidence"):
                return self._send(200, console.evidence(rest[:-len("/evidence")]))
            if rest.endswith("/graph"):
                return self._send(200, console.graph(rest[:-len("/graph")]))  # spec 4
            if rest.endswith("/log"):
                return self._send(200, {"log": console.read_log(rest[:-len("/log")])})
            return self._send(200, console.status(rest))
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/api/runs":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            # Bring-your-own creds: map the form fields to secret env. These are passed to
            # console.start_run, which injects them into the child env and NEVER persists them.
            creds = {}
            if body.get("railway_token"):
                creds["RAILWAY_TOKEN"] = body["railway_token"]
            if body.get("railway_project_id"):
                creds["RAILWAY_PROJECT_ID"] = body["railway_project_id"]
            req = RunRequest(
                description=body.get("description", ""),
                context=body.get("context", ""),
                budget=float(body.get("budget", 100)),
                target=body.get("target", "railway"),
                credentials=creds,
            )
            return self._send(200, {"run_id": console.start_run(req)})
        return self._send(404, {"error": "not found"})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8765"))
    # Loopback only: the console + the BYO creds form are for local single-user use, never
    # exposed on the network. Override with SF_BIND=0.0.0.0 if you really mean to.
    host = os.environ.get("SF_BIND", "127.0.0.1")
    import getpass
    print(f"[runner] uid={os.getuid()} user={getpass.getuser()} home={os.environ.get('HOME')}", flush=True)
    print(f"software-factory console on http://{host}:{port}  (runs in {os.path.abspath(RUNS_DIR)})")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
