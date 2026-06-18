#!/usr/bin/env bash
# Launch a LOCAL-ONLY factory console. This script deliberately scrubs production tokens so
# development cannot accidentally talk to the live factory-console DB or Railway project.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

export SF_ENVIRONMENT=dev
export SF_DB=sqlite
export SF_RUNS_DIR="${SF_RUNS_DIR:-${ROOT_DIR}/.runs-dev}"
export PORT="${PORT:-8473}"

# Strip tokens / URLs that point at shared production infrastructure.
unset DATABASE_URL RAILWAY_TOKEN RAILWAY_API_TOKEN RAILWAY_PROJECT_ID \
      SUPABASE_ACCESS_TOKEN SUPABASE_SERVICE_ROLE_KEY SUPABASE_URL \
      OPENROUTER_API_KEY OPENAI_API_KEY ANTHROPIC_API_KEY GH_TOKEN \
      RESEND_API_KEY LANGFUSE_PUBLIC_KEY LANGFUSE_SECRET_KEY \
      SF_PROD_DB_HOST SF_ALLOW_DEV_PG 2>/dev/null || true

mkdir -p "${SF_RUNS_DIR}"

PYTHON="${ROOT_DIR}/.venv/bin/python3"
if [ ! -x "$PYTHON" ]; then
    PYTHON="python3"
fi

echo "[dev-console] SF_ENVIRONMENT=${SF_ENVIRONMENT} SF_DB=${SF_DB} SF_RUNS_DIR=${SF_RUNS_DIR} PORT=${PORT}"
cd "${ROOT_DIR}"
exec "$PYTHON" -m uvicorn console.app:app --host "${SF_BIND:-127.0.0.1}" --port "${PORT}" "$@"
