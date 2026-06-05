"""MCP health check: verify servers respond to JSON-RPC initialize before launching a stage."""
import json
from software_factory.mcp_health import check_mcp, _INIT_REQUEST


def _make_config(tmp_path, servers=None):
    cfg = {"mcpServers": servers or {"ruflo": {"command": "echo", "args": ["hi"]}}}
    p = tmp_path / ".mcp.json"
    p.write_text(json.dumps(cfg))
    return str(p)


def _fake_runner(response_json=None, timeout=False, error=None):
    def run(cmd, input_data, timeout_s):
        if error:
            raise RuntimeError(error)
        if timeout:
            return -1, "", "timeout"
        stdout = json.dumps(response_json) if response_json else ""
        return 0, stdout, ""
    return run


def test_healthy_mcp_returns_ok(tmp_path):
    cfg = _make_config(tmp_path)
    resp = {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2024-11-05", "serverInfo": {"name": "ruflo"}}}
    checks = check_mcp(cfg, run=_fake_runner(response_json=resp))
    assert len(checks) == 1
    assert checks[0].ok is True
    assert checks[0].name == "ruflo"
    assert checks[0].detail == "connected"


def test_timeout_returns_not_ok(tmp_path):
    cfg = _make_config(tmp_path)
    checks = check_mcp(cfg, run=_fake_runner(timeout=True))
    assert checks[0].ok is False
    assert "timeout" in checks[0].detail


def test_malformed_response_returns_not_ok(tmp_path):
    cfg = _make_config(tmp_path)
    checks = check_mcp(cfg, run=_fake_runner(response_json={"jsonrpc": "2.0", "id": 1, "error": {"code": -1}}))
    assert checks[0].ok is False
    assert "no result" in checks[0].detail


def test_exception_returns_not_ok(tmp_path):
    cfg = _make_config(tmp_path)
    checks = check_mcp(cfg, run=_fake_runner(error="spawn failed"))
    assert checks[0].ok is False
    assert "spawn failed" in checks[0].detail


def test_missing_config_returns_not_ok(tmp_path):
    checks = check_mcp(str(tmp_path / "nope.json"))
    assert len(checks) == 1
    assert checks[0].ok is False
    assert "not found" in checks[0].detail


def test_multiple_servers(tmp_path):
    servers = {
        "ruflo": {"command": "claude-flow", "args": ["mcp", "start"]},
        "playwright": {"command": "npx", "args": ["-y", "@playwright/mcp"]},
    }
    cfg = _make_config(tmp_path, servers)
    good = {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}
    checks = check_mcp(cfg, run=_fake_runner(response_json=good))
    assert len(checks) == 2
    assert all(c.ok for c in checks)
