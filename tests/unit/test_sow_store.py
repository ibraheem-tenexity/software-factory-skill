"""SowStore unit tests — validation logic, no live DB needed."""
import os
import pytest
from unittest.mock import patch

from software_factory.sow import SowStore, SOW_STATUSES


def test_sow_statuses_are_correct():
    assert set(SOW_STATUSES) == {"Template", "Draft", "In review", "Sent", "Signed"}


def test_create_raises_on_invalid_status(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"postgresql://localhost/nodb")
    store = SowStore()
    with pytest.raises(ValueError, match="invalid status"):
        store.create("My SOW", status="Bogus")


def test_update_raises_on_invalid_status(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/nodb")
    store = SowStore()
    with pytest.raises(ValueError, match="invalid status"):
        store.update(1, {"status": "Oops"})


def test_update_noop_when_no_allowed_fields(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/nodb")
    store = SowStore()
    import software_factory.sow as sow_mod
    with patch.object(sow_mod, "_row", return_value={"id": 1, "title": "X"}):
        result = store.update(1, {"unknown_field": "val"})
    assert result == {"id": 1, "title": "X"}
