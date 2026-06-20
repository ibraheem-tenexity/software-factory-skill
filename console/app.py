"""FastAPI shell around software_factory.console (Phase 2 of docs/plans/fastapi-db-replacement.md).

Replaces the hand-rolled stdlib BaseHTTPRequestHandler (console/server.py). Same routes, same JSON
contract, same auth/ownership rules — now with Pydantic bodies, dependency-injected auth, an
APIRouter, SSE via StreamingResponse, and the background poller started in the app lifespan.

  GET  /                       -> UI (graph + chat panel)  [login page when auth-enabled + unauthed]
  POST /api/projects               -> launches a run (legacy form path)
  GET  /api/projects/<id>          -> live status
  GET  /api/projects/<id>/evidence -> proof-of-run bundle
  POST /api/chat               -> send chat message, get agent response
  GET  /api/chat/<id>/history  -> full chat history for a run
  POST /api/chat/<id>/deps     -> submit dep values securely
  GET  /api/chat/<id>/stream   -> SSE for real-time pipeline updates

Run:  uvicorn console.app:app --host 0.0.0.0 --port 8765   (or python3 console/app.py)
"""
import asyncio
import base64
import contextlib
import datetime
import json
import os
import sys
import threading
import time

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from software_factory.console import Console, ProjectRequest  # noqa: E402
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
from software_factory import tenexity_os  # noqa: E402
from software_factory.users import UserStore  # noqa: E402
from software_factory.blobs import BlobStore  # noqa: E402
from software_factory.agent_prompts import PromptStore  # noqa: E402
from software_factory.registries import ToolStore, AgentRegistryStore  # noqa: E402

PROJECTS_DIR = os.environ.get("SF_PROJECTS_DIR", os.path.join(os.path.dirname(__file__), "..", ".projects"))
HERE = os.path.dirname(__file__)
console = Console(PROJECTS_DIR)

# User directory (roles + login membership). Seeds env SF_ADMIN_EMAILS as admins and backs
# auth's role/membership decisions; without it auth falls back to the env lists.
users = UserStore()
auth.register_user_store(users.is_member, users.get_role)

# Blob manifest — org knowledge-base docs + run-scoped uploaded materials (bytes live in storage).
blobs = BlobStore()

# Editable agent system prompts (Tenexity OS §3.4) — stored/served, not yet applied to live agents.
prompts = PromptStore()

# Tools/MCP registry + agent identity registry (§3.4/§3.5) — real datastore (seeded), CRUD-able.
tool_store = ToolStore()
agent_store = AgentRegistryStore()

# The concierge runs on OpenAI (gpt-4o) or OpenRouter (Kimi) — either key enables chat.
_has_chat_key = bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENROUTER_API_KEY"))
_chat_runner = ChatAgentRunner(console, users) if _has_chat_key else None

_sse_clients: dict[str, list] = {}
_sse_lock = threading.Lock()
_project_stages: dict[str, int] = {}


def _chat_path(project_id: str) -> str:
    return os.path.join(PROJECTS_DIR, project_id, "chat.jsonl")


def _push_sse(project_id: str, msgs: list[ChatMessage]):
    """Push messages to all SSE clients watching this run."""
    with _sse_lock:
        clients = _sse_clients.get(project_id, [])
    for msg in msgs:
        data = json.dumps(msg.to_dict())
        for q in clients:
            q.append(f"data: {data}\n\n")


_stage2_launched: set = set()
_stage3_launched: set = set()


def _auto_advance(pid: str):
    """SPEC §1+§3: flip stage-done (gate + finished process) and launch the next stage, so runs
    advance with no manual nudge. Stage 2 auto-launches when Stage 1 is done; deps auto-satisfy
    when no human secret is needed; Stage 3 auto-launches once deps are satisfied. Launch guards
    are marked ONLY on success so a refusal (e.g. prior process still alive) retries next tick."""
    try:
        if not console.is_pipeline_project(pid):
            return  # resurfaced pre-redesign dir (empty project store) — never auto-advance/zombie-launch it
        if console.detect_stage1_done(pid):
            s = console.status(pid)
            if s.get("stage") == 1 and pid not in _stage2_launched:
                if console.start_stage2(pid):
                    _stage2_launched.add(pid)
        if console.detect_stage2_done(pid):  # flips stage2_done + parses required tokens
            console.maybe_autosatisfy_deps(pid)   # SPEC §3: no 'provide' token -> no pause
            s = console.status(pid)
            if s.get("deps_satisfied") and s.get("stage") == 2 and pid not in _stage3_launched:
                if console.start_stage3(pid):
                    _stage3_launched.add(pid)
        console.detect_stage3_done(pid)  # marks done ONLY with a recorded passing Playwright verification
    except Exception:
        pass


_narrated: set = set()
# project_id -> crash auto-resume attempts, bounded per server life. Configurable: long opencode
# sessions (multi-hour Kimi build/test loops) crash more often than claude's — run-b594a5f4
# exhausted 2 resumes mid-test-phase and stalled 12h. The bound exists to stop crash loops,
# not to ration recovery; budget enforcement is the real spend brake.
_AUTO_RESUME_MAX = int(os.environ.get("SF_AUTO_RESUME_MAX", "2") or 2)
_auto_resumed: dict = {}


def _append_notifications(pid: str, msgs):
    """Persist + push stage notifications, deduped against the persisted chat history —
    a restarted server re-walks stage transitions and re-fired old notifications AFTER
    newer messages, scrambling the chat panel's chronology (run-45b8c4d5)."""
    store = ChatStore(_chat_path(pid))
    try:
        seen = {m.content for m in store.history()}
    except Exception:
        seen = set()
    fresh = [m for m in msgs if m.content not in seen]
    for m in fresh:
        store.append(m)
    if fresh:
        _push_sse(pid, fresh)


def _narrate(pid: str, key: str, text: str):
    """SPEC §6: deterministic chat-panel narration — one message per (run, event), no LLM.
    Dedup survives server restarts by checking the persisted chat history, not just memory."""
    if (pid, key) in _narrated:
        return
    _narrated.add((pid, key))
    store = ChatStore(_chat_path(pid))
    try:
        if any(m.content == text for m in store.history()):
            return  # already narrated in a previous server life
    except Exception:
        pass
    msg = ChatMessage(role="assistant", content=text)
    store.append(msg)
    _push_sse(pid, [msg])
    # Operator email on the four operator-relevant events (done / depswait / budget / crash) —
    # placed AFTER the dedup so an email fires at most once per (run, event). Fire-and-forget:
    # notify.send never raises and must never block the poller.
    if notify.should_email(key):
        threading.Thread(
            target=notify.send,
            args=(f"[factory] {pid}: {text[:90]}", f"{text}\n\nrun: {pid}"),
            daemon=True,
        ).start()


def _narrate_project(pid: str, st: dict):
    links = console.project_links(pid)
    if links.get("repo"):
        _narrate(pid, "repo", f"📦 Source repo: {links['repo']}")
    if st.get("stage1_done"):
        _narrate(pid, "s1", "✅ Research complete — design & architecture starting.")
    if st.get("stage2_done"):
        if st.get("deps_satisfied"):
            _narrate(pid, "deps", "🔓 Design complete — dependencies satisfied, build starting.")
        elif st.get("deps_required"):
            need = [n for n in (st.get("deps_required") or [])]
            _narrate(pid, "depswait", "⏸ Design complete — waiting for you to supply: " + ", ".join(need))
    if links.get("live") and not st.get("done"):
        _narrate(pid, "deployed", f"🚀 Deployed (verifying): {links['live']}")
    if st.get("done"):
        live = st.get("deploy_url") or links.get("live") or ""
        repo = links.get("repo") or ""
        msg = f"✅ Done — Live demo: {live}" + (f" · 📦 Repo: {repo}" if repo else "")
        try:
            creds = console.demo_credentials(pid)
        except Exception:
            creds = None
        if creds:
            # The seeded throwaway demo login (SPEC §6) — without it an auth'd app can't be demoed.
            msg += "\n🔑 Demo login:\n" + creds
        _narrate(pid, "done", msg)


_tracer = tracing.Tracer()
_health_bad_since = [None]  # [-]: None = healthy; float = first failure ts (alert once)


def _health() -> dict:
    """Liveness for probes + the console dot. pg=None means sqlite mode (nothing to check)."""
    import shutil as _sh
    pg = None
    if (os.environ.get("SF_DB") or "").lower() == "postgres":
        from software_factory import dbshim
        try:
            dbshim.registry_projects()
            pg = True
        except Exception:
            pg = False
    try:
        free_mb = int(_sh.disk_usage(PROJECTS_DIR).free / 1048576)
    except OSError:
        free_mb = -1
    ok = (pg is not False) and free_mb > 200
    return {"ok": ok, "pg": pg, "disk_free_mb": free_mb}


def _poll_transitions():
    """Background thread: auto-advance stages, enforce the per-project budget, narrate progress."""
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
            for project_info in console.list_projects():
                pid = project_info.get("id") or project_info.get("project_id", "")
                if not pid:
                    continue
                if project_info.get("held"):  # gated hold: nothing to advance/enforce/narrate
                    continue
                _auto_advance(pid)
                st = console.status(pid)
                # LLM traces: ship this run's new log lines to Langfuse (no-op without keys).
                _tracer.tick(pid, os.path.join(PROJECTS_DIR, pid, "project.log"),
                             meta={"runtime": st.get("runtime", "")})
                try:
                    if not st.get("done") and console.enforce_budget(pid):
                        _narrate(pid, "budget-%d" % int(console._budget_ceiling(pid)),
                                 "⏸ Budget cap reached — stage stopped (state preserved). "
                                 "Raise the cap to continue.")
                    # SPEC §3 zero-touch: resume a crashed stage automatically (bounded).
                    if not st.get("done") and _auto_resumed.get(pid, 0) < _AUTO_RESUME_MAX:
                        if console.auto_resume_dead_stage(pid):
                            _auto_resumed[pid] = _auto_resumed.get(pid, 0) + 1
                            _narrate(pid, "resume-%d" % _auto_resumed[pid],
                                     "⚠️ Stage process died mid-flight — auto-resumed "
                                     f"(attempt {_auto_resumed[pid]}/{_AUTO_RESUME_MAX}).")
                    _narrate_project(pid, st)
                except Exception:
                    pass
                if st.get("done") or st.get("phase") == "pending":
                    continue
                prev = _project_stages.get(pid, 0)
                cur = st.get("stage", 1)
                if cur != prev:
                    _project_stages[pid] = cur
                    if _chat_runner:
                        _append_notifications(pid, _chat_runner.check_and_notify(pid, prev_stage=prev))
                if st.get("done") and prev > 0:
                    if _chat_runner:
                        _append_notifications(pid, _chat_runner.check_and_notify(pid, prev_stage=cur))
                    _project_stages.pop(pid, None)
        except Exception:
            pass


def _boot():
    """One-time boot work that lived in the old server's __main__ block: announce the runtime
    user, quarantine debris, prod pg-backfill, and owner-backfill. Runs in the app lifespan."""
    import getpass
    print(f"[runner] uid={os.getuid()} user={getpass.getuser()} home={os.environ.get('HOME')}", flush=True)
    if not _has_chat_key:
        print("[warn] no OPENAI_API_KEY or OPENROUTER_API_KEY — chat agent disabled, API-only mode")
    # Quarantine debris under projects_dir: agents misusing db verbs once created dirs like
    # "build-plan.md/project store" on the volume — moved aside (never deleted), so discovery and
    # the boot backfill only ever see real runs.
    try:
        from software_factory.console import PROJECT_ID_RE
        qdir = os.path.join(PROJECTS_DIR, "_quarantine")
        for name in os.listdir(PROJECTS_DIR):
            p = os.path.join(PROJECTS_DIR, name)
            if os.path.isdir(p) and name != "_quarantine" and not PROJECT_ID_RE.fullmatch(name):
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
    print(f"software-factory console (FastAPI) — runs in {os.path.abspath(PROJECTS_DIR)}", flush=True)
    yield


app = FastAPI(title="software-factory console", lifespan=lifespan)


# ── Structured access log ───────────────────────────────────────────────────────────────────
# One JSON line per response on stdout — Railway captures stdout natively, so `railway logs`
# becomes greppable by route/status/project_id. Mirrors the old Handler._send logging.
@app.middleware("http")
async def _access_log(request: Request, call_next):
    t0 = time.time()
    response = await call_next(request)
    try:
        path = request.url.path
        pid = path.split("/api/projects/")[1].split("/")[0] if "/api/projects/" in path else ""
        print(json.dumps({"ts": round(time.time(), 3), "method": request.method,
                          "path": path, "status": response.status_code, "project_id": pid,
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


def _can_see(v: tuple, project_id: str) -> bool:
    """Ownership gate enforced on EVERY run-scoped route — filtering the list is not enough,
    a member could fetch another's run by URL. Admin/service = all; member = own only."""
    email, role, ok = v
    if not ok:
        return False
    if role == "admin":
        return True
    return bool(project_id) and console.project_owner(project_id) == (email or "").lower()


def authorize_project(pid: str, v: tuple = Depends(require_authed)) -> tuple:
    """For run-scoped routes carrying {pid}: 403 unless admin/service or the run's owner."""
    if not _can_see(v, pid):
        raise HTTPException(status_code=403, detail="forbidden")
    return v


def require_admin(v: tuple = Depends(require_authed)) -> tuple:
    if v[1] != "admin":
        raise HTTPException(status_code=403, detail="admin only")
    return v


def require_staff(v: tuple = Depends(require_authed)) -> tuple:
    """Tenexity OS gate (§3): platform staff ONLY — cross-tenant data. A customer org-admin does
    NOT qualify. Admits: service token / auth-disabled (viewer email=None, role=admin), an
    SF_ADMIN_EMAILS operator, or a user with the `tenexity` flag set."""
    email, role, _ = v
    if email is None and role == "admin":          # service token or auth disabled = platform access
        return v
    em = (email or "").lower()
    env_admins = {e.strip().lower() for e in os.environ.get("SF_ADMIN_EMAILS", "").split(",") if e.strip()}
    if em and em in env_admins:
        return v
    u = users.get_user(em)
    if u and u.get("tenexity") in (1, True):
        return v
    raise HTTPException(status_code=403, detail="staff only")


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


class OrgDocPatchIn(BaseModel):
    name: str | None = None
    tag: str | None = None


class OrgDocUseIn(BaseModel):
    project_id: str = ""


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
    project_id: str | None = None
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


class ProjectPatchIn(BaseModel):
    name: str | None = None
    description: str | None = None
    scope: list | None = None


class MaterialScopeIn(BaseModel):
    scope: str = "project"     # "project" | "org"


class Stage3In(BaseModel):
    creds: dict | None = None


class BudgetIn(BaseModel):
    ceiling: float | None = None


class RetryIn(BaseModel):
    stage: int = 0
    creds: dict | None = None


class ProjectCreateIn(BaseModel):
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
    if not (body.project_id or "").strip():
        raise HTTPException(status_code=400, detail="project_id required")
    return {"used_count": blobs.record_use(doc_id, body.project_id)}


@app.patch("/api/org/docs/{doc_id}")
def org_doc_update(doc_id: int, body: OrgDocPatchIn, v: tuple = Depends(require_admin)):
    org = _caller_org(v)
    _org_doc_or_404(doc_id, org["id"])
    blobs.update(doc_id, name=body.name, tag=body.tag)
    doc = next((d for d in blobs.list_org_docs(org["id"]) if d["id"] == doc_id), None)
    return {"doc": doc}


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
    runs = [r for r in console.list_projects(owner=None)
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
    em = auth.session_email(token)               # flip an invited allow-list user → active (§3.6)
    if em:
        users.mark_active(em)
    resp = JSONResponse({"ok": True})
    resp.set_cookie(auth.COOKIE, token, max_age=auth.SESSION_TTL, path="/",
                    httponly=True, samesite="lax")
    return resp


# ── Tenexity OS admin (PRD §3) — CROSS-TENANT, staff-gated ──────────────────────────────────────
class DemoIn(BaseModel):
    is_demo: bool = False


class PromptIn(BaseModel):
    prompt: str = ""


class InviteIn(BaseModel):
    email: str = ""
    access_type: str = "org"     # "org" | "tenexity"
    org_name: str | None = None


class AccessPatchIn(BaseModel):
    role: str | None = None
    status: str | None = None


class AgentIn(BaseModel):
    callsign: str = ""
    name: str = ""
    role: str | None = None
    model: str | None = None
    cost_tier: int = 1
    descr: str | None = None


class AgentPatchIn(BaseModel):
    name: str | None = None
    role: str | None = None
    model: str | None = None
    cost_tier: int | None = None
    descr: str | None = None


class ToolIn(BaseModel):
    name: str = ""
    type: str | None = None
    provider: str | None = None
    scope: str | None = None
    auth: str | None = None
    status: str = "available"


class ToolPatchIn(BaseModel):
    name: str | None = None
    type: str | None = None
    provider: str | None = None
    scope: str | None = None
    auth: str | None = None
    status: str | None = None


class ClientIn(BaseModel):
    name: str = ""
    industry: str | None = None
    website: str | None = None


class ClientPatchIn(BaseModel):
    name: str | None = None
    industry: str | None = None
    headcount: str | None = None
    revenue: str | None = None
    location: str | None = None
    website: str | None = None
    plan: str | None = None
    monthly_budget_cap: float | None = None


def _midnight_epoch() -> float:
    now = datetime.datetime.now()
    return now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


def _admin_context():
    """Shared cross-tenant reads: all projects, all orgs, members-by-org, owner→org-name map."""
    runs = console.list_projects(owner=None)
    orgs = users.list_orgs()
    members_by_org = {o["id"]: users.list_org_members(o["id"]) for o in orgs}
    o2o = tenexity_os.owner_to_org(orgs, members_by_org)
    return runs, orgs, members_by_org, o2o


@app.get("/api/admin/overview")
def admin_overview(v: tuple = Depends(require_staff)):
    runs, orgs, _members, o2o = _admin_context()
    rollups = tenexity_os.agent_rollups()
    roster = tenexity_os.agent_roster(agent_store.all(), rollups, prompts.all())
    return tenexity_os.overview(orgs, runs, rollups, tenexity_os.agents_active_count(),
                                tenexity_os.today_burn(_midnight_epoch()), roster, o2o)


@app.get("/api/admin/clients")
def admin_clients(v: tuple = Depends(require_staff)):
    runs, orgs, members_by_org, _o2o = _admin_context()
    return {"clients": tenexity_os.client_rows(orgs, runs, members_by_org,
                                               tenexity_os.open_tickets_by_project())}


@app.get("/api/admin/projects")
def admin_projects(mode: str = "all", v: tuple = Depends(require_staff)):
    runs, _orgs, _members, o2o = _admin_context()
    return {"projects": tenexity_os.project_rows(runs, o2o, tenexity_os.ticket_counts_by_project(),
                                                 mode=mode)}


@app.patch("/api/admin/projects/{pid}")
def admin_set_demo(pid: str, body: DemoIn, v: tuple = Depends(require_staff)):
    return {"project_id": pid, "is_demo": console.set_demo(pid, body.is_demo)}


# Agents (identity from agent_registry table; cost/success merged live; prompt editable) ----------
@app.get("/api/admin/agents")
def admin_agents(v: tuple = Depends(require_staff)):
    return {"agents": tenexity_os.agent_roster(agent_store.all(), tenexity_os.agent_rollups(),
                                               prompts.all())}


@app.get("/api/admin/agents/{callsign}")
def admin_agent(callsign: str, v: tuple = Depends(require_staff)):
    cs = callsign.upper()
    card = next((a for a in tenexity_os.agent_roster(agent_store.all(), tenexity_os.agent_rollups(),
                                                     prompts.all()) if a["callsign"] == cs), None)
    if not card:
        raise HTTPException(status_code=404, detail="unknown agent")
    p = prompts.get(cs)
    return {**card, "prompt": p["prompt"] if p else "",
            "prompt_applied": False,   # saved here but NOT yet wired into the live pipeline
            "tools": [t for t in tool_store.all() if t["status"] == "connected"],
            "activity": []}


@app.post("/api/admin/agents")
def admin_agent_create(body: AgentIn, v: tuple = Depends(require_staff)):
    cs = (body.callsign or "").strip().upper()
    if not cs or not (body.name or "").strip():
        raise HTTPException(status_code=400, detail="callsign + name required")
    if agent_store.get(cs):
        raise HTTPException(status_code=409, detail="callsign exists")
    return {"agent": agent_store.create(cs, body.name, role=body.role, model=body.model,
                                        cost_tier=body.cost_tier, descr=body.descr)}


@app.patch("/api/admin/agents/{callsign}")
def admin_agent_update(callsign: str, body: AgentPatchIn, v: tuple = Depends(require_staff)):
    cs = callsign.upper()
    if not agent_store.get(cs):
        raise HTTPException(status_code=404, detail="unknown agent")
    fields = {k: val for k, val in body.model_dump().items() if val is not None}
    return {"agent": agent_store.update(cs, fields)}


@app.delete("/api/admin/agents/{callsign}")
def admin_agent_delete(callsign: str, v: tuple = Depends(require_staff)):
    cs = callsign.upper()
    if not agent_store.get(cs):
        raise HTTPException(status_code=404, detail="unknown agent")
    agent_store.delete(cs)
    return {"ok": True}


@app.patch("/api/admin/agents/{callsign}/prompt")
def admin_set_prompt(callsign: str, body: PromptIn, v: tuple = Depends(require_staff)):
    row = prompts.set(callsign.upper(), body.prompt or "", by=v[0] or "")
    return {"callsign": row["callsign"], "prompt": row["prompt"], "version": row["version"],
            "updated_by": row["updated_by"], "updated_at": row["updated_at"],
            "applied": False}   # honest: stored, not yet applied to live agents


# Tools / MCP registry (real datastore) -----------------------------------------------------------
@app.get("/api/admin/tools")
def admin_tools(v: tuple = Depends(require_staff)):
    return {"tools": [{**t, "used": None} for t in tool_store.all()]}


@app.post("/api/admin/tools")
def admin_tool_create(body: ToolIn, v: tuple = Depends(require_staff)):
    if not (body.name or "").strip():
        raise HTTPException(status_code=400, detail="name required")
    return {"tool": tool_store.create(body.name, type=body.type, provider=body.provider,
                                      scope=body.scope, auth=body.auth, status=body.status)}


@app.patch("/api/admin/tools/{tool_id}")
def admin_tool_update(tool_id: int, body: ToolPatchIn, v: tuple = Depends(require_staff)):
    fields = {k: val for k, val in body.model_dump().items() if val is not None}
    tool = tool_store.update(tool_id, fields)
    if not tool:
        raise HTTPException(status_code=404, detail="unknown tool")
    return {"tool": tool}


@app.delete("/api/admin/tools/{tool_id}")
def admin_tool_delete(tool_id: int, v: tuple = Depends(require_staff)):
    tool_store.delete(tool_id)
    return {"ok": True}


# Clients / tenants (admin-scoped org CRUD) -------------------------------------------------------
@app.post("/api/admin/clients")
def admin_client_create(body: ClientIn, v: tuple = Depends(require_staff)):
    if not (body.name or "").strip():
        raise HTTPException(status_code=400, detail="name required")
    oid = users.create_org(body.name, industry=body.industry, website=body.website, by=v[0] or "")
    return {"client": users.get_org(oid)}


@app.patch("/api/admin/clients/{org_id}")
def admin_client_update(org_id: str, body: ClientPatchIn, v: tuple = Depends(require_staff)):
    if not users.get_org(org_id):
        raise HTTPException(status_code=404, detail="unknown org")
    fields = {k: val for k, val in body.model_dump().items() if val is not None}
    users.update_org(org_id, **fields)
    return {"client": users.get_org(org_id)}


@app.delete("/api/admin/clients/{org_id}")
def admin_client_delete(org_id: str, v: tuple = Depends(require_staff)):
    if not users.get_org(org_id):
        raise HTTPException(status_code=404, detail="unknown org")
    users.delete_org(org_id)
    return {"ok": True}


# Invites / allow-list ----------------------------------------------------------------------------
def _access_rows():
    out = []
    for u in users.list_users():
        staff = u.get("tenexity") in (1, True)
        org = users.get_org(u["org_id"]) if u.get("org_id") else None
        out.append({"email": u["email"], "type": "Tenexity" if staff else "New org",
                    "org": "Tenexity" if staff else (org["name"] if org else None),
                    "role": u["role"], "status": u.get("status") or "active"})
    return {"users": out}


@app.get("/api/admin/access")
def admin_access(v: tuple = Depends(require_staff)):
    return _access_rows()


@app.post("/api/admin/access")
def admin_invite(body: InviteIn, v: tuple = Depends(require_staff)):
    email = (body.email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="email required")
    by = v[0] or ""
    if body.access_type == "tenexity":
        users.upsert(email, "member", by=by)
        users.set_profile(email, tenexity=True)
    else:
        if not (body.org_name or "").strip():
            raise HTTPException(status_code=400, detail="org_name required for a new org")
        oid = users.create_org(body.org_name, by=by)
        users.invite_member(email, oid, role="admin", by=by)
    users.set_status(email, "invited")
    return _access_rows()


@app.patch("/api/admin/access/{email}")
def admin_access_update(email: str, body: AccessPatchIn, v: tuple = Depends(require_staff)):
    em = (email or "").strip().lower()
    if not users.get_user(em):
        raise HTTPException(status_code=404, detail="unknown user")
    if body.role in ("admin", "member"):
        users.upsert(em, body.role, by=v[0] or "")
    if body.status in ("active", "invited"):
        users.set_status(em, body.status)
    return _access_rows()


@app.delete("/api/admin/access/{email}")
def admin_access_revoke(email: str, v: tuple = Depends(require_staff)):
    users.remove((email or "").strip().lower())
    return _access_rows()


# ── Runs: list + create ───────────────────────────────────────────────────────────────────────
@app.get("/api/projects")
def projects_list(v: tuple = Depends(require_authed)):
    owner = None if v[1] == "admin" else v[0]
    return {"projects": console.list_projects(owner=owner)}


@app.post("/api/projects")
def projects_create(body: ProjectCreateIn, v: tuple = Depends(require_authed)):
    creds = {}
    if body.railway_token:
        creds["RAILWAY_TOKEN"] = body.railway_token
    if body.railway_project_id:
        creds["RAILWAY_PROJECT_ID"] = body.railway_project_id
    req = ProjectRequest(
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
        return {"project_id": console.start_project(req)}
    except ValueError as e:           # duplicate project name
        raise HTTPException(status_code=409, detail=str(e))


# ── Drafts (Option C onboarding) ──────────────────────────────────────────────────────────────
@app.post("/api/drafts")
def create_draft(body: DraftCreateIn, v: tuple = Depends(require_authed)):
    """Mint a durable draft run at the START of onboarding (the form is the sole eager creator on
    mount). Returns its canonical run-<8hex> id; the form passes it into every subsequent
    PATCH/attach/promote and into /api/chat so the rail and the form share ONE draft."""
    project_id = console.create_draft(owner=v[0] or "", name=body.project_name,
                                  runtime=body.runtime, planning_model=body.planning_model,
                                  impl_model=body.impl_model)
    return {"project_id": project_id}


# ── Run-scoped GETs ─────────────────────────────────────────────────────────────────────────
@app.get("/api/projects/{pid}")
def project_status(pid: str, v: tuple = Depends(authorize_project)):
    return console.status(pid)


@app.get("/api/projects/{pid}/evidence")
def project_evidence(pid: str, v: tuple = Depends(authorize_project)):
    return console.evidence(pid)


@app.get("/api/projects/{pid}/graph")
def project_graph(pid: str, v: tuple = Depends(authorize_project)):
    return console.graph(pid)


@app.get("/api/projects/{pid}/tickets")
def project_tickets(pid: str, v: tuple = Depends(authorize_project)):
    """Build-ticket projection for the kanban view (empty before Stage 2)."""
    return console.tickets(pid)


@app.get("/api/projects/{pid}/deployments")
def project_deployments(pid: str, v: tuple = Depends(authorize_project)):
    """Per-deliverable deployments (a run may ship multiple apps)."""
    return console.deployments(pid)


@app.get("/api/projects/{pid}/brief")
def project_brief(pid: str, v: tuple = Depends(authorize_project)):
    """The structured onboarding brief (shared by the chat interview and the brief form)."""
    from software_factory.brief import coverage as _cov
    brief = console.draft_brief(pid)
    return {"brief": brief, "coverage": _cov(brief)}


@app.put("/api/projects/{pid}/brief")
def update_project_brief(pid: str, body: dict, v: tuple = Depends(authorize_project)):
    """Edit the brief from the form. Body: {section: text, ...} (only known sections persist)."""
    from software_factory.brief import BRIEF_SECTIONS
    sections = {k: v2 for k, v2 in (body or {}).items() if k in BRIEF_SECTIONS}
    cov = console.update_draft_brief(pid, sections)
    return {"brief": console.draft_brief(pid), "coverage": cov}


@app.get("/api/projects/{pid}/events")
def project_events(pid: str, v: tuple = Depends(authorize_project)):
    return {"events": console.events(pid)}


@app.get("/api/projects/{pid}/artifact")
def project_artifact(pid: str, path: str = "", raw: str = "", v: tuple = Depends(authorize_project)):
    result = console.artifact(pid, path)
    if raw and "content" in result:
        # Raw mode: serve the file itself (right Content-Type) so e.g. the architecture SVG
        # opens full-size in its own browser tab.
        ctype = {"svg": "image/svg+xml", "html": "text/html", "json": "application/json",
                 "md": "text/markdown"}.get(path.rsplit(".", 1)[-1].lower(), "text/plain")
        return Response(content=result["content"].encode(), media_type=f"{ctype}; charset=utf-8")
    return result


@app.get("/api/projects/{pid}/log")
def project_log(pid: str, full: str = "", v: tuple = Depends(authorize_project)):
    if full == "json":
        return {"log": console.read_log(pid, max_bytes=None)}
    if full:
        body = console.read_log(pid, max_bytes=None)
        return PlainTextResponse(body, media_type="text/plain; charset=utf-8",
                                 headers={"Content-Disposition": f'attachment; filename="{pid}.log"'})
    return console.read_log_envelope(pid)


@app.get("/api/projects/{pid}/deps")
def project_deps(pid: str, v: tuple = Depends(authorize_project)):
    return console.stage2_artifacts(pid)


# ── Project View (PRD §2.5): Overview + Documents aggregates ─────────────────────────────────────
@app.get("/api/projects/{pid}/overview")
def project_overview(pid: str, v: tuple = Depends(authorize_project)):
    status = console.status(pid)
    tickets = console.tickets(pid)["tickets"]
    deployments = console.deployments(pid)["deployments"]
    owner = status.get("owner") or ""
    org = users.org_for_user(owner) if owner else None
    has_verification = bool(status.get("done")) or any(d.get("verified") for d in deployments)
    in_build = (status.get("stage") or 0) >= 2 and not status.get("done")
    docs = project_view.documents(blobs.list_for("project", pid), console.artifacts(pid))
    return {
        "brief": project_view.brief_block(console.draft_project(pid), status,
                                          console.project_created(pid)),
        "build": project_view.build_status(status, tickets),
        "services": project_view.services_at_work(org, deployments, status.get("impl_model") or "",
                                                  has_verification, in_build),
        "agents": project_view.agents_projection(console.agents(pid), tickets),
        "org": ({"name": org["name"], "industry": org.get("industry"),
                 "connected_systems": org.get("connected_systems", [])} if org else None),
        "materials_count": len(docs["uploaded"]),
        "produced_count": len(docs["produced"]),
    }


@app.get("/api/projects/{pid}/documents")
def project_documents(pid: str, v: tuple = Depends(authorize_project)):
    return project_view.documents(blobs.list_for("project", pid), console.artifacts(pid))


@app.post("/api/projects/{pid}/materials")
def project_material_upload(pid: str, body: OrgDocIn, v: tuple = Depends(authorize_project)):
    """Upload a project-scoped material at ANY phase (attach is draft-only). Shows up in
    GET /api/projects/{pid}/documents.uploaded."""
    if not (body.name or "").strip():
        raise HTTPException(status_code=400, detail="name required")
    try:
        raw = base64.b64decode(body.data_b64 or "", validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="data_b64 must be valid base64")
    key = f"materials/{body.name}"
    storage.put(pid, key, raw)
    blobs.record("project", pid, f"{pid}/{key}", name=body.name, tag=body.tag,
                 kind=_doc_kind(body.name), content_type=body.content_type,
                 size_bytes=len(raw), sha256=storage.sha256(raw))
    return project_view.documents(blobs.list_for("project", pid), console.artifacts(pid))


@app.patch("/api/projects/{pid}")
def project_update(pid: str, body: ProjectPatchIn, v: tuple = Depends(authorize_project)):
    """Rename / re-scope / re-describe a promoted project (drafts use PATCH /api/projects/{pid}/draft).
    Sending `scope` recomposes the description (goal + scope line) server-side."""
    return console.rename_project(pid, name=body.name, description=body.description, scope=body.scope)


@app.delete("/api/projects/{pid}")
def project_delete(pid: str, v: tuple = Depends(authorize_project)):
    """Soft-delete (archive) a project — hidden from every listing; discards a draft."""
    return {"project_id": pid, "archived": console.set_archived(pid, True)}


@app.patch("/api/projects/{pid}/materials/{material_id}")
def project_material_scope(pid: str, material_id: int, body: MaterialScopeIn,
                           v: tuple = Depends(authorize_project)):
    """Move an uploaded material between project-scope and org-wide (PRD §2.4). →org puts it in the
    org knowledge base (appears in /api/org/docs); →project moves it back to this project."""
    b = blobs.get_blob(material_id)
    if not b:
        raise HTTPException(status_code=404, detail="material not found")
    if body.scope == "org":
        org = users.org_for_user(console.project_owner(pid))
        if not org:
            raise HTTPException(status_code=409, detail="project owner has no org on file")
        blobs.set_scope(material_id, "org", org["id"])
    elif body.scope == "project":
        blobs.set_scope(material_id, "project", pid)
    else:
        raise HTTPException(status_code=400, detail="scope must be 'project' or 'org'")
    return project_view.documents(blobs.list_for("project", pid), console.artifacts(pid))


# ── Run-scoped actions ──────────────────────────────────────────────────────────────────────
@app.post("/api/projects/{pid}/continue")
def project_continue(pid: str, body: ContinueIn, v: tuple = Depends(authorize_project)):
    return console.continue_project(pid, body.gate)


@app.post("/api/projects/{pid}/deps")
def project_submit_deps(pid: str, body: DepsIn, v: tuple = Depends(authorize_project)):
    return console.submit_deps(pid, body.deps)


@app.post("/api/projects/{pid}/stage2")
def project_stage2(pid: str, v: tuple = Depends(authorize_project)):
    result = console.start_stage2(pid)
    if result:
        return {"project_id": result, "stage": 2}
    raise HTTPException(status_code=409, detail="stage1 not done or MCP unhealthy")


@app.post("/api/projects/{pid}/stage3")
def project_stage3(pid: str, body: Stage3In, v: tuple = Depends(authorize_project)):
    result = console.start_stage3(pid, extra_creds=extract_env_creds(body.creds or {}))
    if result:
        return {"project_id": result, "stage": 3}
    raise HTTPException(status_code=409, detail="stage2 not done or deps not satisfied")


@app.post("/api/projects/{pid}/budget")
def project_budget(pid: str, body: BudgetIn, v: tuple = Depends(authorize_project)):
    try:
        ceiling = float(body.ceiling)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="ceiling (number) required")
    return console.raise_budget(pid, ceiling)


@app.post("/api/projects/{pid}/retry")
def project_retry(pid: str, body: RetryIn, v: tuple = Depends(authorize_project)):
    result = console.retry_stage(pid, int(body.stage), extra_creds=body.creds)
    if result:
        return {"project_id": result, "retried_stage": int(body.stage)}
    raise HTTPException(status_code=409, detail="cannot retry: invalid stage or prior stage not done")


@app.post("/api/projects/{pid}/release")
def project_release(pid: str, v: tuple = Depends(authorize_project)):
    if console.release_project(pid):
        return {"project_id": pid, "released": True}
    raise HTTPException(status_code=409, detail="not held")


# ── Draft write-through + handoff (Option C onboarding; drafts only) ──────────────────────────
@app.patch("/api/projects/{pid}/draft")
def patch_draft(pid: str, body: DraftPatchIn, v: tuple = Depends(authorize_project)):
    """Structured project write-through: {name?, goal?, scope?}. Server composes the canonical
    description (goal + scope-of-work line). Call debounced/on-blur, NOT per keystroke."""
    if not console.is_draft(pid):
        raise HTTPException(status_code=409, detail="not a draft (already promoted)")
    return console.set_draft_project(pid, name=body.name, goal=body.goal, scope=body.scope)


@app.post("/api/projects/{pid}/attach")
def attach_draft(pid: str, body: AttachIn, v: tuple = Depends(authorize_project)):
    """Attach project materials (walkthrough video / documents) to the draft's input/."""
    if not console.is_draft(pid):
        raise HTTPException(status_code=409, detail="not a draft (already promoted)")
    return {"attached": console.attach_to_draft(pid, body.files or [])}


@app.post("/api/projects/{pid}/promote")
def promote_draft(pid: str, body: PromoteIn, v: tuple = Depends(authorize_project)):
    """Hand off to the factory: promote the draft into a real run and launch Stage 1. The composed
    state.description + accumulated brief are the payload (description override optional)."""
    if not console.is_draft(pid):
        raise HTTPException(status_code=409, detail="not a draft (already promoted)")
    try:
        project_id = console.promote_draft(pid, description=body.description, target=body.target)
    except ValueError as e:                # duplicate project name
        raise HTTPException(status_code=409, detail=str(e))
    return {"project_id": project_id, "status": "started"}


# ── Chat ────────────────────────────────────────────────────────────────────────────────────
@app.post("/api/chat")
async def chat(body: ChatIn, v: tuple = Depends(require_authed)):
    if not _chat_runner:
        raise HTTPException(status_code=503,
                            detail="no OPENAI_API_KEY or OPENROUTER_API_KEY — chat unavailable")
    project_id = body.project_id
    # Messaging an EXISTING run requires ownership; a new conversation mints a durable DRAFT
    # (canonical run-<8hex>) up front so the interview persists to chat.jsonl from turn one and
    # survives a refresh/restart. The draft is invisible to the pipeline poller until promotion.
    if project_id and not _can_see(v, project_id):
        raise HTTPException(status_code=403, detail="forbidden")
    if not project_id:
        project_id = console.create_draft(owner=v[0] or "", name=body.project_name or "",
                                      runtime=body.runtime, planning_model=body.planning_model,
                                      impl_model=body.impl_model)
    # Files/images attached during the interview persist into the draft now (wireframes survive),
    # so they're in input/ for Stage 1 regardless of which turn they arrived on. Drafts only.
    if (body.files or body.images) and console.is_draft(project_id):
        try:
            console.attach_to_draft(project_id, (body.files or []) + (body.images or []))
        except Exception:
            pass  # a bad attachment must not 500 the chat turn

    user_msg = ChatMessage(role="user", content=body.message, msg_type="text", ts=time.time())
    if body.files:
        user_msg.metadata["files"] = [f.get("name", "file") for f in body.files]
    if body.images:
        user_msg.metadata["images"] = [i.get("name", "image") for i in body.images]

    try:
        result_project_id, response_msgs = await _chat_runner.handle_message(
            project_id, body.message, body.files, body.images, runtime=body.runtime,
            planning_model=body.planning_model, impl_model=body.impl_model,
            project_name=body.project_name, gated=body.gated,
            owner=v[0] or "", role=v[1] or "member")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not project_id:
        project_id = result_project_id
    if project_id:
        store = ChatStore(_chat_path(project_id))
        store.append(user_msg)
        for m in response_msgs:
            store.append(m)
        _push_sse(project_id, response_msgs)

    return {"project_id": project_id, "messages": [m.to_dict() for m in response_msgs]}


@app.get("/api/chat/{pid}/history")
def chat_history(pid: str, v: tuple = Depends(authorize_project)):
    store = ChatStore(_chat_path(pid))
    return {"messages": [m.to_dict() for m in store.history()]}


@app.post("/api/chat/{pid}/deps")
def chat_deps(pid: str, body: DepsIn, v: tuple = Depends(authorize_project)):
    deps = body.deps
    result = console.submit_deps(pid, deps)
    dep_msg = ChatMessage(role="user", content=f"Provided: {', '.join(deps.keys())}",
                          msg_type="dep_submit", ts=time.time(),
                          metadata={"dep_names": list(deps.keys())})
    store = ChatStore(_chat_path(pid))
    store.append(dep_msg)
    if result.get("satisfied"):
        console.start_stage3(pid, extra_creds=extract_env_creds(deps))
        launch_msg = ChatMessage(role="system", content="Dependencies received. Build stage launching.",
                                 msg_type="status_update", ts=time.time(),
                                 metadata={"project_id": pid, "stage": 3})
        store.append(launch_msg)
        _push_sse(pid, [dep_msg, launch_msg])
    else:
        _push_sse(pid, [dep_msg])
    return result


@app.get("/api/chat/{pid}/stream")
async def chat_stream(pid: str, v: tuple = Depends(authorize_project)):
    """SSE for real-time pipeline updates. Drains a per-client queue fed by _push_sse (from the
    poller thread + chat/deps handlers); keepalive every 2s."""
    q: list[str] = []
    with _sse_lock:
        _sse_clients.setdefault(pid, []).append(q)

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
                clients = _sse_clients.get(pid, [])
                if q in clients:
                    clients.remove(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8765"))
    host = os.environ.get("SF_BIND", "127.0.0.1")
    uvicorn.run(app, host=host, port=port)
