"""Tests for the pre-verify Railway link re-assertion (software_factory.railway_link).

A drifted link must FAIL LOUDLY (LinkDriftError) rather than letting a verify run against the
wrong project/env/service (TEN-151 / KNOWN_ISSUES #87). The runner is injected so these run
offline with canned `railway status` output.
"""
import pytest

from software_factory import railway_link as rl

# Real `railway status` shape (the run-app project — i.e. the WRONG target for a console verify).
_RUNAPP_STATUS = """
Workspace:       Tenexity

Project:         software-factory-projects
Project ID:      8ecbd1b2-2722-4968-91c9-4a242f8120f3

Environment:     production
Environment ID:  3c8117be-4cb0-41b0-a4ff-0bc9eb8e90eb

Linked service

    Service:         None

────────────────────────────────────────────────
"""

_CONSOLE_STATUS = """
Workspace:       Tenexity

Project:         softwarefactory
Project ID:      11112222-3333-4444-5555-666677778888

Environment:     software-factory-as-skill
Environment ID:  99990000-aaaa-bbbb-cccc-ddddeeeeffff

Linked service

    Service:         factory-console

────────────────────────────────────────────────
"""


def _run(text, rc=0):
    return lambda args: (text, rc)


def test_parse_status_extracts_linked_fields():
    s = rl.parse_status(_CONSOLE_STATUS)
    assert s["project"] == "softwarefactory"
    assert s["project_id"] == "11112222-3333-4444-5555-666677778888"
    assert s["environment"] == "software-factory-as-skill"
    assert s["service"] == "factory-console"


def test_parse_status_captures_service_none():
    assert rl.parse_status(_RUNAPP_STATUS)["service"] == "None"


def test_assert_link_passes_on_match():
    expected = {"project": "softwarefactory", "environment": "software-factory-as-skill", "service": "factory-console"}
    actual = rl.assert_link(expected, run=_run(_CONSOLE_STATUS))
    assert actual["project"] == "softwarefactory"


def test_assert_link_fails_loudly_on_wrong_project():
    # Linked to the run-app project, but we expect the console project → must raise.
    expected = rl.expected_from_env(env={})  # defaults: softwarefactory / ... / factory-console
    with pytest.raises(rl.LinkDriftError) as ei:
        rl.assert_link(expected, run=_run(_RUNAPP_STATUS))
    msg = str(ei.value)
    assert "project" in msg and "softwarefactory" in msg and "software-factory-projects" in msg


def test_assert_link_fails_on_missing_service():
    expected = {"service": "factory-console"}
    with pytest.raises(rl.LinkDriftError) as ei:
        rl.assert_link(expected, run=_run(_RUNAPP_STATUS))
    assert "service" in str(ei.value) and "None" in str(ei.value)


def test_assert_link_prefers_ids_when_set():
    expected = {"project_id": "deadbeef-0000-0000-0000-000000000000"}
    with pytest.raises(rl.LinkDriftError):
        rl.assert_link(expected, run=_run(_CONSOLE_STATUS))


def test_assert_link_raises_when_status_fails():
    with pytest.raises(rl.LinkDriftError) as ei:
        rl.assert_link({"project": "softwarefactory"}, run=_run("not logged in", rc=1))
    assert "railway status" in str(ei.value)


def test_assert_link_skips_empty_expected_fields():
    # Unset (empty) expected fields must not trigger a mismatch.
    expected = {"project": "softwarefactory", "project_id": "", "environment_id": ""}
    assert rl.assert_link(expected, run=_run(_CONSOLE_STATUS))["project"] == "softwarefactory"


def test_expected_from_env_defaults_and_overrides():
    d = rl.expected_from_env(env={})
    assert d["project"] == "softwarefactory" and d["service"] == "factory-console"
    o = rl.expected_from_env(env={"SF_DEPLOY_PROJECT": "other", "SF_DEPLOY_PROJECT_ID": "xyz"})
    assert o["project"] == "other" and o["project_id"] == "xyz"
