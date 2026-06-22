"""Shared singletons + SSE registry + SPA/serving helpers for the console app.

ONE canonical home for the long-lived stores and the view helpers, so every router — and the tests
that monkeypatch them — reference a single location. This is also what breaks the import cycle:
routers/poller import from `state`; `app.py` imports the routers. Nothing here imports back from them.

Singletons live behind `reset()`, which `app.py` calls on every (re)import. That preserves the
monolith's behavior where `importlib.reload(console.app)` re-instantiated the stores each test —
notably re-seeding the bootstrap admin AFTER conftest's per-test TRUNCATE. Consumers therefore
reference these as module attributes (`state.console`, `state.users`, …) so they always see the
current instance after a reset; they must NOT `from console.state import console` (that would bind a
stale object across a reset).
"""
import json
import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from software_factory.console import Console  # noqa: E402
from software_factory.chat_agent import ChatAgentRunner  # noqa: E402
from software_factory import auth  # noqa: E402
from software_factory.users import UserStore  # noqa: E402
from software_factory.blobs import BlobStore  # noqa: E402
from software_factory.agent_prompts import PromptStore  # noqa: E402
from software_factory.registries import ToolStore, AgentRegistryStore  # noqa: E402

HERE = os.path.dirname(__file__)
# The React SPA (console/web/dist) is served when SF_CONSOLE=react AND it's been built; otherwise the
# legacy single-file console (index.html) is the default — so the migration is opt-in and safe.
_REACT_DIST = os.path.join(HERE, "web", "dist")

# Populated by reset() (called at import + on every app reload). Declared here for clarity.
PROJECTS_DIR = ""
console = None
users = None
blobs = None
prompts = None
tool_store = None
agent_store = None
_has_chat_key = False
_chat_runner = None
_sse_clients: dict[str, list] = {}
_sse_lock = threading.Lock()
_project_stages: dict[str, int] = {}


def reset():
    """(Re)instantiate the long-lived singletons from the current environment. Called at import and
    by app.py on every reload — matches the monolith's reload-re-instantiates-stores behavior."""
    global PROJECTS_DIR, console, users, blobs, prompts, tool_store, agent_store
    global _has_chat_key, _chat_runner, _sse_clients, _sse_lock, _project_stages

    PROJECTS_DIR = os.environ.get("SF_PROJECTS_DIR", os.path.join(HERE, "..", ".projects"))
    console = Console(PROJECTS_DIR)
    # User directory + RBAC + orgs — the SINGLE source of truth for who can access (status invited/
    # active/disabled). No env allowlist: the cold-start admin is seeded from SF_BOOTSTRAP_ADMIN_EMAIL
    # inside UserStore.__init__, and all access thereafter is managed via Team & access (no redeploy).
    users = UserStore()
    blobs = BlobStore()           # org KB docs + run-scoped uploaded materials (bytes live in storage)
    prompts = PromptStore()       # editable agent prompts (§3.4) — stored/served, not yet applied
    tool_store = ToolStore()      # tools/MCP registry (§3.5) — real datastore (seeded), CRUD-able
    agent_store = AgentRegistryStore()   # agent identity registry (§3.4)
    # The concierge runs on OpenAI (gpt-4o) or OpenRouter (Kimi) — either key enables chat.
    _has_chat_key = bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENROUTER_API_KEY"))
    _chat_runner = ChatAgentRunner(console, users) if _has_chat_key else None
    _sse_clients = {}
    _sse_lock = threading.Lock()
    _project_stages = {}


reset()


# Filename → doc-kind classifier for uploaded materials / KB docs (shared by org + projects routers).
_DOC_KIND = {"pdf": "pdf", "xlsx": "xlsx", "xls": "xlsx", "csv": "csv", "doc": "doc", "docx": "doc",
             "mp4": "video", "mov": "video", "png": "img", "jpg": "img", "jpeg": "img"}


def _doc_kind(name: str) -> str:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return _DOC_KIND.get(ext, "doc")


def _chat_path(project_id: str) -> str:
    return os.path.join(PROJECTS_DIR, project_id, "chat.jsonl")


def _push_sse(project_id: str, msgs):
    """Push messages to all SSE clients watching this run."""
    with _sse_lock:
        clients = _sse_clients.get(project_id, [])
    for msg in msgs:
        data = json.dumps(msg.to_dict())
        for q in clients:
            q.append(f"data: {data}\n\n")


def _react_enabled() -> bool:
    return (os.environ.get("SF_CONSOLE", "").strip().lower() == "react"
            and os.path.isfile(os.path.join(_REACT_DIST, "index.html")))


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
