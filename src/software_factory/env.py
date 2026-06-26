"""Environment-tier guardrails.

The factory console and the software it builds are intentionally run in the same process
image, so the only real boundary between them is the environment variables we hand to a
stage process. This module centralises the tier concept (dev/test/staging/prod) and the
rules for

* which env vars a stage agent is allowed to inherit, and
* which Railway project IDs may be targeted by run apps.
"""
from __future__ import annotations

import os

ALLOWED_ENVIRONMENTS = {"dev", "test", "staging", "prod"}

# Credentialed deploy targets are not allowed to aim at the console project.
# Empty value means "no allowlist configured"; in prod the operator must set this.
_RUNAPP_RAILWAY_PROJECT_IDS: set[str] = set(
    (os.environ.get("SF_RUNAPP_RAILWAY_PROJECT_IDS") or "").split(",")
    if os.environ.get("SF_RUNAPP_RAILWAY_PROJECT_IDS")
    else []
)

_CONSOLE_RAILWAY_PROJECT_IDS: set[str] = set(
    (os.environ.get("SF_CONSOLE_RAILWAY_PROJECT_IDS") or "softwarefactory").split(",")
)

# The Railway environment ID where run-app DBs are provisioned (production env of
# software-factory-projects). Used for GraphQL variables queries which require an environmentId.
# Example: SF_RUNAPP_RAILWAY_ENVIRONMENT_IDS=3c8117be-4cb0-41b0-a4ff-0bc9eb8e90eb
_RUNAPP_RAILWAY_ENVIRONMENT_IDS: set[str] = set(
    (os.environ.get("SF_RUNAPP_RAILWAY_ENVIRONMENT_IDS") or "").split(",")
    if os.environ.get("SF_RUNAPP_RAILWAY_ENVIRONMENT_IDS")
    else []
)

# Variables a stage child must be able to see even when we scrub the console's full
# environment. Keep this list tiny and well-known.
_STAGE_ESSENTIAL = {
    # Shell / user basics
    "PATH", "HOME", "USER", "LOGNAME", "SHELL",
    "LANG", "LC_ALL", "LC_CTYPE", "TERM",
    # Working directory / Python
    "PWD", "PYTHONPATH",
    # Temp
    "TMPDIR", "TEMP", "TMP",
    # OpenCode isolation helpers (overridden by launch code, but harmless to carry)
    "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_RUNTIME_DIR",
    # Factory swarm tooling only
    "SF_SWARM_BIN",
    "OPENCODE_SWARM_PLUGIN",
    # Exa web-search MCP key — the workspace exa server (wired into every stage) resolves
    # ${EXA_API_KEY}/{env:EXA_API_KEY} from the stage env, so this must survive the scrub or
    # web search 401s. It's the factory's key (set on factory-console), not an app secret; the
    # built app never sees it (it's not forwarded to the app's Railway service vars).
    "EXA_API_KEY",
}


def sf_environment() -> str:
    """Return dev/test/staging/prod.

    Explicit SF_ENVIRONMENT wins. Otherwise prod is inferred only from Railway's own env so
    that misconfigured local shells default to dev.
    """
    explicit = (os.environ.get("SF_ENVIRONMENT") or "").strip().lower()
    if explicit in ALLOWED_ENVIRONMENTS:
        return explicit
    if os.environ.get("RAILWAY_ENVIRONMENT") == "production":
        return "prod"
    return "dev"


def is_prod() -> bool:
    return sf_environment() == "prod"


def stage_env_baseline(provided: dict | None = None) -> dict:
    """Return a scrubbed environment for a stage subprocess.

    Stops workspace agents from inheriting the console's SF_DB, DATABASE_URL,
    RAILWAY_TOKEN, ANTHROPIC_API_KEY, etc. unless the run explicitly declared them as
    credentials (which are passed in ``provided``).

    The factory state-DB URL is forwarded under the dedicated ``SF_STATE_DB_URL`` name so
    ``python3 -m software_factory.db`` (called inside the stage to record run-state) can
    connect without ``DATABASE_URL`` appearing in the stage env.  Using a non-standard name
    prevents deployment tools from accidentally forwarding the factory DB URL to the customer
    app's Railway service variables.
    """
    base = {k: v for k, v in os.environ.items() if k in _STAGE_ESSENTIAL}
    # Forward the factory state-DB URL under a dedicated name (not DATABASE_URL).
    state_db = os.environ.get("SF_STATE_DB_URL") or os.environ.get("DATABASE_URL")
    if state_db:
        base["SF_STATE_DB_URL"] = state_db
    if provided:
        base.update(provided)
    return base


def runapp_railway_project_id() -> str | None:
    """The single Railway project ID for run-app provision/deploy/teardown.

    Derived from SF_RUNAPP_RAILWAY_PROJECT_IDS (must be exactly one entry configured).
    Returns None when the env is absent or has multiple entries.

    Use this instead of os.environ["RAILWAY_PROJECT_ID"]: Railway forcibly injects
    RAILWAY_PROJECT_ID as the CONSOLE's own project into every service it runs, so that
    var cannot be overridden at the dashboard level and must never be used as the provision
    target.
    """
    if len(_RUNAPP_RAILWAY_PROJECT_IDS) == 1:
        return next(iter(_RUNAPP_RAILWAY_PROJECT_IDS))
    return None


def runapp_railway_environment_id() -> str | None:
    """The Railway environment ID where run-app DBs are provisioned.

    Derived from SF_RUNAPP_RAILWAY_ENVIRONMENT_IDS (must be exactly one entry configured).
    Returns None when unset or when multiple entries are configured.

    Required for GraphQL variables queries (which need an environmentId) but not for
    the CLI fallback path, so absence is safe — provision falls back to the CLI.
    """
    if len(_RUNAPP_RAILWAY_ENVIRONMENT_IDS) == 1:
        return next(iter(_RUNAPP_RAILWAY_ENVIRONMENT_IDS))
    return None


def railway_project_allowed(project_id: str | None) -> bool:
    """True when a run app may target the given Railway project.

    No allowlist configured (empty SF_RUNAPP_RAILWAY_PROJECT_IDS) means "not enforced".
    The console project is always rejected.
    """
    if not project_id:
        return True
    if project_id in _CONSOLE_RAILWAY_PROJECT_IDS:
        return False
    if not _RUNAPP_RAILWAY_PROJECT_IDS:
        return True
    return project_id in _RUNAPP_RAILWAY_PROJECT_IDS
