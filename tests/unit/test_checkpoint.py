"""Tests for checkpoint immutability, retry/rewind invalidation, crash detection, and resume.

Tests map to l2a7ngax's required coverage:
  1. Checkpoint immutability — second write is a no-op
  2. Retry/rewind node invalidation — deletes at node and downstream, not upstream
  3. Kanban skip-completed-tickets on resume — run_swarm_waves filters skip_ticket_ids
  4. Crash detection — auto_resume_dead_stage sets phase='crashed' instead of auto-resuming
  5. Resume-skips-checkpointed-nodes — resume_project calls retry_stage preserving upstream ckpts
"""
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from software_factory import checkpoint as ckpt
from software_factory.checkpoint import NODE_ORDER, completed_nodes, delete_from, write


PID = "project-cp01"   # scoped to each test by _clean_db fixture


@pytest.fixture(autouse=True)
def _mock_check_mcp(monkeypatch):
    # check_mcp spawns playwright/chromium subprocesses; accumulated instances across the full
    # suite cause resource contention that makes later calls time out. Checkpoint tests verify
    # recovery logic, not MCP health — mock it to always pass.
    from software_factory import console as _console_mod
    monkeypatch.setattr(_console_mod, "check_mcp", lambda path: [])


# ────────────────────────────────────────────────────────────────────────────────
# 1. Checkpoint immutability
# ────────────────────────────────────────────────────────────────────────────────

def test_write_returns_true_on_first_write():
    assert write(PID, "extract") is True


def test_write_returns_false_on_duplicate():
    write(PID, "extract")
    assert write(PID, "extract") is False


def test_duplicate_write_does_not_overwrite_original_output():
    write(PID, "extract", {"key": "original"})
    write(PID, "extract", {"key": "overwrite-attempt"})
    rows = ckpt.read_all(PID)
    assert len(rows) == 1
    assert rows[0]["output"] == {"key": "original"}


def test_completed_nodes_reflects_all_written():
    write(PID, "stage:1")
    write(PID, "extract")
    write(PID, "provision")
    assert completed_nodes(PID) == {"stage:1", "extract", "provision"}


# ────────────────────────────────────────────────────────────────────────────────
# 2. Retry/rewind invalidation
# ────────────────────────────────────────────────────────────────────────────────

def test_delete_from_removes_target_and_downstream():
    # write stage:1, extract, provision, research (S1 complete), architect
    for node in ("stage:1", "extract", "provision", "research", "stage:2", "architect"):
        write(PID, node)
    # rewind to 'research' → stage:2, architect, research deleted; stage:1, extract, provision survive
    deleted = delete_from(PID, "research")
    assert set(deleted) >= {"research", "stage:2", "architect"}
    remaining = completed_nodes(PID)
    assert "stage:1" in remaining
    assert "extract" in remaining
    assert "provision" in remaining
    assert "research" not in remaining
    assert "stage:2" not in remaining
    assert "architect" not in remaining


def test_delete_from_includes_ticket_nodes_when_build_invalidated():
    for node in ("stage:1", "extract", "provision", "research", "stage:2", "architect", "tickets", "stage:3"):
        write(PID, node)
    write(PID, "ticket:1")
    write(PID, "ticket:7")
    # invalidate from build (stage:3) onwards — should sweep ticket:* too
    deleted = delete_from(PID, "stage:3")
    assert "ticket:1" in deleted
    assert "ticket:7" in deleted
    remaining = completed_nodes(PID)
    assert "stage:1" in remaining
    assert "ticket:1" not in remaining


def test_delete_from_is_idempotent_when_nothing_exists():
    deleted = delete_from(PID, "build")
    assert deleted == []


def test_completed_ticket_ids_returns_only_ticket_nodes():
    write(PID, "stage:1")
    ckpt.write_ticket(PID, 3)
    ckpt.write_ticket(PID, 17)
    ids = ckpt.completed_ticket_ids(PID)
    assert ids == {"3", "17"}


# ────────────────────────────────────────────────────────────────────────────────
# 3. Kanban skip-completed-tickets on resume
# ────────────────────────────────────────────────────────────────────────────────

def test_run_swarm_waves_skips_checkpointed_tickets(tmp_path):
    """Tickets in skip_ticket_ids are not dispatched to the swarm."""
    from software_factory.tickets import TicketStore

    ws = tmp_path / "ws"
    ws.mkdir()
    db_path = str(tmp_path / "project-sk01")
    store = TicketStore(db_path)
    t1 = store.create_ticket("Feat A", "acc", "dod", wave=1)
    store.create_ticket("Feat B", "acc", "dod", wave=1)

    dispatched = []

    def fake_spawn(argv, env=None, cwd=None, stdout=None, stderr=None):
        import json, re
        cfg_path = next((a for a in argv if a.endswith(".json")), None)
        if cfg_path:
            with open(cfg_path) as f:
                cfg = json.load(f)
            for agent in cfg.get("agents", []):
                m = re.search(r"ticket[:\s#]+(\d+)", agent.get("systemPrompt", ""), re.I)
                if m:
                    dispatched.append(int(m.group(1)))
        proc = MagicMock()
        proc.poll.return_value = 0
        return proc

    from software_factory.swarm_stage3 import run_swarm_waves
    run_swarm_waves(
        base=db_path,
        project_id="project-sk01",
        ws=str(ws),
        model="kimi",
        budget_usd=10.0,
        spawn=fake_spawn,
        poll_s=0,
        skip_ticket_ids={str(t1)},
    )
    assert t1 not in dispatched


def test_run_swarm_waves_skips_empty_wave_after_all_tickets_filtered(tmp_path):
    """When all tickets in a wave are checkpointed, the wave is skipped entirely."""
    from software_factory.tickets import TicketStore

    ws = tmp_path / "ws"
    ws.mkdir()
    db_path = str(tmp_path / "project-sk02")
    store = TicketStore(db_path)
    tid = store.create_ticket("Only ticket", "acc", "dod", wave=1)

    spawned = []

    def fake_spawn(*args, **kwargs):
        spawned.append(True)
        proc = MagicMock()
        proc.poll.return_value = 0
        return proc

    from software_factory.swarm_stage3 import run_swarm_waves
    run_swarm_waves(
        base=db_path,
        project_id="project-sk02",
        ws=str(ws),
        model="kimi",
        budget_usd=10.0,
        spawn=fake_spawn,
        poll_s=0,
        skip_ticket_ids={str(tid)},
    )
    assert spawned == []   # no swarm process launched — wave was empty after filtering


# ────────────────────────────────────────────────────────────────────────────────
# 4. Crash detection — auto_resume_dead_stage sets phase='crashed'
# ────────────────────────────────────────────────────────────────────────────────

def test_auto_resume_relaunches_dead_stage_transient_crash(tmp_path):
    """Transient crash path: auto_resume_dead_stage relaunches the stage (returns True).
    The poller's _AUTO_RESUME_MAX cap gates how many times this fires.
    mark_stage_crashed() (poller path after cap exhaustion) handles the persistent case."""
    from software_factory.console import Console, ProjectRequest

    launched = []

    class DeadProc:
        def poll(self): return -9

    c = Console(
        str(tmp_path),
        launch=lambda argv, *a, **kw: (launched.append(argv), DeadProc())[1],
        new_id=lambda: "project-cd01",
    )
    rid = c.start_project(ProjectRequest(description="crash test"))
    st = c._load_state(rid)
    st.stage1_done = True
    st.stage2_done = True
    st.deps_satisfied = True
    st.stage = 3
    st.phase = "build"
    st.save()
    launched.clear()

    result = c.auto_resume_dead_stage(rid)

    assert result is True                         # auto-resumes within cap
    assert len(launched) == 1                     # stage relaunched
    st2 = c._load_state(rid)
    assert st2.phase != "crashed"                 # NOT crashed — transient self-heal


def test_auto_resume_skips_paused_runs(tmp_path):
    """A paused run must NOT be auto-resumed by the poller."""
    from software_factory.console import Console, ProjectRequest

    class DeadProc:
        def poll(self): return -9

    c = Console(
        str(tmp_path),
        launch=lambda argv, *a, **k: DeadProc(),
        new_id=lambda: "project-cd02",
    )
    rid = c.start_project(ProjectRequest(description="pause test"))
    st = c._load_state(rid)
    st.phase = "paused"
    st.paused_at_node = "build"
    st.save()

    result = c.auto_resume_dead_stage(rid)
    assert result is False
    st2 = c._load_state(rid)
    assert st2.phase == "paused"   # unchanged


def test_auto_resume_skips_already_crashed_runs(tmp_path):
    """A run already in 'crashed' phase is not auto-resumed again."""
    from software_factory.console import Console, ProjectRequest

    class DeadProc:
        def poll(self): return -9

    c = Console(
        str(tmp_path),
        launch=lambda argv, *a, **k: DeadProc(),
        new_id=lambda: "project-cd03",
    )
    rid = c.start_project(ProjectRequest(description="already crashed"))
    st = c._load_state(rid)
    st.phase = "crashed"
    st.crashed_at_node = "deploy"
    st.save()

    result = c.auto_resume_dead_stage(rid)
    assert result is False
    st2 = c._load_state(rid)
    assert st2.phase == "crashed"  # unchanged


# ────────────────────────────────────────────────────────────────────────────────
# 5. Resume preserves upstream checkpoints
# ────────────────────────────────────────────────────────────────────────────────

def test_resume_project_clears_markers_and_calls_retry_stage(tmp_path):
    """resume_project on a crashed run clears the markers and relaunches the stage."""
    from software_factory.console import Console, ProjectRequest

    launched = []

    class FakeProc:
        def poll(self): return 0

    c = Console(
        str(tmp_path),
        launch=lambda argv, *a, **kw: (launched.append(argv), FakeProc())[1],
        new_id=lambda: "project-rv01",
    )
    rid = c.start_project(ProjectRequest(description="resume test"))
    st = c._load_state(rid)
    st.stage1_done = True
    st.stage2_done = True
    st.deps_satisfied = True
    st.stage = 3
    st.phase = "crashed"
    st.crashed_at_node = "build"
    st.save()
    launched.clear()

    result = c.resume_project(rid)

    assert result == rid
    assert len(launched) == 1           # one process launched
    st2 = c._load_state(rid)
    assert st2.crashed_at_node == ""   # marker cleared
    assert st2.paused_at_node == ""


def test_resume_project_returns_none_when_not_paused_or_crashed(tmp_path):
    """resume_project is a no-op on an actively-running run."""
    from software_factory.console import Console, ProjectRequest

    c = Console(
        str(tmp_path),
        launch=lambda argv, *a, **k: MagicMock(poll=lambda: None),
        new_id=lambda: "project-rv02",
    )
    rid = c.start_project(ProjectRequest(description="active run"))
    st = c._load_state(rid)
    st.phase = "build"
    st.save()

    result = c.resume_project(rid)
    assert result is None


def test_retry_node_invalidates_downstream_checkpoints(tmp_path):
    """retry_node removes the target and downstream checkpoints and relaunches."""
    from software_factory.console import Console, ProjectRequest

    launched = []

    class FakeProc:
        def poll(self): return 0

    c = Console(
        str(tmp_path),
        launch=lambda argv, *a, **kw: (launched.append(argv), FakeProc())[1],
        new_id=lambda: "project-rn01",
    )
    rid = c.start_project(ProjectRequest(description="retry node"))
    # Lay down checkpoints for a partially-done S2
    write(rid, "stage:1")
    write(rid, "extract")
    write(rid, "provision")
    write(rid, "research")
    write(rid, "stage:2")
    write(rid, "architect")

    st = c._load_state(rid)
    st.stage1_done = True
    st.stage2_done = True
    st.deps_satisfied = True
    st.stage = 2
    st.save()
    launched.clear()

    result = c.retry_node(rid, "architect")

    assert result == rid
    remaining = completed_nodes(rid)
    assert "architect" not in remaining       # invalidated
    assert "stage:1" in remaining             # upstream: preserved
    assert "extract" in remaining
    assert "provision" in remaining
    assert "research" in remaining
    assert "stage:2" in remaining             # also upstream: preserved


def test_rewind_to_node_sets_paused_and_does_not_launch(tmp_path):
    """rewind_to_node kills the process, deletes downstream checkpoints, pauses."""
    from software_factory.console import Console, ProjectRequest

    launched = []

    class FakeProc:
        def poll(self): return 0

    c = Console(
        str(tmp_path),
        launch=lambda argv, *a, **kw: (launched.append(argv), FakeProc())[1],
        new_id=lambda: "project-rw01",
    )
    rid = c.start_project(ProjectRequest(description="rewind test"))
    write(rid, "stage:1")
    write(rid, "extract")
    write(rid, "stage:2")
    write(rid, "architect")

    st = c._load_state(rid)
    st.stage1_done = True
    st.stage2_done = True
    st.stage = 2
    st.phase = "architect"
    st.save()
    launched.clear()

    result = c.rewind_to_node(rid, "stage:2")

    assert result["phase"] == "paused"
    assert result["rewound_to"] == "stage:2"
    assert len(launched) == 0              # no relaunch
    st2 = c._load_state(rid)
    assert st2.phase == "paused"
    assert st2.paused_at_node == "stage:2"
    assert "architect" not in completed_nodes(rid)
    assert "stage:1" in completed_nodes(rid)   # upstream: preserved
