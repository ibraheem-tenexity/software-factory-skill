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


def test_agent_store_ensures_real_agents_and_purges_fakes():
    s = AgentRegistryStore()                # init ensures the 4 REAL orchestrators + purges the fakes
    signs = {a["callsign"] for a in s.all()}
    assert {"STAGE-1", "STAGE-2", "STAGE-3", "CONCIERGE"} <= signs
    assert "ATLAS" not in signs and "PROFIT" not in signs   # the 12 fakes are gone, never reseeded
    assert s.get("STAGE-1")["name"] == "Stage 1 · Research"
    # a delete of a fake STICKS — .all() is a pure read and must not resurrect it
    s.create("ATLAS", "x")
    s.delete("ATLAS")
    s.all()
    assert s.get("ATLAS") is None
    # custom-agent CRUD still works
    a = s.create("NOVA", "Novelist", role="nova", model="m", cost_tier=2, descr="d")
    assert a["callsign"] == "NOVA"
    assert s.update("NOVA", {"model": "m2"})["model"] == "m2"
    s.delete("NOVA")
    assert s.get("NOVA") is None
