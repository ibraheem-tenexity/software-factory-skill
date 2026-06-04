#!/bin/sh
# Railway may start the container as root regardless of the Dockerfile USER directive, and
# Claude Code refuses bypassed permissions as root. So if we're root, drop to the unprivileged
# `factory` user (uid 1000) before launching; otherwise run as-is.
cd /app
if [ "$(id -u)" = "0" ]; then
    exec setpriv --reuid=1000 --regid=1000 --init-groups python3 console/server.py
fi
exec python3 console/server.py
