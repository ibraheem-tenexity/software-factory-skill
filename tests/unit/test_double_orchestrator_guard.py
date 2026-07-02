"""Tests for the §1 double-orchestrator guard in _launch_stage.

Bug: _launch_stage overwrites _procs[project_id] unconditionally. A duplicate call (two
concurrent HTTP requests, double promote_draft, rapid retry) spawned a second orchestrator
while the first was still alive; the second write to _procs[project_id] left the first
untracked — invisible to _stage_process_alive, never budget-gated, never reaped.
Two live stage-1 orchestrators raced the same project.log in the E2E pilot (~2x burn).

Fix: _launch_stage checks _stage_process_alive at entry and returns None immediately if alive.
This covers _provision_and_launch (no outer guard) and shrinks the TOCTOU window for
start_stage2/3 / retry_stage (which already check before calling).

These tests assert:
  (1) _launch_stage refuses a duplicate launch while first orchestrator is alive
  (2) _procs[project_id] retains the FIRST process (not overwritten by the refused second)
  (3) The second launch() call is never made (FakeLauncher call-count stays at 1)
  (4) Duplicate _provision_and_launch (draft promoted twice) is blocked
  (5) After the process exits, _launch_stage accepts a new launch (guard only blocks ALIVE)
"""
import pytest

from software_factory.console import Console, ProjectRequest


class CountingLauncher:
    """Records every launch call and returns a fake Popen-like object."""

    def __init__(self):
        self.calls = 0
        self._procs: list = []

    def __call__(self, argv, env=None, log_path=None, cwd=None):
        self.calls += 1
        proc = _FakeProc()
        self._procs.append(proc)
        return proc


class _FakeProc:
    """Minimal Popen-like stub. alive=True until .kill() called."""

    def __init__(self):
        self._rc = None  # None = still running

    def poll(self):
        return self._rc

    def terminate(self):
        self._rc = -15

    def kill(self):
        self._rc = -9

    def wait(self, timeout=None):
        pass


@pytest.fixture(autouse=True)
def _mock_check_mcp(monkeypatch):
    from software_factory import console as _cm
    monkeypatch.setattr(_cm, "check_mcp", lambda path: [])


def _make_console(tmp_path, ids):
    it = iter(ids)
    launcher = CountingLauncher()
    c = Console(str(tmp_path), launch=launcher, new_id=lambda: next(it))
    return c, launcher


# ── (1-3) _launch_stage refuses while first orchestrator is alive ────────────────────────

def test_duplicate_launch_refused_while_first_alive(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key-x")
    c, launcher = _make_console(tmp_path, ["project-dup01"])
    pid = c.start_project(ProjectRequest(description="app"))

    assert launcher.calls == 1
    # First process is still alive (poll() returns None)
    assert c._stage_process_alive(pid)

    # Second _launch_stage call for the same project — should be refused
    result = c._launch_stage(pid, 1, "prompt", {})

    assert result is None, "_launch_stage must return None when a stage process is alive"
    assert launcher.calls == 1, "second launch() must NOT be called"


def test_first_proc_not_overwritten_on_refused_second(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key-x")
    c, launcher = _make_console(tmp_path, ["project-dup02"])
    pid = c.start_project(ProjectRequest(description="app"))

    first_proc = c._procs.get(pid)
    assert first_proc is not None

    c._launch_stage(pid, 1, "prompt", {})

    assert c._procs.get(pid) is first_proc, "_procs[project_id] must not be overwritten"


# ── (4) _provision_and_launch path (promote_draft called twice) ───────────────────────────

def test_promote_draft_twice_blocked(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key-x")
    c, launcher = _make_console(tmp_path, ["project-draft01", "project-draft02"])
    draft_id = c.create_draft(owner="u@x.com")
    c.update_draft_brief(draft_id, {
        "goals": "a todo app for personal task tracking",
        "success_metrics": "a user can add, complete, and delete a task",
        "definition_of_done": "the todo screen is deployed and browser-verified",
    })

    # First promote: succeeds, stage-1 starts
    c.promote_draft(draft_id, description="todo app")
    assert launcher.calls == 1

    # Make the promoted project appear alive so the second promote hits the guard
    # (in practice: the project is now running, re-promote would be a double start)
    assert c._stage_process_alive(draft_id)

    # A second _launch_stage call (as would happen in a second promote_draft while
    # the first is still running) must be refused
    result = c._launch_stage(draft_id, 1, "prompt-2", {})
    assert result is None
    assert launcher.calls == 1


# ── (5) after process exits, new launch is allowed ────────────────────────────────────────

def test_launch_allowed_after_process_exits(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key-x")
    c, launcher = _make_console(tmp_path, ["project-exit01"])
    pid = c.start_project(ProjectRequest(description="app"))
    assert launcher.calls == 1

    # Simulate process exit
    c._procs[pid].terminate()
    assert not c._stage_process_alive(pid)

    # Stage finished — a new launch should be accepted
    result = c._launch_stage(pid, 2, "stage2-prompt", {})
    assert result is not None, "_launch_stage must succeed when prior process has exited"
    assert launcher.calls == 2
