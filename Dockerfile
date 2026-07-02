# Factory RUNNER image — everything the skill needs to run a full build in the cloud.
# Software only; SECRETS are runtime env vars on the service (never baked into an image).
FROM node:20-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Puppeteer (mermaid-cli) chromium into a SHARED path reachable by the non-root runtime user.
ENV PUPPETEER_CACHE_DIR=/ms-puppeteer
# Deploy CLI + browser-test MCP + Mermaid->SVG (architecture diagrams), all global.
# NOTE: Claude Code is NOT installed via npm — its npm package is now a thin launcher
# whose postinstall must download a platform-native binary, which fails in this build
# (omit=optional / no network for the optional dep) and leaves an unrunnable text stub.
# We install it via the official native installer below instead.
RUN npm install -g @railway/cli @playwright/mcp playwright @mermaid-js/mermaid-cli

# Chromium + OS libs into a SHARED path so the non-root runtime user can use them.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN npx -y playwright install --with-deps chromium

# GitHub CLI
RUN curl -fsSL https://github.com/cli/cli/releases/download/v2.62.0/gh_2.62.0_linux_amd64.tar.gz \
        | tar -xz -C /tmp \
    && mv /tmp/gh_2.62.0_linux_amd64/bin/gh /usr/local/bin/gh \
    && rm -rf /tmp/gh_2.62.0_linux_amd64

# The node base image already ships an unprivileged `node` user (uid 1000) with home
# /home/node — reuse it (Claude Code refuses bypassed permissions as root).
ENV HOME=/home/node

# Claude Code via the official native installer (a self-contained ELF binary, not the
# broken npm launcher). It lands in $HOME/.local; symlink onto PATH so `claude` resolves
# for the orchestrator's `subprocess` calls. Verify the binary actually runs at build time.
# VERSION is pinned so a silent upstream release can't silently rename flags or add root
# restrictions without a deliberate Dockerfile bump (v2.1.195 introduced
# --dangerously-skip-permissions; root restriction addressed in _default_launch preexec_fn).
RUN curl -fsSL https://claude.ai/install.sh | VERSION=2.1.195 bash \
    && ln -sf /home/node/.local/bin/claude /usr/local/bin/claude \
    && claude --version

# OpenCode (the second runtime, SPEC §9) — PINNED to the version the stream-parser fixture
# was captured against (tests/fixtures/opencode-run.jsonl); its event schema is not a stable
# wire format, so an unpinned upgrade could silently break cost parsing. Lands in
# $HOME/.opencode; symlink onto PATH. The container has no opencode auth.json, so
# OPENROUTER_API_KEY (runtime env) is load-bearing for this runtime.
RUN curl -fsSL https://opencode.ai/install | VERSION=1.16.0 bash \
    && ln -sf /home/node/.opencode/bin/opencode /usr/local/bin/opencode \
    && opencode --version

# opencode-swarm (SF_SWARM=1 stage-3 build mode, SPEC §9) — the pinned release ships a
# compiled binary + bundled plugin, so no bun in the image. The runner finds the plugin
# next to the executable, but containers move things: OPENCODE_SWARM_PLUGIN is explicit.
RUN mkdir -p /opt/swarm \
    && curl -fsSL https://github.com/ibraheem-111/opencode-swarm/releases/download/v0.2.2/opencode-swarm-0.2.2-linux-x64.tar.gz \
       | tar -xz -C /opt/swarm \
    && /opt/swarm/swarm --version \
    && test -f /opt/swarm/swarm-plugin.js
ENV SF_SWARM_BIN=/opt/swarm/swarm OPENCODE_SWARM_PLUGIN=/opt/swarm/swarm-plugin.js

WORKDIR /app

# Python deps FROM pyproject.toml — the single source of truth (SOF-48). A separate hand-
# maintained pip3 list here used to drift from pyproject.toml (a dependency could be added to one
# and not the other) and silently crash-loop prod on the next deploy (#237: pgvector). Only
# pyproject.toml + src/ copied at this point (not the full repo below) so an unrelated console/
# or docs/ change doesn't invalidate this layer.
COPY pyproject.toml /app/pyproject.toml
COPY src /app/src
# [postgres] extra pulls psycopg[binary] (prebuilt libpq, no system libpq-dev in this image —
# apt-get above never installs one).
RUN pip3 install --break-system-packages "/app[postgres]"

COPY . /app

# Import-smoke check: FAILS THE BUILD (not a live deploy) if any software_factory/console module,
# or a known lazily-imported package (see scripts/verify_deps.py), doesn't actually resolve —
# catches the case pip installing successfully but the code still not importing (e.g. an ABI
# mismatch), which a dependency-list diff alone would miss. `console` lives at repo root, not
# under src/, so it needs /app on the path too (matching how the entrypoint's `cd /app` +
# uvicorn resolve it at runtime).
RUN PYTHONPATH=/app/src:/app python3 /app/scripts/verify_deps.py

# Build the React console SPA (served when SF_CONSOLE=react). Node is already in the base image,
# so this is build-time only — the runtime is still uvicorn. Non-fatal: legacy index.html serves
# if the build is skipped/fails.
RUN cd /app/console/web && npm ci --no-audit --no-fund && npm run build || \
    echo "[build] React console build skipped/failed — legacy index.html will serve"

RUN mkdir -p /home/node/.claude/skills /ms-puppeteer \
    && ln -sfn /app /home/node/.claude/skills/software-factory \
    && cp /app/claude-settings.json /home/node/.claude/settings.json \
    && chmod +x /app/entrypoint.sh \
    && chown -R node:node /app /home/node /ms-playwright /ms-puppeteer

# Entrypoint drops to uid 1000 (node) even if the platform starts us as root.
# Required at runtime (set on the service): ANTHROPIC_API_KEY, OPENAI_API_KEY, GH_TOKEN,
# RAILWAY_TOKEN, SUPABASE_ACCESS_TOKEN, OPENROUTER_API_KEY (opencode runtime + concierge),
# and optionally SF_RUNTIME / SF_CHAT_MODEL (runtime defaults; the UI picker overrides per-run).
# PYTHONPATH so `import software_factory` works for any python invocation (the orchestrator
# shells fresh python processes, not just the server).
ENV PYTHONUNBUFFERED=1 SF_BIND=0.0.0.0 PYTHONPATH=/app/src
CMD ["/app/entrypoint.sh"]
