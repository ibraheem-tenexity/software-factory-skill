"""Durable drafts: an interview that persists BEFORE a run exists, then promotes into a real
Stage-1 launch carrying the accumulated brief. Plus the kanban tickets projection."""
from software_factory.console import Console, RunRequest


class FakeLauncher:
    def __init__(self):
        self.argv = None

    def __call__(self, argv, env=None, log_path=None, cwd=None):
        self.argv = argv
        return {"pid": 1234}


def _console(tmp_path, launcher):
    ids = iter([f"run-{i:08x}" for i in range(1, 50)])
    return Console(str(tmp_path), launch=launcher,
                   new_id=lambda: next(ids), extract=lambda p: "# x")


def test_create_draft_mints_canonical_id_and_is_not_a_pipeline_run(tmp_path):
    c = _console(tmp_path, FakeLauncher())
    rid = c.create_draft(owner="op@tenexity.ai", name="Cargo", runtime="claude")
    assert rid.startswith("run-") and len(rid) == 12       # run-<8hex>, registry-safe
    assert c.is_draft(rid) is True
    # NO artifact recorded → the poller / ghost-resume guard ignore the draft
    assert c.is_pipeline_run(rid) is False
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
    assert c.is_pipeline_run(rid) is True              # now provisioned (artifacts recorded)
    # the brief reached the Stage-1 prompt the orchestrator was launched with
    prompt = " ".join(str(a) for a in launcher.argv)
    assert "PROJECT BRIEF" in prompt
    assert "ground handlers" in prompt
    # and the brief.md / interview.md artifacts were written to input/
    base = c._paths(rid)["base"]
    import os
    assert os.path.isfile(os.path.join(base, "input", "brief.md"))
    assert os.path.isfile(os.path.join(base, "input", "interview.md"))


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
    assert by_title["Login screen"]["status"] == "claimed"
    assert by_title["Login screen"]["agent"] == "impl-1"
