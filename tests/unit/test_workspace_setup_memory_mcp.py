"""Pure unit tests for the memory MCP's wiring into mcp_config()/opencode_config() (SOF-41/T4.2).
No DB, no filesystem writes (unlike test_workspace_setup.py's prepare_workspace tests) — these
call mcp_config/opencode_config directly, which are pure dict-building.

SOF-71: memory is always wired now, no flag to gate it — these tests were previously parametrized
on SF_MEMORY on/off; the off-path tests are gone (that state no longer exists), the on-path tests
are unconditional."""
from software_factory.workspace_setup import mcp_config, opencode_config


def test_memory_mcp_present_at_every_stage():
    for stage in (1, 2, 3):
        cfg = mcp_config(stage)
        assert cfg["mcpServers"]["memory"] == {
            "type": "http", "url": "${SF_MEMORY_MCP_URL}",
            "headers": {"Authorization": "Bearer ${SF_MEMORY_TOKEN}"},
        }


def test_memory_mcp_url_and_token_are_env_refs_never_literal():
    """Same posture as EXA_API_KEY — the actual secret/URL must never be a literal in .mcp.json,
    only resolved from the stage's own env at MCP-load time."""
    memory = mcp_config(1)["mcpServers"]["memory"]
    assert memory["url"] == "${SF_MEMORY_MCP_URL}"
    assert memory["headers"]["Authorization"] == "Bearer ${SF_MEMORY_TOKEN}"


def test_opencode_translates_the_memory_mcp_to_the_remote_shape():
    servers = opencode_config(1)["mcp"]
    assert servers["memory"] == {
        "type": "remote", "url": "${SF_MEMORY_MCP_URL}",
        "headers": {"Authorization": "Bearer {env:SF_MEMORY_TOKEN}"}, "enabled": True,
    }
