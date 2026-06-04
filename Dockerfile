# Factory RUNNER image — everything the skill needs to run a full build in the cloud.
# Software only; SECRETS are runtime env vars on the service (never baked into an image).
FROM node:20-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Puppeteer (mermaid-cli) chromium into a SHARED path reachable by the non-root runtime user.
ENV PUPPETEER_CACHE_DIR=/ms-puppeteer
# Orchestrator runtime + deploy CLI + browser-test MCP + Mermaid->SVG (architecture diagrams), all global
RUN npm install -g @anthropic-ai/claude-code @railway/cli @playwright/mcp playwright @mermaid-js/mermaid-cli

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

WORKDIR /app
COPY . /app

RUN mkdir -p /home/node/.claude/skills /ms-puppeteer \
    && ln -sfn /app /home/node/.claude/skills/software-factory \
    && printf '%s\n' '{"mcpServers":{"playwright":{"command":"npx","args":["-y","@playwright/mcp@latest","--headless","--browser","chromium"]},"ruflo":{"command":"npx","args":["-y","ruflo@latest","mcp","start"]}}}' > /app/.mcp.json \
    && printf '%s\n' '{"enableAllProjectMcpServers":true}' > /home/node/.claude/settings.json \
    && chmod +x /app/entrypoint.sh \
    && chown -R node:node /app /home/node /ms-playwright /ms-puppeteer

# Entrypoint drops to uid 1000 (node) even if the platform starts us as root.
# Required at runtime (set on the service): ANTHROPIC_API_KEY, GH_TOKEN, RAILWAY_TOKEN, SUPABASE_ACCESS_TOKEN
# PYTHONPATH so `import software_factory` works for any python invocation (the orchestrator
# shells fresh python processes, not just the server).
ENV PYTHONUNBUFFERED=1 SF_BIND=0.0.0.0 PYTHONPATH=/app/src
CMD ["/app/entrypoint.sh"]
