"""Tests for chat_store — JSONL persistence for chat messages."""
import json
import os
import tempfile
import time

import pytest

from software_factory.chat_store import ChatMessage, ChatStore


@pytest.fixture
def store(tmp_path):
    return ChatStore(str(tmp_path / "chat.jsonl"))


def _msg(role="user", content="hello", msg_type="text", **kw):
    return ChatMessage(role=role, content=content, msg_type=msg_type,
                       ts=time.time(), metadata=kw)


class TestChatMessage:
    def test_to_dict_roundtrip(self):
        m = _msg(content="hi", file_name="a.pdf")
        d = m.to_dict()
        assert d["role"] == "user"
        assert d["content"] == "hi"
        assert d["metadata"]["file_name"] == "a.pdf"
        m2 = ChatMessage.from_dict(d)
        assert m2.role == m.role
        assert m2.content == m.content
        assert m2.metadata == m.metadata

    def test_from_dict_missing_fields_get_defaults(self):
        m = ChatMessage.from_dict({"role": "assistant", "content": "ok"})
        assert m.msg_type == "text"
        assert m.metadata == {}
        assert isinstance(m.ts, float)


class TestChatStore:
    def test_empty_history(self, store):
        assert store.history() == []

    def test_append_and_history(self, store):
        store.append(_msg(content="one"))
        store.append(_msg(role="assistant", content="two"))
        h = store.history()
        assert len(h) == 2
        assert h[0].content == "one"
        assert h[1].content == "two"
        assert h[1].role == "assistant"

    def test_persistence_across_instances(self, tmp_path):
        path = str(tmp_path / "chat.jsonl")
        s1 = ChatStore(path)
        s1.append(_msg(content="persisted"))
        s2 = ChatStore(path)
        assert len(s2.history()) == 1
        assert s2.history()[0].content == "persisted"

    def test_file_is_jsonl(self, store, tmp_path):
        store.append(_msg(content="line1"))
        store.append(_msg(content="line2"))
        raw = (tmp_path / "chat.jsonl").read_text()
        lines = [l for l in raw.strip().split("\n") if l]
        assert len(lines) == 2
        assert json.loads(lines[0])["content"] == "line1"
        assert json.loads(lines[1])["content"] == "line2"

    def test_last_assistant_returns_none_when_empty(self, store):
        assert store.last_assistant() is None

    def test_last_assistant_skips_user_messages(self, store):
        store.append(_msg(role="user", content="q"))
        store.append(_msg(role="assistant", content="a1"))
        store.append(_msg(role="user", content="q2"))
        store.append(_msg(role="assistant", content="a2"))
        assert store.last_assistant().content == "a2"

    def test_dep_values_never_stored(self, store, tmp_path):
        store.append(_msg(role="user", content="Provided: RAILWAY_TOKEN",
                          msg_type="dep_submit", dep_names=["RAILWAY_TOKEN"]))
        raw = (tmp_path / "chat.jsonl").read_text()
        assert "rwt_" not in raw
        assert "RAILWAY_TOKEN" in raw  # name is ok

    def test_handles_corrupt_line_gracefully(self, tmp_path):
        path = tmp_path / "chat.jsonl"
        path.write_text('{"role":"user","content":"ok"}\nNOT JSON\n{"role":"assistant","content":"yes"}\n')
        s = ChatStore(str(path))
        h = s.history()
        assert len(h) == 2
        assert h[0].content == "ok"
        assert h[1].content == "yes"

    def test_creates_parent_dirs(self, tmp_path):
        path = str(tmp_path / "deep" / "nested" / "chat.jsonl")
        s = ChatStore(path)
        s.append(_msg(content="deep"))
        assert len(s.history()) == 1
