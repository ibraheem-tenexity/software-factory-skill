#!/usr/bin/env python3
"""Claude Code Stop-hook: ships stage-run transcripts to Langfuse.

Registered as a Stop hook in the stage workspace claude-settings.json when
TRACE_TO_LANGFUSE=1. Claude Code invokes this script at the end of every -p
session, passing a JSON payload on stdin:

    {"session_id": "...", "transcript_path": "/path/to/session.jsonl", ...}

Each line of the transcript JSONL is a message dict with at minimum "role" and
"content". We create one Langfuse trace per session and one generation for each
assistant turn, paired with the user message that preceded it.

This implementation targets langfuse SDK v4 (OpenTelemetry-based). The legacy
``Langfuse.trace()``/``trace.generation()`` API is no longer available in the
v4 package, so we use ``get_client()``, ``start_as_current_observation()``, and
``propagate_attributes()`` instead.

Exit codes: always 0 — a tracing failure must never kill the stage run.
"""
from __future__ import annotations

import json
import os
import sys


def _read_transcript(path: str) -> list[dict]:
    """Return the transcript messages, tolerant of JSON arrays or JSONL."""
    try:
        with open(path) as f:
            raw = f.read()
    except OSError:
        return []

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        pass
    else:
        if isinstance(data, list):
            return [m for m in data if isinstance(m, dict)]

    msgs: list[dict] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            msgs.append(obj)
    return msgs


def _text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            b.get("text", "")
            for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        ]
        return "\n".join(p for p in parts if p)
    return ""


def _usage_details(msg: dict) -> dict[str, int] | None:
    usage = msg.get("usage") if isinstance(msg.get("usage"), dict) else None
    if not usage:
        return None

    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    total_tokens = usage.get("total_tokens")

    details: dict[str, int] = {}
    if isinstance(input_tokens, (int, float)):
        details["input_tokens"] = int(input_tokens)
    if isinstance(output_tokens, (int, float)):
        details["output_tokens"] = int(output_tokens)
    if isinstance(total_tokens, (int, float)):
        details["total_tokens"] = int(total_tokens)
    return details or None


def _preceding_user_input(msgs: list[dict], assistant_index: int) -> str | None:
    for j in range(assistant_index - 1, -1, -1):
        if msgs[j].get("role") == "user":
            text = _text(msgs[j].get("content", ""))
            return text or None
    return None


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, OSError):
        return

    if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")):
        return

    try:
        from langfuse import get_client, propagate_attributes
    except ImportError:
        sys.stderr.write("[langfuse_hook] langfuse package missing — stage tracing skipped\n")
        return

    session_id: str = payload.get("session_id") or ""
    transcript_path: str = payload.get("transcript_path") or ""
    msgs = _read_transcript(transcript_path)
    if not msgs:
        return

    cwd = os.environ.get("PWD", "")
    trace_name = f"stage:{os.path.basename(cwd)}" if cwd else "stage-run"

    lf = get_client()

    try:
        with lf.start_as_current_observation(as_type="span", name=trace_name):
            with propagate_attributes(trace_name=trace_name, session_id=session_id or None):
                for i, msg in enumerate(msgs):
                    if msg.get("role") != "assistant":
                        continue

                    output = _text(msg.get("content", ""))
                    if not output:
                        continue

                    user_input = _preceding_user_input(msgs, i)
                    model = msg.get("model") or None
                    usage_details = _usage_details(msg)

                    with lf.start_as_current_observation(
                        as_type="generation",
                        name="assistant",
                        input=user_input,
                        output=output,
                        model=model,
                        usage_details=usage_details,
                    ):
                        pass

        lf.flush()
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[langfuse_hook] error: {e}\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[langfuse_hook] error: {e}\n")
