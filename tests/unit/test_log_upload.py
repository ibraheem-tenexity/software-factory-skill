"""Tests for _upload_project_log — project.log → Supabase Storage at stage completion.

Covers:
  - storage disabled → graceful skip, log_url stays None
  - storage enabled, log exists → put() called, log_url stamped
  - log file missing → skip (nothing to upload)
  - upload failure → no exception propagated, log_url stays None
  - log_url field persisted in ProjectState / _PERSISTED
"""
import os
import pytest
from unittest.mock import MagicMock, patch

from software_factory.projectstate import ProjectState, _PERSISTED


# ---------------------------------------------------------------------------
# ProjectState field presence
# ---------------------------------------------------------------------------

def test_log_url_in_persisted():
    assert "log_url" in _PERSISTED


def test_log_url_default_none():
    s = ProjectState(project_id="proj-test1234")
    assert s.log_url is None


def test_log_url_survives_round_trip():
    from software_factory.projectstate import JsonFileStore
    import tempfile, json
    with tempfile.TemporaryDirectory() as d:
        store = JsonFileStore(d)
        s = ProjectState(project_id="proj-rt123456", _store=store)
        s.log_url = "https://example.com/storage/v1/object/public/bucket/proj-rt123456/logs/project.log"
        s.save()
        s2 = ProjectState.load("proj-rt123456", store)
        assert s2.log_url == s.log_url


# ---------------------------------------------------------------------------
# _upload_project_log helper (tested via Console with mocked internals)
# ---------------------------------------------------------------------------

def _make_console(tmp_path):
    """Minimal Console instance with projects_dir pointing to tmp_path."""
    from software_factory.console import Console
    return Console(str(tmp_path))


@pytest.fixture
def project_dir(tmp_path):
    pid = "proj-logtest1"
    d = tmp_path / pid
    d.mkdir()
    log = d / "project.log"
    log.write_text("stage1 output\nstage2 output\n")
    return tmp_path, pid, log


def test_upload_skipped_when_storage_disabled(project_dir, monkeypatch):
    tmp_path, pid, _ = project_dir
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    monkeypatch.delenv("SF_STORAGE_BUCKET", raising=False)
    monkeypatch.setenv("SF_BLOB_DIR", str(tmp_path / "blobs"))
    console = _make_console(tmp_path)
    state = MagicMock()
    state.log_url = None
    # When storage is disabled, put() uses the local fallback — should still succeed
    console._upload_project_log(pid, state)
    # local fallback writes the file; log_url is set (file:// URL)
    assert state.log_url is not None
    assert state.log_url.startswith("file://")


def test_upload_sets_log_url_when_enabled(project_dir, monkeypatch):
    tmp_path, pid, _ = project_dir
    fake_url = f"https://supabase.example.com/storage/v1/object/public/bucket/{pid}/logs/project.log"
    with patch("software_factory.storage.put", return_value=fake_url) as mock_put:
        monkeypatch.setenv("SUPABASE_URL", "https://supabase.example.com")
        monkeypatch.setenv("SUPABASE_SERVICE_KEY", "svc-key")
        monkeypatch.setenv("SF_STORAGE_BUCKET", "bucket")
        console = _make_console(tmp_path)
        state = MagicMock()
        console._upload_project_log(pid, state)
        mock_put.assert_called_once_with(pid, "logs/project.log", str(tmp_path / pid / "project.log"))
        assert state.log_url == fake_url


def test_upload_skipped_when_log_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    pid = "proj-nolog123"
    (tmp_path / pid).mkdir()
    # no project.log in the dir
    console = _make_console(tmp_path)
    state = MagicMock()
    state.log_url = None
    with patch("software_factory.storage.put") as mock_put:
        console._upload_project_log(pid, state)
        mock_put.assert_not_called()
    assert state.log_url is None


def test_upload_failure_does_not_propagate(project_dir, monkeypatch):
    tmp_path, pid, _ = project_dir
    with patch("software_factory.storage.put", side_effect=Exception("network error")):
        monkeypatch.setenv("SUPABASE_URL", "https://supabase.example.com")
        monkeypatch.setenv("SUPABASE_SERVICE_KEY", "svc-key")
        monkeypatch.setenv("SF_STORAGE_BUCKET", "bucket")
        console = _make_console(tmp_path)
        state = MagicMock()
        state.log_url = None
        # Must not raise
        console._upload_project_log(pid, state)
        assert state.log_url is None
