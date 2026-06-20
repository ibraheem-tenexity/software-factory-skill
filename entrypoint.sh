#!/bin/sh
# Railway may start the container as root regardless of the Dockerfile USER directive, and
# Claude Code refuses bypassed permissions as root. So if we're root, make the runs dir (which
# may be a freshly-mounted volume owned by root) writable by the unprivileged user, then drop
# to uid 1000 (node) before launching. Otherwise run as-is.
set -eu

cd /app

PROJECTS="${SF_PROJECTS_DIR:-/app/.projects}"
mkdir -p "$PROJECTS" 2>/dev/null || true

# Apply DB migrations (Alembic, the single public schema) BEFORE serving, so the schema is
# deterministic. Postgres everywhere; a no-op without DATABASE_URL. Non-fatal: the lifespan boot
# retries if this can't reach the DB.
echo "[entrypoint] applying DB migrations..."
python3 -m software_factory.migrate || echo "[entrypoint] WARN: migrate failed; continuing (boot will retry)" >&2

UVICORN="uvicorn console.app:app --host ${SF_BIND:-0.0.0.0} --port ${PORT:-8765}"
if [ "$(id -u)" = "0" ]; then
    chown -R 1000:1000 "$PROJECTS" 2>/dev/null || true
    exec setpriv --reuid=1000 --regid=1000 --init-groups $UVICORN
fi
exec $UVICORN
