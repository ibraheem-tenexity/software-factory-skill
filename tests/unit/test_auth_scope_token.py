"""Pure unit tests for auth.sign_scope_token/verify_scope_token (SOF-41) — no DB. This is the
enforcement point for the memory MCP's critical security AC ("agent scoped to project A cannot
read project B's memory"), so it gets tested directly and adversarially, not just happy-path."""
import time

import pytest

from software_factory import auth


def test_round_trips_the_project_id():
    token = auth.sign_scope_token("project-abc")
    assert auth.verify_scope_token(token) == "project-abc"


def test_tampered_payload_is_rejected():
    token = auth.sign_scope_token("project-abc")
    raw, sig = token.rsplit(".", 1)
    # Flip the pid without re-signing — simulates an attacker editing the token to read another
    # project's memory.
    import base64
    import json
    payload = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    payload["pid"] = "project-victim"
    tampered_raw = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()).rstrip(b"=").decode()
    tampered = f"{tampered_raw}.{sig}"
    assert auth.verify_scope_token(tampered) is None


def test_expired_token_is_rejected():
    token = auth.sign_scope_token("project-abc", ttl_seconds=-1)
    assert auth.verify_scope_token(token) is None


def test_garbage_token_is_rejected():
    assert auth.verify_scope_token("not-a-real-token") is None
    assert auth.verify_scope_token("") is None
    assert auth.verify_scope_token(None) is None


def test_a_user_session_cookie_is_never_accepted_as_a_scope_token():
    """Cross-token-type confusion must fail closed — a session cookie has no `pid`/`purpose`
    claim, so even with a valid signature it must not resolve to a project scope."""
    session_cookie = auth.sign_session("user-123", 1)
    assert auth.verify_scope_token(session_cookie) is None


def test_a_scope_token_used_as_a_session_cookie_never_resolves_a_uid():
    """verify_session has no `purpose` check (out of scope to add here — it's a shared, heavily-
    used login path), so a scope token's valid signature does pass verify_session's own check.
    What actually protects the system: the payload it returns has no `uid`/`tv` claim, so
    console/deps.py's `state.users.get_by_id(payload.get("uid"))` can never resolve a real user
    from it — a scope token grants zero session access even though verify_session doesn't reject
    it outright."""
    scope_token = auth.sign_scope_token("project-abc")
    payload = auth.verify_session(scope_token)
    assert payload is None or "uid" not in payload


def test_different_projects_get_non_interchangeable_tokens():
    a = auth.sign_scope_token("project-a")
    b = auth.sign_scope_token("project-b")
    assert auth.verify_scope_token(a) == "project-a"
    assert auth.verify_scope_token(b) == "project-b"
    assert a != b
