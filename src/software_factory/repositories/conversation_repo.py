"""Pure CRUD for `conversation` (SQLAlchemy Core). Global table — no project-path scoping;
callers pass session_id/scope values explicitly (mirrors blobs_repo.py, see #212)."""
from __future__ import annotations

import json

from sqlalchemy import select, insert, func

from ..models import conversation

_COLS = (conversation.c.id, conversation.c.session_id, conversation.c.seq,
         conversation.c.user_id, conversation.c.project_id, conversation.c.org_id,
         conversation.c.role, conversation.c.input, conversation.c.json_blob,
         conversation.c.tool_name, conversation.c.tool_call_id, conversation.c.tool_result,
         conversation.c.referenced_artifact, conversation.c.model, conversation.c.provider,
         conversation.c.input_tokens, conversation.c.output_tokens, conversation.c.cost_usd,
         conversation.c.created_at)


class ConversationRepository:
    def __init__(self, exec_):
        self._x = exec_

    def next_seq(self, session_id) -> int:
        """The next `seq` for this session (0 if none yet). Callers must still handle a race —
        two writers can both read the same next_seq before either inserts; the unique
        `(session_id, seq)` constraint is the actual guard, this is just the common-case guess."""
        row = self._x.fetchone(
            select(func.coalesce(func.max(conversation.c.seq), -1).label("max_seq"))
            .where(conversation.c.session_id == session_id))
        return row["max_seq"] + 1

    def insert(self, *, session_id, seq, role, json_blob, user_id=None, project_id=None,
              org_id=None, input_text=None, tool_name=None, tool_call_id=None,
              tool_result=None, referenced_artifact=None, model=None, provider=None,
              input_tokens=0, output_tokens=0, cost_usd=0.0):
        """Insert one message row at the given seq. Raises psycopg.errors.UniqueViolation if
        another writer already took this (session_id, seq) — the caller (ConversationStore.append)
        retries with a fresh seq on that specific exception.

        JSONB columns are passed as `json.dumps(...)` strings, matching checkpoint_repo.py's
        convention — this codebase's `_exec.py` compiles Core statements to raw SQL + params and
        hands them straight to psycopg3, bypassing SQLAlchemy's own bind_processor, so a plain
        Python list/dict is never auto-serialized on the way in (Postgres auto-decodes JSONB back
        to a Python object on the way OUT, via its own type OID — asymmetric by design)."""
        stmt = insert(conversation).values(
            session_id=session_id, seq=seq, role=role, json_blob=json.dumps(json_blob),
            user_id=user_id, project_id=project_id, org_id=org_id, input=input_text,
            tool_name=tool_name, tool_call_id=tool_call_id,
            tool_result=json.dumps(tool_result) if tool_result is not None else None,
            referenced_artifact=referenced_artifact, model=model, provider=provider,
            input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=cost_usd,
        ).returning(conversation.c.id)
        return self._x.fetchone(stmt)["id"]

    def all_for_session(self, session_id) -> list:
        return self._x.fetchall(select(*_COLS)
                                .where(conversation.c.session_id == session_id)
                                .order_by(conversation.c.seq))
