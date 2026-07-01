"""In-memory mock Concierge conversation — stands in until the real LangChain agent + the DB-backed
chat-history store ship (see docs/concierge-agent-spec.md). Returns deterministic scripted turns so
the frontend conversation loop (plain-text vs up-to-4-choice questions → hand off) can be built and
demoed without a model key.

Framework-free (only `time` + `errors.py`); one in-memory transcript per project_id; resets on
restart — expected for the mock. When the real agent lands, its class replaces this one in
`console/state.py::reset()` with the SAME `turn()` contract, leaving the route + frontend untouched.
"""
import time

from software_factory.services.errors import Invalid

# Scripted agent turns, walked by the count of prior agent turns. Each entry is (message, choices);
# `choices` empty ⇒ a plain-text turn, otherwise ≤4 single-select options. The real agent decides
# text-vs-choices per turn; the mock just cycles a representative script (text → choices → choices).
_SCRIPT: list[tuple[str, list[str]]] = [
    ("Thanks — that's a solid start. In one line, what's the single most important outcome this "
     "project has to deliver?", []),
    ("Which part of the workflow is the biggest bottleneck today?",
     ["Manual data entry / re-keying", "Approvals & sign-off", "Reporting & visibility", "Something else"]),
    ("Who are the primary users of what we build?",
     ["Internal ops team", "Sales / quoting", "External customers", "Management"]),
]
_HANDOFF = ("I have enough to draft the brief. Hand off to the factory whenever you're ready — or keep "
            "adding detail and I'll fold it in.", [])


class Conversation:
    """Mock conversation service: one in-memory transcript per project."""

    def __init__(self):
        self._store: dict = {}  # project_id → list[{role, content, choices}]

    def history(self, project_id: str) -> list[dict]:
        """The full transcript for a project (oldest first). Empty if none yet."""
        return list(self._store.get(project_id, []))

    def turn(self, project_id: str, message: str) -> dict:
        """Record the user's message and return the (mock) agent's next turn:
        {"message": str, "choices": list[str] (≤4), "done": bool}. `done` = the agent has no more
        questions and is inviting hand-off. Raises `Invalid` on an empty message."""
        text = (message or "").strip()
        if not text:
            raise Invalid("message is empty")
        turns = self._store.setdefault(project_id, [])
        turns.append({"role": "user", "content": text, "choices": []})

        prior_agent_turns = sum(1 for t in turns if t["role"] == "agent")
        done = prior_agent_turns >= len(_SCRIPT)
        reply, choices = _HANDOFF if done else _SCRIPT[prior_agent_turns]
        turns.append({"role": "agent", "content": reply, "choices": list(choices), "ts": _now()})
        return {"message": reply, "choices": list(choices), "done": done}


def _now() -> float:
    return time.time()
