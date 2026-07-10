"""Operator email notifications (Resend) — env-gated, fire-and-forget.

Events (operator-picked): run done, waiting-on-input at the deps gate, budget-stop,
stage crash/auto-resume. Wired into the server's _narrate dedup point, so an email
fires at most once per (run, event) — the same dedup discipline as the chat panel.

Env: RESEND_API_KEY + SF_NOTIFY_EMAIL enable it (either absent -> silent no-op).
SF_NOTIFY_FROM overrides the sender; the default is Resend's sandbox sender, which
delivers only to the Resend account owner — fine for a single operator.
A notification failure must never break the poller: send() never raises.
"""
from __future__ import annotations

import json
import os
import urllib.request

_EMAIL_KEYS = ("done", "depswait", "crashed-final")
_EMAIL_PREFIXES = ("budget-", "resume-")


def should_email(key: str) -> bool:
    return key in _EMAIL_KEYS or key.startswith(_EMAIL_PREFIXES)


def _post(url: str, payload: dict, headers: dict) -> bool:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **headers}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return 200 <= r.status < 300


def send(subject: str, body: str) -> bool:
    key = os.environ.get("RESEND_API_KEY")
    to = os.environ.get("SF_NOTIFY_EMAIL")
    if not key or not to:
        return False
    try:
        return _post(
            "https://api.resend.com/emails",
            {"from": os.environ.get("SF_NOTIFY_FROM", "Factory <onboarding@resend.dev>"),
             "to": [to], "subject": subject, "text": body},
            {"Authorization": f"Bearer {key}"})
    except Exception:
        return False


def send_to(to: str, subject: str, body: str) -> bool:
    """Send one email to an ARBITRARY recipient (e.g. a team-invite notice), not the fixed
    operator address `send()` uses. Same Resend transport; gated only on RESEND_API_KEY (the
    recipient is explicit). Returns True iff Resend accepted it; never raises — an email failure
    must never break the caller (SOF-140: an invite must still succeed if the email can't send).

    NOTE: with the default sandbox sender (`onboarding@resend.dev`), Resend delivers only to the
    account owner; delivering to arbitrary invitees needs SF_NOTIFY_FROM set to a verified-domain
    sender. That's an env/config concern, not this function's."""
    key = os.environ.get("RESEND_API_KEY")
    to = (to or "").strip()
    if not key or not to:
        return False
    try:
        return _post(
            "https://api.resend.com/emails",
            {"from": os.environ.get("SF_NOTIFY_FROM", "Factory <onboarding@resend.dev>"),
             "to": [to], "subject": subject, "text": body},
            {"Authorization": f"Bearer {key}"})
    except Exception:
        return False
