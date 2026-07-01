"""Pure unit tests for ToolStore.ensure_tool (SOF-41/T4.2) — no DB. Injects a fake repo so the
idempotent check-then-insert logic is verified without touching mcp_tools."""
from software_factory.registries import ToolStore, MEMORY_MCP_TOOL, SEED_TOOLS


class _FakeRepo:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.insert_calls = []

    def any_row(self):
        return bool(self.rows)

    def all(self):
        return list(self.rows)

    def insert(self, name, type, provider, scope, status, auth):
        self.insert_calls.append(name)
        self.rows.append({"name": name, "type": type, "provider": provider, "scope": scope,
                          "status": status, "auth": auth})


def test_ensure_tool_inserts_when_absent():
    repo = _FakeRepo(rows=[{"name": t["name"]} for t in SEED_TOOLS])   # already seeded, memory tool absent
    store = ToolStore(repo=repo)
    store.ensure_tool(MEMORY_MCP_TOOL)
    assert repo.insert_calls == ["Project Memory MCP"]


def test_ensure_tool_is_idempotent_when_already_present():
    repo = _FakeRepo(rows=[{"name": t["name"]} for t in SEED_TOOLS] + [{"name": "Project Memory MCP"}])
    store = ToolStore(repo=repo)
    store.ensure_tool(MEMORY_MCP_TOOL)
    assert repo.insert_calls == []


def test_ensure_tool_also_seeds_the_base_set_on_a_fully_empty_table():
    repo = _FakeRepo(rows=[])
    store = ToolStore(repo=repo)
    store.ensure_tool(MEMORY_MCP_TOOL)
    assert repo.insert_calls == [t["name"] for t in SEED_TOOLS] + ["Project Memory MCP"]
