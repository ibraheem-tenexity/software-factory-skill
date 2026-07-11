"""SOF-41 (T4.2): console-hosted Project Memory MCP — project-memory-integration.md §4,
project-memory-design.md §7/§8.

Exposes seven tools over streamable-HTTP MCP: `get_project_overview`, `list_documents`,
`get_document_summary`, `search_memory` (T4.1), `search_document_summaries` (SOF-60),
`get_chunk`, `add_memory_note` (the ONLY writer).
Every tool is scoped from the request's bearer token (`auth.verify_scope_token`), never from a
caller-supplied argument — no tool signature below even HAS a `project_id` parameter, so an agent
cannot ask for another project's memory by passing one.

Two layers, deliberately separate:
- The module-level functions (`get_project_overview`, `list_documents`, ...) do the actual DB work,
  take `project_id` as an explicit first argument, and accept injectable `connect`/`mem`/`blobs`/
  `embed` — fully testable without a live DB or a network call (mirrors `search.py`/`store.py`'s
  own injectable-dependency convention).
- `build_mcp()` registers thin FastMCP tool wrappers that pull the ENFORCED project_id from
  `_current_project_id()` (a contextvar set by `_BearerScopeMiddleware`, never from an argument)
  and call straight into the layer above.

Auth is a plain ASGI middleware, not FastMCP's built-in OAuth `token_verifier`/`AuthSettings`
path: that machinery requires a real `issuer_url`/`resource_server_url` (it's built for OAuth
resource servers) — unnecessary ceremony for a single internal HMAC bearer check that's already
solved by the console's own `auth.sign_scope_token`/`verify_scope_token`.
"""
from __future__ import annotations

import contextlib
import contextvars

from mcp.server.fastmcp import FastMCP
from starlette.responses import PlainTextResponse

from .. import auth, dbshim
from ..blobs import BlobStore
from .embed import embed_texts
from .search import search as search_memory_rrf
from .search import search_documents as search_documents_dense
from .store import MemoryStore

_NOTES_BLOB_KIND = "memory_note"


# ── Scope-safe core operations (DB work, fully injectable/testable) ─────────────────────────────

def _in_scope_blob_ids(project_id: str, *, connect=None) -> set[int]:
    """Every blob_id this project may read: its own uploads plus org docs imported via
    `blob_uses`. The single source of truth for the MCP's scope boundary — every ID-taking tool
    (`get_document_summary`, `get_chunk`) checks its target against this before returning
    anything, so a caller can't read another tenant's document just by guessing/enumerating an id."""
    connect = connect or (lambda: dbshim.connect("."))
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id FROM blobs WHERE scope = 'project' AND scope_id = ? "
            "UNION SELECT blob_id AS id FROM blob_uses WHERE project_id = ?",
            (project_id, project_id),
        ).fetchall()
    finally:
        conn.close()
    return {r["id"] for r in rows}


def _assert_in_scope(blob_id: int, project_id: str, *, connect=None) -> None:
    if blob_id not in _in_scope_blob_ids(project_id, connect=connect):
        raise PermissionError(f"blob {blob_id!r} is not in scope for project {project_id!r}")


def get_project_overview(project_id: str, *, mem=None) -> dict:
    mem = mem or MemoryStore()
    return mem.overview("project", project_id)


def list_documents(project_id: str, *, connect=None) -> list[dict]:
    connect = connect or (lambda: dbshim.connect("."))
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT b.id AS blob_id, b.name, b.kind, ds.status, ds.summary_md "
            "FROM blobs b LEFT JOIN doc_summary ds ON ds.blob_id = b.id "
            "WHERE b.id IN ("
            "  SELECT id FROM blobs WHERE scope = 'project' AND scope_id = ? "
            "  UNION SELECT blob_id AS id FROM blob_uses WHERE project_id = ?"
            ") ORDER BY b.name",
            (project_id, project_id),
        ).fetchall()
    finally:
        conn.close()
    return rows


def get_document_summary(project_id: str, blob_id: int, *, connect=None, mem=None) -> dict:
    connect = connect or (lambda: dbshim.connect("."))
    _assert_in_scope(blob_id, project_id, connect=connect)
    mem = mem or MemoryStore(connect=connect)
    row = mem.get_doc_summary(blob_id)
    if row is None:
        raise ValueError(f"no summary yet for blob_id {blob_id!r}")
    return row


def get_chunk(project_id: str, chunk_id: int, window: int = 0, *, connect=None, mem=None) -> dict:
    """The chunk plus up to `window` neighbors on each side, ordered by `ordinal` within the same
    document — expands context around a search_memory hit."""
    connect = connect or (lambda: dbshim.connect("."))
    conn = connect()
    try:
        row = conn.execute(
            "SELECT id, blob_id, ordinal, section_path, content FROM chunk WHERE id = ?",
            (chunk_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise ValueError(f"unknown chunk_id {chunk_id!r}")
    _assert_in_scope(row["blob_id"], project_id, connect=connect)

    mem = mem or MemoryStore(connect=connect)
    siblings = mem.chunks_for(row["blob_id"])   # ordinal-ordered
    idx = next((i for i, s in enumerate(siblings) if s["id"] == chunk_id), None)
    if idx is None:
        return {"chunk": row, "neighbors": []}
    lo, hi = max(0, idx - window), min(len(siblings), idx + window + 1)
    neighbors = [s for s in siblings[lo:hi] if s["id"] != chunk_id]
    return {"chunk": row, "neighbors": neighbors}


def search_memory(project_id: str, query: str, k: int = 8, *, search_fn=None) -> list[dict]:
    """Wraps T4.1's search() — always scope='project', scope_id=project_id; no other scope is
    reachable from this MCP."""
    search_fn = search_fn or search_memory_rrf
    return search_fn("project", project_id, query, k)


def search_document_summaries(project_id: str, query: str, k: int = 8, *, search_fn=None) -> list[dict]:
    """Wraps SOF-60's search_documents() — same enforced project scoping as search_memory."""
    search_fn = search_fn or search_documents_dense
    return search_fn("project", project_id, query, k)


def _notes_blob_id(project_id: str, *, blobs=None) -> int:
    """The (at most one) sentinel blob that holds this project's agent-authored notes, created
    lazily on first use. Notes become chunk rows on this blob — same table search_memory already
    scans, so a note is immediately retrievable, no separate notes surface needed."""
    blobs = blobs or BlobStore()
    existing = next((b for b in blobs.list_for("project", project_id)
                     if b.get("kind") == _NOTES_BLOB_KIND), None)
    if existing:
        return existing["id"]
    return blobs.record("project", project_id, storage_key=f"memory-notes/{project_id}",
                        kind=_NOTES_BLOB_KIND, name="Memory notes", content_type="text/markdown")


def add_memory_note(project_id: str, body_md: str, *, blobs=None, mem=None, embed=None) -> dict:
    """The only write path this MCP exposes. Embeds the note (dense) so it's retrievable via
    BOTH search_memory channels, not just the keyword one."""
    text = (body_md or "").strip()
    if not text:
        raise ValueError("body_md is empty")
    blobs = blobs or BlobStore()
    mem = mem or MemoryStore()
    embed = embed or embed_texts
    blob_id = _notes_blob_id(project_id, blobs=blobs)
    ordinal = len(mem.chunks_for(blob_id))
    dense = embed([text])[0]
    note_id = mem.add_chunk(blob_id, "project", project_id, ordinal, None, text, dense=dense)
    return {"note_id": note_id}


# ── MCP wiring — auth boundary + tool registration ──────────────────────────────────────────────

_project_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("memory_mcp_project_id")


def _current_project_id() -> str:
    try:
        return _project_ctx.get()
    except LookupError:
        raise PermissionError("no verified memory scope token for this request")


class _BearerScopeMiddleware:
    """Verifies `Authorization: Bearer <scope token>` on every request BEFORE it reaches the MCP
    server, and sets the enforced project_id in a contextvar the tools read. This IS the
    boundary the ticket's security AC asks for: scope comes from the verified token, never from
    an argument a tool accepts."""

    def __init__(self, app):
        self._app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        raw = headers.get(b"authorization", b"").decode("latin-1")
        token = raw[7:] if raw.lower().startswith("bearer ") else None
        project_id = auth.verify_scope_token(token) if token else None
        if not project_id:
            resp = PlainTextResponse("unauthorized", status_code=401)
            await resp(scope, receive, send)
            return
        reset_token = _project_ctx.set(project_id)
        try:
            await self._app(scope, receive, send)
        finally:
            _project_ctx.reset(reset_token)


def build_mcp() -> FastMCP:
    mcp = FastMCP("project-memory")

    @mcp.tool(name="get_project_overview",
             description="Project brief + rollup summary + assumptions digest. Call this first "
                         "in almost every run.")
    def _get_project_overview() -> dict:
        return get_project_overview(_current_project_id())

    @mcp.tool(name="list_documents",
             description="Titles, kind, ingestion status, and summary of every document in "
                         "scope — this project's own uploads plus any org knowledge-base doc "
                         "imported into it.")
    def _list_documents() -> list[dict]:
        return list_documents(_current_project_id())

    @mcp.tool(name="get_document_summary",
             description="summary_md, outline, and assumptions for one document — call after "
                         "deciding (via list_documents/search_document_summaries) that it's "
                         "relevant.")
    def _get_document_summary(blob_id: int) -> dict:
        return get_document_summary(_current_project_id(), blob_id)

    @mcp.tool(name="search_memory",
             description="Hybrid (semantic + keyword) search over this project's documents, "
                         "brief, and notes. Returns the most relevant passages with their source "
                         "document and section — the workhorse retrieval tool.")
    def _search_memory(query: str, k: int = 8) -> list[dict]:
        return search_memory(_current_project_id(), query, k)

    @mcp.tool(name="search_document_summaries",
             description="Coarse, whole-document semantic search — which documents are relevant "
                         "to this query, before drilling into search_memory for passages. "
                         "Semantic-only; exact-keyword queries should use search_memory.")
    def _search_document_summaries(query: str, k: int = 8) -> list[dict]:
        return search_document_summaries(_current_project_id(), query, k)

    @mcp.tool(name="get_chunk",
             description="One chunk plus `window` neighboring chunks (by ordinal) from the same "
                         "document — use after search_memory to expand context around a hit.")
    def _get_chunk(chunk_id: int, window: int = 0) -> dict:
        return get_chunk(_current_project_id(), chunk_id, window)

    @mcp.tool(name="add_memory_note",
             description="Append a learning/note to this project's memory — the ONLY tool that "
                         "writes. Immediately retrievable via search_memory.")
    def _add_memory_note(body_md: str) -> dict:
        return add_memory_note(_current_project_id(), body_md)

    return mcp


# ONE FastMCP instance + ONE streamable-HTTP app, shared between the mount (memory_asgi_app) and
# the lifespan (memory_mcp_lifespan). The session manager is created lazily by streamable_http_app()
# and must be the SAME object the lifespan runs — so build both exactly once (SOF-157).
_MCP = None
_MCP_APP = None


def _memory_mcp():
    global _MCP, _MCP_APP
    if _MCP is None:
        _MCP = build_mcp()
        _MCP_APP = _MCP.streamable_http_app()   # creates the session manager (accessible only after this)
    return _MCP, _MCP_APP


def memory_asgi_app():
    """The mountable ASGI app — `console/app.py` mounts this unconditionally at `/mcp/memory`
    behind `_BearerScopeMiddleware`, which enforces the per-project scope token boundary. FastMCP
    serves its handler at the sub-app's `/mcp` path, so the effective endpoint is `/mcp/memory/mcp`
    (that's what SF_MEMORY_MCP_URL points at — SOF-157)."""
    _, app = _memory_mcp()
    return _BearerScopeMiddleware(app)


@contextlib.asynccontextmanager
async def memory_mcp_lifespan():
    """Run the FastMCP streamable-HTTP session manager (SOF-157). A Starlette sub-app mounted via
    `app.mount()` does NOT get its lifespan run by the parent, so `StreamableHTTPSessionManager.run()`
    (which initializes the task group) never fires — and every `/mcp/memory` request 500s with
    'Task group is not initialized'. The console app enters THIS in its own lifespan so the memory
    MCP actually works."""
    mcp, _ = _memory_mcp()
    async with mcp.session_manager.run():
        yield
