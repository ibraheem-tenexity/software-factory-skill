"""Verify MCP servers are reachable before launching a stage.

Sends a JSON-RPC 2.0 'initialize' handshake to each server defined in .mcp.json.
If any required server fails, the stage should not launch.
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Callable


@dataclass
class McpCheck:
    name: str
    ok: bool
    detail: str


def _real_run(command: list[str], input_data: str, timeout: float) -> tuple[int, str, str]:
    proc = subprocess.Popen(
        command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True,
    )
    try:
        stdout, stderr = proc.communicate(input=input_data, timeout=timeout)
        return proc.returncode, stdout, stderr
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        return -1, "", "timeout"


_INIT_REQUEST = json.dumps({
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "sf-healthcheck", "version": "0.1"},
    },
})


def check_mcp(
    config_path: str,
    timeout_s: float = 10.0,
    run: Callable = _real_run,
) -> list[McpCheck]:
    if not os.path.isfile(config_path):
        return [McpCheck(name="config", ok=False, detail=f"{config_path} not found")]
    with open(config_path) as f:
        cfg = json.load(f)
    servers = cfg.get("mcpServers", {})
    results = []
    for name, spec in servers.items():
        cmd = [spec["command"]] + spec.get("args", [])
        try:
            _rc, stdout, stderr = run(cmd, _INIT_REQUEST + "\n", timeout_s)
        except Exception as exc:
            results.append(McpCheck(name=name, ok=False, detail=str(exc)))
            continue
        if _rc == -1:
            results.append(McpCheck(name=name, ok=False, detail="timeout"))
            continue
        first_line = (stdout or "").strip().split("\n")[0] if stdout else ""
        try:
            resp = json.loads(first_line)
            if "result" in resp:
                results.append(McpCheck(name=name, ok=True, detail="connected"))
            else:
                results.append(McpCheck(name=name, ok=False, detail=f"no result: {first_line[:120]}"))
        except (json.JSONDecodeError, ValueError):
            results.append(McpCheck(name=name, ok=False, detail=f"bad response: {first_line[:120]}"))
    return results
