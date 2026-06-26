"""Tests for _log_flush_tick — incremental project.log upload to Supabase Storage.

Covers:
  - storage disabled → no upload
  - log file missing → no upload
  - file size unchanged since last flush → no upload
  - file has grown → storage.put() called, offset updated
  - upload failure → no exception propagated
"""
import os
import pytest
from unittest.mock import patch

import console.poller as poller


@pytest.fixture(autouse=True)
def reset_offsets():
    poller._log_offsets.clear()
    yield
    poller._log_offsets.clear()


def test_skip_when_storage_disabled(tmp_path, monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    monkeypatch.delenv("SF_STORAGE_BUCKET", raising=False)
    log = tmp_path / "project.log"
    log.write_bytes(b"some output\n")
    with patch("software_factory.storage.put") as mock_put:
        poller._log_flush_tick("proj-abc12345", str(log))
    mock_put.assert_not_called()


def test_skip_when_log_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "svc")
    monkeypatch.setenv("SF_STORAGE_BUCKET", "bucket")
    with patch("software_factory.storage.put") as mock_put:
        poller._log_flush_tick("proj-abc12345", str(tmp_path / "missing.log"))
    mock_put.assert_not_called()


def test_skip_when_size_unchanged(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "svc")
    monkeypatch.setenv("SF_STORAGE_BUCKET", "bucket")
    log = tmp_path / "project.log"
    log.write_bytes(b"line1\n")
    poller._log_offsets["proj-abc12345"] = log.stat().st_size  # pretend already flushed
    with patch("software_factory.storage.put") as mock_put:
        poller._log_flush_tick("proj-abc12345", str(log))
    mock_put.assert_not_called()


def test_uploads_when_file_grows(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "svc")
    monkeypatch.setenv("SF_STORAGE_BUCKET", "bucket")
    log = tmp_path / "project.log"
    log.write_bytes(b"line1\nline2\n")
    with patch("software_factory.storage.put", return_value="https://signed") as mock_put:
        poller._log_flush_tick("proj-abc12345", str(log))
    mock_put.assert_called_once_with("proj-abc12345", "logs/project.log", str(log))


def test_offset_updated_after_upload(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "svc")
    monkeypatch.setenv("SF_STORAGE_BUCKET", "bucket")
    log = tmp_path / "project.log"
    log.write_bytes(b"line1\nline2\n")
    with patch("software_factory.storage.put", return_value="https://signed"):
        poller._log_flush_tick("proj-abc12345", str(log))
    assert poller._log_offsets["proj-abc12345"] == log.stat().st_size


def test_failure_does_not_propagate(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "svc")
    monkeypatch.setenv("SF_STORAGE_BUCKET", "bucket")
    log = tmp_path / "project.log"
    log.write_bytes(b"data\n")
    with patch("software_factory.storage.put", side_effect=Exception("network error")):
        poller._log_flush_tick("proj-abc12345", str(log))  # must not raise
    # offset NOT updated on failure
    assert poller._log_offsets.get("proj-abc12345", 0) == 0


def test_uploads_first_bytes_from_zero(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "svc")
    monkeypatch.setenv("SF_STORAGE_BUCKET", "bucket")
    log = tmp_path / "project.log"
    log.write_bytes(b"first batch\n")
    assert "proj-abc12345" not in poller._log_offsets
    with patch("software_factory.storage.put", return_value="https://signed") as mock_put:
        poller._log_flush_tick("proj-abc12345", str(log))
    mock_put.assert_called_once()
    assert poller._log_offsets["proj-abc12345"] > 0
