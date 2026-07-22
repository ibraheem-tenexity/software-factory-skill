"""OS process primitives used by factory stage execution."""
from __future__ import annotations

import os
from typing import Any

from .. import env as _env


def _make_drop_privileges(uid: int, gid: int):
    """Return a preexec_fn that drops from root to (uid, gid) in the child process."""
    def _drop():
        os.setgid(gid)
        os.setuid(uid)
    return _drop


def proc_state(pid: int) -> str | None:
    """The process-state char from /proc/{pid}/stat ('Z' = zombie/defunct), or None if the pid
    doesn't exist at all (already fully reaped by something else). An independent, OS-level
    signal — #129: a tracked Popen handle's own .poll() was observed to persistently report
    "not exited" for hours for a process `ps` showed as `<defunct>`, so it must never be the
    ONLY signal of whether a stage process is actually still alive."""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None
    # Format: "pid (comm) state ...". comm can itself contain spaces/parens, so split on the
    # LAST ')' rather than the first.
    after = text.rsplit(")", 1)[-1].split()
    return after[0] if after else None


def default_launch(argv: list[str], env: dict, log_path: str | None = None, cwd: str | None = None) -> Any:
    """Launch a stage with stdout appended DIRECTLY to project.log — never through a pipe
    pumped by this server. A pump thread dies with the server, leaving the orchestrator
    writing into a readerless pipe: project.log freezes, the §4 brake goes spend-blind, and
    the child can wedge on the full pipe buffer (run-5b7aef7a live scar — the monolithic
    agent built for an hour with zero log visibility after a server restart). The child
    owning its own log fd survives any number of server deaths."""
    import subprocess

    # Claude Code refuses --dangerously-skip-permissions when run as root. When the factory
    # is running as root (Railway may start the container as root despite the Dockerfile USER
    # directive, or the entrypoint setpriv may not be available), drop the child process to the
    # unprivileged `node` user (uid/gid 1000 in node:20-bookworm) before exec. The parent
    # server process keeps its uid — only the spawned stage agent drops.
    preexec_fn = None
    if os.geteuid() == 0:
        import pwd
        try:
            pw = pwd.getpwnam("node")
            preexec_fn = _make_drop_privileges(pw.pw_uid, pw.pw_gid)
        except KeyError:
            pass  # node user absent (local dev); proceed as-is
    if log_path:
        with open(log_path, "ab") as logf:
            return subprocess.Popen(
                argv, env=_env.stage_env_baseline(env), cwd=cwd,
                stdout=logf, stderr=subprocess.STDOUT, preexec_fn=preexec_fn,
            )
    return subprocess.Popen(
        argv, env=_env.stage_env_baseline(env), cwd=cwd,
        stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, preexec_fn=preexec_fn,
    )
