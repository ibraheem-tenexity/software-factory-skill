"""The happy-flow gate is the run's definition of done. Code merging != a working app;
only a passing browser journey counts.

Critical scar: a missing/empty/garbage result must read as FAIL, never PASS. Done has to
be earned with positive evidence, not inferred from the absence of a failure.
"""
from software_factory.gate import happy_flow_passed, bugs_from


def passing_result():
    return {
        "journey": "guestbook",
        "steps": [
            {"name": "load page", "ok": True},
            {"name": "submit name", "ok": True},
            {"name": "see name in list", "ok": True},
        ],
    }


def test_all_steps_ok_passes():
    assert happy_flow_passed(passing_result()) is True


def test_any_failing_step_fails():
    r = passing_result()
    r["steps"][1]["ok"] = False
    assert happy_flow_passed(r) is False


def test_empty_result_is_fail_not_pass():
    assert happy_flow_passed({}) is False
    assert happy_flow_passed(None) is False


def test_result_with_no_steps_is_fail():
    # No steps ran -> nothing was verified -> not done.
    assert happy_flow_passed({"journey": "guestbook", "steps": []}) is False


def test_bugs_lists_only_failing_steps_with_detail():
    r = passing_result()
    r["steps"][1] = {"name": "submit name", "ok": False, "error": "500 from /api/entries"}
    bugs = bugs_from(r)
    assert len(bugs) == 1
    assert bugs[0]["step"] == "submit name"
    assert "500" in bugs[0]["error"]


def test_no_bugs_when_all_pass():
    assert bugs_from(passing_result()) == []
