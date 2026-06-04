"""Render the architecture diagram: Mermaid text -> SVG via `mmdc` (mermaid-cli).

The runner image ships `@mermaid-js/mermaid-cli` + chromium, so this shells `mmdc`. The runner
is injectable for offline tests. A non-zero exit or a missing output file is an error — we never
pretend a diagram was produced.
"""
from __future__ import annotations

import subprocess
from typing import Callable

from .deploy import RunResult


def _real_runner(args: list[str]) -> RunResult:
    proc = subprocess.run(args, capture_output=True, text=True)
    return RunResult(stdout=proc.stdout, returncode=proc.returncode)


def render(mermaid_text: str, out_path: str, run: Callable[[list[str]], RunResult] = _real_runner) -> str:
    import os

    src = out_path + ".mmd"
    with open(src, "w") as f:
        f.write(mermaid_text)
    res = run(["mmdc", "-i", src, "-o", out_path])
    if res.returncode != 0:
        raise RuntimeError(f"mmdc failed ({res.returncode}): {res.stdout[:200]}")
    if not os.path.exists(out_path):
        raise RuntimeError(f"mmdc produced no output at {out_path}")
    return out_path
