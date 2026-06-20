"""Tools/MCP registry + agent registry stores — seed-on-first-read + CRUD (no code-constant data)."""
from software_factory.registries import ToolStore, AgentRegistryStore


def test_tool_store_seeds_then_crud():
    s = ToolStore()
    tools = s.all()                         # seeds the real defaults into the empty table
    assert any(t["name"] == "Playwright MCP" for t in tools)
    n = len(tools)
    t = s.create("Custom MCP", type="MCP", provider="X", scope="y", auth="token")
    assert t["id"] and t["name"] == "Custom MCP" and t["status"] == "available"
    assert len(s.all()) == n + 1
    upd = s.update(t["id"], {"status": "connected"})
    assert upd["status"] == "connected"
    s.delete(t["id"])
    assert len(s.all()) == n


def test_agent_store_seeds_then_crud():
    s = AgentRegistryStore()
    agents = s.all()                        # seeds the 12 canonical callsigns
    assert any(a["callsign"] == "ATLAS" for a in agents)
    assert s.get("ATLAS")["name"] == "Orchestrator"
    a = s.create("NOVA", "Novelist", role="nova", model="m", cost_tier=2, descr="d")
    assert a["callsign"] == "NOVA"
    upd = s.update("NOVA", {"model": "m2"})
    assert upd["model"] == "m2"
    s.delete("NOVA")
    assert s.get("NOVA") is None
