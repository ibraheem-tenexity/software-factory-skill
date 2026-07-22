"""Chat-agent data types — every DTO the Concierge/chat surfaces move over the wire or to disk.

Two groups live here together on purpose (all chat-agent DTOs in one file):
  · ChatMessage — one persisted/streamed chat turn (used by the /api/chat dock + poller narration).
  · SuggestedResponse / ConciergeTurn — the Concierge output contract:
    the JSON the agent emits to the human, from which the multiple-choice UI is derived
    (empty suggested_responses ⇒ plain text; non-empty ⇒ single-select radios / multi-select
    checkboxes; each item's `type` decides). No `choices` field, no `done` flag — the shape IS the state.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field


@dataclass
class ChatMessage:
    role: str
    content: str
    msg_type: str = "text"
    ts: float = 0.0
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.ts == 0.0:
            self.ts = time.time()

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content,
                "msg_type": self.msg_type, "ts": self.ts,
                "metadata": self.metadata}

    @classmethod
    def from_dict(cls, d: dict) -> ChatMessage:
        return cls(role=d["role"], content=d["content"],
                   msg_type=d.get("msg_type", "text"),
                   ts=d.get("ts") or time.time(),
                   metadata=d.get("metadata", {}))


class SuggestedResponse(BaseModel):
    response: str = Field(min_length=1)
    type: Literal["single select", "multi select"]


class ConciergeTurn(BaseModel):
    response: str = Field(min_length=1)   # required, non-empty — the assistant's utterance
    suggested_responses: list[SuggestedResponse] = Field(default_factory=list)
