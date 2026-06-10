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
RUN npm install -g @railway/cli @playwright/mcp playwright @mermaid-js/mermaid-cli @supabase/mcp-server-supabase
RUN pip3 install --break-system-packages openai-agents 'markitdown[pdf,docx]' pypandoc_binary

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
RUN curl -fsSL https://claude.ai/install.sh | bash \
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

WORKDIR /app
COPY . /app

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
