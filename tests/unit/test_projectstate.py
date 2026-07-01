"""Run state must survive a crash or a /loop re-entry: load -> work -> save -> resume.

The backend is pluggable (local JSON here; the per-project project.db in a real run) so the same
resume contract is unit-testable without any live dependency.
"""
from software_factory.projectstate import ProjectState, JsonFileStore


def store(tmp_path):
    return JsonFileStore(str(tmp_path))


def test_fresh_run_starts_at_provision_with_zero_spend(tmp_path):
    s = ProjectState.load("project-1", store(tmp_path))
    assert s.phase == "provision"
    assert s.spent_usd == 0.0
    assert s.repo_url is None
    assert s.deploy_url is None


def test_loading_an_unknown_run_is_fresh_not_an_error(tmp_path):
    s = ProjectState.load("never-seen", store(tmp_path))
    assert s.project_id == "never-seen"
    assert s.phase == "provision"


def test_save_then_load_resumes_exactly_where_it_left_off(tmp_path):
    st = store(tmp_path)
    s = ProjectState.load("project-2", st)
    s.phase = "build"
    s.spent_usd = 42.5
    s.repo_url = "https://github.com/acme/guestbook"
    s.save()

    # Simulate a crash + /loop re-entry: brand-new object, same backend.
    resumed = ProjectState.load("project-2", store(tmp_path))
    assert resumed.phase == "build"
    assert resumed.spent_usd == 42.5
    assert resumed.repo_url == "https://github.com/acme/guestbook"


def test_deploy_db_attempts_persist_so_the_retry_cap_actually_parks(tmp_path):
    # The provision retry cap lives across /loop re-entries: each tick re-loads state, so the attempt
    # counter MUST survive a reload or the cap never trips and the poller loops forever (it was a
    # dataclass field but missing from _PERSISTED — this guards that regression).
    s = ProjectState.load("project-cap", store(tmp_path))
    s.deploy_db_attempts = 2
    s.save()
    assert ProjectState.load("project-cap", store(tmp_path)).deploy_db_attempts == 2


def test_deploy_db_service_id_persists_for_durable_teardown(tmp_path):
    # The captured Railway serviceId is the durable teardown handle: it must survive a reload so the
    # reaper can delete the run's Postgres even after the context dir (which also holds it) is gone.
    s = ProjectState.load("project-td", store(tmp_path))
    assert s.deploy_db_service_id == ""            # default for runs that never provisioned a DB
    s.deploy_db_service_id = "svc-RNK8"
    s.save()
    assert ProjectState.load("project-td", store(tmp_path)).deploy_db_service_id == "svc-RNK8"


def test_proof_marker_is_stamped_and_persists(tmp_path):
    # At provision the orchestrator stamps WHICH skill drove the run — the run's receipt.
    st = store(tmp_path)
    s = ProjectState.load("project-proof", st)
    assert s.skill is None  # not yet stamped
    s.skill = "software-factory"
    s.skill_version = "0.0.1"
    s.description = "guestbook web app"
    s.deploy_target = "railway"
    s.save()

    resumed = ProjectState.load("project-proof", store(tmp_path))
    assert resumed.skill == "software-factory"
    assert resumed.skill_version == "0.0.1"
    assert resumed.description == "guestbook web app"
    assert resumed.deploy_target == "railway"


def test_runs_are_isolated_by_id(tmp_path):
    st = store(tmp_path)
    a = ProjectState.load("a", st)
    a.phase = "deploy"
    a.save()
    b = ProjectState.load("b", store(tmp_path))
    assert b.phase == "provision"  # 'a' did not leak into 'b'


def test_per_run_model_picks_persist_across_reload(tmp_path):
    # Operator-picked models (planning = S1/S2 orchestrators, impl = S3) are pinned at
    # start_project and must survive crashes/retries like every other run-scoped decision.
    st = store(tmp_path)
    s = ProjectState.load("project-m", st)
    s.planning_model = "claude-fable-5"
    s.impl_model = "claude-opus-4-8"
    s.save()
    resumed = ProjectState.load("project-m", store(tmp_path))
    assert resumed.planning_model == "claude-fable-5"
    assert resumed.impl_model == "claude-opus-4-8"


def test_project_name_persists_across_reload(tmp_path):
    st = store(tmp_path)
    s = ProjectState.load("project-n", st)
    s.name = "Acme CRM"
    s.save()
    assert ProjectState.load("project-n", store(tmp_path)).name == "Acme CRM"


def test_owner_github_username_persists(tmp_path):
    # SOF-3: the owner's GitHub handle must survive a reload so a relaunch/release can thread it
    # back into the Stage-1 prompt (it was a dataclass field but missing from _PERSISTED, exactly
    # the deploy_db_attempts regression the sibling test above guards).
    s = ProjectState.load("project-gh", store(tmp_path))
    assert s.owner_github_username == ""           # default for runs with no username on file
    s.owner_github_username = "demo-owner"
    s.save()
    assert ProjectState.load("project-gh", store(tmp_path)).owner_github_username == "demo-owner"


def test_creds_vault_ids_persist_for_byok_vault_storage(tmp_path):
    # Vault UUIDs (the only persistent form of a BYOK key — never the plaintext) must survive
    # a reload so _launch_stage can retrieve them on Stages 2 + 3 and retries.
    st = store(tmp_path)
    s = ProjectState.load("project-vault", st)
    assert s.creds_vault_ids == {}  # default: no vault entries
    s.creds_vault_ids = {"RAILWAY_TOKEN": "vault-uuid-abc123"}
    s.save()
    resumed = ProjectState.load("project-vault", store(tmp_path))
    assert resumed.creds_vault_ids == {"RAILWAY_TOKEN": "vault-uuid-abc123"}
