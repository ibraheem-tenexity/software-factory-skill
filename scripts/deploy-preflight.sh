#!/usr/bin/env bash
# Deploy preflight — HARD-FAIL before `railway up` if the tree/link is unsafe to deploy.
#
# Why this exists: `railway up` ships the CURRENT working directory. If the dir has
# uncommitted changes, a `git pull --ff-only` silently fails and HEAD stays stale, so the
# deploy ships OLD code (or a frankenstein mix of stale HEAD + another agent's uncommitted
# edits). That silent failure shipped a stale tree once (the #98 guard never went live until
# caught). This script makes a deploy from a dirty/unsynced/mis-linked tree IMPOSSIBLE.
#
# Checks (any failure aborts non-zero):
#   1. clean working tree   — no uncommitted TRACKED changes (the shared main dir must be clean)
#   2. HEAD == origin/main  — never ship a stale HEAD
#   3. correct railway link — softwarefactory / factory-console (the console project), not the
#                             run-app project (software-factory-projects) which has no console
#
# Usage:  scripts/deploy-preflight.sh   (exits 0 = safe to `railway up`)
set -euo pipefail

EXPECT_PROJECT="${SF_DEPLOY_PROJECT:-softwarefactory}"
EXPECT_SERVICE="${SF_DEPLOY_SERVICE:-factory-console}"

fail() { printf '\n❌ DEPLOY PREFLIGHT FAILED: %s\n' "$1" >&2; exit 1; }

# 1. clean working tree (untracked files don't ship via git, so ignore them; tracked mods would)
git update-index -q --refresh || true
DIRTY="$(git status --porcelain --untracked-files=no)"
[ -z "$DIRTY" ] || fail "working tree has uncommitted tracked changes — another agent may be \
editing this shared dir. Commit/stash/clean it first:
$DIRTY"

# 2. HEAD must equal origin/main (synced — never ship a stale HEAD)
git fetch origin main -q
HEAD_SHA="$(git rev-parse HEAD)"
MAIN_SHA="$(git rev-parse origin/main)"
[ "$HEAD_SHA" = "$MAIN_SHA" ] || fail "HEAD ($(git rev-parse --short HEAD)) != origin/main \
($(git rev-parse --short origin/main)). ff-pull/checkout to origin/main before deploying \
(a blocked pull is exactly how a stale tree ships)."

# 3. railway link must be the console project/service
STATUS="$(railway status 2>/dev/null || true)"
echo "$STATUS" | grep -qE "Project:[[:space:]]+${EXPECT_PROJECT}\b" || fail "railway link is NOT on \
'${EXPECT_PROJECT}'. Re-link before deploying:
  railway link -w Tenexity -p ${EXPECT_PROJECT} -e software-factory-as-skill -s ${EXPECT_SERVICE}
Current:
$STATUS"

printf '✅ deploy preflight OK — clean tree · HEAD==origin/main (%s) · linked to %s/%s\n' \
  "$(git rev-parse --short HEAD)" "$EXPECT_PROJECT" "$EXPECT_SERVICE"
