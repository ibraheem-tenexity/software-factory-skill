"""Thin stdlib HTTP shell around software_factory.console — no third-party deps.

Serves the operator page, a JSON API, and a chat interface backed by OpenAI Agents SDK:
  GET  /                       -> UI (graph + chat panel)
  POST /api/runs               -> launches a run (legacy form path)
  GET  /api/runs/<id>          -> live status
  GET  /api/runs/<id>/evidence -> proof-of-run bundle
  POST /api/chat               -> send chat message, get agent response
  GET  /api/chat/<id>/history  -> full chat history for a run
  POST /api/chat/<id>/deps     -> submit dep values securely
  GET  /api/chat/<id>/stream   -> SSE for real-time pipeline updates

Run:  python3 console/server.py   (then open http://localhost:8765)
"""
import asyncio
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from software_factory.console import Console, RunRequest  # noqa: E402
from software_factory.chat_store import ChatStore, ChatMessage  # noqa: E402
from software_factory.chat_agent import ChatAgentRunner  # noqa: E402
from software_factory.deps import extract_env_creds  # noqa: E402
from software_factory import notify  # noqa: E402
from software_factory import auth  # noqa: E402

RUNS_DIR = os.environ.get("SF_RUNS_DIR", os.path.join(os.path.dirname(__file__), "..", ".runs"))
HERE = os.path.dirname(__file__)
console = Console(RUNS_DIR)

# The concierge runs on OpenAI (gpt-4o) or OpenRouter (Kimi) — either key enables chat.
_has_chat_key = bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENROUTER_API_KEY"))
_chat_runner = ChatAgentRunner(console) if _has_chat_key else None

_sse_clients: dict[str, list] = {}
_sse_lock = threading.Lock()
_run_stages: dict[str, int] = {}


def _chat_path(run_id: str) -> str:
    return os.path.join(RUNS_DIR, run_id, "chat.jsonl")


def _run_async(coro):
    """Run an async coroutine from sync code."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _push_sse(run_id: str, msgs: list[ChatMessage]):
    """Push messages to all SSE clients watching this run."""
    with _sse_lock:
        clients = _sse_clients.get(run_id, [])
    for msg in msgs:
        data = json.dumps(msg.to_dict())
        for q in clients:
            q.append(f"data: {data}\n\n")


_stage2_launched: set = set()
_stage3_launched: set = set()


def _auto_advance(rid: str):
    """SPEC §1+§3: flip stage-done (gate + finished process) and launch the next stage, so runs
    advance with no manual nudge. Stage 2 auto-launches when Stage 1 is done; deps auto-satisfy
    when no human secret is needed; Stage 3 auto-launches once deps are satisfied. Launch guards
    are marked ONLY on success so a refusal (e.g. prior process still alive) retries next tick."""
    try:
        if not console.is_pipeline_run(rid):
            return  # resurfaced pre-redesign dir (empty run.db) — never auto-advance/zombie-launch it
        if console.detect_stage1_done(rid):
            s = console.status(rid)
            if s.get("stage") == 1 and rid not in _stage2_launched:
                if console.start_stage2(rid):
                    _stage2_launched.add(rid)
        if console.detect_stage2_done(rid):  # flips stage2_done + parses required tokens
            console.maybe_autosatisfy_deps(rid)   # SPEC §3: no 'provide' token -> no pause
            s = console.status(rid)
            if s.get("deps_satisfied") and s.get("stage") == 2 and rid not in _stage3_launched:
                if console.start_stage3(rid):
                    _stage3_launched.add(rid)
        console.detect_stage3_done(rid)  # marks done ONLY with a recorded passing Playwright verification
    except Exception:
        pass


_narrated: set = set()
# run_id -> crash auto-resume attempts, bounded per server life. Configurable: long opencode
# sessions (multi-hour Kimi build/test loops) crash more often than claude's — run-b594a5f4
# exhausted 2 resumes mid-test-phase and stalled 12h. The bound exists to stop crash loops,
# not to ration recovery; budget enforcement is the real spend brake.
_AUTO_RESUME_MAX = int(os.environ.get("SF_AUTO_RESUME_MAX", "2") or 2)
_auto_resumed: dict = {}


def _append_notifications(rid: str, msgs):
    """Persist + push stage notifications, deduped against the persisted chat history —
    a restarted server re-walks stage transitions and re-fired old notifications AFTER
    newer messages, scrambling the chat panel's chronology (run-45b8c4d5)."""
    store = ChatStore(_chat_path(rid))
    try:
        seen = {m.content for m in store.history()}
    except Exception:
        seen = set()
    fresh = [m for m in msgs if m.content not in seen]
    for m in fresh:
        store.append(m)
    if fresh:
        _push_sse(rid, fresh)


def _narrate(rid: str, key: str, text: str):
    """SPEC §6: deterministic chat-panel narration — one message per (run, event), no LLM.
    Dedup survives server restarts by checking the persisted chat history, not just memory."""
    if (rid, key) in _narrated:
        return
    _narrated.add((rid, key))
    store = ChatStore(_chat_path(rid))
    try:
        if any(m.content == text for m in store.history()):
            return  # already narrated in a previous server life
    except Exception:
        pass
    msg = ChatMessage(role="assistant", content=text)
    store.append(msg)
    _push_sse(rid, [msg])
    # Operator email on the four operator-relevant events (done / depswait / budget / crash) —
    # placed AFTER the dedup so an email fires at most once per (run, event). Fire-and-forget:
    # notify.send never raises and must never block the poller.
    if notify.should_email(key):
        threading.Thread(
            target=notify.send,
            args=(f"[factory] {rid}: {text[:90]}", f"{text}\n\nrun: {rid}"),
            daemon=True,
        ).start()


def _narrate_run(rid: str, st: dict):
    links = console.run_links(rid)
    if links.get("repo"):
        _narrate(rid, "repo", f"📦 Source repo: {links['repo']}")
    if st.get("stage1_done"):
        _narrate(rid, "s1", "✅ Research complete — design & architecture starting.")
    if st.get("stage2_done"):
        if st.get("deps_satisfied"):
            _narrate(rid, "deps", "🔓 Design complete — dependencies satisfied, build starting.")
        elif st.get("deps_required"):
            need = [n for n in (st.get("deps_required") or [])]
            _narrate(rid, "depswait", "⏸ Design complete — waiting for you to supply: " + ", ".join(need))
    if links.get("live") and not st.get("done"):
        _narrate(rid, "deployed", f"🚀 Deployed (verifying): {links['live']}")
    if st.get("done"):
        live = st.get("deploy_url") or links.get("live") or ""
        repo = links.get("repo") or ""
        msg = f"✅ Done — Live demo: {live}" + (f" · 📦 Repo: {repo}" if repo else "")
        try:
            creds = console.demo_credentials(rid)
        except Exception:
            creds = None
        if creds:
            # The seeded throwaway demo login (SPEC §6) — without it an auth'd app can't be demoed.
            msg += "\n🔑 Demo login:\n" + creds
        _narrate(rid, "done", msg)


def _poll_transitions():
    """Background thread: auto-advance stages, enforce the per-run budget, narrate progress."""
    while True:
        time.sleep(3)
        try:
            for run_info in console.list_runs():
                rid = run_info.get("id") or run_info.get("run_id", "")
                if not rid:
                    continue
                _auto_advance(rid)
                st = console.status(rid)
                try:
                    if not st.get("done") and console.enforce_budget(rid):
                        _narrate(rid, "budget-%d" % int(console._budget_ceiling(rid)),
                                 "⏸ Budget cap reached — stage stopped (state preserved). "
                                 "Raise the cap to continue.")
                    # SPEC §3 zero-touch: resume a crashed stage automatically (bounded).
                    if not st.get("done") and _auto_resumed.get(rid, 0) < _AUTO_RESUME_MAX:
                        if console.auto_resume_dead_stage(rid):
                            _auto_resumed[rid] = _auto_resumed.get(rid, 0) + 1
                            _narrate(rid, "resume-%d" % _auto_resumed[rid],
                                     "⚠️ Stage process died mid-flight — auto-resumed "
                                     f"(attempt {_auto_resumed[rid]}/{_AUTO_RESUME_MAX}).")
                    _narrate_run(rid, st)
                except Exception:
                    pass
                if st.get("done") or st.get("phase") == "pending":
                    continue
                prev = _run_stages.get(rid, 0)
                cur = st.get("stage", 1)
                if cur != prev:
                    _run_stages[rid] = cur
                    if _chat_runner:
                        _append_notifications(rid, _chat_runner.check_and_notify(rid, prev_stage=prev))
                if st.get("done") and prev > 0:
                    if _chat_runner:
                        _append_notifications(rid, _chat_runner.check_and_notify(rid, prev_stage=cur))
                    _run_stages.pop(rid, None)
        except Exception:
            pass


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authed(self) -> bool:
        """True when auth is disabled (env-gated) or the request carries a valid session."""
        if not auth.enabled():
            return True
        cookies = self.headers.get("Cookie", "")
        for part in cookies.split(";"):
            k, _, v = part.strip().partition("=")
            if k == auth.COOKIE and auth.session_valid(v):
                return True
        return False

    def do_GET(self):
        parsed = urlparse(self.path)
        path, qs = parsed.path, parse_qs(parsed.query)
        if not self._authed():
            # The root serves the Google sign-in page; every API route refuses outright.
            if path == "/" or path == "/index.html":
                with open(os.path.join(HERE, "login.html")) as f:
                    page = f.read().replace("{{CLIENT_ID}}", auth.client_id())
                return self._send(200, page.encode(), "text/html")
            return self._send(401, {"error": "unauthorized"})
        # Match on the PATH only — self.path carries the query string, so "/?run=x" must still
        # serve the console (the ?run= restore link 404'd as raw JSON when matched verbatim).
        if path == "/" or path == "/index.html":
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                return self._send(200, f.read(), "text/html")
        if path in ("/api/runs", "/api/runs/"):
            return self._send(200, {"runs": console.list_runs()})

        # Chat history
        if path.startswith("/api/chat/") and path.endswith("/history"):
            run_id = path[len("/api/chat/"):-len("/history")]
            store = ChatStore(_chat_path(run_id))
            return self._send(200, {"messages": [m.to_dict() for m in store.history()]})

        # SSE stream
        if path.startswith("/api/chat/") and path.endswith("/stream"):
            run_id = path[len("/api/chat/"):-len("/stream")]
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            q: list[str] = []
            with _sse_lock:
                _sse_clients.setdefault(run_id, []).append(q)
            try:
                while True:
                    if q:
                        chunk = q.pop(0)
                        self.wfile.write(chunk.encode())
                        self.wfile.flush()
                    else:
                        self.wfile.write(b": keepalive\n\n")
                        self.wfile.flush()
                        time.sleep(2)
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                with _sse_lock:
                    clients = _sse_clients.get(run_id, [])
                    if q in clients:
                        clients.remove(q)
            return

        if path.startswith("/api/runs/"):
            rest = path[len("/api/runs/"):]
            if rest.endswith("/evidence"):
                return self._send(200, console.evidence(rest[:-len("/evidence")]))
            if rest.endswith("/graph"):
                return self._send(200, console.graph(rest[:-len("/graph")]))
            if rest.endswith("/events"):
                return self._send(200, {"events": console.events(rest[:-len("/events")])})
            if rest.endswith("/artifact"):
                rid = rest[:-len("/artifact")]
                apath = qs.get("path", [""])[0]
                result = console.artifact(rid, apath)
                if (qs.get("raw") or [None])[0] and "content" in result:
                    # Raw mode: serve the file itself (right Content-Type) so e.g. the
                    # architecture SVG opens full-size in its own browser tab.
                    body = result["content"].encode()
                    ctype = {"svg": "image/svg+xml", "html": "text/html", "json": "application/json",
                             "md": "text/markdown"}.get(apath.rsplit(".", 1)[-1].lower(), "text/plain")
                    self.send_response(200)
                    self.send_header("Content-Type", f"{ctype}; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers(); self.wfile.write(body); return
                return self._send(200, result)
            if rest.endswith("/log"):
                rid = rest[:-len("/log")]
                full = (qs.get("full") or [None])[0]
                if full == "json":
                    return self._send(200, {"log": console.read_log(rid, max_bytes=None)})
                if full:
                    body = console.read_log(rid, max_bytes=None).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Content-Disposition", f'attachment; filename="{rid}.log"')
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers(); self.wfile.write(body); return
                return self._send(200, {"log": console.read_log(rid)})
            if rest.endswith("/deps"):
                return self._send(200, console.stage2_artifacts(rest[:-len("/deps")]))
            return self._send(200, console.status(rest))
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        # The login exchange is the ONLY route reachable without a session.
        if urlparse(self.path).path == "/api/auth/google":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            token = auth.login(body.get("credential", ""))
            if not token:
                return self._send(403, {"error": "not authorized"})
            data = json.dumps({"ok": True}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header(
                "Set-Cookie",
                f"{auth.COOKIE}={token}; Path=/; Max-Age={auth.SESSION_TTL}; "
                f"HttpOnly; SameSite=Lax")
            self.end_headers()
            self.wfile.write(data)
            return
        if not self._authed():
            return self._send(401, {"error": "unauthorized"})
        # Chat message
        if self.path == "/api/chat":
            if not _chat_runner:
                return self._send(503, {"error": "no OPENAI_API_KEY or OPENROUTER_API_KEY — chat unavailable"})
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            run_id = body.get("run_id")
            message = body.get("message", "")
            files = body.get("files", [])
            images = body.get("images", [])
            runtime = body.get("runtime", "")  # claude | opencode from the UI picker
            planning_model = body.get("planning_model", "")  # per-run model picks (claude runtime)
            impl_model = body.get("impl_model", "")
            project_name = body.get("project_name", "")

            store = ChatStore(_chat_path(run_id)) if run_id else None
            user_msg = ChatMessage(role="user", content=message, msg_type="text",
                                   ts=time.time())
            if files:
                user_msg.metadata["files"] = [f.get("name", "file") for f in files]
            if images:
                user_msg.metadata["images"] = [i.get("name", "image") for i in images]

            try:
                result_run_id, response_msgs = _run_async(
                    _chat_runner.handle_message(run_id, message, files, images, runtime=runtime,
                                                planning_model=planning_model,
                                                impl_model=impl_model,
                                                project_name=project_name)
                )
            except Exception as e:
                return self._send(500, {"error": str(e)})

            if not run_id:
                run_id = result_run_id
            if run_id:
                store = ChatStore(_chat_path(run_id))
                store.append(user_msg)
                for m in response_msgs:
                    store.append(m)
                _push_sse(run_id, response_msgs)

            return self._send(200, {
                "run_id": run_id,
                "messages": [m.to_dict() for m in response_msgs],
            })

        # Chat deps submission
        if self.path.startswith("/api/chat/") and self.path.endswith("/deps"):
            run_id = self.path[len("/api/chat/"):-len("/deps")]
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            deps = body.get("deps", {})
            result = console.submit_deps(run_id, deps)
            dep_msg = ChatMessage(
                role="user", content=f"Provided: {', '.join(deps.keys())}",
                msg_type="dep_submit", ts=time.time(),
                metadata={"dep_names": list(deps.keys())},
            )
            store = ChatStore(_chat_path(run_id))
            store.append(dep_msg)
            if result.get("satisfied"):
                console.start_stage3(run_id, extra_creds=extract_env_creds(deps))
                launch_msg = ChatMessage(
                    role="system",
                    content="Dependencies received. Build stage launching.",
                    msg_type="status_update", ts=time.time(),
                    metadata={"run_id": run_id, "stage": 3},
                )
                store.append(launch_msg)
                _push_sse(run_id, [dep_msg, launch_msg])
            else:
                _push_sse(run_id, [dep_msg])
            return self._send(200, result)

        # Legacy: existing run management endpoints
        if self.path.startswith("/api/runs/") and self.path.endswith("/continue"):
            run_id = self.path[len("/api/runs/"):-len("/continue")]
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            return self._send(200, console.continue_run(run_id, body.get("gate", "")))
        if self.path.startswith("/api/runs/") and self.path.endswith("/deps"):
            run_id = self.path[len("/api/runs/"):-len("/deps")]
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            return self._send(200, console.submit_deps(run_id, body.get("deps", {})))
        if self.path.startswith("/api/runs/") and self.path.endswith("/stage2"):
            run_id = self.path[len("/api/runs/"):-len("/stage2")]
            result = console.start_stage2(run_id)
            if result:
                return self._send(200, {"run_id": result, "stage": 2})
            return self._send(409, {"error": "stage1 not done or MCP unhealthy"})
        if self.path.startswith("/api/runs/") and self.path.endswith("/stage3"):
            run_id = self.path[len("/api/runs/"):-len("/stage3")]
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            result = console.start_stage3(run_id, extra_creds=extract_env_creds(body.get("creds") or {}))
            if result:
                return self._send(200, {"run_id": result, "stage": 3})
            return self._send(409, {"error": "stage2 not done or deps not satisfied"})
        if self.path.startswith("/api/runs/") and self.path.endswith("/budget"):
            run_id = self.path[len("/api/runs/"):-len("/budget")]
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            try:
                ceiling = float(body.get("ceiling"))
            except (TypeError, ValueError):
                return self._send(400, {"error": "ceiling (number) required"})
            return self._send(200, console.raise_budget(run_id, ceiling))
        if self.path.startswith("/api/runs/") and self.path.endswith("/retry"):
            run_id = self.path[len("/api/runs/"):-len("/retry")]
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            result = console.retry_stage(run_id, int(body.get("stage", 0)),
                                         extra_creds=body.get("creds"))
            if result:
                return self._send(200, {"run_id": result, "retried_stage": int(body["stage"])})
            return self._send(409, {"error": "cannot retry: invalid stage or prior stage not done"})
        if self.path == "/api/runs":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
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
                context_files=body.get("files", []),
                runtime=body.get("runtime", ""),
                planning_model=body.get("planning_model", ""),
                impl_model=body.get("impl_model", ""),
                name=body.get("project_name", ""),
            )
            return self._send(200, {"run_id": console.start_run(req)})
        return self._send(404, {"error": "not found"})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8765"))
    host = os.environ.get("SF_BIND", "127.0.0.1")
    import getpass
    print(f"[runner] uid={os.getuid()} user={getpass.getuser()} home={os.environ.get('HOME')}", flush=True)
    if not _has_chat_key:
        print("[warn] no OPENAI_API_KEY or OPENROUTER_API_KEY — chat agent disabled, API-only mode")
    if (os.environ.get("SF_DB") or "").lower() == "postgres":
        # Self-backfilling flip: runs that exist only as sqlite files on the volume are
        # copied into pg at boot (idempotent — registered runs skip in one registry read).
        try:
            from software_factory.backfill import backfill_all
            for rid, res in backfill_all(RUNS_DIR).items():
                print(f"[backfill] {rid}: {res}", flush=True)
        except Exception as e:
            print(f"[backfill] FAILED: {e}", flush=True)
    t = threading.Thread(target=_poll_transitions, daemon=True)
    t.start()
    print(f"software-factory console on http://{host}:{port}  (runs in {os.path.abspath(RUNS_DIR)})")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
