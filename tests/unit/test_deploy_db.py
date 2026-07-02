"""Factory-side deploy-database provisioning (the replacement for agent Supabase access).

These tests assert the REAL railway-CLI flow (verified live, CLI 5.12.1): `railway add --database
postgres --json` returns {serviceId, serviceName:"Postgres-XXXX"} (auto-named — NOT a name we pass),
then `railway variables --service <serviceId> --json` yields DATABASE_URL. The old tests mocked a
read-back by a guessed name that never existed in prod — that blind spot shipped the orphan-leak bug.
"""
import json
import os

import pytest

from software_factory import deploy_db
from software_factory.deploy import RunResult


def _runner(outputs):
    seq = iter(outputs)
    calls = []

    def run(args):
        calls.append(args)
        return RunResult(stdout=next(seq), returncode=0)
    run.calls = calls
    return run


_NO_SLEEP = lambda _: None  # noqa: E731 — injected as `sleep=` to skip actual waits in tests

_ADD = json.dumps({"serviceId": "svc-123", "serviceName": "Postgres-RNK8", "templateName": "PostgreSQL"})
_VARS = json.dumps({"DATABASE_URL": "postgresql://u:p@h:5432/railway", "PGHOST": "h"})
_EMPTY_VARS = json.dumps({"PGHOST": "h"})  # no DATABASE_URL — simulates async provisioning in progress


def test_provision_captures_real_service_id_and_reads_url(tmp_path, monkeypatch):
    monkeypatch.delenv("RAILWAY_PROJECT_ID", raising=False)
    run = _runner([_ADD, _VARS])
    info = deploy_db.provision("project-abcd1234", str(tmp_path), run=run)
    assert info["DATABASE_URL"] == "postgresql://u:p@h:5432/railway"
    assert info["service_id"] == "svc-123" and info["service"] == "Postgres-RNK8"
    assert info["provider"] == "railway-postgres"
    # add uses --json (NON-interactive); variables reads by the CAPTURED serviceId (never a guessed name)
    assert run.calls[0] == ["railway", "add", "--database", "postgres", "--json"]
    assert run.calls[1] == ["railway", "variables", "--service", "svc-123", "--json"]
    assert json.load(open(os.path.join(str(tmp_path), deploy_db.DEPLOY_DB_FILE)))["service_id"] == "svc-123"


def test_provision_is_noop_when_already_provisioned(tmp_path):
    deploy_db.write_file(str(tmp_path), {"DATABASE_URL": "x", "service_id": "s", "service": "Postgres-Z"})
    run = _runner([])                                   # must call NOTHING
    info = deploy_db.provision("p", str(tmp_path), run=run)
    assert info["DATABASE_URL"] == "x" and run.calls == []


def test_provision_resumes_from_persisted_service_without_re_adding(tmp_path):
    # A partial handle (add succeeded, URL not yet read) → reuse the service: read variables, NO new add.
    deploy_db.write_file(str(tmp_path), {"service_id": "svc-9", "service": "Postgres-Old",
                                         "provider": "railway-postgres", "project_id": "p"})
    run = _runner([_VARS])
    info = deploy_db.provision("p", str(tmp_path), run=run)
    assert info["DATABASE_URL"] == "postgresql://u:p@h:5432/railway" and info["service_id"] == "svc-9"
    assert run.calls[0] == ["railway", "variables", "--service", "svc-9", "--json"]   # NO add


def test_handle_persisted_before_variables_so_retry_never_re_adds(tmp_path, monkeypatch):
    monkeypatch.delenv("RAILWAY_PROJECT_ID", raising=False)
    # Attempt 1: add succeeds but ALL poll attempts return no URL → raises. serviceId MUST be persisted.
    from software_factory import deploy_db as _db
    n = _db._PROVISION_URL_POLL_ATTEMPTS
    run1 = _runner([_ADD] + [_EMPTY_VARS] * n)   # n vars polls, all without DATABASE_URL
    with pytest.raises(RuntimeError):
        deploy_db.provision("p", str(tmp_path), run=run1, sleep=_NO_SLEEP)
    saved = json.load(open(os.path.join(str(tmp_path), deploy_db.DEPLOY_DB_FILE)))
    assert saved["service_id"] == "svc-123" and "DATABASE_URL" not in saved
    # Attempt 2: reuse the persisted service — NO second add (no orphan), just re-read variables.
    run2 = _runner([_VARS])
    info = deploy_db.provision("p", str(tmp_path), run=run2, sleep=_NO_SLEEP)
    assert info["DATABASE_URL"] == "postgresql://u:p@h:5432/railway"
    assert run2.calls[0][:2] == ["railway", "variables"]      # reused; no "railway add"


def test_provision_polls_until_database_url_appears(tmp_path, monkeypatch):
    """Railway provisions Postgres asynchronously: DATABASE_URL may be absent on early variable
    reads. provision() must retry until it appears (up to _PROVISION_URL_POLL_ATTEMPTS)."""
    monkeypatch.delenv("RAILWAY_PROJECT_ID", raising=False)
    slept = []
    # First 3 variable reads return no URL (async init in progress); 4th has the URL.
    run = _runner([_ADD, _EMPTY_VARS, _EMPTY_VARS, _EMPTY_VARS, _VARS, "{}"])  # vol list = {}
    info = deploy_db.provision("p", str(tmp_path), run=run, sleep=slept.append)
    assert info["DATABASE_URL"] == "postgresql://u:p@h:5432/railway"
    vars_calls = [c for c in run.calls if c[:2] == ["railway", "variables"]]
    assert len(vars_calls) == 4          # 3 empty + 1 success
    assert len(slept) == 3              # slept between each failed attempt


def test_provision_raises_when_url_never_appears_after_all_polls(tmp_path, monkeypatch):
    """If DATABASE_URL never appears across all poll attempts, provision() raises RuntimeError."""
    monkeypatch.delenv("RAILWAY_PROJECT_ID", raising=False)
    from software_factory import deploy_db as _db
    n = _db._PROVISION_URL_POLL_ATTEMPTS
    run = _runner([_ADD] + [_EMPTY_VARS] * n)
    with pytest.raises(RuntimeError, match="after .* attempts"):
        deploy_db.provision("p", str(tmp_path), run=run, sleep=_NO_SLEEP)
    vars_calls = [c for c in run.calls if c[:2] == ["railway", "variables"]]
    assert len(vars_calls) == n         # polled exactly _PROVISION_URL_POLL_ATTEMPTS times


def test_provision_links_project_when_no_token_and_project_id_configured(tmp_path, monkeypatch):
    """In dev (no RAILWAY_TOKEN), links CLI to the configured project ID before `railway add`."""
    from software_factory import env as _env
    monkeypatch.delenv("RAILWAY_TOKEN", raising=False)
    monkeypatch.setattr(_env, "runapp_railway_project_id", lambda: "proj-dev-123")
    _LINK_OK = ""
    run = _runner([_LINK_OK, _ADD, _VARS])
    deploy_db.provision("proj-dev-123", str(tmp_path), run=run)
    assert run.calls[0] == ["railway", "link", "-p", "proj-dev-123"]
    assert run.calls[1] == ["railway", "add", "--database", "postgres", "--json"]


def test_provision_skips_link_in_prod_when_railway_token_is_set(tmp_path, monkeypatch):
    """In prod, RAILWAY_TOKEN is project-scoped; no link call should be made."""
    monkeypatch.setenv("RAILWAY_TOKEN", "tok-xyz")
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "proj-prod-456")
    run = _runner([_ADD, _VARS])
    deploy_db.provision("proj-prod-456", str(tmp_path), run=run)
    assert run.calls[0] == ["railway", "add", "--database", "postgres", "--json"]


def test_provision_raises_when_add_returns_no_service_id(tmp_path, monkeypatch):
    monkeypatch.delenv("RAILWAY_PROJECT_ID", raising=False)
    run = _runner([json.dumps({"error": "nope"}), _VARS])
    with pytest.raises(RuntimeError):
        deploy_db.provision("p", str(tmp_path), run=run)


def test_provision_refuses_disallowed_railway_project(tmp_path, monkeypatch):
    # the console's own project must never host a run app's DB — guard raises BEFORE any CLI call
    from software_factory import env
    monkeypatch.setattr(env, "railway_project_allowed", lambda pid: False)
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "some-other-proj")
    run = _runner([])
    with pytest.raises(RuntimeError):
        deploy_db.provision("project-q", str(tmp_path), run=run)
    assert run.calls == []                              # refused before any railway call


def test_write_file_roundtrip(tmp_path):
    p = deploy_db.write_file(str(tmp_path / "context"), {"DATABASE_URL": "x", "provider": "railway-postgres"})
    assert p.endswith("deploy-db.json")
    assert json.load(open(p))["DATABASE_URL"] == "x"


# ---------------------------------------------------------------------------------------
# TEARDOWN + REAPER — the second half of the orphan-leak fix. Delete the EXACT captured
# Railway Postgres service on terminal/archive (its volume cascades — operator-verified),
# gated by an A/B policy that DEFAULTS DISARMED (dry-run only), idempotent + never a guess.
# Exact incantation (operator l2a7ngax confirmed live): `railway service delete -s <id>
# -p <projectId> -e <ENV> -y`; the -e env MUST match the service's project env or the CLI
# silently "not found"s — so it's pulled from RAILWAY_ENVIRONMENT, never hardcoded.
# ---------------------------------------------------------------------------------------

def _delete_runner(results):
    """results: list of (stdout, returncode) tuples (or RunResult). Records each call's argv."""
    seq = iter(results)
    calls = []

    def run(args):
        calls.append(args)
        r = next(seq)
        return r if isinstance(r, RunResult) else RunResult(stdout=r[0], returncode=r[1])
    run.calls = calls
    return run


def _rec(**kw):
    base = dict(project_id="p", service_id="svc", archived=False, phase="", has_verified_deploy=False)
    base.update(kw)
    return deploy_db.ReapRecord(**base)


def test_teardown_deletes_captured_service_with_full_env_scope(monkeypatch):
    # Primary path: teardown uses runapp_railway_project_id() (from SF_RUNAPP_RAILWAY_PROJECT_IDS),
    # NOT RAILWAY_PROJECT_ID (which Railway forces to the console's own project on prod).
    from software_factory import env as _env
    monkeypatch.setattr(_env, "runapp_railway_project_id", lambda: "8ecbd1b2")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "software-factory-as-skill")
    monkeypatch.delenv("RAILWAY_ENVIRONMENT_ID", raising=False)
    run = _delete_runner([("Service deleted", 0)])
    res = deploy_db.teardown("svc-123", run=run)
    assert res["ok"] and res["deleted"] and not res["already_gone"]
    # `service delete` (NOT `railway delete`, which removes the whole project); -e is the project's
    # real env; no volume_id passed so no separate volume command issued.
    assert run.calls == [["railway", "service", "delete", "-s", "svc-123",
                          "-p", "8ecbd1b2", "-e", "software-factory-as-skill", "-y"]]
    assert res["volume_already_gone"] is True and res["volume_deleted"] is False


def test_teardown_falls_back_to_railway_project_id_when_runapp_not_configured(monkeypatch):
    # Fallback: when SF_RUNAPP_RAILWAY_PROJECT_IDS is absent, use RAILWAY_PROJECT_ID.
    from software_factory import env as _env
    monkeypatch.setattr(_env, "runapp_railway_project_id", lambda: None)
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "fallback-proj")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.delenv("RAILWAY_ENVIRONMENT_ID", raising=False)
    run = _delete_runner([("Service deleted", 0)])
    res = deploy_db.teardown("svc-fb", run=run)
    assert res["ok"] and res["deleted"]
    assert run.calls[0][run.calls[0].index("-p") + 1] == "fallback-proj"


def test_teardown_is_idempotent_when_service_already_gone(monkeypatch):
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "p")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    run = _delete_runner([("Service not found", 1)])      # re-attempt of a gone service
    res = deploy_db.teardown("svc-9", run=run)
    assert res["ok"] and res["already_gone"] and not res["deleted"]


def test_teardown_detects_already_gone_when_not_found_is_on_stderr(monkeypatch):
    # railway may print "not found" to stderr (rc!=0) rather than stdout — still an idempotent success.
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "p")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    run = _delete_runner([RunResult(stdout="", returncode=1, stderr="Service not found")])
    res = deploy_db.teardown("svc-gone", run=run)
    assert res["ok"] and res["already_gone"] and not res["deleted"]


def test_teardown_idempotent_no_services_found_stderr(monkeypatch):
    # Live rehearsal (zji9befj) caught: re-deleting a gone service prints
    # "No services found in environment 'production'" on stderr with rc=1.
    # Must map to already_gone=True, ok=True — not a failure.
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "p")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    run = _delete_runner([RunResult(stdout="", returncode=1,
                                   stderr="No services found in environment 'production'")])
    res = deploy_db.teardown("svc-reherase", run=run)
    assert res["ok"] and res["already_gone"] and not res["deleted"]


def test_teardown_refuses_empty_service_id_without_any_cli_call():
    run = _delete_runner([])
    for bad in ("", "   ", None):
        with pytest.raises(ValueError):
            deploy_db.teardown(bad, run=run)
    assert run.calls == []        # never guess a name, never call the CLI without a captured id


def test_teardown_env_falls_back_to_id_then_production(monkeypatch):
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "p")
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "env-uuid-1")
    run = _delete_runner([("ok", 0)])
    deploy_db.teardown("s", run=run)
    assert run.calls[0][run.calls[0].index("-e") + 1] == "env-uuid-1"
    monkeypatch.delenv("RAILWAY_ENVIRONMENT_ID", raising=False)
    run2 = _delete_runner([("ok", 0)])
    deploy_db.teardown("s", run=run2)
    assert run2.calls[0][run2.calls[0].index("-e") + 1] == "production"


def test_teardown_reports_real_failure(monkeypatch):
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "p")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    run = _delete_runner([("Unauthorized", 1)])           # a real error, NOT "not found"
    res = deploy_db.teardown("svc-x", run=run)
    assert not res["ok"] and not res["already_gone"] and not res["deleted"]


def test_teardown_mode_reads_env_default_off(monkeypatch):
    monkeypatch.delenv("SF_DEPLOY_DB_TEARDOWN", raising=False)
    assert deploy_db.teardown_mode() == "off"             # DISARMED by default — the HELD state
    for v in ("persistent", "b", "B", " Persistent "):
        monkeypatch.setenv("SF_DEPLOY_DB_TEARDOWN", v)
        assert deploy_db.teardown_mode() == "persistent"
    for v in ("ephemeral", "a", "A"):
        monkeypatch.setenv("SF_DEPLOY_DB_TEARDOWN", v)
        assert deploy_db.teardown_mode() == "ephemeral"
    monkeypatch.setenv("SF_DEPLOY_DB_TEARDOWN", "garbage")
    assert deploy_db.teardown_mode() == "off"             # unknown value is treated as disarmed


def test_reap_reason_persistent_policy_keeps_live_demos():
    R = deploy_db._reap_reason
    assert R(_rec(archived=True), "persistent") == "archived"
    assert R(_rec(archived=True, has_verified_deploy=True), "persistent") == "archived"  # discard reaps even a live one
    assert R(_rec(phase="stopped"), "persistent") == "stopped-without-deploy"
    assert R(_rec(phase="stopped", has_verified_deploy=True), "persistent") is None       # KEEP live demo
    assert R(_rec(phase="done", has_verified_deploy=True), "persistent") is None           # KEEP the demo
    assert R(_rec(phase="done"), "persistent") is None                                     # no auto-reap on done
    assert R(_rec(phase="stage3"), "persistent") is None                                   # active → keep


def test_reap_reason_ephemeral_policy_reaps_any_terminal():
    R = deploy_db._reap_reason
    assert R(_rec(phase="done", has_verified_deploy=True), "ephemeral") == "done"          # reap even a live one
    assert R(_rec(phase="stopped"), "ephemeral") == "stopped"
    assert R(_rec(archived=True), "ephemeral") == "archived"
    assert R(_rec(phase="provision"), "ephemeral") is None                                 # active → keep


def test_reap_disarmed_is_dry_run_and_deletes_nothing(monkeypatch):
    monkeypatch.delenv("SF_DEPLOY_DB_TEARDOWN", raising=False)        # off
    _empty_vols = json.dumps({"volumes": []})
    run = _delete_runner([(_empty_vols, 0)])                         # only the volume list probe
    recs = [_rec(project_id="p1", service_id="s1", archived=True),
            _rec(project_id="p2", service_id="s2", phase="done", has_verified_deploy=True)]
    report = deploy_db.reap(recs, run=run, log=lambda m: None)
    delete_calls = [c for c in run.calls if "delete" in c]
    assert delete_calls == []                                        # DRY-RUN: no deletes
    assert report["armed"] is False and report["mode"] == "off"
    assert {w["service_id"] for w in report["would_reap"]} == {"s1"}  # archived → would reap under B
    assert {k["service_id"] for k in report["kept"]} == {"s2"}       # live done → kept


def test_reap_armed_persistent_deletes_only_eligible_and_keeps_demos(monkeypatch):
    monkeypatch.setenv("SF_DEPLOY_DB_TEARDOWN", "persistent")
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "softwarefactory")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "software-factory-as-skill")
    recs = [_rec(project_id="p1", service_id="s1", archived=True),                    # reap
            _rec(project_id="p2", service_id="s2", phase="stopped"),                  # reap (no deploy)
            _rec(project_id="p3", service_id="s3", phase="done", has_verified_deploy=True),  # KEEP demo
            _rec(project_id="p4", service_id="")]                                     # never provisioned → skip
    _empty_vols = json.dumps({"volumes": []})
    run = _delete_runner([("deleted", 0), ("deleted", 0), (_empty_vols, 0)])  # 2 service deletes + vol list
    report = deploy_db.reap(recs, run=run, log=lambda m: None)
    svc_delete_calls = [c for c in run.calls if "service" in c and "delete" in c]
    deleted_ids = sorted(c[c.index("-s") + 1] for c in svc_delete_calls)
    assert deleted_ids == ["s1", "s2"]                              # demo s3 untouched; empty s4 skipped
    assert {r["service_id"] for r in report["reaped"]} == {"s1", "s2"}
    assert {k["service_id"] for k in report["kept"]} == {"s3"}


def test_reap_dry_run_override_forces_preview_even_when_armed(monkeypatch):
    monkeypatch.setenv("SF_DEPLOY_DB_TEARDOWN", "ephemeral")          # armed
    _empty_vols = json.dumps({"volumes": []})
    run = _delete_runner([(_empty_vols, 0)])                         # only the volume list probe
    report = deploy_db.reap([_rec(service_id="s1", archived=True)], run=run,
                            log=lambda m: None, dry_run=True)
    delete_calls = [c for c in run.calls if "delete" in c]
    assert delete_calls == []                                        # forced preview: no deletes
    assert {w["service_id"] for w in report["would_reap"]} == {"s1"}


# ---------------------------------------------------------------------------------------
# Volume teardown tests — live-verified (2026-06-24): `railway service delete` does NOT
# cascade volumes. These tests verify the explicit volume delete path.
# ---------------------------------------------------------------------------------------

def test_teardown_also_deletes_volume_after_service(monkeypatch):
    from software_factory import env as _env
    monkeypatch.setattr(_env, "runapp_railway_project_id", lambda: "8ecbd1b2")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.delenv("RAILWAY_ENVIRONMENT_ID", raising=False)
    run = _delete_runner([("Service deleted", 0), ("Volume deleted", 0)])
    res = deploy_db.teardown("svc-123", volume_id="vol-456", run=run)
    assert res["ok"] and res["deleted"] and res["volume_deleted"]
    assert not res["volume_already_gone"]
    assert run.calls[0][:4] == ["railway", "service", "delete", "-s"]
    assert run.calls[1] == ["railway", "volume", "delete", "--volume", "vol-456", "--yes"]


def test_teardown_volume_idempotent_when_already_gone(monkeypatch):
    from software_factory import env as _env
    monkeypatch.setattr(_env, "runapp_railway_project_id", lambda: "8ecbd1b2")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.delenv("RAILWAY_ENVIRONMENT_ID", raising=False)
    run = _delete_runner([("Service deleted", 0),
                          RunResult(stdout="", returncode=1, stderr="volume does not exist")])
    res = deploy_db.teardown("svc-123", volume_id="vol-456", run=run)
    assert res["ok"] and res["volume_already_gone"] and not res["volume_deleted"]


def test_parse_detached_volumes_returns_ids_with_no_service_name():
    vol_json = json.dumps({"volumes": [
        {"id": "vol-orphan1", "serviceName": None, "deletedAt": None},
        {"id": "vol-orphan2", "serviceName": "", "deletedAt": None},
        {"id": "vol-attached", "serviceName": "Postgres-XYZ", "deletedAt": None},
        {"id": "vol-deleted", "serviceName": None, "deletedAt": "2024-01-01"},
    ]})
    ids = deploy_db._parse_detached_volumes(vol_json)
    assert set(ids) == {"vol-orphan1", "vol-orphan2"}


def test_sweep_detached_volumes_dry_run_logs_without_deleting():
    vol_json = json.dumps({"volumes": [
        {"id": "vol-1", "serviceName": None, "deletedAt": None},
        {"id": "vol-2", "serviceName": None, "deletedAt": None},
    ]})
    run = _delete_runner([(vol_json, 0)])  # only the list call
    msgs = []
    report = deploy_db.sweep_detached_volumes(run=run, log=msgs.append, dry_run=True)
    assert set(report["would_sweep"]) == {"vol-1", "vol-2"}
    assert report["swept"] == [] and report["failed"] == []
    assert run.calls == [["railway", "volume", "list", "--json"]]  # no delete calls


def test_sweep_detached_volumes_armed_deletes_orphans():
    vol_json = json.dumps({"volumes": [
        {"id": "vol-orphan", "serviceName": None, "deletedAt": None},
        {"id": "vol-attached", "serviceName": "Postgres-RNK8", "deletedAt": None},
    ]})
    run = _delete_runner([(vol_json, 0), ("Volume deleted", 0)])
    report = deploy_db.sweep_detached_volumes(run=run, log=lambda m: None, dry_run=False)
    assert report["swept"] == ["vol-orphan"]
    assert report["would_sweep"] == [] and report["failed"] == []
    assert run.calls[1] == ["railway", "volume", "delete", "--volume", "vol-orphan", "--yes"]


def test_reap_includes_detached_volume_sweep_in_report(monkeypatch):
    monkeypatch.setenv("SF_DEPLOY_DB_TEARDOWN", "persistent")
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "softwarefactory")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    vol_json = json.dumps({"volumes": [
        {"id": "vol-orphan", "serviceName": None, "deletedAt": None},
    ]})
    # 1 service delete + 1 volume list + 1 volume delete
    run = _delete_runner([("deleted", 0), (vol_json, 0), ("Volume deleted", 0)])
    recs = [_rec(project_id="p1", service_id="s1", archived=True)]
    report = deploy_db.reap(recs, run=run, log=lambda m: None)
    assert report["detached_volumes"]["swept"] == ["vol-orphan"]


def test_provision_captures_volume_id(tmp_path, monkeypatch):
    monkeypatch.delenv("RAILWAY_PROJECT_ID", raising=False)
    vol_list = json.dumps({"volumes": [
        {"id": "vol-abc", "serviceName": "Postgres-RNK8", "deletedAt": None},
        {"id": "vol-other", "serviceName": "OtherService", "deletedAt": None},
    ]})
    run = _runner([_ADD, _VARS, vol_list])
    info = deploy_db.provision("project-abcd1234", str(tmp_path), run=run)
    assert info.get("volume_id") == "vol-abc"
    assert run.calls[2] == ["railway", "volume", "list", "--json"]
    saved = json.load(open(os.path.join(str(tmp_path), deploy_db.DEPLOY_DB_FILE)))
    assert saved.get("volume_id") == "vol-abc"


# =======================================================================================
# GraphQL API path — teardown (serviceDelete) + variables-read (DATABASE_URL query).
#
# Both ops use `RAILWAY_TOKEN` for bearer-auth. No ambient CLI link state.
# Tests mock urllib.request.urlopen to avoid real HTTP calls.
# =======================================================================================

import io
import urllib.request


def _mock_urlopen(body: dict | None = None, exc: Exception | None = None):
    """Return a context-manager mock for urllib.request.urlopen.

    Pass `body` for a successful response (JSON-serialised) or `exc` to simulate an error.
    """
    if exc is not None:
        def _raise(*a, **kw):
            raise exc
        return _raise

    encoded = json.dumps(body or {}).encode()

    class _FakeResp:
        def read(self):
            return encoded
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass

    def _open(*a, **kw):
        return _FakeResp()
    return _open


# ---------------------------------------------------------------------------------------
# _graphql_service_delete — the low-level GraphQL helper
# ---------------------------------------------------------------------------------------

def test_graphql_service_delete_success(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen",
                        _mock_urlopen({"data": {"serviceDelete": True}}))
    res = deploy_db._graphql_service_delete("svc-gql-1", "tok-abc")
    assert res["ok"] and res["deleted"] and not res["already_gone"]
    assert res["service_id"] == "svc-gql-1"


def test_graphql_service_delete_not_found_is_idempotent(monkeypatch):
    body = {"errors": [{"message": "Service not found"}]}
    monkeypatch.setattr(urllib.request, "urlopen", _mock_urlopen(body))
    res = deploy_db._graphql_service_delete("svc-gone", "tok-abc")
    assert res["ok"] and res["already_gone"] and not res["deleted"]


def test_graphql_service_delete_real_failure(monkeypatch):
    body = {"errors": [{"message": "Unauthorized"}]}
    monkeypatch.setattr(urllib.request, "urlopen", _mock_urlopen(body))
    res = deploy_db._graphql_service_delete("svc-x", "tok-bad")
    assert not res["ok"] and not res["deleted"] and not res["already_gone"]
    assert "Unauthorized" in res["detail"]


def test_graphql_service_delete_network_error_returns_failure(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen",
                        _mock_urlopen(exc=OSError("connection refused")))
    res = deploy_db._graphql_service_delete("svc-x", "tok-abc")
    assert not res["ok"] and not res["deleted"]
    assert "graphql error" in res["detail"]


# ---------------------------------------------------------------------------------------
# _graphql_get_database_url — the variables-read helper
# ---------------------------------------------------------------------------------------

def test_graphql_get_database_url_success(monkeypatch):
    url = "postgresql://u:p@host:5432/db"
    body = {"data": {"variables": {"DATABASE_URL": url, "PGHOST": "host"}}}
    monkeypatch.setattr(urllib.request, "urlopen", _mock_urlopen(body))
    result = deploy_db._graphql_get_database_url("svc-1", "proj-1", "env-1", "tok")
    assert result == url


def test_graphql_get_database_url_falls_back_to_public_url(monkeypatch):
    url = "postgresql://u:p@host:5432/db"
    body = {"data": {"variables": {"DATABASE_PUBLIC_URL": url}}}
    monkeypatch.setattr(urllib.request, "urlopen", _mock_urlopen(body))
    result = deploy_db._graphql_get_database_url("svc-1", "proj-1", "env-1", "tok")
    assert result == url


def test_graphql_get_database_url_returns_none_when_missing(monkeypatch):
    body = {"data": {"variables": {"PGHOST": "host"}}}
    monkeypatch.setattr(urllib.request, "urlopen", _mock_urlopen(body))
    result = deploy_db._graphql_get_database_url("svc-1", "proj-1", "env-1", "tok")
    assert result is None


def test_graphql_get_database_url_returns_none_on_network_error(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen",
                        _mock_urlopen(exc=OSError("timeout")))
    result = deploy_db._graphql_get_database_url("svc-1", "proj-1", "env-1", "tok")
    assert result is None


# ---------------------------------------------------------------------------------------
# teardown() — GraphQL path when RAILWAY_TOKEN is set
# ---------------------------------------------------------------------------------------

def test_teardown_uses_graphql_when_railway_token_set(monkeypatch):
    """With RAILWAY_TOKEN set, teardown() uses GraphQL — the CLI `run` function is never called."""
    monkeypatch.setenv("RAILWAY_TOKEN", "tok-prod")
    monkeypatch.setattr(urllib.request, "urlopen",
                        _mock_urlopen({"data": {"serviceDelete": True}}))
    run = _delete_runner([])         # must stay empty — GraphQL path, not CLI
    res = deploy_db.teardown("svc-graphql", run=run)
    assert res["ok"] and res["deleted"] and res["service_id"] == "svc-graphql"
    assert run.calls == []           # no CLI calls


def test_teardown_graphql_idempotent_when_not_found(monkeypatch):
    monkeypatch.setenv("RAILWAY_TOKEN", "tok-prod")
    body = {"errors": [{"message": "Service not found"}]}
    monkeypatch.setattr(urllib.request, "urlopen", _mock_urlopen(body))
    run = _delete_runner([])
    res = deploy_db.teardown("svc-gone", run=run)
    assert res["ok"] and res["already_gone"] and not res["deleted"]
    assert run.calls == []


def test_teardown_graphql_and_cli_volume_delete(monkeypatch):
    """Service delete via GraphQL; volume delete still uses the CLI (out of scope)."""
    monkeypatch.setenv("RAILWAY_TOKEN", "tok-prod")
    monkeypatch.setattr(urllib.request, "urlopen",
                        _mock_urlopen({"data": {"serviceDelete": True}}))
    run = _delete_runner([("Volume deleted", 0)])
    res = deploy_db.teardown("svc-g", volume_id="vol-v", run=run)
    assert res["ok"] and res["deleted"] and res["volume_deleted"]
    assert run.calls == [["railway", "volume", "delete", "--volume", "vol-v", "--yes"]]


def test_teardown_cli_fallback_when_no_railway_token(monkeypatch):
    """Without RAILWAY_TOKEN (dev environment), teardown() falls back to the CLI."""
    monkeypatch.delenv("RAILWAY_TOKEN", raising=False)
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "proj-dev")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    run = _delete_runner([("Service deleted", 0)])
    res = deploy_db.teardown("svc-cli", run=run)
    assert res["ok"] and res["deleted"]
    assert any("service" in c and "delete" in c for c in run.calls)


# ---------------------------------------------------------------------------------------
# provision() — variables read via GraphQL when RAILWAY_TOKEN + env_id are both set
# ---------------------------------------------------------------------------------------

def test_provision_variables_read_via_graphql_when_token_and_env_id_set(tmp_path, monkeypatch):
    """provision() uses GraphQL for the DATABASE_URL poll when RAILWAY_TOKEN and
    SF_RUNAPP_RAILWAY_ENVIRONMENT_IDS are both configured (the prod path)."""
    monkeypatch.setenv("RAILWAY_TOKEN", "tok-prod")
    from software_factory import env as _env
    monkeypatch.setattr(_env, "runapp_railway_project_id", lambda: "proj-sfp")
    monkeypatch.setattr(_env, "runapp_railway_environment_id", lambda: "env-prod-sfp")
    monkeypatch.delenv("RAILWAY_PROJECT_ID", raising=False)

    url = "postgresql://u:p@host:5432/db"
    gql_body = {"data": {"variables": {"DATABASE_URL": url}}}
    vol_json = json.dumps({"volumes": []})
    monkeypatch.setattr(urllib.request, "urlopen", _mock_urlopen(gql_body))

    # run is called for: railway add, railway volume list. NOT for variables (GraphQL handles it).
    run = _runner([_ADD, vol_json])
    info = deploy_db.provision("project-abcd1234", str(tmp_path), run=run)
    assert info["DATABASE_URL"] == url
    assert info["service_id"] == "svc-123"
    # Exactly 2 CLI calls: add + volume list. No "railway variables" call.
    assert len(run.calls) == 2
    assert run.calls[0] == ["railway", "add", "--database", "postgres", "--json"]
    assert run.calls[1] == ["railway", "volume", "list", "--json"]


def test_provision_variables_read_falls_back_to_cli_when_no_env_id(tmp_path, monkeypatch):
    """Without SF_RUNAPP_RAILWAY_ENVIRONMENT_IDS, provision() uses CLI `railway variables`."""
    monkeypatch.setenv("RAILWAY_TOKEN", "tok-prod")
    from software_factory import env as _env
    monkeypatch.setattr(_env, "runapp_railway_project_id", lambda: "proj-sfp")
    monkeypatch.setattr(_env, "runapp_railway_environment_id", lambda: None)  # not set
    monkeypatch.delenv("RAILWAY_PROJECT_ID", raising=False)

    vol_json = json.dumps({"volumes": []})
    run = _runner([_ADD, _VARS, vol_json])
    info = deploy_db.provision("project-abcd1234", str(tmp_path), run=run)
    assert info["DATABASE_URL"] == "postgresql://u:p@h:5432/railway"
    # 3 CLI calls: add + variables (CLI fallback) + volume list
    assert run.calls[1] == ["railway", "variables", "--service", "svc-123", "--json"]


def test_provision_variables_read_falls_back_to_cli_when_no_token(tmp_path, monkeypatch):
    """Without RAILWAY_TOKEN (dev), provision() uses CLI `railway variables`."""
    monkeypatch.delenv("RAILWAY_TOKEN", raising=False)
    monkeypatch.delenv("RAILWAY_PROJECT_ID", raising=False)
    from software_factory import env as _env
    monkeypatch.setattr(_env, "runapp_railway_environment_id", lambda: "env-prod-sfp")

    vol_json = json.dumps({"volumes": []})
    run = _runner([_ADD, _VARS, vol_json])
    info = deploy_db.provision("project-abcd1234", str(tmp_path), run=run)
    assert info["DATABASE_URL"] == "postgresql://u:p@h:5432/railway"
    assert run.calls[1] == ["railway", "variables", "--service", "svc-123", "--json"]


# ---------------------------------------------------------------------------------------
# env.runapp_railway_environment_id()
# ---------------------------------------------------------------------------------------

def test_runapp_railway_environment_id_returns_single_id(monkeypatch):
    from software_factory import env as _env
    monkeypatch.setattr(_env, "_RUNAPP_RAILWAY_ENVIRONMENT_IDS",
                        {"3c8117be-4cb0-41b0-a4ff-0bc9eb8e90eb"})
    assert _env.runapp_railway_environment_id() == "3c8117be-4cb0-41b0-a4ff-0bc9eb8e90eb"


def test_runapp_railway_environment_id_returns_none_when_unset(monkeypatch):
    from software_factory import env as _env
    monkeypatch.setattr(_env, "_RUNAPP_RAILWAY_ENVIRONMENT_IDS", set())
    assert _env.runapp_railway_environment_id() is None


def test_runapp_railway_environment_id_returns_none_when_multiple(monkeypatch):
    from software_factory import env as _env
    monkeypatch.setattr(_env, "_RUNAPP_RAILWAY_ENVIRONMENT_IDS", {"env-1", "env-2"})
    assert _env.runapp_railway_environment_id() is None


# ---------------------------------------------------------------------------------------
# #107 post-deploy "provide your own key" flow — set_app_variable pushes a value onto the
# run-app's OWN Railway service (never the deploy-DB service) and triggers a redeploy.
# Unlike the deploy-DB service (Railway auto-names it, e.g. "Postgres-RNK8" — the exact scar
# above), the app's service name IS deterministic: stage-3's SKILL always creates it as
# f"sf-{project_id}" — so an exact-name GraphQL lookup here is not the same guess.
# ---------------------------------------------------------------------------------------

_SERVICES_PAGE = {
    "data": {"project": {"services": {"edges": [
        {"node": {"id": "svc-other", "name": "sf-project-other"}},
        {"node": {"id": "svc-app123", "name": "sf-project-app123"}},
    ]}}}
}


def _configure_runapp(monkeypatch, project_id="runapp-proj", env_id="runapp-env"):
    from software_factory import env as _env
    monkeypatch.setattr(_env, "runapp_railway_project_id", lambda: project_id)
    monkeypatch.setattr(_env, "runapp_railway_environment_id", lambda: env_id)
    monkeypatch.setenv("RAILWAY_TOKEN", "tok-xyz")


def test_find_service_by_name_exact_match_only(monkeypatch):
    monkeypatch.setattr(deploy_db, "_graphql", lambda q, v, t: _SERVICES_PAGE)
    assert deploy_db._graphql_find_service_by_name("p", "sf-project-app123", "tok") == "svc-app123"
    assert deploy_db._graphql_find_service_by_name("p", "sf-project-app123-extra", "tok") is None
    assert deploy_db._graphql_find_service_by_name("p", "sf-project-app", "tok") is None  # no partial match


def test_find_service_by_name_returns_none_on_graphql_error(monkeypatch):
    def _boom(q, v, t):
        raise RuntimeError("network down")
    monkeypatch.setattr(deploy_db, "_graphql", _boom)
    assert deploy_db._graphql_find_service_by_name("p", "sf-x", "tok") is None


def test_set_app_variable_fails_loud_with_no_token(monkeypatch):
    monkeypatch.delenv("RAILWAY_TOKEN", raising=False)
    res = deploy_db.set_app_variable("proj-app123", "OPENROUTER_API_KEY", "sk-real")
    assert res == {"ok": False, "detail": "RAILWAY_TOKEN not set on the console"}


def test_set_app_variable_fails_loud_when_runapp_project_unconfigured(monkeypatch):
    from software_factory import env as _env
    monkeypatch.setenv("RAILWAY_TOKEN", "tok-xyz")
    monkeypatch.setattr(_env, "runapp_railway_project_id", lambda: None)
    monkeypatch.setattr(_env, "runapp_railway_environment_id", lambda: None)
    res = deploy_db.set_app_variable("proj-app123", "OPENROUTER_API_KEY", "sk-real")
    assert res["ok"] is False and "not configured" in res["detail"]


def test_set_app_variable_fails_loud_when_service_not_found(monkeypatch):
    _configure_runapp(monkeypatch)
    monkeypatch.setattr(deploy_db, "_graphql", lambda q, v, t: {"data": {"project": {"services": {"edges": []}}}})
    res = deploy_db.set_app_variable("proj-nope", "OPENROUTER_API_KEY", "sk-real")
    assert res["ok"] is False
    assert "sf-proj-nope" in res["detail"]


def test_set_app_variable_upserts_and_returns_resolved_service_id(monkeypatch):
    _configure_runapp(monkeypatch)
    calls = []

    def _fake_graphql(query, variables, token):
        calls.append((query, variables))
        if "project(id:" in query or "services" in query:
            return _SERVICES_PAGE
        return {"data": {"variableUpsert": True}}
    monkeypatch.setattr(deploy_db, "_graphql", _fake_graphql)
    res = deploy_db.set_app_variable("project-app123", "OPENROUTER_API_KEY", "sk-real")
    assert res == {"ok": True, "service_id": "svc-app123"}
    # The upsert call carried the resolved serviceId + the run-app project/env, never a guess.
    upsert_call = [c for c in calls if "variableUpsert" in c[0]][0]
    assert upsert_call[1]["input"] == {
        "projectId": "runapp-proj", "environmentId": "runapp-env",
        "serviceId": "svc-app123", "name": "OPENROUTER_API_KEY", "value": "sk-real",
    }


def test_set_app_variable_skips_lookup_when_service_id_given(monkeypatch):
    _configure_runapp(monkeypatch)
    calls = []

    def _fake_graphql(query, variables, token):
        calls.append(query)
        return {"data": {"variableUpsert": True}}
    monkeypatch.setattr(deploy_db, "_graphql", _fake_graphql)
    res = deploy_db.set_app_variable("project-app123", "OPENROUTER_API_KEY", "sk-real", service_id="svc-known")
    assert res == {"ok": True, "service_id": "svc-known"}
    assert len(calls) == 1  # no name-lookup query at all — the explicit id short-circuits it


def test_set_app_variable_fails_loud_on_graphql_errors(monkeypatch):
    _configure_runapp(monkeypatch)

    def _fake_graphql(query, variables, token):
        if "services" in query:
            return _SERVICES_PAGE
        return {"errors": [{"message": "variable value too large"}]}
    monkeypatch.setattr(deploy_db, "_graphql", _fake_graphql)
    res = deploy_db.set_app_variable("project-app123", "OPENROUTER_API_KEY", "x" * 999999)
    assert res["ok"] is False and "too large" in res["detail"]
