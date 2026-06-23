"""The reaper CLI is a thin, SAFE invocation surface for Console.reap_deploy_dbs: it defaults to a
dry-run PREVIEW and only deletes when BOTH --apply is passed AND the policy env is armed."""
from software_factory import reap_deploy_dbs as cli


def test_cli_defaults_to_dry_run_preview(monkeypatch):
    captured = {}
    monkeypatch.setattr(cli, "_run_sweep", lambda dry_run: captured.update(dry_run=dry_run) or {"reaped": []})
    assert cli.main([]) == 0
    assert captured["dry_run"] is True            # no --apply → preview, never deletes


def test_cli_apply_flag_lets_the_armed_policy_delete(monkeypatch):
    captured = {}
    monkeypatch.setattr(cli, "_run_sweep", lambda dry_run: captured.update(dry_run=dry_run) or {"reaped": []})
    assert cli.main(["--apply"]) == 0
    assert captured["dry_run"] is False           # --apply → defer to SF_DEPLOY_DB_TEARDOWN (armed?)
