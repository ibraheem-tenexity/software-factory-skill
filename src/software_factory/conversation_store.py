"""ConversationStore (SOF-28/T1.1) — durable, provider-agnostic conversation persistence over
`dbshim`. Pure CRUD: `append` + `history`. No agent logic, no scripting, no provider rendering
(that's `to_provider`, T1.2/SOF-30) — locked with nm0w1psh (T2.1) so `services/conversation.py`'s
`Conversation.turn()` stays the sole orchestrating entry point that drives this store, exactly like
it drives the in-memory mock today.
"""
from __future__ import annotations

import psycopg

from .repositories._exec import GlobalExec
from .repositories.conversation import ConversationRepository
from .conversation_blocks import validate_blocks, first_text, first_tool_result
from .users import UserStore

_MAX_SEQ_RETRIES = 5


class ConversationStore:
    def __init__(self, repo: ConversationRepository | None = None, users: UserStore | None = None):
        # Both are injectable: `repo` so tests can exercise the seq-retry-on-conflict logic
        # (SOF-28's own concurrency AC) with a fake repo instead of a real DB; `users` so
        # console/state.py's shared UserStore singleton isn't redundantly re-seeded on construct.
        self._repo = repo if repo is not None else ConversationRepository(GlobalExec())
        self._users = users

    def _resolve_user_id(self, email: str | None) -> str | None:
        if not email:
            return None
        if self._users is None:
            self._users = UserStore()
        row = self._users.get_user(email)
        return row["id"] if row else None

    def append(self, session_id: str, role: str, blocks: list, *,
              user_email: str | None = None, project_id: str | None = None,
              org_id: str | None = None, tool_name: str | None = None,
              tool_call_id: str | None = None,
              model: str | None = None, provider: str | None = None,
              input_tokens: int = 0, output_tokens: int = 0, cost_usd: float = 0.0) -> str:
        """Append one message to `session_id`. `blocks` is a non-empty list of canonical content
        blocks (conversation_blocks.py); raises ValueError if any block is malformed. Returns the
        new message_id.

        Concurrency: two writers appending to the same session race on `seq`. `next_seq()` is a
        best-effort read (not a lock); the unique `(session_id, seq)` constraint is the real guard
        — a losing writer's insert raises psycopg.errors.UniqueViolation, and we retry with a fresh
        seq up to _MAX_SEQ_RETRIES times."""
        validate_blocks(blocks)
        user_id = self._resolve_user_id(user_email)
        input_text = first_text(blocks)
        tool_result_block = first_tool_result(blocks)

        last_exc = None
        for _ in range(_MAX_SEQ_RETRIES):
            seq = self._repo.next_seq(session_id)
            try:
                return self._repo.insert(
                    session_id=session_id, seq=seq, role=role, json_blob=blocks,
                    user_id=user_id, project_id=project_id, org_id=org_id,
                    input_text=input_text, tool_name=tool_name, tool_call_id=tool_call_id,
                    tool_result=tool_result_block,
                    model=model, provider=provider, input_tokens=input_tokens,
                    output_tokens=output_tokens, cost_usd=cost_usd,
                )
            except psycopg.errors.UniqueViolation as exc:
                last_exc = exc
                continue
        raise last_exc

    def history(self, session_id: str) -> list[dict]:
        """The full transcript for `session_id`, oldest first (ordered by `seq`)."""
        return self._repo.all_for_session(session_id)
