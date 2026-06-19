"""Local SQLite ticket store. The point of using a DB over a markdown file is ENFORCED
state: a ticket cannot reach `done` without a real merged PR and a non-empty diff.

This is the "no hollow done" scar made mechanical — the last run merged a QA ticket that
did nothing. Here that transition simply raises.
"""
import pytest

from software_factory.tickets import TicketStore, HollowWorkError, IllegalTransition


def fresh(tmp_path):
    return TicketStore(str(tmp_path / "tickets.db"))


def test_buildable_count_zero_on_empty_store(tmp_path):
    assert fresh(tmp_path).buildable_count() == 0


def test_buildable_count_requires_nonempty_acceptance_and_dod(tmp_path):
    ts = fresh(tmp_path)
    ts.create_ticket("real", acceptance="user sees X", dod="happy flow green", wave=1)
    ts.create_ticket("hollow", acceptance="", dod="", wave=1)          # empty → not buildable
    ts.create_ticket("half", acceptance="something", dod="   ", wave=2)  # blank dod → not buildable
    assert ts.buildable_count() == 1


def test_create_and_list_open_tickets(tmp_path):
    ts = fresh(tmp_path)
    tid = ts.create_ticket("Guestbook form", acceptance="submit shows name", dod="happy flow green", wave=1)
    assert isinstance(tid, int)
    open_ids = [t.id for t in ts.open_tickets(wave=1)]
    assert open_ids == [tid]


def test_open_tickets_are_scoped_by_wave(tmp_path):
    ts = fresh(tmp_path)
    ts.create_ticket("wave1 task", acceptance="a", dod="d", wave=1)
    w2 = ts.create_ticket("wave2 task", acceptance="a", dod="d", wave=2)
    assert [t.id for t in ts.open_tickets(wave=2)] == [w2]


def test_claim_assigns_agent_and_moves_to_in_progress(tmp_path):
    ts = fresh(tmp_path)
    tid = ts.create_ticket("t", acceptance="a", dod="d", wave=1)
    ts.claim(tid, agent="build-agent-1")
    t = ts.get(tid)
    assert t.status == "in_progress"
    assert t.agent == "build-agent-1"


def test_mark_done_refuses_without_a_real_pr(tmp_path):
    ts = fresh(tmp_path)
    tid = ts.create_ticket("t", acceptance="a", dod="d", wave=1)
    with pytest.raises(HollowWorkError):
        ts.mark_done(tid, provenance=None, diff_lines=120)
    assert ts.get(tid).status != "done"


def test_mark_done_refuses_an_empty_diff(tmp_path):
    ts = fresh(tmp_path)
    tid = ts.create_ticket("t", acceptance="a", dod="d", wave=1)
    with pytest.raises(HollowWorkError):
        ts.mark_done(tid, provenance="7", diff_lines=0)
    assert ts.get(tid).status != "done"


def test_mark_done_with_a_real_merged_change_succeeds(tmp_path):
    ts = fresh(tmp_path)
    tid = ts.create_ticket("t", acceptance="a", dod="d", wave=1)
    ts.mark_done(tid, provenance="7", diff_lines=120)
    t = ts.get(tid)
    assert t.status == "done"
    assert t.provenance == "7"
    assert t.provenance_type == "pr"
    assert tid not in [x.id for x in ts.open_tickets(wave=1)]


def test_state_survives_reopening_the_db(tmp_path):
    db = str(tmp_path / "t.db")
    tid = TicketStore(db).create_ticket("t", acceptance="a", dod="d", wave=1)
    # Reopen: a /loop re-entry sees the same tickets.
    assert [t.id for t in TicketStore(db).open_tickets(wave=1)] == [tid]


def test_done_tickets_returns_only_closed_ones_with_their_pr(tmp_path):
    ts = fresh(tmp_path)
    a = ts.create_ticket("done one", acceptance="a", dod="d", wave=1)
    ts.create_ticket("still open", acceptance="a", dod="d", wave=1)
    ts.mark_done(a, provenance="7", diff_lines=120)
    done = ts.done_tickets()
    assert [t.id for t in done] == [a]
    assert done[0].provenance == "7" and done[0].diff_lines == 120
    assert done[0].provenance_type == "pr"


def test_render_markdown_view_lists_tickets_and_status(tmp_path):
    ts = fresh(tmp_path)
    ts.create_ticket("Guestbook form", acceptance="submit shows name", dod="green", wave=1)
    md = ts.render_markdown()
    assert "Guestbook form" in md
    assert "open" in md


# -- 6-state lifecycle + QA loop --------------------------------------------------------
def _to_deployed(ts):
    tid = ts.create_ticket("t", acceptance="a", dod="d", wave=1)
    ts.claim(tid, agent="build-1")
    ts.mark_done(tid, provenance="abc1234", diff_lines=40)
    ts.mark_deployed(tid)
    return tid


def test_full_happy_lifecycle_to_approved(tmp_path):
    ts = fresh(tmp_path)
    tid = _to_deployed(ts)
    assert ts.get(tid).status == "deployed"
    ts.start_qa(tid)
    assert ts.get(tid).status == "qa_testing"
    ts.qa_approve(tid)
    assert ts.get(tid).status == "approved"
    assert ts.all_approved()
    assert [t.id for t in ts.approved_tickets()] == [tid]


def test_qa_reject_bounces_to_open_with_bug_report(tmp_path):
    ts = fresh(tmp_path)
    tid = _to_deployed(ts)
    ts.start_qa(tid)
    ts.qa_reject(tid, "Submit button 404s.\n\n![shot](https://x/y.png)")
    t = ts.get(tid)
    assert t.status == "open"               # back in the build queue
    assert t.agent is None                  # cleared for a fresh claim
    assert "QA bug" in t.description and "Submit button 404s" in t.description
    assert "y.png" in t.description          # screenshot link carried for the next build agent
    assert tid in [x.id for x in ts.open_tickets(wave=1)]   # re-buildable


def test_done_tickets_includes_built_and_beyond(tmp_path):
    ts = fresh(tmp_path)
    tid = _to_deployed(ts)                   # status == deployed
    assert tid in [t.id for t in ts.done_tickets()]   # still counts as built-or-beyond
    assert not ts.all_approved()


def test_illegal_transitions_raise(tmp_path):
    ts = fresh(tmp_path)
    tid = ts.create_ticket("t", acceptance="a", dod="d", wave=1)
    with pytest.raises(IllegalTransition):
        ts.mark_deployed(tid)                # open → deployed (must be done first)
    with pytest.raises(IllegalTransition):
        ts.qa_approve(tid)                   # open → approved (never QA'd)
    ts.claim(tid, "b1"); ts.mark_done(tid, provenance="9", diff_lines=5)
    with pytest.raises(IllegalTransition):
        ts.start_qa(tid)                     # done → qa_testing (must deploy first)
    with pytest.raises(IllegalTransition):
        ts.qa_reject(tid, "nope")            # done → open via qa_reject (not in qa_testing)


def test_create_ticket_with_description(tmp_path):
    ts = fresh(tmp_path)
    tid = ts.create_ticket("t", acceptance="a", dod="d", wave=1, description="build the thing")
    assert ts.get(tid).description == "build the thing"
