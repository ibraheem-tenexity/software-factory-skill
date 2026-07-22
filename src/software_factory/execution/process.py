"""OS process primitives used by factory stage execution."""
from __future__ import annotations

import os
from typing import Any

from .. import env as _env


def _make_drop_privileges(uid: int, gid: int):
    """Return a preexec function that drops a child process to the requested user."""
    def _drop():
        os.setgid(gid)
        os.setuid(uid)
    return _drop


def proc_state(pid: int) -> str | None:
    """Return the Linux process-state character or None when the process has gone away."""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None
    after = text.rsplit(")", 1)[-1].split()
    return after[0] if after else None


def default_launch(argv: list[str], env: dict, log_path: str | None = None, cwd: str | None = None) -> Any:
    """Launch a stage with stdout owned directly by the durable project log."""
    import subprocess

    preexec_fn = None
    if os.geteuid() == 0:
        import pwd
        try:
            pw = pwd.getpwnam("node")
            preexec_fn = _make_drop_privileges(pw.pw_uid, pw.pw_gid)
        except KeyError:
            pass
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
