#!/bin/sh
# Railway may start the container as root regardless of the Dockerfile USER directive, and
# Claude Code refuses bypassed permissions as root. So if we're root, make the runs dir (which
# may be a freshly-mounted volume owned by root) writable by the unprivileged user, then drop
# to uid 1000 (node) before launching. Otherwise run as-is.
cd /app
RUNS="${SF_RUNS_DIR:-/app/.runs}"
mkdir -p "$RUNS" 2>/dev/null || true
if [ "$(id -u)" = "0" ]; then
    chown -R 1000:1000 "$RUNS" 2>/dev/null || true
    exec setpriv --reuid=1000 --regid=1000 --init-groups python3 console/server.py
fi
exec python3 console/server.py
