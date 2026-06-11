"""Operator email notifications (Resend) — env-gated, fire-and-forget, never raises.

The wiring point is the server's _narrate dedup: an email fires at most once per
(run, event), exactly like the chat-panel message it mirrors.
"""
from software_factory import notify


def test_no_creds_is_a_silent_noop(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("SF_NOTIFY_EMAIL", raising=False)
    calls = []
    monkeypatch.setattr(notify, "_post", lambda *a: calls.append(a) or True)
    assert notify.send("s", "b") is False
    assert calls == []


def test_send_posts_to_resend_with_auth(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test_123")
    monkeypatch.setenv("SF_NOTIFY_EMAIL", "op@example.com")
    seen = {}

    def fake_post(url, payload, headers):
        seen.update(url=url, payload=payload, headers=headers)
        return True

    monkeypatch.setattr(notify, "_post", fake_post)
    assert notify.send("run done", "demo: https://x") is True
    assert seen["url"] == "https://api.resend.com/emails"
    assert seen["headers"]["Authorization"] == "Bearer re_test_123"
    assert seen["payload"]["to"] == ["op@example.com"]
    assert "run done" in seen["payload"]["subject"]
    assert "demo: https://x" in seen["payload"]["text"]


def test_send_never_raises_on_network_failure(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_x")
    monkeypatch.setenv("SF_NOTIFY_EMAIL", "op@example.com")

    def boom(*a):
        raise RuntimeError("network down")

    monkeypatch.setattr(notify, "_post", boom)
    assert notify.send("s", "b") is False


def test_should_email_covers_exactly_the_four_operator_events():
    # Operator picked: run done, waiting-on-input, budget-stop, stage crash.
    assert notify.should_email("done")
    assert notify.should_email("depswait")
    assert notify.should_email("budget-30")
    assert notify.should_email("resume-1")
    # Routine narration stays chat-only.
    for quiet in ("repo", "s1", "deps", "deployed"):
        assert not notify.should_email(quiet), quiet
