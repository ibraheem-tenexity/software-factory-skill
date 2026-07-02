#!/usr/bin/env bash
# Provision the shared local test Postgres (SOF-53).
#
# Why this exists: conftest.py points every worktree's DATABASE_URL at a Postgres server on
# localhost:5434 and, at collection, runs `CREATE EXTENSION IF NOT EXISTS vector` in each
# throwaway per-process DB (models.py has pgvector Vector columns — SOF-26). So the server MUST
# be a pgvector-capable image; a plain `postgres` image makes `CREATE EXTENSION vector` fail and
# breaks pytest collection FLEET-WIDE (every worktree), not just the memory tests. That regression
# is exactly SOF-53 — this script pins the correct image so it can't recur silently.
#
# Idempotent: re-run any time. Recreates the container ONLY if it's missing or on the wrong image
# (won't blow away a healthy pgvector container mid-run). Data is disposable by design — conftest
# mints its own throwaway databases per process, nothing persistent lives here.
set -euo pipefail

NAME="sf-test-pg"
IMAGE="pgvector/pgvector:pg16"
PORT="5434"

current_image="$(docker inspect --format '{{.Config.Image}}' "$NAME" 2>/dev/null || true)"

if [ "$current_image" = "$IMAGE" ] && [ "$(docker inspect --format '{{.State.Running}}' "$NAME" 2>/dev/null || echo false)" = "true" ]; then
    echo "[setup-test-db] $NAME already running on $IMAGE — leaving it alone."
else
    if [ -n "$current_image" ]; then
        echo "[setup-test-db] $NAME exists on '$current_image' (want $IMAGE) — recreating."
        docker rm -f "$NAME" >/dev/null
    fi
    echo "[setup-test-db] starting $NAME ($IMAGE) on localhost:$PORT ..."
    docker run -d --name "$NAME" \
        -e POSTGRES_PASSWORD=postgres \
        -p "$PORT:5432" \
        "$IMAGE" >/dev/null
    for _ in $(seq 1 30); do
        docker exec "$NAME" pg_isready -U postgres >/dev/null 2>&1 && break
        sleep 1
    done
fi

# Enable the extension in template1 so every conftest-created database inherits it even if a
# future conftest ever stops running CREATE EXTENSION itself (belt-and-braces; harmless if already
# present). This is what makes the image's pgvector actually usable per-DB.
docker exec "$NAME" psql -U postgres -d template1 -c "CREATE EXTENSION IF NOT EXISTS vector;" >/dev/null
echo "[setup-test-db] pgvector ready. conftest.py will connect at postgresql://postgres:postgres@localhost:$PORT/postgres"
