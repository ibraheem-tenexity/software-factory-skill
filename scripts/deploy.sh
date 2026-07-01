#!/usr/bin/env bash
# Deploy factory-console to Railway — runs the preflight FIRST, then `railway up`.
# The preflight hard-fails on a dirty/unsynced/mis-linked tree so a stale deploy can't ship.
# Usage:  scripts/deploy.sh   (or: make deploy)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"$HERE/deploy-preflight.sh"

# Bake the deploying commit onto the service so GET /api/version reports the real running SHA
# on a MANUAL deploy — Railway's git-metadata vars (RAILWAY_GIT_COMMIT_SHA etc.) are only
# injected for deploys triggered by a connected GitHub source, never for `railway up`, and the
# container has no .git, so this is the only signal a manual deploy has. --skip-deploys sets the
# var without an extra rollout; the `railway up` below ships it. Preflight already proved HEAD==
# origin/main and the link is the console service, so this targets the right place. (TEN-151)
#
# SOF-24: this var is a PERSISTENT Railway service variable, so it outlives this one deploy — a
# later native-git-source AUTO-deploy (SOF-16) never touches it and could otherwise be shadowed
# by this now-stale value. That's made safe by version.py preferring RAILWAY_GIT_COMMIT_SHA over
# this var whenever it's present (i.e. whenever the running deploy actually came from git-source);
# this var only "counts" as a fallback for manual deploys, where RAILWAY_GIT_COMMIT_SHA is absent
# and this is correctly the freshest value anyway (set moments before `railway up`, right below).
SF_SHA="$(git rev-parse HEAD)"
echo "→ baking SF_GIT_SHA=$(git rev-parse --short HEAD) onto ${SF_DEPLOY_SERVICE:-factory-console}"
railway variables --set "SF_GIT_SHA=${SF_SHA}" --service "${SF_DEPLOY_SERVICE:-factory-console}" --skip-deploys

echo "→ railway up --service ${SF_DEPLOY_SERVICE:-factory-console} --ci"
railway up --service "${SF_DEPLOY_SERVICE:-factory-console}" --ci
