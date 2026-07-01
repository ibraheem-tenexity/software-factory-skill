"""Pure unit tests for the memory MCP's wiring into mcp_config()/opencode_config() (SOF-41/T4.2)
— no DB, no filesystem writes (unlike test_workspace_setup.py's prepare_workspace tests, these
call mcp_config/opencode_config directly, which are pure dict-building). Env-var mutation is
undone in a finally so this can't leak SF_MEMORY into any other test run in the same process."""
import os

from software_factory.workspace_setup import mcp_config, opencode_config


def _with_sf_memory(value, fn):
    had = "SF_MEMORY" in os.environ
    prev = os.environ.get("SF_MEMORY")
    if value is None:
        os.environ.pop("SF_MEMORY", None)
    else:
        os.environ["SF_MEMORY"] = value
    try:
        return fn()
    finally:
        if had:
            os.environ["SF_MEMORY"] = prev
        else:
            os.environ.pop("SF_MEMORY", None)


def test_memory_mcp_absent_when_flag_is_off():
    cfg = _with_sf_memory(None, lambda: mcp_config(1))
    assert "memory" not in cfg["mcpServers"]


def test_memory_mcp_present_when_flag_is_on_every_stage():
    for stage in (1, 2, 3):
        cfg = _with_sf_memory("1", lambda: mcp_config(stage))
        assert cfg["mcpServers"]["memory"] == {
            "type": "http", "url": "${SF_MEMORY_MCP_URL}",
            "headers": {"Authorization": "Bearer ${SF_MEMORY_TOKEN}"},
        }


def test_memory_mcp_url_and_token_are_env_refs_never_literal():
    """Same posture as EXA_API_KEY — the actual secret/URL must never be a literal in .mcp.json,
    only resolved from the stage's own env at MCP-load time."""
    cfg = _with_sf_memory("1", lambda: mcp_config(1))
    memory = cfg["mcpServers"]["memory"]
    assert memory["url"] == "${SF_MEMORY_MCP_URL}"
    assert memory["headers"]["Authorization"] == "Bearer ${SF_MEMORY_TOKEN}"


def test_opencode_translates_the_memory_mcp_to_the_remote_shape():
    servers = _with_sf_memory("1", lambda: opencode_config(1)["mcp"])
    assert servers["memory"] == {
        "type": "remote", "url": "${SF_MEMORY_MCP_URL}",
        "headers": {"Authorization": "Bearer {env:SF_MEMORY_TOKEN}"}, "enabled": True,
    }


def test_opencode_has_no_memory_entry_when_flag_is_off():
    servers = _with_sf_memory(None, lambda: opencode_config(1)["mcp"])
    assert "memory" not in servers
