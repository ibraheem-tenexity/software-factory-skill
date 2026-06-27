"""Tests for the Langfuse stage-run stop-hook."""
from __future__ import annotations

import io
import json
import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def transcript(tmp_path):
    path = tmp_path / "session.jsonl"
    path.write_text(
        json.dumps(
            [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Hi"},
                {
                    "role": "assistant",
                    "content": "Hello!",
                    "model": "claude-sonnet-4-6",
                    "usage": {
                        "input_tokens": 10,
                        "output_tokens": 5,
                        "total_tokens": 15,
                    },
                },
                {"role": "user", "content": "Bye"},
                {"role": "assistant", "content": "See ya!"},
            ]
        )
    )
    return path


def _run(payload: dict, monkeypatch, tmp_path) -> tuple[MagicMock, MagicMock, MagicMock]:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    monkeypatch.setenv("PWD", str(tmp_path))
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))

    lf = MagicMock()
    start_obs = MagicMock()
    lf.start_as_current_observation = start_obs
    lf.flush = MagicMock()

    root_cm = MagicMock()
    start_obs.return_value.__enter__ = MagicMock(return_value=root_cm)
    start_obs.return_value.__exit__ = MagicMock(return_value=False)

    prop_cm = MagicMock()
    prop_patch = MagicMock()
    prop_patch.return_value.__enter__ = MagicMock(return_value=prop_cm)
    prop_patch.return_value.__exit__ = MagicMock(return_value=False)

    from software_factory import langfuse_hook

    with patch("langfuse.get_client", return_value=lf, create=True), patch(
        "langfuse.propagate_attributes", prop_patch, create=True
    ):
        langfuse_hook.main()

    return lf, start_obs, prop_patch


def test_hook_creates_trace_and_generations(transcript, monkeypatch, tmp_path):
    lf, start_obs, prop_patch = _run(
        {"session_id": "sess-123", "transcript_path": str(transcript)},
        monkeypatch,
        tmp_path,
    )

    # One root span and one generation per assistant message.
    assert start_obs.call_count == 3

    # Root span is created first.
    root_call = start_obs.call_args_list[0]
    assert root_call.kwargs["as_type"] == "span"
    assert root_call.kwargs["name"] == f"stage:{tmp_path.name}"

    # propagate_attributes carries session id and trace name.
    prop_patch.assert_called_once_with(
        trace_name=f"stage:{tmp_path.name}",
        session_id="sess-123",
    )

    # First generation has usage and model from the assistant message.
    gen1 = start_obs.call_args_list[1]
    assert gen1.kwargs["as_type"] == "generation"
    assert gen1.kwargs["name"] == "assistant"
    assert gen1.kwargs["input"] == "Hi"
    assert gen1.kwargs["output"] == "Hello!"
    assert gen1.kwargs["model"] == "claude-sonnet-4-6"
    assert gen1.kwargs["usage_details"] == {
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
    }

    # Second generation pairs with the preceding user message.
    gen2 = start_obs.call_args_list[2]
    assert gen2.kwargs["input"] == "Bye"
    assert gen2.kwargs["output"] == "See ya!"
    assert gen2.kwargs["model"] is None
    assert gen2.kwargs["usage_details"] is None

    lf.flush.assert_called_once()


def test_hook_reads_jsonl_objects(transcript, monkeypatch, tmp_path):
    path = tmp_path / "session.jsonl"
    path.write_text(
        json.dumps({"role": "user", "content": "Q"})
        + "\n"
        + json.dumps({"role": "assistant", "content": "A"})
        + "\n"
    )
    lf, start_obs, _ = _run(
        {"session_id": "sess-456", "transcript_path": str(path)},
        monkeypatch,
        tmp_path,
    )
    assert start_obs.call_count == 2  # root + one generation
    gen = start_obs.call_args_list[1]
    assert gen.kwargs["input"] == "Q"
    assert gen.kwargs["output"] == "A"


def test_hook_skips_when_keys_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    from software_factory import langfuse_hook

    langfuse_hook.main()
    # No exception means we tolerantly skipped.
