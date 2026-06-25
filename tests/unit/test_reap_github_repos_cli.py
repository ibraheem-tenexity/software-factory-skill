"""The GitHub repo reaper CLI defaults to dry-run; only deletes when BOTH --apply is passed
AND SF_GITHUB_REPO_REAPER=on is set."""
from software_factory import reap_github_repos as cli


def test_cli_defaults_to_dry_run_preview(monkeypatch):
    captured = {}
    monkeypatch.setattr(cli, "_run_sweep",
                        lambda org, dry_run: captured.update(org=org, dry_run=dry_run) or {"reaped": []})
    assert cli.main([]) == 0
    assert captured["dry_run"] is True            # no --apply → preview, never deletes

def test_cli_apply_flag_defers_to_arm_gate(monkeypatch):
    captured = {}
    monkeypatch.setattr(cli, "_run_sweep",
                        lambda org, dry_run: captured.update(org=org, dry_run=dry_run) or {"reaped": []})
    assert cli.main(["--apply"]) == 0
    assert captured["dry_run"] is False           # --apply → defer to SF_GITHUB_REPO_REAPER

def test_cli_uses_sf_github_org_env(monkeypatch):
    captured = {}
    monkeypatch.setenv("SF_GITHUB_ORG", "my-org")
    monkeypatch.setattr(cli, "_run_sweep",
                        lambda org, dry_run: captured.update(org=org, dry_run=dry_run) or {"reaped": []})
    cli.main([])
    assert captured["org"] == "my-org"

def test_cli_defaults_org_to_ibraheem_tenexity(monkeypatch):
    captured = {}
    monkeypatch.delenv("SF_GITHUB_ORG", raising=False)
    monkeypatch.setattr(cli, "_run_sweep",
                        lambda org, dry_run: captured.update(org=org, dry_run=dry_run) or {"reaped": []})
    cli.main([])
    assert captured["org"] == "ibraheem-tenexity"
