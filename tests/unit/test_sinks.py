"""SupabaseSink pushes agent events to a Supabase table so the external dashboard can
render the run live. The HTTP poster is injected, so this is tested without a network or
real creds. Building the sink from env is opt-in and returns NullSink when unconfigured —
visibility must never crash a run just because the dashboard isn't set up.
"""
from software_factory.sinks import SupabaseSink, sink_from_env
from software_factory.agents import NullSink


class FakePoster:
    def __init__(self, status=201):
        self.calls = []
        self._status = status

    def __call__(self, url, headers, json):
        self.calls.append({"url": url, "headers": headers, "json": json})
        return self._status


def test_emit_posts_event_to_the_table_endpoint():
    poster = FakePoster()
    sink = SupabaseSink("https://proj.supabase.co", "service-key", table="agent_events", post=poster)
    sink.emit({"event": "spawn", "agent_id": "a1", "run_id": "run"})
    assert len(poster.calls) == 1
    call = poster.calls[0]
    assert call["url"] == "https://proj.supabase.co/rest/v1/agent_events"
    assert call["json"]["agent_id"] == "a1"


def test_emit_sends_auth_headers():
    poster = FakePoster()
    SupabaseSink("https://proj.supabase.co", "service-key", post=poster).emit({"event": "spawn"})
    h = poster.calls[0]["headers"]
    assert h["apikey"] == "service-key"
    assert h["Authorization"] == "Bearer service-key"


def test_emit_never_raises_even_if_post_fails():
    # A dashboard outage must not take down a factory run.
    def boom(url, headers, json):
        raise ConnectionError("dashboard down")

    SupabaseSink("https://proj.supabase.co", "k", post=boom).emit({"event": "spawn"})  # no raise


def test_sink_from_env_returns_nullsink_when_unconfigured():
    assert isinstance(sink_from_env(env={}), NullSink)


def test_sink_from_env_builds_supabase_sink_when_configured():
    env = {"SUPABASE_URL": "https://proj.supabase.co", "SUPABASE_SERVICE_KEY": "k"}
    assert isinstance(sink_from_env(env=env), SupabaseSink)
