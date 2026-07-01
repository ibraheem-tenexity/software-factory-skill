"""SOF-55: boundary-type tests for the GlobalExec repos — real round trips against a live
Postgres (there's no way to observe psycopg3's actual decode type from a FakeExec/mocked
connection; the *_repo_compile.py files check SQL shape, not runtime types).

Every repo here executes SQLAlchemy Core statements over a raw psycopg3 connection, bypassing
SQLAlchemy's own bind/result type processors (see repositories/_exec.py) — so column-type
handling is governed entirely by psycopg3's own default adapters, and two gotchas apply
everywhere a UUID or DateTime column is selected:

  - UUID columns decode to `uuid.UUID` unless cast to Text in the SELECT.
  - DateTime columns decode to `datetime.datetime` unless extracted as epoch; but a bare
    `func.extract("epoch", col)` ALSO leaks — Postgres's EXTRACT returns `numeric`, which
    psycopg3 decodes to `decimal.Decimal`, not `float`. The fix needs `cast(extract(...), Float)`.

Each test creates its own throwaway row, asserts the real Python types, and deletes the row
after — safe to run against a shared scratch DB.
"""
from software_factory import dbshim
from software_factory.repositories._exec import GlobalExec
from software_factory.repositories.agent_prompts_repo import AgentPromptRepository
from software_factory.repositories.blobs_repo import BlobRepository
from software_factory.repositories.conversation_repo import ConversationRepository
from software_factory.repositories.sow_repo import SowRepository
from software_factory.repositories.users import UserRepository


def test_sow_repo_created_at_and_updated_at_are_float_not_decimal_or_datetime():
    repo = SowRepository(GlobalExec())
    row = repo.insert(title="SOF-55 boundary test", org=None, project=None, value=None,
                      file=None, version=1, status="Draft", body=None)
    try:
        assert isinstance(row["created_at"], float)
        assert isinstance(row["updated_at"], float)
        assert isinstance(repo.by_id(row["id"])["created_at"], float)
        updated = repo.update_fields(row["id"], title="renamed")
        assert isinstance(updated["updated_at"], float)
        assert any(isinstance(r["created_at"], float) for r in repo.list_all() if r["id"] == row["id"])
    finally:
        conn = dbshim.connect(".")
        try:
            conn.execute("DELETE FROM sow WHERE id = ?", (row["id"],))
        finally:
            conn.close()


def test_agent_prompts_repo_updated_at_is_float_not_decimal():
    repo = AgentPromptRepository(GlobalExec())
    try:
        repo.upsert("SOF55TYPETEST", "a test prompt", "op@tenexity.ai")
        row = repo.by_callsign("SOF55TYPETEST")
        assert isinstance(row["updated_at"], float)
    finally:
        repo.delete("SOF55TYPETEST")


def test_blobs_repo_list_org_docs_updated_is_float_not_decimal():
    repo = BlobRepository(GlobalExec())
    org_id = "org-sof55-typetest"
    blob_id = repo.insert("org", org_id, "kind", "name.txt", "tag", "key", "text/plain", 10, "sha")
    try:
        docs = repo.list_org_docs(org_id)
        assert isinstance(docs[0]["updated"], float)
    finally:
        conn = dbshim.connect(".")
        try:
            conn.execute("DELETE FROM blobs WHERE id = ?", (blob_id,))
        finally:
            conn.close()


def test_users_repo_id_is_string_not_uuid_and_timestamps_are_float_not_decimal():
    import uuid
    repo = UserRepository(GlobalExec())
    email = "sof55-typetest@tenexity.ai"
    uid = str(uuid.uuid4())
    conn = dbshim.connect(".")
    try:
        role_id = conn.execute("SELECT id FROM roles WHERE name = 'admin'").fetchone()["id"]
    finally:
        conn.close()
    try:
        repo.upsert_user(uid, email, str(role_id), None)
        repo.set_identity(uid, "google-sub-sof55-typetest")
        rows = repo.by_google_sub("google-sub-sof55-typetest")
        assert len(rows) == 1
        row = rows[0]
        assert isinstance(row["id"], str)                # not uuid.UUID
        assert isinstance(row["created_at"], float)      # not Decimal/datetime
        assert isinstance(row["onboarded_at"], float)     # set_identity coalesces it to now()
        assert isinstance(row["is_internal"], bool)

        rows2 = repo.by_email(email)
        assert isinstance(rows2[0]["id"], str)

        creds = repo.credentials(email)
        assert isinstance(creds[0]["id"], str)
    finally:
        conn = dbshim.connect(".")
        try:
            conn.execute("DELETE FROM users WHERE email = ?", (email,))
        finally:
            conn.close()


def test_users_repo_org_created_at_is_float_not_decimal():
    from software_factory.users import UserStore
    us = UserStore()
    org_id = us.create_org("SOF-55 boundary test org", by="sof55-typetest@tenexity.ai")
    try:
        org = us.get_org(org_id)
        assert isinstance(org["created_at"], float)
    finally:
        conn = dbshim.connect(".")
        try:
            conn.execute("DELETE FROM organizations WHERE id = ?", (org_id,))
        finally:
            conn.close()


def test_conversation_repo_id_and_created_at_are_str_and_float_not_uuid_and_decimal():
    """The UUID-cast fix landed on the Phase-2-concierge branch already (osweozhk) — but
    created_at was still a leak (a bare column, no epoch extraction at all) discovered during
    SOF-55's re-audit after that branch merged. Also covers rollup()'s last_activity, which
    needed the SAME cast expression repeated in SELECT/HAVING/ORDER BY, not just the output —
    a cursor read back from a previous page must compare against the identical type."""
    import uuid
    repo = ConversationRepository(GlobalExec())
    session_id = str(uuid.uuid4())
    org_id = "org-sof55-conv-typetest"
    try:
        mid = repo.insert(session_id=session_id, seq=0, role="user",
                          json_blob=[{"type": "text", "text": "hi"}], org_id=org_id)
        assert isinstance(mid, str)

        rows = repo.all_for_session(session_id)
        assert isinstance(rows[0]["id"], str)
        assert isinstance(rows[0]["session_id"], str)
        assert isinstance(rows[0]["created_at"], float)

        rollup = repo.rollup(org_id=org_id)
        assert isinstance(rollup[0]["last_activity"], float)

        # the cursor/HAVING comparison must work with the SAME (float) type on both sides
        last_activity, rollup_session_id = rollup[0]["last_activity"], rollup[0]["session_id"]
        assert repo.rollup(org_id=org_id, cursor=(last_activity - 1, rollup_session_id)) == []
        assert len(repo.rollup(org_id=org_id, cursor=(last_activity + 1, rollup_session_id))) == 1
    finally:
        conn = dbshim.connect(".")
        try:
            conn.execute("DELETE FROM conversation WHERE session_id = ?", (session_id,))
        finally:
            conn.close()
