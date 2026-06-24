"""Durable drafts: an interview that persists BEFORE a run exists, then promotes into a real
Stage-1 launch carrying the accumulated brief. Plus the kanban tickets projection."""
from software_factory.console import Console, ProjectRequest


class FakeLauncher:
    def __init__(self):
        self.argv = None

    def __call__(self, argv, env=None, log_path=None, cwd=None):
        self.argv = argv
        return {"pid": 1234}


def _console(tmp_path, launcher):
    ids = iter([f"project-{i:08x}" for i in range(1, 50)])
    return Console(str(tmp_path), launch=launcher,
                   new_id=lambda: next(ids), extract=lambda p: "# x")


def test_create_draft_mints_canonical_id_and_is_not_a_pipeline_run(tmp_path):
    c = _console(tmp_path, FakeLauncher())
    rid = c.create_draft(owner="op@tenexity.ai", name="Cargo", runtime="claude")
    assert rid.startswith("project-") and len(rid) == 16       # project-<8hex>, registry-safe
    assert c.is_draft(rid) is True
    # NO artifact recorded → the poller / ghost-resume guard ignore the draft
    assert c.is_pipeline_project(rid) is False
    st = c.status(rid)
    assert st["phase"] == "draft"


def test_update_draft_brief_merges_and_reports_coverage(tmp_path):
    c = _console(tmp_path, FakeLauncher())
    rid = c.create_draft(owner="op@tenexity.ai")
    c.update_draft_brief(rid, {"goals": "A cargo screening prototype for ground handlers."})
    cov = c.update_draft_brief(rid, {"success_metrics": "Indistinguishable from the hand-built demo."})
    assert cov["goals"] is True and cov["success_metrics"] is True
    # merge, not replace
    st_brief = c._load_state(rid).brief
    assert "goals" in st_brief and "success_metrics" in st_brief


def test_promote_draft_launches_stage1_with_brief_threaded(tmp_path):
    launcher = FakeLauncher()
    c = _console(tmp_path, launcher)
    rid = c.create_draft(owner="op@tenexity.ai", name="Cargo", runtime="claude")
    c.update_draft_brief(rid, {
        "goals": "A cargo screening prototype for ground handlers to log screening events.",
        "success_metrics": "A stakeholder cannot distinguish it from the hand-built demo.",
        "definition_of_done": "All V1 screens deployed and browser-verified.",
    })
    out = c.promote_draft(rid, interview_md="USER: build cargo screening\nAI: on it")
    assert out == rid                                  # same id, no re-mint
    assert c.is_draft(rid) is False
    assert c.is_pipeline_project(rid) is True              # now provisioned (artifacts recorded)
    # the brief reached the Stage-1 prompt the orchestrator was launched with
    prompt = " ".join(str(a) for a in launcher.argv)
    assert "PROJECT BRIEF" in prompt
    assert "ground handlers" in prompt
    # and the brief.md / interview.md artifacts were written to input/
    base = c._paths(rid)["base"]
    import os
    assert os.path.isfile(os.path.join(base, "input", "brief.md"))
    assert os.path.isfile(os.path.join(base, "input", "interview.md"))


def test_set_draft_project_writes_name_goal_and_composes_description(tmp_path):
    c = _console(tmp_path, FakeLauncher())
    rid = c.create_draft(owner="op@tenexity.ai")
    out = c.set_draft_project(rid, name="Quote-to-Epicor",
                              goal="Replace the manual quoting spreadsheet.",
                              scope=["Quoting / RFQ", "Pricing & approvals"])
    assert out["name"] == "Quote-to-Epicor"
    assert out["brief"]["goals"] == "Replace the manual quoting spreadsheet."   # goal → brief.goals
    assert out["scope"] == ["Quoting / RFQ", "Pricing & approvals"]
    # canonical description = goal + scope-of-work line (composed server-side)
    assert out["description"] == ("Replace the manual quoting spreadsheet.\n\n"
                                  "Scope of work: Quoting / RFQ, Pricing & approvals.")
    st = c._load_state(rid)
    assert st.scope == ["Quoting / RFQ", "Pricing & approvals"]
    assert st.description == out["description"]


def test_set_draft_project_updates_runtime_so_promote_uses_the_picked_engine(tmp_path):
    # The Build-engine card: an eager create mints the draft with the default runtime (claude), then
    # the user switches to OpenCode. set_draft_project(runtime=...) must persist the change so promote
    # launches opencode (not the stale create-time default) — otherwise the pick is silently dropped.
    launcher = FakeLauncher()
    c = _console(tmp_path, launcher)
    rid = c.create_draft(owner="op@tenexity.ai", runtime="claude")
    assert c._load_state(rid).runtime == "claude"
    c.set_draft_project(rid, runtime="opencode")
    assert c._load_state(rid).runtime == "opencode"
    c.promote_draft(rid)
    # promote threads state.runtime into the ProjectRequest the launcher sees
    assert "opencode" in launcher.argv or any("opencode" in str(a) for a in launcher.argv)


def test_set_draft_project_recomposes_idempotently_across_independent_calls(tmp_path):
    # set_project_basics (goal) then set_project_scope (scope) arrive as separate tool calls —
    # the second must recompose against the persisted goal, not wipe it.
    c = _console(tmp_path, FakeLauncher())
    rid = c.create_draft(owner="op@tenexity.ai")
    c.set_draft_project(rid, goal="Build quotes against our Epicor SKUs.")
    out = c.set_draft_project(rid, scope=["Quoting / RFQ"])
    assert out["description"] == "Build quotes against our Epicor SKUs.\n\nScope of work: Quoting / RFQ."
    # updating just the goal later keeps the existing scope in the recomposed description
    out2 = c.set_draft_project(rid, goal="Build quotes and route discounts for approval.")
    assert out2["description"] == ("Build quotes and route discounts for approval.\n\n"
                                   "Scope of work: Quoting / RFQ.")


def test_tickets_projection_empty_for_fresh_run(tmp_path):
    c = _console(tmp_path, FakeLauncher())
    rid = c.create_draft(owner="op@tenexity.ai")
    out = c.tickets(rid)
    assert out == {"tickets": [], "waves": []}


def test_tickets_projection_groups_by_status_and_wave(tmp_path):
    from software_factory.tickets import TicketStore
    c = _console(tmp_path, FakeLauncher())
    rid = c.create_draft(owner="op@tenexity.ai")
    store = TicketStore(c._paths(rid)["tickets_db"])
    t1 = store.create_ticket("Login screen", "user can log in", "tested+deployed", 1)
    store.create_ticket("Dashboard", "shows events", "tested+deployed", 2)
    store.claim(t1, "impl-1")
    out = c.tickets(rid)
    assert {t["title"] for t in out["tickets"]} == {"Login screen", "Dashboard"}
    assert out["waves"] == [1, 2]
    by_title = {t["title"]: t for t in out["tickets"]}
    assert by_title["Login screen"]["status"] == "in_progress"
    assert by_title["Login screen"]["agent"] == "impl-1"


def test_tickets_carry_app_for_multi_deliverable_runs(tmp_path):
    from software_factory.tickets import TicketStore
    c = _console(tmp_path, FakeLauncher())
    rid = c.create_draft(owner="op@tenexity.ai")
    store = TicketStore(c._paths(rid)["tickets_db"])
    store.create_ticket("AWB capture", "handler captures AWB", "deployed", 1, app="mobile-web")
    store.create_ticket("Ops dashboard", "ops sees events", "deployed", 1, app="web")
    by_title = {t["title"]: t for t in c.tickets(rid)["tickets"]}
    assert by_title["AWB capture"]["app"] == "mobile-web"
    assert by_title["Ops dashboard"]["app"] == "web"


def test_deployments_are_per_deliverable(tmp_path):
    from software_factory.db import ProjectStore
    c = _console(tmp_path, FakeLauncher())
    rid = c.create_draft(owner="op@tenexity.ai")
    db = ProjectStore(c._paths(rid)["db"])
    db.record_deployment("mobile-web", "https://sf-x-mobile.up.railway.app", verified=True)
    db.record_deployment("web", "https://sf-x-web.up.railway.app", status="live")
    out = c.deployments(rid)
    assert out["apps"] == ["mobile-web", "web"]
    assert {d["url"] for d in out["deployments"]} == {
        "https://sf-x-mobile.up.railway.app", "https://sf-x-web.up.railway.app"}


# ── BYOK draft-creds path ─────────────────────────────────────────────────────────────────────

def _console_with_vault(tmp_path, vault_store_fn):
    """Console wired with a fake vault_store so tests don't need Supabase."""
    import software_factory.vault as _v
    from unittest.mock import patch
    launcher = FakeLauncher()
    c = Console(str(tmp_path), launch=launcher,
                new_id=lambda: "project-00000001", extract=lambda p: "# x")
    return c, launcher, patch.object(_v, "vault_store", side_effect=vault_store_fn)


def test_store_draft_creds_records_vault_uuids_in_state(tmp_path):
    import software_factory.vault as _v
    from unittest.mock import patch

    stored = {}

    def fake_vault_store(name, value):
        uid = f"uuid-{name}"
        stored[name] = value
        return uid

    launcher = FakeLauncher()
    c = Console(str(tmp_path), launch=launcher,
                new_id=lambda: "project-00000001", extract=lambda p: "# x")
    rid = c.create_draft(owner="op@tenexity.ai")

    with patch.object(_v, "vault_store", side_effect=fake_vault_store):
        result = c.store_draft_creds(rid, {"ANTHROPIC_API_KEY": "sk-test"})

    assert result["creds_provided"] == ["ANTHROPIC_API_KEY"]
    state = c._load_state(rid)
    assert "ANTHROPIC_API_KEY" in state.creds_vault_ids
    assert state.creds_vault_ids["ANTHROPIC_API_KEY"].startswith("uuid-")
    assert state.creds_provided == ["ANTHROPIC_API_KEY"]


def test_store_draft_creds_skips_empty_values(tmp_path):
    import software_factory.vault as _v
    from unittest.mock import patch

    call_count = {"n": 0}

    def fake_vault_store(name, value):
        call_count["n"] += 1
        return f"uuid-{name}"

    launcher = FakeLauncher()
    c = Console(str(tmp_path), launch=launcher,
                new_id=lambda: "project-00000001", extract=lambda p: "# x")
    rid = c.create_draft(owner="op@tenexity.ai")

    with patch.object(_v, "vault_store", side_effect=fake_vault_store):
        result = c.store_draft_creds(rid, {"ANTHROPIC_API_KEY": "sk-test", "EMPTY_KEY": ""})

    assert call_count["n"] == 1          # only the non-empty key was vaulted
    assert result["creds_provided"] == ["ANTHROPIC_API_KEY"]


def test_store_draft_creds_merges_with_existing_entries(tmp_path):
    import software_factory.vault as _v
    from unittest.mock import patch

    launcher = FakeLauncher()
    c = Console(str(tmp_path), launch=launcher,
                new_id=lambda: "project-00000001", extract=lambda p: "# x")
    rid = c.create_draft(owner="op@tenexity.ai")

    def make_vault(prefix):
        def fake_vault_store(name, value):
            return f"{prefix}-{name}"
        return fake_vault_store

    with patch.object(_v, "vault_store", side_effect=make_vault("v1")):
        c.store_draft_creds(rid, {"ANTHROPIC_API_KEY": "sk-a"})
    with patch.object(_v, "vault_store", side_effect=make_vault("v2")):
        result = c.store_draft_creds(rid, {"OPENROUTER_API_KEY": "or-b"})

    assert set(result["creds_provided"]) == {"ANTHROPIC_API_KEY", "OPENROUTER_API_KEY"}
    state = c._load_state(rid)
    # both entries present; second call didn't wipe the first
    assert "ANTHROPIC_API_KEY" in state.creds_vault_ids
    assert "OPENROUTER_API_KEY" in state.creds_vault_ids


def test_promote_draft_threads_draft_vault_ids_into_provision(tmp_path):
    """promote_draft must carry draft-stored vault_ids into _provision_and_launch so Stage 2/3
    can retrieve the BYOK key — the promote path must NOT overwrite them with an empty dict."""
    import software_factory.vault as _v
    from unittest.mock import patch

    launcher = FakeLauncher()
    c = Console(str(tmp_path), launch=launcher,
                new_id=lambda: "project-00000001", extract=lambda p: "# x")
    rid = c.create_draft(owner="op@tenexity.ai")

    # Store a BYOK key via the draft-creds endpoint
    with patch.object(_v, "vault_store", return_value="vault-uuid-111"):
        c.store_draft_creds(rid, {"ANTHROPIC_API_KEY": "sk-secret"})

    # promote_draft must not call vault_store again (no re-encryption) but must keep the entry
    with patch.object(_v, "vault_store", return_value=None) as mock_vault:
        c.promote_draft(rid)

    state = c._load_state(rid)
    assert state.creds_vault_ids.get("ANTHROPIC_API_KEY") == "vault-uuid-111"
    assert "ANTHROPIC_API_KEY" in state.creds_provided


# ── budget-cap draft path ─────────────────────────────────────────────────────────────────────

def test_create_draft_with_budget_sets_budget_ceiling(tmp_path):
    c = _console(tmp_path, FakeLauncher())
    rid = c.create_draft(owner="op@tenexity.ai", budget=75.0)
    state = c._load_state(rid)
    assert state.budget_ceiling == 75.0


def test_promote_draft_carries_budget_ceiling(tmp_path):
    launcher = FakeLauncher()
    c = _console(tmp_path, launcher)
    rid = c.create_draft(owner="op@tenexity.ai", name="Cargo", runtime="claude", budget=99.0)
    c.update_draft_brief(rid, {
        "goals": "A prototype.",
        "success_metrics": "Indistinguishable from the hand-built demo.",
        "definition_of_done": "Deployed.",
        "constraints": "Web only.",
    })
    c.set_draft_project(rid, name="Cargo", goal="A prototype.", scope=["web"])
    c.promote_draft(rid)
    # budget_ceiling must survive the promote; _provision_and_launch must not zero it
    state = c._load_state(rid)
    assert state.budget_ceiling == 99.0


def test_patch_draft_budget_updates_ceiling_and_supports_lowering(tmp_path):
    c = _console(tmp_path, FakeLauncher())
    rid = c.create_draft(owner="op@tenexity.ai", budget=100.0)
    # raise
    c.raise_budget(rid, 200.0)
    assert c._load_state(rid).budget_ceiling == 200.0
    # lower (must also work)
    c.raise_budget(rid, 50.0)
    assert c._load_state(rid).budget_ceiling == 50.0


def test_status_exposes_budget_ceiling(tmp_path):
    c = _console(tmp_path, FakeLauncher())
    rid = c.create_draft(owner="op@tenexity.ai", budget=42.0)
    st = c.status(rid)
    assert st["budget_ceiling"] == 42.0


def test_store_draft_creds_survives_vault_unavailable(tmp_path):
    """If Vault is down, store_draft_creds still records the key name so the user sees it
    registered; the UUID is absent (gracefully degraded)."""
    import software_factory.vault as _v
    from unittest.mock import patch

    launcher = FakeLauncher()
    c = Console(str(tmp_path), launch=launcher,
                new_id=lambda: "project-00000001", extract=lambda p: "# x")
    rid = c.create_draft(owner="op@tenexity.ai")

    def failing_vault(name, value):
        raise RuntimeError("Vault unreachable")

    with patch.object(_v, "vault_store", side_effect=failing_vault):
        result = c.store_draft_creds(rid, {"ANTHROPIC_API_KEY": "sk-test"})

    assert "ANTHROPIC_API_KEY" in result["creds_provided"]
    state = c._load_state(rid)
    # name present; UUID absent (Vault failed)
    assert "ANTHROPIC_API_KEY" in state.creds_provided
