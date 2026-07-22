"""FastAPI shell around the factory application (Phase 2 of docs/plans/fastapi-db-replacement.md).

Modularized: this file is now ONLY the FastAPI app + access-log middleware + lifespan + the static
mounts + router includes. The pieces live in sibling modules:
  console/state.py            — shared singletons (console/users/blobs/tool_store/agent_store/
                                _chat_runner), the ingest-SSE registry, and the SPA/serving helpers
  console/deps.py             — auth dependencies (viewer/require_authed/authorize_project/require_admin/
                                _staff_session/require_staff)
  console/schemas.py          — all Pydantic request bodies
  software_factory/workers/   — the background supervisor (_poll_transitions/_auto_advance/
                                _narrate*/_boot) + _health + the lifespan
  console/routers/open_routes — /, /index.html, /admin (gated), /api/health
  console/routers/auth        — /api/auth/*, /api/me, /api/users
  console/routers/org         — /api/org* (organization + Org Admin §2.3)
  console/routers/admin_os     — /api/admin* (Tenexity OS §3, staff-gated)
  console/routers/projects     — /api/projects* + /api/drafts (runs, Project View §2.5, actions)
  console/routers/chat         — /api/chat*

Run:  uvicorn console.app:app --host 0.0.0.0 --port 8765   (or python3 console/app.py)
"""
import contextlib
import json
import os
import sys
import time

from fastapi import FastAPI, Request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def _load_local_env(path: str | None = None) -> None:
    """Load the repo-root .env for LOCAL runs so secrets ibraheem keeps there (e.g. LANGFUSE_*) are
    picked up. override=False → real process/Railway env ALWAYS wins; .env only fills gaps. Prod ships
    no .env (gitignored) → no-op there. SKIPPED under the test suite (SF_ENVIRONMENT=test) so a dev's
    local .env can't leak keys into tests, and a missing python-dotenv never blocks startup."""
    if os.environ.get("SF_ENVIRONMENT") == "test":
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(path or os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"), override=False)


# Must run BEFORE `import console.state` — state.reset() reads os.environ at import time.
_load_local_env()

import console.state as state  # noqa: E402  (also: app_mod.state is the patch home for view-helpers)

# Re-instantiate the singletons from the CURRENT environment on every (re)import. The tests reload
# console.app per case; this preserves the monolith's reload-re-instantiates-stores behavior — most
# importantly re-seeding the bootstrap admin AFTER conftest's per-test TRUNCATE.
state.reset()

from software_factory.workers.supervisor import lifespan as _poller_lifespan  # noqa: E402
from console.routers import open_routes, auth, org, admin_os, projects, chat, research  # noqa: E402
from software_factory.memory.mcp_server import memory_asgi_app, memory_mcp_lifespan  # noqa: E402


@contextlib.asynccontextmanager
async def lifespan(app: "FastAPI"):
    # SOF-157: a Starlette sub-app mounted via app.mount() does NOT get its lifespan run by the
    # parent, so the memory MCP's StreamableHTTPSessionManager.run() never fired and every
    # /mcp/memory request 500'd. Run it here (alongside the poller lifespan) for the app's lifetime.
    async with memory_mcp_lifespan():
        async with _poller_lifespan(app):
            yield

# Re-exported so the public `console.app` surface (and the tests that read/patch object attributes
# on them) is preserved across the split. Bound AFTER reset() → the current instances; the same
# objects the routers use (the routers read them late via `state.<name>`).
from console.state import console, users, blobs, tool_store, agent_store  # noqa: E402,F401

app = FastAPI(title="software-factory console", lifespan=lifespan)


# ── Service-layer domain errors → HTTP ────────────────────────────────────────────────────────
# Services raise framework-free errors (software_factory.services.errors); map each to its status
# with the same {"detail": ...} body FastAPI's HTTPException uses, so the wire contract is unchanged.
from fastapi.responses import JSONResponse  # noqa: E402
from software_factory.services.errors import ServiceError  # noqa: E402
from software_factory.recipes.store import RecipeValidationError  # noqa: E402


@app.exception_handler(ServiceError)
async def _service_error_handler(request: Request, exc: ServiceError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


# CBT-9: a recipe save refused for a bad repo (the one sanctioned fact gate) — the admin sees
# EXACTLY the store's own reason, same shape as ServiceError's {"detail": ...} body.
@app.exception_handler(RecipeValidationError)
async def _recipe_validation_error_handler(request: Request, exc: RecipeValidationError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


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


# ── Static SPA assets (React mode). The /admin chunk lives in this shared mount; the /admin PAGE
# route is gated in open_routes — the bundle carries no data/secrets, page + data are gated. ──────
if os.path.isdir(os.path.join(state._REACT_DIST, "assets")):
    from fastapi.staticfiles import StaticFiles
    app.mount("/assets", StaticFiles(directory=os.path.join(state._REACT_DIST, "assets")), name="assets")

# Self-hosted brand fonts (Vite copies console/web/public/fonts → dist/fonts; admin.css @font-face
# references them at absolute /fonts/*.ttf). Served like /assets, else the portal falls back to system fonts.
if os.path.isdir(os.path.join(state._REACT_DIST, "fonts")):
    from fastapi.staticfiles import StaticFiles
    app.mount("/fonts", StaticFiles(directory=os.path.join(state._REACT_DIST, "fonts")), name="fonts")


# ── Router includes (1:1 with the pre-split route set; paths/methods/auth/shapes unchanged) ──────
app.include_router(open_routes.router)
app.include_router(auth.router)
app.include_router(org.router)
app.include_router(admin_os.router)
app.include_router(projects.router)
app.include_router(chat.router)
app.include_router(research.router)

# Project Memory MCP (SOF-41/T4.2) — console-hosted, not a router (it's a full ASGI sub-app
# speaking the MCP streamable-HTTP transport, mounted the same way the static SPA assets are
# above). Bearer-token scope enforcement lives in the sub-app itself (memory/mcp_server.py's
# _BearerScopeMiddleware). Always mounted (SOF-71) — memory is core product, not opt-in.
app.mount("/mcp/memory", memory_asgi_app())  # memory_asgi_app imported above (SOF-157 lifespan wiring)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8765"))
    host = os.environ.get("SF_BIND", "127.0.0.1")
    uvicorn.run(app, host=host, port=port)
