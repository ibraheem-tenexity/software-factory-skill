"""Architectural guard: the SKILL is the six deterministic core modules; the telemetry/proof
harness (agents, sinks, evidence) and the console are the demo layer ON TOP.

Dependencies must run one way: product -> core, never core -> product. This test imports the
core in a CLEAN interpreter and asserts none of the harness got pulled in transitively. It
fails the instant a core module gains `from .agents import ...` (etc.), catching the drift
that prompted the decoupling.
"""
import subprocess
import sys

CORE = ["budget", "runstate", "tickets", "repo", "deploy", "gate", "workspace", "creds", "streamlog", "events", "gates", "diagram", "memory"]
HARNESS = ["agents", "sinks", "evidence", "console"]


def test_core_modules_do_not_import_the_harness():
    program = (
        "import sys;"
        + "".join(f"import software_factory.{m};" for m in CORE)
        + "loaded=[h for h in "
        + repr(HARNESS)
        + " if 'software_factory.'+h in sys.modules];"
        + "print(','.join(loaded))"
    )
    out = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True, text=True, cwd="src",
    )
    assert out.returncode == 0, out.stderr
    leaked = out.stdout.strip()
    assert leaked == "", f"core modules transitively imported the harness: {leaked}"
