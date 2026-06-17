"""Langfuse exporter: run.log events -> LLM traces (trace=run, generation=assistant turn,
event=tool call). Tapped from the console poller — no agent/launch-path changes; works for
both runtimes because it parses the same stream run.log already holds.

Env-gated like notify.py: LANGFUSE_PUBLIC_KEY + LANGFUSE_SECRET_KEY absent -> no-op.
Host: LANGFUSE_BASE_URL (or LANGFUSE_HOST), default https://cloud.langfuse.com.

Event ids are DETERMINISTIC (run_id + log offset), so re-exports after a restart (offsets
are in-memory) dedupe server-side instead of duplicating observations.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import urllib.request

from .streamlog import _events

_MAX_BATCH = 100


def enabled() -> bool:
    return bool(os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"))


def _host() -> str:
    return (os.environ.get("LANGFUSE_BASE_URL") or os.environ.get("LANGFUSE_HOST")
            or "https://cloud.langfuse.com").rstrip("/")


def _post(batch: list) -> None:
    creds = f"{os.environ['LANGFUSE_PUBLIC_KEY']}:{os.environ['LANGFUSE_SECRET_KEY']}"
    req = urllib.request.Request(
        _host() + "/api/public/ingestion",
        data=json.dumps({"batch": batch}).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": "Basic " + base64.b64encode(creds.encode()).decode()})
    urllib.request.urlopen(req, timeout=15).read()


def _eid(run_id: str, kind: str, seq: int) -> str:
    return hashlib.sha1(f"{run_id}:{kind}:{seq}".encode()).hexdigest()


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())


def map_events(run_id: str, text: str, meta: dict | None = None, seq0: int = 0) -> list:
    """run.log lines -> Langfuse ingestion events. seq0 keeps ids unique across ticks."""
    ts = _now()
    out = []
    if seq0 == 0:
        out.append({"id": _eid(run_id, "trace", 0), "type": "trace-create", "timestamp": ts,
                    "body": {"id": run_id, "name": run_id, "metadata": meta or {}}})
    seq = seq0
    for ev in _events(text):
        seq += 1
        msg = ev.get("message") or {}
        usage = msg.get("usage")
        if usage:  # claude assistant turn with token usage -> generation
            text_part = next((c.get("text", "") for c in (msg.get("content") or [])
                              if isinstance(c, dict) and c.get("type") == "text"), "")
            out.append({"id": _eid(run_id, "gen", seq), "type": "generation-create",
                        "timestamp": ts, "body": {
                            "id": _eid(run_id, "gen", seq), "traceId": run_id,
                            "name": "turn", "model": msg.get("model", ""),
                            "startTime": ts, "endTime": ts,
                            "usage": {"input": usage.get("input_tokens", 0),
                                      "output": usage.get("output_tokens", 0)},
                            "output": text_part[:300]}})
        part = ev.get("part") or {}
        if ev.get("type") == "step_finish" and part.get("type") == "step-finish":
            tokens = part.get("tokens") or {}
            out.append({"id": _eid(run_id, "gen", seq), "type": "generation-create",
                        "timestamp": ts, "body": {
                            "id": _eid(run_id, "gen", seq), "traceId": run_id,
                            "name": "step", "model": "kimi-k2.7-code",
                            "startTime": ts, "endTime": ts,
                            "usage": {"input": tokens.get("input", 0),
                                      "output": tokens.get("output", 0)},
                            "metadata": {"cost": part.get("cost")}}})
        for c in (msg.get("content") or []) or []:
            if isinstance(c, dict) and c.get("type") == "tool_use":
                out.append({"id": _eid(run_id, "tool", seq), "type": "event-create",
                            "timestamp": ts, "body": {
                                "id": _eid(run_id, "tool", seq), "traceId": run_id,
                                "name": "tool:" + c.get("name", "?"), "startTime": ts}})
    return out


class Tracer:
    """Per-run incremental exporter. tick() reads the log tail since the last offset and
    ships whole lines; errors never propagate (observability must not break the factory)."""

    def __init__(self):
        self._offsets: dict[str, int] = {}
        self._seqs: dict[str, int] = {}

    def tick(self, run_id: str, log_path: str, meta: dict | None = None) -> int:
        if not enabled() or not os.path.exists(log_path):
            return 0
        try:
            start = self._offsets.get(run_id, 0)
            with open(log_path, "rb") as f:
                f.seek(start)
                chunk = f.read()
            if not chunk:
                return 0
            nl = chunk.rfind(b"\n")
            if nl < 0:  # no complete line yet
                return 0
            text = chunk[:nl + 1].decode("utf-8", "replace")
            events = map_events(run_id, text, meta=meta, seq0=self._seqs.get(run_id, 0))
            sent = 0
            for i in range(0, len(events), _MAX_BATCH):
                _post(events[i:i + _MAX_BATCH])
                sent += len(events[i:i + _MAX_BATCH])
            # advance only after a successful ship (deterministic ids make retries safe)
            self._offsets[run_id] = start + nl + 1
            self._seqs[run_id] = self._seqs.get(run_id, 0) + len(text.splitlines())
            return sent
        except Exception:
            return 0
