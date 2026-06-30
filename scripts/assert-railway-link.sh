#!/usr/bin/env bash
# Re-assert the Railway CLI is linked to the EXPECTED console target (softwarefactory /
# software-factory-as-skill / factory-console — override via SF_DEPLOY_PROJECT / _ENVIRONMENT /
# _SERVICE, or pin exact IDs via SF_DEPLOY_PROJECT_ID / _ENVIRONMENT_ID). FAILS LOUDLY (non-zero)
# on drift so a verify can't silently run against the wrong project/env/service.
# Run this BEFORE verifying a deploy.  TEN-151 / docs/KNOWN_ISSUES.md #87.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE/.."
exec python3 -m software_factory.railway_link
