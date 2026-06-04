"""Render the architecture diagram (Mermaid -> SVG) via mmdc (mermaid-cli, uses the chromium
already in the runner image). Injectable runner so we test the command + failure handling offline.
"""
import os

import pytest

from software_factory.diagram import render
from software_factory.deploy import RunResult

MERMAID = "graph TD; web[Vercel] --> api[Railway]; api --> db[Supabase]"


def test_render_invokes_mmdc_and_returns_the_svg_path(tmp_path):
    out = str(tmp_path / "architecture.svg")
    calls = []
    def run(args):
        calls.append(args)
        # mmdc -i <src> -o <out> ; simulate it producing the file
        oi = args.index("-o")
        open(args[oi + 1], "w").write("<svg/>")
        return RunResult(stdout="", returncode=0)
    assert render(MERMAID, out, run=run) == out
    assert os.path.exists(out)
    assert calls[0][0] == "mmdc"
    assert "-o" in calls[0] and out in calls[0]


def test_render_raises_when_mmdc_fails(tmp_path):
    out = str(tmp_path / "architecture.svg")
    with pytest.raises(RuntimeError):
        render(MERMAID, out, run=lambda args: RunResult(stdout="boom", returncode=1))


def test_render_raises_if_no_svg_produced(tmp_path):
    out = str(tmp_path / "architecture.svg")
    # returncode 0 but no file written -> still a failure
    with pytest.raises(RuntimeError):
        render(MERMAID, out, run=lambda args: RunResult(stdout="", returncode=0))
