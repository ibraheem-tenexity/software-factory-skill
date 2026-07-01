#!/usr/bin/env bash
# SOF-16: connect factory-console's Railway source to this GitHub repo so push-to-main
# triggers an automatic build+deploy — the fleet stops depending on an operator's manual
# "deploy go." One-time, idempotent (re-running just re-confirms the same connection).
#
# This is a LIVE change to the console's deploy source. Per SOF-16 it is deliberately NOT
# run automatically by any agent — an operator with softwarefactory-project Railway access
# runs it by hand, once.
#
# Usage:  scripts/enable-auto-deploy.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

EXPECT_PROJECT="${SF_DEPLOY_PROJECT:-softwarefactory}"
EXPECT_ENV="${SF_DEPLOY_ENV:-software-factory-as-skill}"
EXPECT_SERVICE="${SF_DEPLOY_SERVICE:-factory-console}"
BRANCH="main"

fail() { printf '\n❌ %s\n' "$1" >&2; exit 1; }

# Derive owner/repo from the same remote deploy-preflight.sh trusts, so this can never
# target the wrong GitHub repo.
REMOTE_URL="$(git -C "$HERE/.." remote get-url origin)"
REPO="$(printf '%s' "$REMOTE_URL" | sed -E 's#^(https://github\.com/|git@github\.com:)##; s#\.git$##')"
[ "$REPO" != "$REMOTE_URL" ] || fail "could not parse owner/repo from origin remote: $REMOTE_URL"

STATUS="$(railway status 2>/dev/null || true)"
echo "$STATUS" | grep -qE "Project:[[:space:]]+${EXPECT_PROJECT}\b" || fail "railway link is NOT on \
'${EXPECT_PROJECT}'. Link first:
  railway link -w Tenexity -p ${EXPECT_PROJECT} -e ${EXPECT_ENV} -s ${EXPECT_SERVICE}
Current:
$STATUS"

echo "→ connecting ${EXPECT_PROJECT}/${EXPECT_SERVICE} (${EXPECT_ENV}) to ${REPO}@${BRANCH}"
railway service source connect --repo "$REPO" --branch "$BRANCH" \
  --project "$EXPECT_PROJECT" --environment "$EXPECT_ENV" --service "$EXPECT_SERVICE"

echo "✅ ${EXPECT_SERVICE} now auto-deploys on push to ${BRANCH}. Verify: push a commit, then \
check GET /api/version reports the new SHA."
