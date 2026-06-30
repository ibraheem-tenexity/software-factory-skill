#!/usr/bin/env bash
# Deploy factory-console to Railway — runs the preflight FIRST, then `railway up`.
# The preflight hard-fails on a dirty/unsynced/mis-linked tree so a stale deploy can't ship.
# Usage:  scripts/deploy.sh   (or: make deploy)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"$HERE/deploy-preflight.sh"

# Bake the deploying commit onto the service so GET /api/version reports the real running SHA
# (the container has no .git, so the endpoint can't derive it itself). --skip-deploys sets the
# var without an extra rollout; the `railway up` below ships it. Preflight already proved HEAD==
# origin/main and the link is the console service, so this targets the right place. (TEN-151)
SF_SHA="$(git rev-parse HEAD)"
echo "→ baking SF_GIT_SHA=$(git rev-parse --short HEAD) onto ${SF_DEPLOY_SERVICE:-factory-console}"
railway variables --set "SF_GIT_SHA=${SF_SHA}" --service "${SF_DEPLOY_SERVICE:-factory-console}" --skip-deploys

echo "→ railway up --service ${SF_DEPLOY_SERVICE:-factory-console} --ci"
railway up --service "${SF_DEPLOY_SERVICE:-factory-console}" --ci
