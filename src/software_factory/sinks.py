"""Event sinks for agent telemetry.

`SupabaseSink` pushes each lifecycle event as a row into a Supabase table; a small web view
subscribes to that table's realtime feed to render the live dashboard. The HTTP poster is
injectable for offline testing, and `emit` swallows transport errors on purpose — a
dashboard outage must never crash a factory run.
"""
from __future__ import annotations

import json as _json
import os
import urllib.request
from typing import Callable, Optional

from .agents import NullSink


def _real_post(url: str, headers: dict, json: dict) -> int:
    data = _json.dumps(json).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status


class SupabaseSink:
    def __init__(
        self,
        url: str,
        service_key: str,
        table: str = "agent_events",
        post: Callable[[str, dict, dict], int] = _real_post,
    ):
        self._endpoint = f"{url.rstrip('/')}/rest/v1/{table}"
        self._key = service_key
        self._post = post

    def emit(self, event: dict) -> None:
        headers = {
            "apikey": self._key,
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }
        try:
            self._post(self._endpoint, headers, event)
        except Exception:
            # Best-effort visibility: never let the dashboard take down the run.
            pass


def sink_from_env(env: Optional[dict] = None):
    """Build a SupabaseSink if creds are present, else NullSink. Visibility is opt-in."""
    env = os.environ if env is None else env
    url = env.get("SUPABASE_URL")
    key = env.get("SUPABASE_SERVICE_KEY")
    if url and key:
        table = env.get("SF_DASHBOARD_TABLE", "agent_events")
        return SupabaseSink(url, key, table=table)
    return NullSink()
