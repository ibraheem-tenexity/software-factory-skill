"""Tests for _reaper_tick — the periodic deploy-DB reaper scheduled inside _poll_transitions.

Two gates must both be open for the reaper to fire:
  1. SF_REAPER_INTERVAL_TICKS > 0 AND tick % interval == 0  (ibraheem's activation knob)
  2. SF_DEPLOY_DB_TEARDOWN != 'off'                         (inner teardown arm)
"""
import pytest
from unittest.mock import MagicMock, patch

from console.poller import _reaper_tick


@pytest.fixture
def console():
    c = MagicMock()
    c.reap_deploy_dbs.return_value = {
        "mode": "persistent",
        "armed": True,
        "reaped": [{"project_id": "proj-aaa1", "service_id": "svc-1"}],
        "would_reap": [],
        "kept": [{"project_id": "proj-bbb2", "service_id": "svc-2",
                  "phase": "done", "has_verified_deploy": True}],
        "failed": [],
        "detached_volumes": {},
    }
    return c


# ---------------------------------------------------------------------------
# Gate 1: interval knob
# ---------------------------------------------------------------------------

def test_disabled_when_interval_zero(console, monkeypatch):
    monkeypatch.setenv("SF_DEPLOY_DB_TEARDOWN", "persistent")
    result = _reaper_tick(tick=7200, interval=0, console=console)
    assert result is None
    console.reap_deploy_dbs.assert_not_called()


def test_disabled_when_interval_negative(console, monkeypatch):
    monkeypatch.setenv("SF_DEPLOY_DB_TEARDOWN", "persistent")
    result = _reaper_tick(tick=100, interval=-1, console=console)
    assert result is None
    console.reap_deploy_dbs.assert_not_called()


def test_does_not_fire_on_tick_zero(console, monkeypatch):
    monkeypatch.setenv("SF_DEPLOY_DB_TEARDOWN", "persistent")
    result = _reaper_tick(tick=0, interval=10, console=console)
    assert result is None
    console.reap_deploy_dbs.assert_not_called()


def test_does_not_fire_between_intervals(console, monkeypatch):
    monkeypatch.setenv("SF_DEPLOY_DB_TEARDOWN", "persistent")
    for tick in [1, 99, 101, 199]:
        result = _reaper_tick(tick=tick, interval=100, console=console)
        assert result is None
    console.reap_deploy_dbs.assert_not_called()


def test_fires_at_interval_boundary(console, monkeypatch):
    monkeypatch.setenv("SF_DEPLOY_DB_TEARDOWN", "persistent")
    result = _reaper_tick(tick=100, interval=100, console=console)
    assert result is not None
    console.reap_deploy_dbs.assert_called_once_with(dry_run=False)


def test_fires_at_multiple_interval_boundaries(console, monkeypatch):
    monkeypatch.setenv("SF_DEPLOY_DB_TEARDOWN", "persistent")
    for tick in [100, 200, 300]:
        _reaper_tick(tick=tick, interval=100, console=console)
    assert console.reap_deploy_dbs.call_count == 3


# ---------------------------------------------------------------------------
# Gate 2: teardown arm
# ---------------------------------------------------------------------------

def test_silent_skip_when_disarmed(console, monkeypatch):
    monkeypatch.delenv("SF_DEPLOY_DB_TEARDOWN", raising=False)
    result = _reaper_tick(tick=100, interval=100, console=console)
    assert result is None
    console.reap_deploy_dbs.assert_not_called()


def test_silent_skip_when_arm_off(console, monkeypatch):
    monkeypatch.setenv("SF_DEPLOY_DB_TEARDOWN", "off")
    result = _reaper_tick(tick=100, interval=100, console=console)
    assert result is None
    console.reap_deploy_dbs.assert_not_called()


def test_fires_when_arm_persistent(console, monkeypatch):
    monkeypatch.setenv("SF_DEPLOY_DB_TEARDOWN", "persistent")
    result = _reaper_tick(tick=100, interval=100, console=console)
    assert result is not None
    console.reap_deploy_dbs.assert_called_once_with(dry_run=False)


def test_fires_when_arm_ephemeral(console, monkeypatch):
    monkeypatch.setenv("SF_DEPLOY_DB_TEARDOWN", "ephemeral")
    result = _reaper_tick(tick=100, interval=100, console=console)
    assert result is not None
    console.reap_deploy_dbs.assert_called_once_with(dry_run=False)


# ---------------------------------------------------------------------------
# Report passthrough
# ---------------------------------------------------------------------------

def test_returns_report_from_reap(console, monkeypatch):
    monkeypatch.setenv("SF_DEPLOY_DB_TEARDOWN", "persistent")
    result = _reaper_tick(tick=100, interval=100, console=console)
    assert result["mode"] == "persistent"
    assert len(result["reaped"]) == 1
    assert len(result["kept"]) == 1


def test_dry_run_false_passed_to_reap(console, monkeypatch):
    """Scheduler never forces dry_run — the arm gate inside reap() decides."""
    monkeypatch.setenv("SF_DEPLOY_DB_TEARDOWN", "persistent")
    _reaper_tick(tick=100, interval=100, console=console)
    console.reap_deploy_dbs.assert_called_once_with(dry_run=False)
