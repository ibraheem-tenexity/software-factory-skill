"""Widen project_id suffix: new ids use 16-hex; existing 8-hex ids still validate."""
import re

from software_factory.db import _PROJECT_ID_RE
from software_factory.console import Console, PROJECT_ID_RE


class FakeLauncher:
    def __call__(self, argv, env=None, log_path=None, cwd=None):
        return {"pid": 1}


def test_new_project_id_has_16hex_suffix(tmp_path):
    c = Console(str(tmp_path), launch=FakeLauncher())
    pid = c.create_draft(owner="u@test.com", name="Test")
    assert pid.startswith("project-"), f"unexpected prefix: {pid!r}"
    suffix = pid[len("project-"):]
    assert len(suffix) == 16, f"expected 16-hex suffix, got {len(suffix)!r} chars: {pid!r}"
    assert re.fullmatch(r"[0-9a-f]{16}", suffix), f"suffix not lowercase hex: {suffix!r}"


def test_db_regex_accepts_existing_8hex_ids():
    assert _PROJECT_ID_RE.fullmatch("project-ab12cd34"), "8-hex id must still validate"


def test_db_regex_accepts_new_16hex_ids():
    assert _PROJECT_ID_RE.fullmatch("project-ab12cd34ef56ab12"), "16-hex id must validate"


def test_db_regex_rejects_7hex():
    assert not _PROJECT_ID_RE.fullmatch("project-ab12cd3"), "7-hex must not validate"


def test_console_regex_accepts_both_widths():
    assert PROJECT_ID_RE.fullmatch("project-ab12cd34"), "console: 8-hex must validate"
    assert PROJECT_ID_RE.fullmatch("project-ab12cd34ef56ab12"), "console: 16-hex must validate"
