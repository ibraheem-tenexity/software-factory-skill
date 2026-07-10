"""Thin Linear GraphQL client for SOF-93's run-autopsy filing. LINEAR_API_KEY-gated: an absent
or invalid key (or a failed call) degrades HONESTLY — every function returns None/False rather
than raising, so a config gap never crashes the caller. run_autopsy.autopsy_and_file still records
the signature/occurrence locally when filing degrades (per the operator's requirement on SOF-93) —
nothing is lost, it just isn't filed until a key exists.

Key provisioning is explicitly out of this ticket's scope (operator-owned, set directly in
Railway — never transiting the peer bus, same rule as a DB password).
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request

logger = logging.getLogger(__name__)

_API_URL = "https://api.linear.app/graphql"
_TEAM_ID_ENV = "SF_LINEAR_TEAM_ID"   # the SOF team's id; required alongside the key to file


def _graphql(query: str, variables: dict, api_key: str) -> dict:
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        _API_URL, data=body, method="POST",
        headers={"Content-Type": "application/json", "Authorization": api_key})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def is_configured() -> bool:
    return bool(os.environ.get("LINEAR_API_KEY")) and bool(os.environ.get(_TEAM_ID_ENV))


def create_issue(title: str, body: str, priority: int = 3) -> dict | None:
    """Files a new issue. Returns {"id", "identifier"} on success, None if not configured or the
    API call fails. Never raises — the caller treats None as "not filed yet", not an error."""
    api_key = os.environ.get("LINEAR_API_KEY")
    team_id = os.environ.get(_TEAM_ID_ENV)
    if not api_key or not team_id:
        logger.warning("[run-autopsy] not filed: LINEAR_API_KEY/%s unset", _TEAM_ID_ENV)
        return None
    query = """
    mutation($input: IssueCreateInput!) {
      issueCreate(input: $input) { success issue { id identifier } }
    }"""
    variables = {"input": {"teamId": team_id, "title": title, "description": body, "priority": priority}}
    try:
        result = _graphql(query, variables, api_key)
        issue = (result.get("data") or {}).get("issueCreate", {}).get("issue")
        if not issue:
            logger.warning("[run-autopsy] issueCreate returned no issue: %s", result)
            return None
        return issue
    except Exception:
        logger.warning("[run-autopsy] issueCreate failed", exc_info=True)
        return None


def create_comment(issue_id: str, body: str) -> bool:
    api_key = os.environ.get("LINEAR_API_KEY")
    if not api_key:
        logger.warning("[run-autopsy] not commented: LINEAR_API_KEY unset")
        return False
    query = """
    mutation($input: CommentCreateInput!) {
      commentCreate(input: $input) { success }
    }"""
    variables = {"input": {"issueId": issue_id, "body": body}}
    try:
        result = _graphql(query, variables, api_key)
        return bool((result.get("data") or {}).get("commentCreate", {}).get("success"))
    except Exception:
        logger.warning("[run-autopsy] commentCreate failed", exc_info=True)
        return False
