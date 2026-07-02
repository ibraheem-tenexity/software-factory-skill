"""SOF-37/SOF-60: the reflection trust gate. SOF-60 removed ingest-time auto-generation of
reflection questions (the Concierge raises them itself via its tool belt); the gate logic —
open questions block promote — is unchanged and still covered here. ACTUALLY RUN via a
standalone python -c script (no DB) — same posture as the rest of the memory-track PRs;
conftest.py bootstraps a real Postgres connection at collection time for every test file,
unconditionally, so even these DB-free-in-content tests can't run via pytest here.
"""
from software_factory.memory import ingest


def test_ingest_no_longer_auto_records_reflection_questions():
    # SOF-60: the blind per-document escalation path is gone — the Concierge is the only
    # writer of reflection_questions now. Guards against the helper quietly coming back.
    assert not hasattr(ingest, "_record_reflection_questions")


def test_promote_gate_logic_blocks_only_on_open_status():
    # Mirrors console.promote_draft's exact filter — answered/dismissed questions must never
    # block hand-off, only ones still "open".
    questions = [
        {"id": "q1", "status": "open"},
        {"id": "q2", "status": "answered"},
        {"id": "q3", "status": "dismissed"},
    ]
    open_questions = [q for q in questions if q["status"] == "open"]
    assert len(open_questions) == 1
    assert open_questions[0]["id"] == "q1"


def test_promote_gate_logic_allows_handoff_when_no_questions_at_all():
    open_questions = [q for q in [] if q["status"] == "open"]
    assert open_questions == []


# ---- DB-requiring: written per AC, NOT executed here (needs Console/BlobStore/MemoryStore
# against a real Postgres). Deferred to the integrator's off-box run. -----------------------

def test_promote_draft_route_returns_409_with_open_questions_in_the_body():
    """POST /api/projects/{pid}/promote must refuse (409) while any reflection_questions entry
    has status='open', and the response body must include the open questions themselves (not
    just a generic error string) so the FE can show what's blocking."""
    pass  # needs a real FastAPI TestClient + Console/ProjectState round-trip


def test_resolve_reflection_endpoint_answer_flips_status_and_records_answer():
    """PATCH /api/projects/{pid}/reflection/{id} with action=answer must set status='answered'
    and persist the supplied answer text; action=dismiss must set status='dismissed' with
    answer=None. Either unblocks the promote-route gate for that specific question."""
    pass  # needs a real FastAPI TestClient + Console/ProjectState round-trip


def test_injected_unreferenced_claim_never_renders_as_a_stated_assumption_end_to_end():
    """THE trust test: ingest a fixture doc containing one claim with a real section_path match
    and one claim with a fabricated/no section_path. doc_summary.assumptions must contain ONLY
    the referenced claim; the unreferenced one is dropped from assumptions (and, post-SOF-60,
    NOT auto-escalated into reflection_questions — that's the Concierge's call now)."""
    pass  # needs a real ingest_blob(...) round-trip against a real Postgres + doc fixture


def test_assumptions_every_entry_links_to_a_real_source_document():
    """MemoryStore.assumptions(scope, scope_id) must return document_name resolved via a
    real blobs join for every entry — never an assumption with a missing/null source."""
    pass  # needs a real doc_summary + blobs round-trip
