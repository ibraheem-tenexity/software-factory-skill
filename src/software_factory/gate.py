"""The happy-flow gate: the only definition of done.

A run is done when the deployed app's primary user journey passes end-to-end in a real
browser. This module turns a Playwright run's structured result into a pass/fail verdict
and a bug list for the fix-loop.

Done must be earned with positive evidence: a missing, empty, or step-less result is FAIL.
"""
from __future__ import annotations

from typing import Optional


def happy_flow_passed(result: Optional[dict]) -> bool:
    if not result:
        return False
    steps = result.get("steps")
    if not steps:  # no steps ran -> nothing verified -> not done
        return False
    return all(step.get("ok") is True for step in steps)


def bugs_from(result: Optional[dict]) -> list[dict]:
    """Failing steps, shaped for dispatch to fix agents."""
    if not result:
        return []
    bugs = []
    for step in result.get("steps", []):
        if step.get("ok") is not True:
            bugs.append({"step": step.get("name", "?"), "error": step.get("error", "")})
    return bugs


_SIGNIN_KEYWORDS = ("sign in", "signin", "log in", "login", "sign-in", "credential",
                    "authenticate", "auth", "sign up", "signup", "register")


def has_signin_step(result: Optional[dict]) -> bool:
    """True when the happy-flow result includes at least one step whose name suggests a sign-in action."""
    if not result:
        return False
    for step in result.get("steps", []):
        name = (step.get("name") or "").lower()
        if any(kw in name for kw in _SIGNIN_KEYWORDS):
            return True
    return False
