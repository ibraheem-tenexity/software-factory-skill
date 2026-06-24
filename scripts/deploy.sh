#!/usr/bin/env bash
# Deploy factory-console to Railway — runs the preflight FIRST, then `railway up`.
# The preflight hard-fails on a dirty/unsynced/mis-linked tree so a stale deploy can't ship.
# Usage:  scripts/deploy.sh   (or: make deploy)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"$HERE/deploy-preflight.sh"

echo "→ railway up --service ${SF_DEPLOY_SERVICE:-factory-console} --ci"
railway up --service "${SF_DEPLOY_SERVICE:-factory-console}" --ci
