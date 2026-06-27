#!/usr/bin/env python3
"""Claude Code Stop-hook: ships stage-run transcripts to Langfuse.

Registered as a Stop hook in the stage workspace claude-settings.json when
TRACE_TO_LANGFUSE=1. Claude Code invokes this script at the end of every -p
session, passing a JSON payload on stdin:

    {"session_id": "...", "transcript_path": "/path/to/session.jsonl", ...}

Each line of the transcript JSONL is a message dict with at minimum "role" and
"content". We create one Langfuse trace per session and one generation for each
assistant turn, paired with the user message that preceded it.

Exit codes: always 0 — a tracing failure must never kill the stage run.
"""
from __future__ import annotations

import json
import os
import sys


def _read_transcript(path: str) -> list[dict]:
    msgs: list[dict] = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        msgs.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except OSError:
        pass
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


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, OSError):
        return

    if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")):
        return

    try:
        from langfuse import Langfuse
    except ImportError:
        sys.stderr.write("[langfuse_hook] langfuse package missing — stage tracing skipped\n")
        return

    session_id: str = payload.get("session_id") or ""
    transcript_path: str = payload.get("transcript_path") or ""
    msgs = _read_transcript(transcript_path)
    if not msgs:
        return

    # Name the trace after the project directory so it's identifiable in the Langfuse UI.
    cwd = os.environ.get("PWD", "")
    trace_name = f"stage:{os.path.basename(cwd)}" if cwd else "stage-run"

    lf = Langfuse(
        public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
        secret_key=os.environ["LANGFUSE_SECRET_KEY"],
        host=(
            os.environ.get("LANGFUSE_BASE_URL")
            or os.environ.get("LANGFUSE_HOST")
            or "https://cloud.langfuse.com"
        ),
    )
    trace = lf.trace(id=session_id or None, name=trace_name)

    for i, msg in enumerate(msgs):
        if msg.get("role") != "assistant":
            continue
        output = _text(msg.get("content", ""))
        if not output:
            continue
        # Walk back to find the nearest preceding user message as the generation input.
        user_input = ""
        for j in range(i - 1, -1, -1):
            if msgs[j].get("role") == "user":
                user_input = _text(msgs[j].get("content", ""))
                break
        usage = msg.get("usage") or {}
        trace.generation(
            name="assistant",
            input=user_input or None,
            output=output,
            model=msg.get("model") or None,
            usage={
                "input": usage.get("input_tokens", 0),
                "output": usage.get("output_tokens", 0),
            } if usage else None,
        )

    lf.flush()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[langfuse_hook] error: {e}\n")
