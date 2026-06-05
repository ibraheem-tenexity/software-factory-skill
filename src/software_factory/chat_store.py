"""Append-only JSONL persistence for chat messages."""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field


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


class ChatStore:
    def __init__(self, chat_path: str):
        self._path = chat_path

    def append(self, msg: ChatMessage) -> None:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "a") as f:
            f.write(json.dumps(msg.to_dict(), separators=(",", ":")) + "\n")

    def history(self) -> list[ChatMessage]:
        if not os.path.exists(self._path):
            return []
        msgs = []
        with open(self._path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    msgs.append(ChatMessage.from_dict(json.loads(line)))
                except (json.JSONDecodeError, KeyError):
                    continue
        return msgs

    def last_assistant(self) -> ChatMessage | None:
        for m in reversed(self.history()):
            if m.role == "assistant":
                return m
        return None
