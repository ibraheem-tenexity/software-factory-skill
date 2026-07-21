"""Verify MCP servers are reachable before launching a stage.

Sends a JSON-RPC 2.0 'initialize' handshake to each server defined in .mcp.json.
If any required server fails, the stage should not launch.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
from dataclasses import dataclass
from typing import Callable


@dataclass
class McpCheck:
    name: str
    ok: bool
    detail: str


def _real_run(command: list[str], input_data: str, timeout: float) -> tuple[int, str, str]:
    """SOF-207: `Popen.communicate(input=...)` writes the request and then CLOSES stdin
    immediately. A still cold-starting MCP server (e.g. npx fetching @playwright/mcp for the
    first time) can see that EOF before it has even begun reading the init request, and exits
    clean with empty stdout — a real request the server never got a chance to answer, not a
    genuine failure. Fix: write the request, leave stdin OPEN, and only read stdout for the
    response within `timeout` — terminate the process AFTER we have an answer or the deadline
    passes, never before. Stderr is drained on its own thread the whole time so a chatty child
    can't deadlock on a full pipe while we're only waiting on stdout, and whatever it wrote is
    still available for an honest failure detail."""
    proc = subprocess.Popen(
        command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True,
    )
    try:
        proc.stdin.write(input_data)
        proc.stdin.flush()
    except (BrokenPipeError, OSError):
        pass  # the server may already have exited; fall through and read whatever it left behind

    stdout_q: "queue.Queue[str]" = queue.Queue()
    stderr_chunks: list[str] = []

    def _read_stdout() -> None:
        stdout_q.put(proc.stdout.readline())

    def _read_stderr() -> None:
        for chunk in iter(proc.stderr.readline, ""):
            stderr_chunks.append(chunk)

    threading.Thread(target=_read_stdout, daemon=True).start()
    t_err = threading.Thread(target=_read_stderr, daemon=True)
    t_err.start()

    try:
        line = stdout_q.get(timeout=timeout)
    except queue.Empty:
        line = ""

    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    t_err.join(timeout=1)  # best-effort: grab whatever stderr arrived before/around termination

    stderr = "".join(stderr_chunks)
    if line:
        return 0, line, stderr
    return -1, "", stderr or "timeout"


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
        if "command" not in spec:
            # Remote (url-only) MCP server, e.g. exa web-search: no local process to spawn-probe.
            # Treat as best-effort/non-spawnable (same posture as railway) so it can't fail the
            # health gate — the JSON-RPC stdio handshake doesn't apply to an HTTP transport.
            results.append(McpCheck(name=name, ok=True, detail="remote (skipped spawn-probe)"))
            continue
        cmd = [spec["command"]] + spec.get("args", [])
        try:
            _rc, stdout, stderr = run(cmd, _INIT_REQUEST + "\n", timeout_s)
        except Exception as exc:
            results.append(McpCheck(name=name, ok=False, detail=str(exc)))
            continue
        # SOF-207 rider: a bare "bad response: " / "timeout" with no reason cost a real
        # diagnosis a round-trip (CLAUDE.md §4, honest errors) — always fold in whatever the
        # child actually printed to stderr, since that's usually where the real error lives.
        stderr_tail = f" | stderr: {stderr[-200:]}" if stderr and stderr != "timeout" else ""
        if _rc == -1:
            results.append(McpCheck(name=name, ok=False, detail=f"timeout{stderr_tail}"))
            continue
        first_line = (stdout or "").strip().split("\n")[0] if stdout else ""
        try:
            resp = json.loads(first_line)
            if "result" in resp:
                results.append(McpCheck(name=name, ok=True, detail="connected"))
            else:
                results.append(McpCheck(
                    name=name, ok=False, detail=f"no result: {first_line[:120]}{stderr_tail}"))
        except (json.JSONDecodeError, ValueError):
            results.append(McpCheck(
                name=name, ok=False, detail=f"bad response: {first_line[:120]}{stderr_tail}"))
    return results
