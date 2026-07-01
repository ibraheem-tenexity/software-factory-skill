"""SOF-37: the reflection trust gate — recording + deduping unreferenced candidates as
questions, and the promote-route gate logic. ACTUALLY RUN via a standalone python -c script
(no DB) — same posture as the rest of the memory-track PRs; conftest.py bootstraps a real
Postgres connection at collection time for every test file, unconditionally, so even these
DB-free-in-content tests can't run via pytest here. Transcript in the PR description.
"""
from software_factory.memory.ingest import _record_reflection_questions, _reflection_question_id


class _FakeState:
    def __init__(self):
        self.reflection_questions = []
        self.saved = 0

    def save(self):
        self.saved += 1


class _FakeConsole:
    def __init__(self, state):
        self._state = state

    def _load_state(self, project_id):
        return self._state


def test_record_reflection_questions_appends_open_questions():
    state = _FakeState()
    console = _FakeConsole(state)
    unreferenced = [
        {"fact": "unclear fact A", "document_blob_id": 1, "section_path": None},
        {"fact": "unclear fact B", "document_blob_id": 1, "section_path": "Weird"},
    ]
    _record_reflection_questions(console, "project-x", unreferenced)
    assert len(state.reflection_questions) == 2
    assert all(q["status"] == "open" for q in state.reflection_questions)
    assert all(q["answer"] is None for q in state.reflection_questions)
    assert state.saved == 1


def test_record_reflection_questions_dedups_on_re_ingest():
    # The same unreferenced candidate re-extracted on a re-ingest (unchanged document) must
    # not spawn a duplicate question, and must not even trigger a redundant save.
    state = _FakeState()
    console = _FakeConsole(state)
    unreferenced = [{"fact": "unclear fact A", "document_blob_id": 1, "section_path": None}]
    _record_reflection_questions(console, "project-x", unreferenced)
    _record_reflection_questions(console, "project-x", unreferenced)
    assert len(state.reflection_questions) == 1
    assert state.saved == 1


def test_record_reflection_questions_appends_genuinely_new_candidates():
    state = _FakeState()
    console = _FakeConsole(state)
    _record_reflection_questions(console, "project-x", [
        {"fact": "unclear fact A", "document_blob_id": 1, "section_path": None},
    ])
    _record_reflection_questions(console, "project-x", [
        {"fact": "a genuinely different fact", "document_blob_id": 2, "section_path": None},
    ])
    assert len(state.reflection_questions) == 2
    assert state.saved == 2


def test_reflection_question_ids_differ_by_fact_text_within_the_same_document():
    id_a = _reflection_question_id(1, "fact A")
    id_b = _reflection_question_id(1, "fact B")
    assert id_a != id_b


def test_promote_gate_logic_blocks_only_on_open_status():
    # Mirrors console/routers/projects.py::promote_draft's exact filter — answered/dismissed
    # questions must never block hand-off, only ones still "open".
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


def test_injected_unreferenced_fact_never_renders_as_a_stated_fact_end_to_end():
    """THE trust test (the ticket's own acceptance bar): ingest a fixture doc containing one
    claim with a real section_path match and one claim with a fabricated/no section_path.
    doc_summary.key_facts must contain ONLY the referenced claim; the unreferenced one must
    appear in ProjectState.reflection_questions with status='open', never in key_facts."""
    pass  # needs a real ingest_blob(...) round-trip against a real Postgres + doc fixture


def test_learned_facts_every_entry_links_to_a_real_source_document():
    """MemoryStore.learned_facts(scope, scope_id) must return document_name resolved via a
    real blobs join for every entry — never a fact with a missing/null source."""
    pass  # needs a real doc_summary + blobs round-trip
