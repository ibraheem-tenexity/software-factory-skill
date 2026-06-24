"""SowStore unit tests — validation logic + real-DB round-trip."""
import os
import pytest
from unittest.mock import patch

from software_factory.sow import SowStore, SOW_STATUSES


def test_sow_statuses_are_correct():
    assert set(SOW_STATUSES) == {"Template", "Draft", "In review", "Sent", "Signed"}


def test_create_and_readback_return_real_values():
    """Real-DB round-trip: create() → list_all() → get() must return REAL values, not col names.

    This is the regression test for the zip(cols, dict_row) bug where every value == its column
    name (e.g. {"id": "id", "title": "title"}) because iterating a dict_row gives its keys.
    """
    store = SowStore()
    row = store.create("Acme SOW Q3", org="Acme", status="Draft",
                       body="## Scope\nBuild a thing.")
    assert row["title"] == "Acme SOW Q3", f"create() returned {row!r}"
    assert row["org"] == "Acme"
    assert row["status"] == "Draft"
    assert isinstance(row["id"], int)

    rows = store.list_all()
    assert any(r["title"] == "Acme SOW Q3" for r in rows), \
        f"list_all() row titles: {[r['title'] for r in rows]}"

    fetched = store.get(row["id"])
    assert fetched["title"] == "Acme SOW Q3", f"get() returned {fetched!r}"
    assert fetched["body"] == "## Scope\nBuild a thing."


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
