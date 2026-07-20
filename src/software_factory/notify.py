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
import logging
import os
import urllib.request

_EMAIL_KEYS = ("done", "depswait", "crashed-final")
_EMAIL_PREFIXES = ("budget-", "resume-")

# Env-driven so an invite sent from staging links the invitee to staging, not prod; the default
# covers prod (staging sets SF_CONSOLE_URL).
CONSOLE_URL = os.environ.get("SF_CONSOLE_URL", "https://softwarefactory-console.up.railway.app")


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


def send_invite(to: str, *, org_name: str, inviter: str, granted: bool = False) -> bool:
    """SOF-197: the ONE invite-email builder for every invite path (org members, admin access) —
    SOF-140 and SOF-195 each hand-rolled their own copy of this; consolidated here so wording,
    the sign-in URL, and the honest-failure behavior can't drift between the two paths again.
    Fire-and-forget via send_to (never raises); the caller decides how to report a False.

    granted=False (the default) — org path, and the admin path's invited-status users: "invited
    to {org_name}... sign in with this email, no link needed." No password involved.
    granted=True — the admin path's password-method users only: "granted access to {org_name}...
    sign in at {url}." Still NEVER includes the password itself — that's shared out-of-band by
    the admin; this email is a notification, not a secret carrier."""
    verb = "granted access to" if granted else "invited to"
    subject = f"You've been {verb} {org_name} on Software Factory"
    if granted:
        body = (f"{inviter or 'An admin'} granted you access to {org_name} on Software Factory. "
                f"Sign in with this email address ({to}) at:\n{CONSOLE_URL}\n")
    else:
        body = (f"{inviter or 'A teammate'} invited you to join {org_name} on Software Factory.\n\n"
                f"Sign in with this email address ({to}) to get started — no invite link needed:\n"
                f"{CONSOLE_URL}\n")
    sent = send_to(to, subject, body)
    if not sent:
        logging.getLogger(__name__).warning(
            "invite email to %s not sent (Resend disabled or rejected — check RESEND_API_KEY / "
            "SF_NOTIFY_FROM verified sender); invite/access still granted", to)
    return sent
