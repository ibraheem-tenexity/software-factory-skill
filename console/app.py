"""FastAPI shell around software_factory.console (Phase 2 of docs/plans/fastapi-db-replacement.md).

Replaces the hand-rolled stdlib BaseHTTPRequestHandler (console/server.py). Same routes, same JSON
contract, same auth/ownership rules — now with Pydantic bodies, dependency-injected auth, an
APIRouter, SSE via StreamingResponse, and the background poller started in the app lifespan.

  GET  /                       -> UI (graph + chat panel)  [login page when auth-enabled + unauthed]
  POST /api/runs               -> launches a run (legacy form path)
  GET  /api/runs/<id>          -> live status
  GET  /api/runs/<id>/evidence -> proof-of-run bundle
  POST /api/chat               -> send chat message, get agent response
  GET  /api/chat/<id>/history  -> full chat history for a run
  POST /api/chat/<id>/deps     -> submit dep values securely
  GET  /api/chat/<id>/stream   -> SSE for real-time pipeline updates

Run:  uvicorn console.app:app --host 0.0.0.0 --port 8765   (or python3 console/app.py)
"""
import asyncio
import base64
import contextlib
import json
import os
import sys
import threading
import time

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from software_factory.console import Console, RunRequest  # noqa: E402
from software_factory.chat_store import ChatStore, ChatMessage  # noqa: E402
from software_factory.chat_agent import ChatAgentRunner  # noqa: E402
from software_factory.deps import extract_env_creds  # noqa: E402
from software_factory import auth  # noqa: E402
from software_factory import env as _env  # noqa: E402
from software_factory import notify  # noqa: E402
from software_factory import tracing  # noqa: E402
from software_factory import storage  # noqa: E402
from software_factory import billing  # noqa: E402
from software_factory import project_view  # noqa: E402
from software_factory.users import UserStore  # noqa: E402
from software_factory.blobs import BlobStore  # noqa: E402

RUNS_DIR = os.environ.get("SF_RUNS_DIR", os.path.join(os.path.dirname(__file__), "..", ".runs"))
HERE = os.path.dirname(__file__)
console = Console(RUNS_DIR)

# User directory (roles + login membership). Seeds env SF_ADMIN_EMAILS as admins and backs
# auth's role/membership decisions; without it auth falls back to the env lists.
users = UserStore(os.path.join(RUNS_DIR, "users.db"))
auth.register_user_store(users.is_member, users.get_role)

# Blob manifest — org knowledge-base docs + run-scoped uploaded materials (bytes live in storage).
blobs = BlobStore(os.path.join(RUNS_DIR, "blobs.db"))

# The concierge runs on OpenAI (gpt-4o) or OpenRouter (Kimi) — either key enables chat.
_has_chat_key = bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENROUTER_API_KEY"))
_chat_runner = ChatAgentRunner(console, users) if _has_chat_key else None

_sse_clients: dict[str, list] = {}
_sse_lock = threading.Lock()
_run_stages: dict[str, int] = {}


def _chat_path(run_id: str) -> str:
    return os.path.join(RUNS_DIR, run_id, "chat.jsonl")


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


_tracer = tracing.Tracer()
_health_bad_since = [None]  # [-]: None = healthy; float = first failure ts (alert once)


def _health() -> dict:
    """Liveness for probes + the console dot. pg=None means sqlite mode (nothing to check)."""
    import shutil as _sh
    pg = None
    if (os.environ.get("SF_DB") or "").lower() == "postgres":
        from software_factory import dbshim
        try:
            dbshim.registry_runs()
            pg = True
        except Exception:
            pg = False
    try:
        free_mb = int(_sh.disk_usage(RUNS_DIR).free / 1048576)
    except OSError:
        free_mb = -1
    ok = (pg is not False) and free_mb > 200
    return {"ok": ok, "pg": pg, "disk_free_mb": free_mb}


def _poll_transitions():
    """Background thread: auto-advance stages, enforce the per-run budget, narrate progress."""
    tick = 0
    while True:
        time.sleep(3)
        tick += 1
        if tick % 10 == 0:  # health every ~30s; email once per unhealthy episode
            try:
                h = _health()
                if not h["ok"] and _health_bad_since[0] is None:
                    _health_bad_since[0] = time.time()
                    notify.send("factory-console UNHEALTHY",
                                f"health: {json.dumps(h)} — pg unreachable or disk low.")
                elif h["ok"]:
                    _health_bad_since[0] = None
            except Exception:
                pass
        try:
            for run_info in console.list_runs():
                rid = run_info.get("id") or run_info.get("run_id", "")
                if not rid:
                    continue
                if run_info.get("held"):  # gated hold: nothing to advance/enforce/narrate
                    continue
                _auto_advance(rid)
                st = console.status(rid)
                # LLM traces: ship this run's new log lines to Langfuse (no-op without keys).
                _tracer.tick(rid, os.path.join(RUNS_DIR, rid, "run.log"),
                             meta={"runtime": st.get("runtime", "")})
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


def _boot():
    """One-time boot work that lived in the old server's __main__ block: announce the runtime
    user, quarantine debris, prod pg-backfill, and owner-backfill. Runs in the app lifespan."""
    import getpass
    print(f"[runner] uid={os.getuid()} user={getpass.getuser()} home={os.environ.get('HOME')}", flush=True)
    if not _has_chat_key:
        print("[warn] no OPENAI_API_KEY or OPENROUTER_API_KEY — chat agent disabled, API-only mode")
    # Quarantine debris under runs_dir: agents misusing db verbs once created dirs like
    # "build-plan.md/run.db" on the volume — moved aside (never deleted), so discovery and
    # the boot backfill only ever see real runs.
    try:
        from software_factory.console import RUN_ID_RE
        qdir = os.path.join(RUNS_DIR, "_quarantine")
        for name in os.listdir(RUNS_DIR):
            p = os.path.join(RUNS_DIR, name)
            if os.path.isdir(p) and name != "_quarantine" and not RUN_ID_RE.fullmatch(name):
                os.makedirs(qdir, exist_ok=True)
                os.rename(p, os.path.join(qdir, f"{name}.{int(time.time())}"))
                print(f"[janitor] quarantined {name}", flush=True)
    except Exception as e:
        print(f"[janitor] FAILED: {e}", flush=True)
    if _env.sf_environment() == "prod":
        # Apply migrations (Alembic upgrade head) so every table exists. Defensive backstop to
        # entrypoint.sh (idempotent).
        try:
            from software_factory import migrate as _migrate
            _migrate.run()
        except Exception as e:
            print(f"[migrate] boot FAILED: {e}", flush=True)
    # Backfill ownership on pre-multitenancy runs → the first bootstrap admin (idempotent).
    _admins = [e.strip() for e in os.environ.get("SF_ADMIN_EMAILS", "").split(",") if e.strip()]
    if _admins:
        try:
            n = console.assign_unowned(_admins[0])
            if n:
                print(f"[owners] assigned {n} unowned run(s) to {_admins[0]}", flush=True)
        except Exception as e:
            print(f"[owners] backfill FAILED: {e}", flush=True)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    _boot()
    t = threading.Thread(target=_poll_transitions, daemon=True)
    t.start()
    print(f"software-factory console (FastAPI) — runs in {os.path.abspath(RUNS_DIR)}", flush=True)
    yield


app = FastAPI(title="software-factory console", lifespan=lifespan)


# ── Structured access log ───────────────────────────────────────────────────────────────────
# One JSON line per response on stdout — Railway captures stdout natively, so `railway logs`
# becomes greppable by route/status/run_id. Mirrors the old Handler._send logging.
@app.middleware("http")
async def _access_log(request: Request, call_next):
    t0 = time.time()
    response = await call_next(request)
    try:
        path = request.url.path
        rid = path.split("/api/runs/")[1].split("/")[0] if "/api/runs/" in path else ""
        print(json.dumps({"ts": round(time.time(), 3), "method": request.method,
                          "path": path, "status": response.status_code, "run_id": rid,
                          "ms": int((time.time() - t0) * 1000)}), flush=True)
    except Exception:
        pass
    return response


# ── Auth dependencies (wrap software_factory.auth; do not change auth resolution) ─────────────
def viewer(request: Request) -> tuple:
    """(email, role, ok). ok = authorized to use the API at all. Auth disabled (local/dev)
    or a valid service token = full admin access; a session cookie = that user's role."""
    if not auth.enabled():
        return (None, "admin", True)
    if auth.service_token_ok(request.headers.get(auth.SERVICE_HEADER)):
        return (None, "admin", True)
    token = request.cookies.get(auth.COOKIE)
    if token:
        email = auth.session_email(token)
        if email:
            return (email, auth.role_for(email) or "member", True)
    return (None, None, False)


def require_authed(v: tuple = Depends(viewer)) -> tuple:
    if not v[2]:
        raise HTTPException(status_code=401, detail="unauthorized")
    return v


def _can_see(v: tuple, run_id: str) -> bool:
    """Ownership gate enforced on EVERY run-scoped route — filtering the list is not enough,
    a member could fetch another's run by URL. Admin/service = all; member = own only."""
    email, role, ok = v
    if not ok:
        return False
    if role == "admin":
        return True
    return bool(run_id) and console.run_owner(run_id) == (email or "").lower()


def authorize_run(rid: str, v: tuple = Depends(require_authed)) -> tuple:
    """For run-scoped routes carrying {rid}: 403 unless admin/service or the run's owner."""
    if not _can_see(v, rid):
        raise HTTPException(status_code=403, detail="forbidden")
    return v


def require_admin(v: tuple = Depends(require_authed)) -> tuple:
    if v[1] != "admin":
        raise HTTPException(status_code=403, detail="admin only")
    return v


# ── Pydantic request bodies (extra keys ignored — mirror the dicts the old server read) ───────
class GoogleLoginIn(BaseModel):
    credential: str = ""


class UserMgmtIn(BaseModel):
    email: str = ""
    role: str | None = None


class OrgIn(BaseModel):
    name: str = ""
    industry: str | None = None
    sub_focus: list = []
    headcount: str | None = None
    revenue: str | None = None
    location: str | None = None
    website: str | None = None
    connected_systems: list = []
    designation: str | None = None
    role_description: str | None = None


class OrgPatchIn(BaseModel):
    name: str | None = None
    industry: str | None = None
    sub_focus: list | None = None
    headcount: str | None = None
    revenue: str | None = None
    location: str | None = None
    website: str | None = None
    connected_systems: list | None = None


class OrgDocIn(BaseModel):
    name: str = ""
    tag: str | None = None
    content_type: str | None = None
    data_b64: str = ""


class OrgDocUseIn(BaseModel):
    run_id: str = ""


class OrgMemberIn(BaseModel):
    email: str = ""
    role: str = "member"
    designation: str | None = None


class OrgMemberPatchIn(BaseModel):
    role: str | None = None
    designation: str | None = None


class OrgBillingIn(BaseModel):
    plan: str | None = None
    monthly_budget_cap: float | None = None


class ChatIn(BaseModel):
    run_id: str | None = None
    message: str = ""
    files: list = []
    images: list = []
    runtime: str = ""
    planning_model: str = ""
    impl_model: str = ""
    project_name: str = ""
    gated: bool = False


class DepsIn(BaseModel):
    deps: dict = {}


class ContinueIn(BaseModel):
    gate: str = ""


class Stage3In(BaseModel):
    creds: dict | None = None


class BudgetIn(BaseModel):
    ceiling: float | None = None


class RetryIn(BaseModel):
    stage: int = 0
    creds: dict | None = None


class RunCreateIn(BaseModel):
    description: str = ""
    context: str = ""
    budget: float = 100
    target: str = "railway"
    files: list = []
    runtime: str = ""
    planning_model: str = ""
    impl_model: str = ""
    project_name: str = ""
    gated: bool = False
    railway_token: str = ""
    railway_project_id: str = ""


# Option C onboarding (draft model): the form eagerly creates a draft on mount, write-throughs the
# project fields, attaches materials, and promotes at handoff. See docs/plans/fastapi-db-replacement.md.
class DraftCreateIn(BaseModel):
    project_name: str = ""
    runtime: str = ""
    planning_model: str = ""
    impl_model: str = ""


class DraftPatchIn(BaseModel):
    name: str | None = None
    goal: str | None = None
    scope: list | None = None


class AttachIn(BaseModel):
    files: list = []


class PromoteIn(BaseModel):
    description: str = ""
    target: str = "railway"


# ── Static + open routes ──────────────────────────────────────────────────────────────────────
# The React SPA (console/web/dist) is served when SF_CONSOLE=react AND it's been built; otherwise the
# legacy single-file console (index.html) is the default — so the migration is opt-in and safe.
_REACT_DIST = os.path.join(HERE, "web", "dist")


def _react_enabled() -> bool:
    return (os.environ.get("SF_CONSOLE", "").strip().lower() == "react"
            and os.path.isfile(os.path.join(_REACT_DIST, "index.html")))


if os.path.isdir(os.path.join(_REACT_DIST, "assets")):
    from fastapi.staticfiles import StaticFiles
    app.mount("/assets", StaticFiles(directory=os.path.join(_REACT_DIST, "assets")), name="assets")


def _index_html() -> bytes:
    path = os.path.join(_REACT_DIST, "index.html") if _react_enabled() else os.path.join(HERE, "index.html")
    with open(path, "rb") as f:
        return f.read()


def _admin_html() -> bytes:
    with open(os.path.join(_REACT_DIST, "admin.html"), "rb") as f:
        return f.read()


def _login_html() -> str:
    with open(os.path.join(HERE, "login.html")) as f:
        return f.read().replace("{{CLIENT_ID}}", auth.client_id())


@app.get("/", response_class=HTMLResponse)
@app.get("/index.html", response_class=HTMLResponse)
def root(v: tuple = Depends(viewer)):
    # The root serves the Google sign-in page when auth is on and the caller has no session;
    # otherwise the console. (Query strings like /?run=x route here too — FastAPI matches path.)
    # React mode: the SPA gates login itself (reads /api/auth/config + /api/me, renders its own
    # LoginScreen on 401), so serve the bundle to unauthed users too. Legacy mode keeps the
    # server-rendered login page.
    if _react_enabled():
        return HTMLResponse(_index_html())
    if not v[2]:
        return HTMLResponse(_login_html())
    return HTMLResponse(_index_html())


@app.get("/admin", response_class=HTMLResponse)
@app.get("/admin.html", response_class=HTMLResponse)
def admin_portal(v: tuple = Depends(viewer)):
    # The Tenexity OS operator portal is a separate SPA entry (console/web/admin.html →
    # src/admin/main.tsx), built alongside index.html. Only available in React mode (the
    # legacy single-file console has no admin entry). Like root(), the SPA gates its own
    # access; the service token / session resolve the full-admin identity it needs.
    if not _react_enabled():
        raise HTTPException(status_code=404, detail="not found")
    return HTMLResponse(_admin_html())


@app.get("/api/health")
def health():
    # Health is OPEN (platform probes don't authenticate) and carries no secrets.
    return _health()


# ── Identity + team ─────────────────────────────────────────────────────────────────────────
@app.get("/api/me")
def me(v: tuple = Depends(require_authed)):
    return {"email": v[0], "role": v[1], "auth": auth.enabled()}


@app.get("/api/users")
def list_users(v: tuple = Depends(require_admin)):
    return {"users": users.list_users()}


@app.post("/api/users")
def manage_users(body: UserMgmtIn, v: tuple = Depends(require_admin)):
    email = (body.email or "").strip().lower()
    role = body.role
    if not email or role not in ("admin", "member", "remove"):
        raise HTTPException(status_code=400, detail="email + role (admin|member|remove) required")
    if role == "remove":
        users.remove(email)
    else:
        users.upsert(email, role, by=v[0] or "admin")
    return {"users": users.list_users()}


# ── Organization (onboarding front door) ──────────────────────────────────────────────────────
# The onboarding screen reads GET /api/org on load: no org on file → first-time path; an org →
# returning path. POST creates the org + links the current user; PATCH is the Manage editor.
@app.get("/api/org")
def get_org(v: tuple = Depends(require_authed)):
    return {"org": users.org_for_user(v[0]) if v[0] else None}


@app.post("/api/org")
def create_org(body: OrgIn, v: tuple = Depends(require_authed)):
    if not (body.name or "").strip():
        raise HTTPException(status_code=400, detail="name required")
    oid = users.create_org(
        body.name, industry=body.industry, sub_focus=body.sub_focus,
        headcount=body.headcount, revenue=body.revenue, location=body.location,
        website=body.website, connected_systems=body.connected_systems, by=v[0] or "")
    if v[0]:
        users.set_profile(v[0], org_id=oid, designation=body.designation,
                          role_description=body.role_description)
    return {"org": users.get_org(oid)}


@app.patch("/api/org")
def patch_org(body: OrgPatchIn, v: tuple = Depends(require_authed)):
    org = users.org_for_user(v[0]) if v[0] else None
    if not org:
        raise HTTPException(status_code=404, detail="no org on file")
    fields = {k: val for k, val in body.model_dump().items() if val is not None}
    users.update_org(org["id"], **fields)
    return {"org": users.get_org(org["id"])}


# ── Org admin (PRD §2.3) ──────────────────────────────────────────────────────────────────────
# Knowledge base, Team & access, Usage & billing — all resolve the org from the caller's session
# (no org_id in the path). Reads need membership (an org on file); writes need admin.
_DOC_KIND = {"pdf": "pdf", "xlsx": "xlsx", "xls": "xlsx", "csv": "csv", "doc": "doc", "docx": "doc",
             "mp4": "video", "mov": "video", "png": "img", "jpg": "img", "jpeg": "img"}


def _doc_kind(name: str) -> str:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return _DOC_KIND.get(ext, "doc")


def _caller_org(v: tuple) -> dict:
    """The org on file for the session, or 404 (mirrors PATCH /api/org)."""
    org = users.org_for_user(v[0]) if v[0] else None
    if not org:
        raise HTTPException(status_code=404, detail="no org on file")
    return org


def _members_payload(org_id: str, me: str) -> dict:
    return {"members": [
        {"email": m["email"], "role": m["role"], "designation": m.get("designation"),
         "you": m["email"] == me}
        for m in users.list_org_members(org_id)]}


def _org_doc_or_404(doc_id: int, org_id: str) -> dict:
    b = blobs.get_blob(doc_id)
    if not b or b["scope"] != "org" or b["scope_id"] != org_id:
        raise HTTPException(status_code=404, detail="doc not found")
    return b


# Knowledge base ----------------------------------------------------------------------------------
@app.get("/api/org/docs")
def org_docs(v: tuple = Depends(require_authed)):
    return {"docs": blobs.list_org_docs(_caller_org(v)["id"])}


@app.post("/api/org/docs")
def org_doc_upload(body: OrgDocIn, v: tuple = Depends(require_admin)):
    org = _caller_org(v)
    if not (body.name or "").strip():
        raise HTTPException(status_code=400, detail="name required")
    try:
        raw = base64.b64decode(body.data_b64 or "", validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="data_b64 must be valid base64")
    scope_id = f"org/{org['id']}"
    key = f"kb/{body.name}"
    storage.put(scope_id, key, raw)
    bid = blobs.record("org", org["id"], f"{scope_id}/{key}", name=body.name, tag=body.tag,
                       kind=_doc_kind(body.name), content_type=body.content_type,
                       size_bytes=len(raw), sha256=storage.sha256(raw))
    doc = next((d for d in blobs.list_org_docs(org["id"]) if d["id"] == bid), None)
    return {"doc": doc}


@app.post("/api/org/docs/{doc_id}/use")
def org_doc_use(doc_id: int, body: OrgDocUseIn, v: tuple = Depends(require_authed)):
    org = _caller_org(v)
    _org_doc_or_404(doc_id, org["id"])
    if not (body.run_id or "").strip():
        raise HTTPException(status_code=400, detail="run_id required")
    return {"used_count": blobs.record_use(doc_id, body.run_id)}


@app.delete("/api/org/docs/{doc_id}")
def org_doc_delete(doc_id: int, v: tuple = Depends(require_admin)):
    org = _caller_org(v)
    _org_doc_or_404(doc_id, org["id"])
    blobs.delete(doc_id)
    return {"ok": True}


# Team & access -----------------------------------------------------------------------------------
@app.get("/api/org/members")
def org_members(v: tuple = Depends(require_authed)):
    return _members_payload(_caller_org(v)["id"], (v[0] or "").lower())


@app.post("/api/org/members")
def org_member_invite(body: OrgMemberIn, v: tuple = Depends(require_admin)):
    org = _caller_org(v)
    if not (body.email or "").strip():
        raise HTTPException(status_code=400, detail="email required")
    users.invite_member(body.email, org["id"], role=body.role or "member",
                        designation=body.designation, by=v[0] or "")
    return _members_payload(org["id"], (v[0] or "").lower())


@app.patch("/api/org/members/{email}")
def org_member_update(email: str, body: OrgMemberPatchIn, v: tuple = Depends(require_admin)):
    org = _caller_org(v)
    member = users.get_user(email)
    if not member or member.get("org_id") != org["id"]:
        raise HTTPException(status_code=404, detail="member not found")
    if body.role in ("admin", "member"):
        users.upsert(email, body.role, by=v[0] or "")
    if body.designation is not None:
        users.set_profile(email, designation=body.designation)
    return _members_payload(org["id"], (v[0] or "").lower())


@app.delete("/api/org/members/{email}")
def org_member_remove(email: str, v: tuple = Depends(require_admin)):
    org = _caller_org(v)
    member = users.get_user(email)
    if not member or member.get("org_id") != org["id"]:
        raise HTTPException(status_code=404, detail="member not found")
    users.remove(email)
    return _members_payload(org["id"], (v[0] or "").lower())


# Usage & billing ---------------------------------------------------------------------------------
@app.get("/api/org/usage")
def org_usage(v: tuple = Depends(require_authed)):
    org = _caller_org(v)
    member_emails = {m["email"].lower() for m in users.list_org_members(org["id"])}
    runs = [r for r in console.list_runs(owner=None)
            if (r.get("owner") or "").lower() in member_emails]
    return billing.summarize(org, runs)


@app.patch("/api/org/billing")
def org_billing(body: OrgBillingIn, v: tuple = Depends(require_admin)):
    org = _caller_org(v)
    fields = {k: val for k, val in body.model_dump().items() if val is not None}
    if fields:
        users.update_org(org["id"], **fields)
    org = users.get_org(org["id"])
    return {"plan": org["plan"], "monthly_budget_cap": org["monthly_budget_cap"]}


# ── Auth exchange ───────────────────────────────────────────────────────────────────────────
@app.get("/api/auth/config")
def auth_config():
    # Public (no session): the React SPA reads this on boot to know whether auth is on and to get
    # the Google OAuth web client id for the sign-in button. client_id is already public (it's
    # embedded in the GIS button); enabled carries no secret.
    return {"enabled": auth.enabled(), "client_id": auth.client_id()}


@app.post("/api/auth/google")
def google_login(body: GoogleLoginIn):
    # The login exchange is the ONLY route reachable without a session.
    token = auth.login(body.credential or "")
    if not token:
        raise HTTPException(status_code=403, detail="not authorized")
    resp = JSONResponse({"ok": True})
    resp.set_cookie(auth.COOKIE, token, max_age=auth.SESSION_TTL, path="/",
                    httponly=True, samesite="lax")
    return resp


# ── Runs: list + create ───────────────────────────────────────────────────────────────────────
@app.get("/api/runs")
def runs_list(v: tuple = Depends(require_authed)):
    owner = None if v[1] == "admin" else v[0]
    return {"runs": console.list_runs(owner=owner)}


@app.post("/api/runs")
def runs_create(body: RunCreateIn, v: tuple = Depends(require_authed)):
    creds = {}
    if body.railway_token:
        creds["RAILWAY_TOKEN"] = body.railway_token
    if body.railway_project_id:
        creds["RAILWAY_PROJECT_ID"] = body.railway_project_id
    req = RunRequest(
        description=body.description,
        context=body.context,
        budget=float(body.budget),
        target=body.target,
        credentials=creds,
        context_files=body.files,
        runtime=body.runtime,
        planning_model=body.planning_model,
        impl_model=body.impl_model,
        name=body.project_name,
        gated=bool(body.gated),
        owner=v[0] or "",
    )
    try:
        return {"run_id": console.start_run(req)}
    except ValueError as e:           # duplicate project name
        raise HTTPException(status_code=409, detail=str(e))


# ── Drafts (Option C onboarding) ──────────────────────────────────────────────────────────────
@app.post("/api/drafts")
def create_draft(body: DraftCreateIn, v: tuple = Depends(require_authed)):
    """Mint a durable draft run at the START of onboarding (the form is the sole eager creator on
    mount). Returns its canonical run-<8hex> id; the form passes it into every subsequent
    PATCH/attach/promote and into /api/chat so the rail and the form share ONE draft."""
    run_id = console.create_draft(owner=v[0] or "", name=body.project_name,
                                  runtime=body.runtime, planning_model=body.planning_model,
                                  impl_model=body.impl_model)
    return {"run_id": run_id}


# ── Run-scoped GETs ─────────────────────────────────────────────────────────────────────────
@app.get("/api/runs/{rid}")
def run_status(rid: str, v: tuple = Depends(authorize_run)):
    return console.status(rid)


@app.get("/api/runs/{rid}/evidence")
def run_evidence(rid: str, v: tuple = Depends(authorize_run)):
    return console.evidence(rid)


@app.get("/api/runs/{rid}/graph")
def run_graph(rid: str, v: tuple = Depends(authorize_run)):
    return console.graph(rid)


@app.get("/api/runs/{rid}/tickets")
def run_tickets(rid: str, v: tuple = Depends(authorize_run)):
    """Build-ticket projection for the kanban view (empty before Stage 2)."""
    return console.tickets(rid)


@app.get("/api/runs/{rid}/deployments")
def run_deployments(rid: str, v: tuple = Depends(authorize_run)):
    """Per-deliverable deployments (a run may ship multiple apps)."""
    return console.deployments(rid)


@app.get("/api/runs/{rid}/brief")
def run_brief(rid: str, v: tuple = Depends(authorize_run)):
    """The structured onboarding brief (shared by the chat interview and the brief form)."""
    from software_factory.brief import coverage as _cov
    brief = console.draft_brief(rid)
    return {"brief": brief, "coverage": _cov(brief)}


@app.put("/api/runs/{rid}/brief")
def update_run_brief(rid: str, body: dict, v: tuple = Depends(authorize_run)):
    """Edit the brief from the form. Body: {section: text, ...} (only known sections persist)."""
    from software_factory.brief import BRIEF_SECTIONS
    sections = {k: v2 for k, v2 in (body or {}).items() if k in BRIEF_SECTIONS}
    cov = console.update_draft_brief(rid, sections)
    return {"brief": console.draft_brief(rid), "coverage": cov}


@app.get("/api/runs/{rid}/events")
def run_events(rid: str, v: tuple = Depends(authorize_run)):
    return {"events": console.events(rid)}


@app.get("/api/runs/{rid}/artifact")
def run_artifact(rid: str, path: str = "", raw: str = "", v: tuple = Depends(authorize_run)):
    result = console.artifact(rid, path)
    if raw and "content" in result:
        # Raw mode: serve the file itself (right Content-Type) so e.g. the architecture SVG
        # opens full-size in its own browser tab.
        ctype = {"svg": "image/svg+xml", "html": "text/html", "json": "application/json",
                 "md": "text/markdown"}.get(path.rsplit(".", 1)[-1].lower(), "text/plain")
        return Response(content=result["content"].encode(), media_type=f"{ctype}; charset=utf-8")
    return result


@app.get("/api/runs/{rid}/log")
def run_log(rid: str, full: str = "", v: tuple = Depends(authorize_run)):
    if full == "json":
        return {"log": console.read_log(rid, max_bytes=None)}
    if full:
        body = console.read_log(rid, max_bytes=None)
        return PlainTextResponse(body, media_type="text/plain; charset=utf-8",
                                 headers={"Content-Disposition": f'attachment; filename="{rid}.log"'})
    return console.read_log_envelope(rid)


@app.get("/api/runs/{rid}/deps")
def run_deps(rid: str, v: tuple = Depends(authorize_run)):
    return console.stage2_artifacts(rid)


# ── Project View (PRD §2.5): Overview + Documents aggregates ─────────────────────────────────────
@app.get("/api/runs/{rid}/overview")
def run_overview(rid: str, v: tuple = Depends(authorize_run)):
    status = console.status(rid)
    tickets = console.tickets(rid)["tickets"]
    deployments = console.deployments(rid)["deployments"]
    owner = status.get("owner") or ""
    org = users.org_for_user(owner) if owner else None
    has_verification = bool(status.get("done")) or any(d.get("verified") for d in deployments)
    in_build = (status.get("stage") or 0) >= 2 and not status.get("done")
    docs = project_view.documents(blobs.list_for("run", rid), console.artifacts(rid))
    return {
        "brief": project_view.brief_block(console.draft_project(rid), status,
                                          console.run_created(rid)),
        "build": project_view.build_status(status, tickets),
        "services": project_view.services_at_work(org, deployments, status.get("impl_model") or "",
                                                  has_verification, in_build),
        "agents": project_view.agents_projection(console.agents(rid), tickets),
        "org": ({"name": org["name"], "industry": org.get("industry"),
                 "connected_systems": org.get("connected_systems", [])} if org else None),
        "materials_count": len(docs["uploaded"]),
        "produced_count": len(docs["produced"]),
    }


@app.get("/api/runs/{rid}/documents")
def run_documents(rid: str, v: tuple = Depends(authorize_run)):
    return project_view.documents(blobs.list_for("run", rid), console.artifacts(rid))


# ── Run-scoped actions ──────────────────────────────────────────────────────────────────────
@app.post("/api/runs/{rid}/continue")
def run_continue(rid: str, body: ContinueIn, v: tuple = Depends(authorize_run)):
    return console.continue_run(rid, body.gate)


@app.post("/api/runs/{rid}/deps")
def run_submit_deps(rid: str, body: DepsIn, v: tuple = Depends(authorize_run)):
    return console.submit_deps(rid, body.deps)


@app.post("/api/runs/{rid}/stage2")
def run_stage2(rid: str, v: tuple = Depends(authorize_run)):
    result = console.start_stage2(rid)
    if result:
        return {"run_id": result, "stage": 2}
    raise HTTPException(status_code=409, detail="stage1 not done or MCP unhealthy")


@app.post("/api/runs/{rid}/stage3")
def run_stage3(rid: str, body: Stage3In, v: tuple = Depends(authorize_run)):
    result = console.start_stage3(rid, extra_creds=extract_env_creds(body.creds or {}))
    if result:
        return {"run_id": result, "stage": 3}
    raise HTTPException(status_code=409, detail="stage2 not done or deps not satisfied")


@app.post("/api/runs/{rid}/budget")
def run_budget(rid: str, body: BudgetIn, v: tuple = Depends(authorize_run)):
    try:
        ceiling = float(body.ceiling)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="ceiling (number) required")
    return console.raise_budget(rid, ceiling)


@app.post("/api/runs/{rid}/retry")
def run_retry(rid: str, body: RetryIn, v: tuple = Depends(authorize_run)):
    result = console.retry_stage(rid, int(body.stage), extra_creds=body.creds)
    if result:
        return {"run_id": result, "retried_stage": int(body.stage)}
    raise HTTPException(status_code=409, detail="cannot retry: invalid stage or prior stage not done")


@app.post("/api/runs/{rid}/release")
def run_release(rid: str, v: tuple = Depends(authorize_run)):
    if console.release_run(rid):
        return {"run_id": rid, "released": True}
    raise HTTPException(status_code=409, detail="not held")


# ── Draft write-through + handoff (Option C onboarding; drafts only) ──────────────────────────
@app.patch("/api/runs/{rid}/draft")
def patch_draft(rid: str, body: DraftPatchIn, v: tuple = Depends(authorize_run)):
    """Structured project write-through: {name?, goal?, scope?}. Server composes the canonical
    description (goal + scope-of-work line). Call debounced/on-blur, NOT per keystroke."""
    if not console.is_draft(rid):
        raise HTTPException(status_code=409, detail="not a draft (already promoted)")
    return console.set_draft_project(rid, name=body.name, goal=body.goal, scope=body.scope)


@app.post("/api/runs/{rid}/attach")
def attach_draft(rid: str, body: AttachIn, v: tuple = Depends(authorize_run)):
    """Attach project materials (walkthrough video / documents) to the draft's input/."""
    if not console.is_draft(rid):
        raise HTTPException(status_code=409, detail="not a draft (already promoted)")
    return {"attached": console.attach_to_draft(rid, body.files or [])}


@app.post("/api/runs/{rid}/promote")
def promote_draft(rid: str, body: PromoteIn, v: tuple = Depends(authorize_run)):
    """Hand off to the factory: promote the draft into a real run and launch Stage 1. The composed
    state.description + accumulated brief are the payload (description override optional)."""
    if not console.is_draft(rid):
        raise HTTPException(status_code=409, detail="not a draft (already promoted)")
    try:
        run_id = console.promote_draft(rid, description=body.description, target=body.target)
    except ValueError as e:                # duplicate project name
        raise HTTPException(status_code=409, detail=str(e))
    return {"run_id": run_id, "status": "started"}


# ── Chat ────────────────────────────────────────────────────────────────────────────────────
@app.post("/api/chat")
async def chat(body: ChatIn, v: tuple = Depends(require_authed)):
    if not _chat_runner:
        raise HTTPException(status_code=503,
                            detail="no OPENAI_API_KEY or OPENROUTER_API_KEY — chat unavailable")
    run_id = body.run_id
    # Messaging an EXISTING run requires ownership; a new conversation mints a durable DRAFT
    # (canonical run-<8hex>) up front so the interview persists to chat.jsonl from turn one and
    # survives a refresh/restart. The draft is invisible to the pipeline poller until promotion.
    if run_id and not _can_see(v, run_id):
        raise HTTPException(status_code=403, detail="forbidden")
    if not run_id:
        run_id = console.create_draft(owner=v[0] or "", name=body.project_name or "",
                                      runtime=body.runtime, planning_model=body.planning_model,
                                      impl_model=body.impl_model)
    # Files/images attached during the interview persist into the draft now (wireframes survive),
    # so they're in input/ for Stage 1 regardless of which turn they arrived on. Drafts only.
    if (body.files or body.images) and console.is_draft(run_id):
        try:
            console.attach_to_draft(run_id, (body.files or []) + (body.images or []))
        except Exception:
            pass  # a bad attachment must not 500 the chat turn

    user_msg = ChatMessage(role="user", content=body.message, msg_type="text", ts=time.time())
    if body.files:
        user_msg.metadata["files"] = [f.get("name", "file") for f in body.files]
    if body.images:
        user_msg.metadata["images"] = [i.get("name", "image") for i in body.images]

    try:
        result_run_id, response_msgs = await _chat_runner.handle_message(
            run_id, body.message, body.files, body.images, runtime=body.runtime,
            planning_model=body.planning_model, impl_model=body.impl_model,
            project_name=body.project_name, gated=body.gated,
            owner=v[0] or "", role=v[1] or "member")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not run_id:
        run_id = result_run_id
    if run_id:
        store = ChatStore(_chat_path(run_id))
        store.append(user_msg)
        for m in response_msgs:
            store.append(m)
        _push_sse(run_id, response_msgs)

    return {"run_id": run_id, "messages": [m.to_dict() for m in response_msgs]}


@app.get("/api/chat/{rid}/history")
def chat_history(rid: str, v: tuple = Depends(authorize_run)):
    store = ChatStore(_chat_path(rid))
    return {"messages": [m.to_dict() for m in store.history()]}


@app.post("/api/chat/{rid}/deps")
def chat_deps(rid: str, body: DepsIn, v: tuple = Depends(authorize_run)):
    deps = body.deps
    result = console.submit_deps(rid, deps)
    dep_msg = ChatMessage(role="user", content=f"Provided: {', '.join(deps.keys())}",
                          msg_type="dep_submit", ts=time.time(),
                          metadata={"dep_names": list(deps.keys())})
    store = ChatStore(_chat_path(rid))
    store.append(dep_msg)
    if result.get("satisfied"):
        console.start_stage3(rid, extra_creds=extract_env_creds(deps))
        launch_msg = ChatMessage(role="system", content="Dependencies received. Build stage launching.",
                                 msg_type="status_update", ts=time.time(),
                                 metadata={"run_id": rid, "stage": 3})
        store.append(launch_msg)
        _push_sse(rid, [dep_msg, launch_msg])
    else:
        _push_sse(rid, [dep_msg])
    return result


@app.get("/api/chat/{rid}/stream")
async def chat_stream(rid: str, v: tuple = Depends(authorize_run)):
    """SSE for real-time pipeline updates. Drains a per-client queue fed by _push_sse (from the
    poller thread + chat/deps handlers); keepalive every 2s."""
    q: list[str] = []
    with _sse_lock:
        _sse_clients.setdefault(rid, []).append(q)

    async def gen():
        try:
            while True:
                if q:
                    yield q.pop(0)
                else:
                    yield ": keepalive\n\n"
                    await asyncio.sleep(2)
        finally:
            with _sse_lock:
                clients = _sse_clients.get(rid, [])
                if q in clients:
                    clients.remove(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8765"))
    host = os.environ.get("SF_BIND", "127.0.0.1")
    uvicorn.run(app, host=host, port=port)
