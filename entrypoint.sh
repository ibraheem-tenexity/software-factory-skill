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
# deterministic. Postgres everywhere; a no-op without DATABASE_URL (migrate exits 0 in that case).
# FATAL on failure (SOF-66): refuse to boot rather than serve new code against a stale/half-migrated
# schema. A non-zero exit here makes Railway keep the PREVIOUS deployment live — the correct
# outcome for version skew (the SOF-64 incident, where a swallowed migrate failure let a deploy go
# live on the old schema). migrate runs once per container start; there is no retry loop.
echo "[entrypoint] applying DB migrations..."
if ! python3 -m software_factory.migrate; then
    echo "[entrypoint] FATAL: DB migrate failed — refusing to boot on a stale schema (SOF-66)." >&2
    exit 1
fi

UVICORN="uvicorn console.app:app --host ${SF_BIND:-0.0.0.0} --port ${PORT:-8765}"
if [ "$(id -u)" = "0" ]; then
    chown -R 1000:1000 "$PROJECTS" 2>/dev/null || true
    exec setpriv --reuid=1000 --regid=1000 --init-groups $UVICORN
fi
exec $UVICORN
