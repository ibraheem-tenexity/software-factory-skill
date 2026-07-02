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
from software_factory import auth  # noqa: E402
from software_factory.users import UserStore  # noqa: E402
from software_factory.blobs import BlobStore  # noqa: E402
from software_factory.system_agents import SystemAgentStore  # noqa: E402
from software_factory.tools import ToolStore  # noqa: E402
from software_factory.sow import SowStore  # noqa: E402
from software_factory.services.org_service import OrgService  # noqa: E402
from software_factory.services.secrets import Secrets  # noqa: E402
from software_factory.repositories.org_secrets import OrgSecretsRepository  # noqa: E402
from software_factory.repositories._exec import GlobalExec  # noqa: E402
from software_factory.services.conversation import Conversation, DbConversation  # noqa: E402
from software_factory.services.admin_service import AdminService  # noqa: E402
from software_factory.repositories.conversation import ConversationRepository  # noqa: E402
from software_factory.services.files import doc_kind as _doc_kind  # noqa: E402,F401

from console.throttle import LoginThrottle  # noqa: E402
from console.chat_dock import ChatDock  # noqa: E402

HERE = os.path.dirname(__file__)
# The React SPA (console/web/dist) is served when SF_CONSOLE=react AND it's been built; otherwise the
# legacy single-file console (index.html) is the default — so the migration is opt-in and safe.
_REACT_DIST = os.path.join(HERE, "web", "dist")

# Populated by reset() (called at import + on every app reload). Declared here for clarity.
PROJECTS_DIR = ""
console = None
users = None
blobs = None
tool_store = None
agent_store = None
sow_store = None
org_service = None
secrets_svc = None
conversation_svc = None
admin_service = None
_has_chat_key = False
_chat_runner = None
_sse_clients: dict[str, list] = {}
_sse_lock = threading.Lock()
# SOF-32: a SEPARATE channel from _sse_clients/_push_sse — that one feeds the live chat
# transcript (ChatPanel.tsx), which does not filter by msg_type, so piping ingest-progress
# events through it would spam the visible chat with "processing chunk 3/12" noise. This is
# its own stream for a future ProcessingScreen (SOF-49) to consume, with zero risk to chat.
_ingest_sse_clients: dict[str, list] = {}
_ingest_sse_lock = threading.Lock()
_project_stages: dict[str, int] = {}
login_throttle = None


def reset():
    """(Re)instantiate the long-lived singletons from the current environment. Called at import and
    by app.py on every reload — matches the monolith's reload-re-instantiates-stores behavior."""
    global PROJECTS_DIR, console, users, blobs, tool_store, agent_store, sow_store
    global org_service, secrets_svc, conversation_svc, admin_service
    global _has_chat_key, _chat_runner, _sse_clients, _sse_lock, _project_stages, login_throttle
    global _ingest_sse_clients, _ingest_sse_lock

    PROJECTS_DIR = os.environ.get("SF_PROJECTS_DIR", os.path.join(HERE, "..", ".projects"))
    console = Console(PROJECTS_DIR)
    # User directory + RBAC + orgs — the SINGLE source of truth for who can access (status invited/
    # active/disabled). No env allowlist: the cold-start admin is seeded from SF_BOOTSTRAP_ADMIN_EMAIL
    # inside UserStore.__init__, and all access thereafter is managed via Team & access (no redeploy).
    users = UserStore()
    blobs = BlobStore()           # org KB docs + run-scoped uploaded materials (bytes live in storage)
    tool_store = ToolStore()      # tools/MCP registry (§3.5) — real datastore, CRUD-able (no seeds)
    agent_store = SystemAgentStore()     # system agents (§3.4): identity + prompt + model_id (no seeds)
    sow_store = SowStore()               # statement-of-work CRUD
    # Service layer (business logic between routers and stores). Built AFTER the stores so it holds
    # the current instances; rebuilt each reset() so per-test TRUNCATE + re-seed is reflected.
    org_service = OrgService(users, blobs, console)
    secrets_svc = Secrets(OrgSecretsRepository(GlobalExec()))  # SOF-45: real Vault-backed store
    # DbConversation (SOF-31/T1.3) is the durable swap for the onboarding mock — same turn()/
    # history() contract, backed by ConversationStore. Opt-in via SF_CONVERSATION_DB so tests and
    # existing deploys stay on the in-memory mock until the flag is flipped.
    conversation_svc = (DbConversation(users=users, console=console)
                        if os.environ.get("SF_CONVERSATION_DB") == "1" else Conversation())
    # Admin history table (SOF-34/T1.5) reads the conversation table directly — independent of
    # conversation_svc/SF_CONVERSATION_DB, since it's a cross-tenant query surface, not the
    # onboarding Concierge's own storage path.
    admin_service = AdminService(console, users, agent_store, tool_store, sow_store,
                                 ConversationRepository(GlobalExec()))
    # The concierge runs on OpenAI or OpenRouter (Kimi) — either key enables chat.
    _has_chat_key = bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENROUTER_API_KEY"))
    # The /api/chat dock: ChatAgent behind ChatDock (console/chat_dock.py), history + persistence
    # on the conversation table (chat.jsonl/ChatStore retired).
    _chat_runner = ChatDock(console, users) if _has_chat_key else None
    _sse_clients = {}
    _sse_lock = threading.Lock()
    _ingest_sse_clients = {}
    _ingest_sse_lock = threading.Lock()
    _project_stages = {}
    login_throttle = LoginThrottle()   # brute-force/DoS guard for POST /api/auth/password (in-process)


reset()


def _push_sse(project_id: str, msgs):
    """Push messages to all SSE clients watching this run."""
    with _sse_lock:
        clients = _sse_clients.get(project_id, [])
    for msg in msgs:
        data = json.dumps(msg.to_dict())
        for q in clients:
            q.append(f"data: {data}\n\n")


def _push_ingest_sse(project_id: str, event: dict):
    """SOF-32: push one ingest-progress event (plain dict, no ChatMessage wrapper needed since
    this channel has no chat-history contract to keep) to clients watching this project's
    ingestion. Shape: {blob_id, doc_name, stage, pct, status}. Separate from _push_sse — see
    the _ingest_sse_clients docstring for why."""
    with _ingest_sse_lock:
        clients = _ingest_sse_clients.get(project_id, [])
    data = json.dumps(event)
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


def _artifact_viewer_html() -> bytes:
    with open(os.path.join(_REACT_DIST, "ArtifactViewer.html"), "rb") as f:
        return f.read()


def _login_html() -> str:
    with open(os.path.join(HERE, "login.html")) as f:
        return f.read().replace("{{CLIENT_ID}}", auth.client_id())
