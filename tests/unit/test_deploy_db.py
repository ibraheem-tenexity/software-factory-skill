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


_ADD = json.dumps({"serviceId": "svc-123", "serviceName": "Postgres-RNK8", "templateName": "PostgreSQL"})
_VARS = json.dumps({"DATABASE_URL": "postgresql://u:p@h:5432/railway", "PGHOST": "h"})


def test_needs_deploy_db():
    assert deploy_db.needs_deploy_db(["DATABASE_URL"])
    assert deploy_db.needs_deploy_db(["SUPABASE_URL", "FOO"])
    assert deploy_db.needs_deploy_db(["POSTGRES_PASSWORD"])
    assert not deploy_db.needs_deploy_db(["OPENROUTER_API_KEY", "NEXTAUTH_SECRET"])
    assert not deploy_db.needs_deploy_db([])
    assert not deploy_db.needs_deploy_db(None)


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
    # Attempt 1: add succeeds but variables returns no URL → raises. The serviceId MUST be persisted.
    run1 = _runner([_ADD, json.dumps({"PGHOST": "h"})])   # vars without DATABASE_URL
    with pytest.raises(RuntimeError):
        deploy_db.provision("p", str(tmp_path), run=run1)
    saved = json.load(open(os.path.join(str(tmp_path), deploy_db.DEPLOY_DB_FILE)))
    assert saved["service_id"] == "svc-123" and "DATABASE_URL" not in saved
    # Attempt 2: reuse the persisted service — NO second add (no orphan), just re-read variables.
    run2 = _runner([_VARS])
    info = deploy_db.provision("p", str(tmp_path), run=run2)
    assert info["DATABASE_URL"] == "postgresql://u:p@h:5432/railway"
    assert run2.calls[0][:2] == ["railway", "variables"]      # reused; no "railway add"


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
    # real env; the volume cascades so there is NO separate volume command.
    assert run.calls == [["railway", "service", "delete", "-s", "svc-123",
                          "-p", "8ecbd1b2", "-e", "software-factory-as-skill", "-y"]]


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
    run = _delete_runner([])                                         # must call NOTHING
    recs = [_rec(project_id="p1", service_id="s1", archived=True),
            _rec(project_id="p2", service_id="s2", phase="done", has_verified_deploy=True)]
    report = deploy_db.reap(recs, run=run, log=lambda m: None)
    assert run.calls == []                                           # DRY-RUN: deletes nothing
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
    run = _delete_runner([("deleted", 0), ("deleted", 0)])           # exactly two deletes
    report = deploy_db.reap(recs, run=run, log=lambda m: None)
    deleted_ids = sorted(c[c.index("-s") + 1] for c in run.calls)
    assert deleted_ids == ["s1", "s2"]                              # demo s3 untouched; empty s4 skipped
    assert {r["service_id"] for r in report["reaped"]} == {"s1", "s2"}
    assert {k["service_id"] for k in report["kept"]} == {"s3"}


def test_reap_dry_run_override_forces_preview_even_when_armed(monkeypatch):
    monkeypatch.setenv("SF_DEPLOY_DB_TEARDOWN", "ephemeral")          # armed
    run = _delete_runner([])
    report = deploy_db.reap([_rec(service_id="s1", archived=True)], run=run,
                            log=lambda m: None, dry_run=True)
    assert run.calls == []                                           # forced preview deletes nothing
    assert {w["service_id"] for w in report["would_reap"]} == {"s1"}
