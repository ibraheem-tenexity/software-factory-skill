"""LIVE smoke of the deploy-DB provision → teardown round-trip against the real Railway CLI.

This is the test the orphan-leak bug demanded: the OLD unit tests MOCKED the railway calls, so the
suite stayed green while prod failed. The teardown incantation (`railway service delete -s <id>
-p <proj> -e <ENV> -y`) has a trap — a wrong `-e` makes the CLI report success/"not found" while the
service SURVIVES. So this smoke does NOT trust teardown's own return: after teardown it INDEPENDENTLY
asserts the service is gone via `railway service list --json` and that its volume cascaded away. A
mock can't satisfy that, and a silently-failing delete fails it loudly.

Run explicitly (opt-in; provisions + deletes a throwaway Postgres in the configured project):
    SF_LIVE=1 RAILWAY_PROJECT_ID=<softwarefactory> RAILWAY_ENVIRONMENT=<the project's env> \
      RAILWAY_TOKEN=... make test-live
RAILWAY_ENVIRONMENT must match the project's real environment (e.g. "software-factory-as-skill" for
the console project, "production" for a standalone one) — a mismatch correctly FAILS this smoke.
Skips silently unless SF_LIVE=1 and `railway` is authenticated.
"""
import json
import os
import subprocess

import pytest

from software_factory import deploy_db, env
from software_factory.deploy import _real_runner

pytestmark = pytest.mark.live


def _railway_authed() -> bool:
    try:
        return subprocess.run(["railway", "whoami"], capture_output=True).returncode == 0
    except FileNotFoundError:
        return False


requires_live = pytest.mark.skipif(
    os.environ.get("SF_LIVE") != "1"
    or not _railway_authed()
    or not env.railway_project_allowed(os.environ.get("RAILWAY_PROJECT_ID")),
    reason="set SF_LIVE=1, authenticate `railway`, and set an allowed RAILWAY_PROJECT_ID to run the live smoke",
)


def _service_ids() -> set:
    """The serviceIds Railway currently reports in the linked project — the independent source of
    truth for "is it gone" (more authoritative than teardown's own return, and uncacheable unlike the
    list_projects MCP)."""
    out = _real_runner(["railway", "service", "list", "--json"]).stdout or "[]"
    data = json.loads(out)
    ids = set()
    # Be permissive about the exact shape: collect any 'id'/'serviceId' field at any depth.
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("id", "serviceId") and isinstance(v, str):
                    ids.add(v)
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(data)
    return ids


def _volume_count_for(service_id: str) -> int:
    out = _real_runner(["railway", "volume", "list", "--json"]).stdout or "[]"
    return json.dumps(json.loads(out)).count(service_id)


@requires_live
def test_provision_then_teardown_really_removes_service_and_volume(tmp_path):
    project_id = "project-smokedb1"
    info = deploy_db.provision(project_id, str(tmp_path), run=_real_runner)
    service_id = info["service_id"]
    assert info["DATABASE_URL"], "provision must yield a real DATABASE_URL"
    assert service_id, "provision must capture the auto-named serviceId"

    try:
        assert service_id in _service_ids(), "the provisioned service should exist before teardown"

        res = deploy_db.teardown(service_id, run=_real_runner)
        assert res["ok"], f"teardown failed: {res['detail']}"

        # INDEPENDENT verification — do NOT trust teardown's own word (a wrong -e silently 'not found's
        # while the service survives). The service AND its cascaded volume must actually be gone.
        assert service_id not in _service_ids(), "service still present after teardown (check the -e env!)"
        assert _volume_count_for(service_id) == 0, "the service's volume did not cascade away"

        # And teardown is idempotent: a re-run of a gone service is a success, not an error.
        assert deploy_db.teardown(service_id, run=_real_runner)["already_gone"] is True
    finally:
        # Never leak a throwaway Postgres if an assertion above blew up mid-way.
        try:
            deploy_db.teardown(service_id, run=_real_runner)
        except Exception:
            pass
