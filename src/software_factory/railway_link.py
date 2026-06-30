"""Re-assert that the Railway CLI is linked to the EXPECTED console target before a deploy is
verified. A drifted link makes the verify run against the wrong project/environment/service and
silently produce a false-negative (TEN-151 / KNOWN_ISSUES #87).

Parses ``railway status`` (plain text — it cleanly prints the *linked* Project / Project ID /
Environment / Environment ID / Service) and compares it to the expected console target, preferring
IDs and falling back to names. Any mismatch raises ``LinkDriftError`` so the caller FAILS LOUDLY
rather than verifying against the wrong target. Asserting (not running ``railway link``) means we
never mutate the global link state — callers pass explicit IDs to their railway commands instead.

CLI: ``python -m software_factory.railway_link`` (exit 0 = linked correctly, 1 = drift). Wrapped by
scripts/assert-railway-link.sh and ``make verify-link``.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from typing import Callable, Mapping, Optional

# Plain `railway status` field → regex capturing the linked value. "Service: None" (no linked
# service) is captured verbatim so it can mismatch an expected service and fail loudly.
# Leading \s* because the Service line is indented under a "Linked service" header in real output.
_FIELDS: dict[str, str] = {
    "project": r"^\s*Project:\s+(.+?)\s*$",
    "project_id": r"^\s*Project ID:\s+(\S+)\s*$",
    "environment": r"^\s*Environment:\s+(.+?)\s*$",
    "environment_id": r"^\s*Environment ID:\s+(\S+)\s*$",
    "service": r"^\s*Service:\s+(.+?)\s*$",
}


class LinkDriftError(RuntimeError):
    """The linked Railway target does not match the expected one."""


def _runner(args: list[str]) -> tuple[str, int]:
    proc = subprocess.run(args, capture_output=True, text=True)
    return (proc.stdout, proc.returncode)


def parse_status(text: str) -> dict:
    """Extract the linked target fields from plain ``railway status`` output. Missing fields are
    None (e.g. a project with no linked service prints 'Service: None', captured as 'None')."""
    out: dict = {}
    for key, pat in _FIELDS.items():
        m = re.search(pat, text, re.MULTILINE)
        out[key] = m.group(1).strip() if m else None
    return out


def expected_from_env(env: Optional[Mapping[str, str]] = None) -> dict:
    """The expected console target. Defaults match scripts/deploy-preflight.sh (softwarefactory /
    factory-console; environment from the preflight's re-link hint). IDs are unset by default —
    set SF_DEPLOY_PROJECT_ID / SF_DEPLOY_ENVIRONMENT_ID to pin exact IDs (preferred over names)."""
    env = os.environ if env is None else env
    return {
        "project": env.get("SF_DEPLOY_PROJECT", "softwarefactory"),
        "environment": env.get("SF_DEPLOY_ENVIRONMENT", "software-factory-as-skill"),
        "service": env.get("SF_DEPLOY_SERVICE", "factory-console"),
        "project_id": env.get("SF_DEPLOY_PROJECT_ID", ""),
        "environment_id": env.get("SF_DEPLOY_ENVIRONMENT_ID", ""),
    }


def assert_link(expected: Mapping[str, str], run: Callable[[list[str]], tuple[str, int]] = _runner) -> dict:
    """Assert the currently-linked Railway target matches ``expected`` (only non-empty expected
    fields are checked). Returns the parsed linked target on success; raises ``LinkDriftError`` —
    loudly listing every mismatch — otherwise. Never mutates link state."""
    out, rc = run(["railway", "status"])
    if rc != 0:
        raise LinkDriftError(
            "could not read `railway status` (exit "
            f"{rc}) — is the Railway CLI logged in and a project linked? Output:\n{out.strip()}"
        )
    actual = parse_status(out)
    mismatches = [
        f"{key}: expected {exp!r}, linked {actual.get(key)!r}"
        for key, exp in expected.items()
        if (exp or "").strip() and (actual.get(key) or "").strip() != exp.strip()
    ]
    if mismatches:
        raise LinkDriftError(
            "railway link drift — refusing to verify against the wrong target:\n  "
            + "\n  ".join(mismatches)
            + f"\n  (linked: {actual.get('project')}/{actual.get('environment')}/{actual.get('service')})"
        )
    return actual


def main(argv: Optional[list[str]] = None) -> int:
    try:
        actual = assert_link(expected_from_env())
    except LinkDriftError as e:
        print(f"\n❌ RAILWAY LINK CHECK FAILED: {e}", file=sys.stderr)
        return 1
    print(
        f"✅ railway link OK — {actual.get('project')} / {actual.get('environment')} / {actual.get('service')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
