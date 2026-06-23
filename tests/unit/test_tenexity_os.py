"""Tenexity OS §3 assemblers + cross-run SQL aggregates."""
from software_factory import tenexity_os as tos
from software_factory.agents import AgentRegistry
from software_factory.console import Console, ProjectRequest
from software_factory.tickets import TicketStore


class FakeLauncher:
    def __call__(self, argv, env=None, log_path=None, cwd=None):
        return {"pid": 1}


# ── stage skills (§3.4 Part 1) ─────────────────────────────────────────────────────────────────
def test_stage_skill_cards_are_three_file_backed_orchestrators():
    cards = tos.stage_skill_cards()
    assert [c["callsign"] for c in cards] == ["STAGE-1", "STAGE-2", "STAGE-3"]
    assert all(c["kind"] == "stage_skill" and c["role"] == "stage-orchestrator" for c in cards)
    assert [c["model"] for c in cards] == ["claude-opus-4-8", "claude-opus-4-8", "claude-sonnet-4-6"]
    assert cards[0]["desc"] and "research" in cards[0]["desc"].lower()   # from SKILL.md frontmatter


def test_stage_skill_detail_reads_real_file_and_variants():
    d = tos.stage_skill_detail("stage-2", )                # case-insensitive callsign match
    assert d["callsign"] == "STAGE-2" and d["prompt_source"] == "skill_file"
    assert d["prompt_applied"] is True and d["editable"] is True    # editable in Part 2
    assert d["prompt"].startswith("---") and "design orchestrator" in d["prompt"].lower()
    assert d["variants"]["opencode"] == "skills/stage-2-design/SKILL.opencode.md"
    assert tos.stage_skill_detail("ATLAS") is None         # role agent → not a stage skill


def test_stage_skill_missing_file_degrades_gracefully(monkeypatch):
    monkeypatch.setattr(tos, "_SKILLS_DIR", "/nonexistent/skills")
    d = tos.stage_skill_detail("STAGE-1")
    assert d is not None and "not found" in d["prompt"].lower()   # clear placeholder, no raise
    assert d["desc"] is None


def test_concierge_card_is_code_backed(monkeypatch):
    monkeypatch.delenv("SF_CHAT_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")              # OpenAI path → gpt-5.4 label
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    card = tos.concierge_card()
    assert card["callsign"] == "CONCIERGE" and card["kind"] == "concierge" and card["model"] == "gpt-5.4"
    d = tos.concierge_detail("concierge")                    # case-insensitive
    assert d["prompt_source"] == "code" and d["prompt_applied"] is True
    assert "Factory Concierge" in d["prompt"]                # the REAL CONCIERGE_INSTRUCTIONS constant
    assert tos.stage_skill_detail("CONCIERGE") is None       # concierge is NOT a stage skill
    assert tos.live_agent_detail("STAGE-2") and tos.live_agent_detail("CONCIERGE")   # both via combiner
    assert {c["callsign"] for c in tos.live_agent_cards()} == {"STAGE-1", "STAGE-2", "STAGE-3", "CONCIERGE"}


# ── pure assemblers ──────────────────────────────────────────────────────────────────────────
_REG = [
    {"callsign": "ATLAS", "name": "Orchestrator", "role": "orchestrator",
     "model": "claude-opus-4-8", "cost_tier": 3, "descr": "x"},
    {"callsign": "SIREN", "name": "Marketing", "role": "siren",
     "model": "claude-sonnet-4-6", "cost_tier": 1, "descr": "y"},
]


def test_agent_roster_merges_live_rollup_and_appends_unmapped():
    rollups = [
        {"role": "orchestrator", "runs": 3, "total": 10, "active": 2, "successes": 8,
         "model": "claude-opus-4-8"},
        {"role": "mystery", "runs": 1, "total": 2, "active": 0, "successes": 1, "model": "x"},
    ]
    roster = tos.agent_roster(_REG, rollups, {"ATLAS": {"version": 4}})
    atlas = next(a for a in roster if a["callsign"] == "ATLAS")
    assert atlas["runs"] == 3 and atlas["on"] is True
    assert atlas["success"] == 80 and atlas["prompt_version"] == 4
    mystery = next(a for a in roster if a["callsign"] == "MYSTERY")   # live role not in roster
    assert mystery["runs"] == 1 and mystery["success"] == 50
    siren = next(a for a in roster if a["callsign"] == "SIREN")        # roster entry, no live data
    assert siren["runs"] == 0 and siren["on"] is False
    assert siren["success"] is None and siren["prompt_version"] == 0


def test_client_rows_rolls_up_org_runs_only():
    orgs = [{"id": "org-1", "name": "Acme Industrial"}]
    members = {"org-1": [{"email": "a@acme.com"}, {"email": "b@acme.com"}]}
    runs = [
        {"project_id": "r1", "owner": "a@acme.com", "spent_usd": 4.0, "updated": 100},
        {"project_id": "r2", "owner": "b@acme.com", "spent_usd": 2.0, "updated": 200},
        {"project_id": "r3", "owner": "stranger@x.com", "spent_usd": 99.0, "updated": 300},
    ]
    rows = tos.client_rows(orgs, runs, members, {"r1": 2, "r2": 1, "r3": 5})
    assert len(rows) == 1
    c = rows[0]
    assert c["name"] == "Acme Industrial" and c["initials"] == "AI"
    assert c["projects"] == 2 and c["tickets"] == 3       # stranger's run excluded
    assert c["spend"] == 6.0 and c["last_activity"] == 200


def test_project_rows_mode_filter_and_fields():
    runs = [
        {"project_id": "r1", "name": "Real", "owner": "a@x.com", "spent_usd": 1.0, "updated": 1,
         "stage": 3, "phase": "build", "runtime": "claude", "is_demo": False},
        {"project_id": "r2", "name": "Demo", "owner": "a@x.com", "spent_usd": 0.0, "updated": 2,
         "stage": 1, "phase": "draft", "runtime": "opencode", "is_demo": True},
    ]
    o2o = {"a@x.com": "Acme"}
    tc = {"r1": {"done": 3, "total": 6}}
    assert {p["name"] for p in tos.project_rows(runs, o2o, tc, "all")} == {"Real", "Demo"}
    real = tos.project_rows(runs, o2o, tc, "real")
    assert [p["name"] for p in real] == ["Real"]
    assert real[0]["client"] == "Acme" and real[0]["factory"] == "claude"
    assert real[0]["tasks_done"] == 3 and real[0]["tasks_total"] == 6
    assert [p["name"] for p in tos.project_rows(runs, o2o, tc, "demo")] == ["Demo"]


def test_overview_pulse_counts_and_null_friction():
    orgs = [{"id": "org-1", "name": "Acme"}]
    runs = [{"project_id": "r1", "name": "P", "owner": "a@x.com", "spent_usd": 4.0, "updated": 10,
             "phase": "build"}]
    rollups = [{"role": "orchestrator", "total": 10, "active": 2, "successes": 9, "runs": 3}]
    roster = tos.agent_roster(_REG, rollups, {})
    ov = tos.overview(orgs, runs, rollups, 2, 1.234, roster, {"a@x.com": "Acme"})
    assert ov["pulse"]["tenants"] == 1 and ov["pulse"]["projects"] == 1
    assert ov["pulse"]["projects_active"] == 1           # the single "build" run is in-flight
    assert ov["pulse"]["agents_active"] == 2 and ov["pulse"]["agents_total"] == 10
    assert ov["pulse"]["today_burn"] == 1.23 and ov["pulse"]["avg_friction"] is None
    assert ov["active_projects"][0]["client"] == "Acme"
    assert len(ov["agents"]) <= 6


def test_pulse_projects_active_excludes_finished_frozen_and_gated():
    # projects_active (definition A) = genuinely executing: phase ∉ {done,stopped} AND not
    # budget_stopped AND not held. Finished, budget-frozen, and gated-pre-launch runs are NOT running.
    runs = [
        {"project_id": "a", "phase": "build"},                          # active
        {"project_id": "b", "phase": "research"},                       # active
        {"project_id": "c", "phase": "done"},                           # finished → excluded
        {"project_id": "d", "phase": "stopped"},                        # canceled → excluded
        {"project_id": "e", "phase": "build", "budget_stopped": True},  # frozen → excluded
        {"project_id": "f", "phase": "research", "held": True},         # gated-pre-launch → excluded
    ]
    ov = tos.overview([], runs, [], 0, 0.0, [], {})
    assert ov["pulse"]["projects"] == 6          # total = every run
    assert ov["pulse"]["projects_active"] == 2   # only a + b are genuinely running


# ── cross-run SQL (seeded Postgres) ──────────────────────────────────────────────────────────
def _seed(tmp_path, rid):
    c = Console(str(tmp_path), launch=FakeLauncher(), new_id=lambda: rid)
    c.start_project(ProjectRequest(description="app", target="railway"))
    return c


def test_stage_override_drives_the_run_workspace(tmp_path):
    # END-TO-END proof Part 2 works: a stored STAGE-1 (claude) override becomes the run's ws/SKILL.md
    # at launch — i.e. a web edit DRIVES the actual run. start_project → _launch_stage(1) → prepare_workspace.
    import os
    from software_factory.agent_prompts import PromptStore, override_key
    PromptStore().set(override_key("STAGE-1", "claude"), "# OVERRIDE DRIVES THE RUN")
    rid = "project-ovrd1111"
    _seed(tmp_path, rid)
    skill = os.path.join(str(tmp_path), rid, "workspace", "SKILL.md")
    assert open(skill).read() == "# OVERRIDE DRIVES THE RUN"


def test_agent_rollups_active_and_burn(tmp_path):
    rid = "project-aaaa1111"
    c = _seed(tmp_path, rid)
    reg = AgentRegistry(c._paths(rid)["agents_db"])
    reg.spawn("a1", rid, 1, "orchestrator", "claude-opus-4-8", "build")    # stays running
    reg.spawn("a2", rid, 2, "orchestrator", "claude-opus-4-8", "build")
    reg.record("a2", "real_diff", cost_usd=2.5)                            # success + cost
    orch = {r["role"]: r for r in tos.agent_rollups()}["orchestrator"]
    assert orch["total"] == 2 and orch["active"] >= 1 and orch["successes"] >= 1
    assert tos.agents_active_count() >= 1
    assert tos.today_burn(0) >= 2.5


def test_ticket_counts_by_run(tmp_path):
    rid = "project-bbbb2222"
    c = _seed(tmp_path, rid)
    ts = TicketStore(c._paths(rid)["tickets_db"])
    t1 = ts.create_ticket("A", "acc", "dod", 1)
    ts.create_ticket("B", "acc", "dod", 1)
    ts.mark_done(t1, "abcdef1", 10)
    counts = tos.ticket_counts_by_project()
    assert counts[rid]["total"] == 2 and counts[rid]["done"] == 1
    assert tos.open_tickets_by_project().get(rid) == 1          # B still open


def test_console_archive_hides_from_list(tmp_path):
    rid = "project-cccc3333"
    c = _seed(tmp_path, rid)
    assert any(r["project_id"] == rid for r in c.list_projects(owner=None))
    c.set_archived(rid, True)
    assert not any(r["project_id"] == rid for r in c.list_projects(owner=None))   # soft-deleted → hidden


def test_console_rename(tmp_path):
    rid = "project-dddd4444"
    c = _seed(tmp_path, rid)
    out = c.rename_project(rid, name="New Name", description="desc")
    assert out["name"] == "New Name"
    assert c.status(rid)["name"] == "New Name"


def test_console_rename_scope_recomposes_description(tmp_path):
    rid = "project-eeee5555"
    c = _seed(tmp_path, rid)
    st = c._load_state(rid)
    st.brief = {"goals": "automate quoting"}
    st.save()
    out = c.rename_project(rid, scope=["Quoting / RFQ", "Pricing"])
    assert out["scope"] == ["Quoting / RFQ", "Pricing"]
    assert "automate quoting" in out["description"] and "Quoting / RFQ" in out["description"]
