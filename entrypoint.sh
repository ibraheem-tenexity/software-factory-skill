#!/bin/sh
# Railway may start the container as root regardless of the Dockerfile USER directive, and
# Claude Code refuses bypassed permissions as root. So if we're root, make the runs dir (which
# may be a freshly-mounted volume owned by root) writable by the unprivileged user, then drop
# to uid 1000 (node) before launching. Otherwise run as-is.
set -eu

cd /app

# Environment safety guard.
SF_DB_LOWER="$(printf '%s' "${SF_DB:-}" | tr '[:upper:]' '[:lower:]')"
SF_ENV_LOWER="$(printf '%s' "${SF_ENVIRONMENT:-}" | tr '[:upper:]' '[:lower:]')"
if [ "$SF_DB_LOWER" = "postgres" ] && [ "$SF_ENV_LOWER" != "prod" ] && [ "${SF_ALLOW_DEV_PG:-}" != "1" ]; then
    echo "[entrypoint] ERROR: SF_DB=postgres is only allowed when SF_ENVIRONMENT=prod. Set SF_ENVIRONMENT=prod on Railway." >&2
    exit 1
fi

RUNS="${SF_RUNS_DIR:-/app/.runs}"
mkdir -p "$RUNS" 2>/dev/null || true

# Apply DB migrations (Alembic global tables + per-run schema fan-out) BEFORE serving, so the
# schema is deterministic. Postgres-only — a no-op on sqlite. Non-fatal: the console's own
# CREATE-IF-NOT-EXISTS + the lifespan boot are a backstop if this can't reach the DB.
if [ "$SF_DB_LOWER" = "postgres" ]; then
    echo "[entrypoint] applying DB migrations..."
    python3 -m software_factory.migrate || echo "[entrypoint] WARN: migrate failed; continuing (boot will retry)" >&2
fi

UVICORN="uvicorn console.app:app --host ${SF_BIND:-0.0.0.0} --port ${PORT:-8765}"
if [ "$(id -u)" = "0" ]; then
    chown -R 1000:1000 "$RUNS" 2>/dev/null || true
    exec setpriv --reuid=1000 --regid=1000 --init-groups $UVICORN
fi
exec $UVICORN
