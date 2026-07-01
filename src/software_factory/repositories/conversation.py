"""Pure CRUD for `conversation` (SQLAlchemy Core). Global table — no project-path scoping;
callers pass session_id/scope values explicitly (mirrors blobs.py, see #212)."""
from __future__ import annotations

from sqlalchemy import select, insert, func, and_, or_

from ..models import conversation
from ._compile import epoch_cast, serialize_jsonb, uuid_str_cast

# id/session_id/user_id are UUID columns. GlobalExec's raw-SQL path bypasses SQLAlchemy's own
# UUID(as_uuid=False) type coercion (the compiled statement + params go straight to psycopg3),
# so a plain `conversation.c.id` in a SELECT list comes back as a real `uuid.UUID` object, not a
# string — psycopg3 has its own native UUID adapter that fires once SQLAlchemy's own isn't in the
# loop. Same bug class as the JSONB-needs-json.dumps gotcha, one column type over. Matches
# repositories/users.py's existing cast(..., Text) convention for its own UUID columns — bind-
# parameter comparisons (WHERE/INSERT VALUES) don't need this (Postgres infers the type from
# context there); only SELECT-list/RETURNING output does.
#
# created_at is DateTime(timezone=True) — a bare column in the SELECT list comes back as a raw
# Python `datetime`, not the epoch float the rest of the app uses everywhere (SOF-55). Extracted +
# cast to match repositories/users.py's corrected reference pattern (a bare
# func.extract("epoch", ...) alone isn't enough either — Postgres's EXTRACT returns numeric, which
# psycopg3 decodes to Decimal, not float).
_COLS = (uuid_str_cast(conversation.c.id).label("id"),
         uuid_str_cast(conversation.c.session_id).label("session_id"),
         conversation.c.seq,
         uuid_str_cast(conversation.c.user_id).label("user_id"),
         conversation.c.project_id, conversation.c.org_id,
         conversation.c.role, conversation.c.input, conversation.c.json_blob,
         conversation.c.tool_name, conversation.c.tool_call_id, conversation.c.tool_result,
         conversation.c.referenced_artifact, conversation.c.model, conversation.c.provider,
         conversation.c.input_tokens, conversation.c.output_tokens, conversation.c.cost_usd,
         epoch_cast(conversation.c.created_at).label("created_at"))


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

        JSONB columns are passed as `json.dumps(...)` strings, matching checkpoint.py's
        convention — this codebase's `_exec.py` compiles Core statements to raw SQL + params and
        hands them straight to psycopg3, bypassing SQLAlchemy's own bind_processor, so a plain
        Python list/dict is never auto-serialized on the way in (Postgres auto-decodes JSONB back
        to a Python object on the way OUT, via its own type OID — asymmetric by design)."""
        stmt = insert(conversation).values(
            session_id=session_id, seq=seq, role=role, json_blob=serialize_jsonb(json_blob),
            user_id=user_id, project_id=project_id, org_id=org_id, input=input_text,
            tool_name=tool_name, tool_call_id=tool_call_id,
            tool_result=serialize_jsonb(tool_result),
            referenced_artifact=referenced_artifact, model=model, provider=provider,
            input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=cost_usd,
        ).returning(uuid_str_cast(conversation.c.id).label("id"))
        return self._x.fetchone(stmt)["id"]

    def all_for_session(self, session_id) -> list:
        return self._x.fetchall(select(*_COLS)
                                .where(conversation.c.session_id == session_id)
                                .order_by(conversation.c.seq))

    def rollup(self, *, org_id=None, project_id=None, user_id=None, session_id=None, role=None,
              date_from=None, date_to=None, cursor=None, limit=50) -> list:
        """One row per session, aggregated from the messages matching the filters — a SINGLE grouped
        query (SOF-34's "no N+1" AC), not a query-per-session. org_id/project_id/user_id are
        session-constant scoping columns (set once when the session starts, ConversationStore never
        varies them mid-session) so grouping by them alongside session_id is exact, not a guess.

        `cursor`, if given, is (last_activity, session_id) from a previous page's last row — keyset
        pagination ordered by (last_activity DESC, session_id DESC), stable under concurrent inserts
        (unlike OFFSET, which can skip/duplicate rows as new messages land).

        last_activity is cast the same way _COLS's created_at is (SOF-55) — MAX() of a
        timestamptz column is itself a timestamptz/raw-datetime leak, and the cast must be
        applied to the SAME shared expression used in SELECT/HAVING/ORDER BY, not just the
        output: a cursor read from a previous page's (already epoch-float) last_activity is
        compared against this expression in HAVING, so both sides must be the same type."""
        last_activity = epoch_cast(func.max(conversation.c.created_at))
        conds = []
        if org_id is not None:
            conds.append(conversation.c.org_id == org_id)
        if project_id is not None:
            conds.append(conversation.c.project_id == project_id)
        if user_id is not None:
            conds.append(conversation.c.user_id == user_id)
        if session_id is not None:
            conds.append(conversation.c.session_id == session_id)
        if role is not None:
            conds.append(conversation.c.role == role)
        if date_from is not None:
            conds.append(conversation.c.created_at >= date_from)
        if date_to is not None:
            conds.append(conversation.c.created_at <= date_to)

        stmt = (
            select(uuid_str_cast(conversation.c.session_id).label("session_id"),
                   conversation.c.org_id, conversation.c.project_id,
                   uuid_str_cast(conversation.c.user_id).label("user_id"),
                   func.count().label("turn_count"),
                   last_activity.label("last_activity"),
                   func.coalesce(func.sum(conversation.c.cost_usd), 0).label("total_cost"))
            # GROUP BY (and the cursor HAVING/ORDER BY below) reference the RAW, uncast column —
            # a cast() in the SELECT list is a deterministic function of the grouped column, so
            # Postgres accepts it without also needing the cast in GROUP BY; the HAVING/ORDER BY
            # comparisons are bind-parameter context (a plain string param against the typed
            # column), which Postgres coerces implicitly, same as users.py's WHERE/INSERT — only
            # SELECT-list/RETURNING *output* needs the explicit cast.
            .group_by(conversation.c.session_id, conversation.c.org_id, conversation.c.project_id,
                      conversation.c.user_id)
        )
        if conds:
            stmt = stmt.where(and_(*conds))
        if cursor is not None:
            cur_activity, cur_session_id = cursor
            stmt = stmt.having(or_(last_activity < cur_activity,
                                   and_(last_activity == cur_activity,
                                        conversation.c.session_id < cur_session_id)))
        stmt = stmt.order_by(last_activity.desc(), conversation.c.session_id.desc()).limit(limit)
        return self._x.fetchall(stmt)
