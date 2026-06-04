# Factory RUNNER image — everything the skill needs to run a full build in the cloud.
# Software only; SECRETS are runtime env vars on the service (never baked into an image).
FROM node:20-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Orchestrator runtime + deploy CLI + browser-test MCP, all global
RUN npm install -g @anthropic-ai/claude-code @railway/cli @playwright/mcp playwright

# Chromium + OS libs into a SHARED path so a non-root runtime user can use them.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN npx -y playwright install --with-deps chromium

# GitHub CLI
RUN curl -fsSL https://github.com/cli/cli/releases/download/v2.62.0/gh_2.62.0_linux_amd64.tar.gz \
        | tar -xz -C /tmp \
    && mv /tmp/gh_2.62.0_linux_amd64/bin/gh /usr/local/bin/gh \
    && rm -rf /tmp/gh_2.62.0_linux_amd64

# Claude Code refuses bypassed permissions as root — run as a non-root user.
RUN useradd -m -u 1000 factory
ENV HOME=/home/factory

WORKDIR /app
COPY . /app

RUN mkdir -p /home/factory/.claude/skills \
    && ln -sfn /app /home/factory/.claude/skills/software-factory \
    && printf '%s\n' '{"mcpServers":{"playwright":{"command":"npx","args":["-y","@playwright/mcp@latest","--headless","--browser","chromium"]}}}' > /app/.mcp.json \
    && printf '%s\n' '{"enableAllProjectMcpServers":true}' > /home/factory/.claude/settings.json \
    && chmod +x /app/entrypoint.sh \
    && chown -R factory:factory /app /home/factory /ms-playwright

# Entrypoint drops to the non-root `factory` user even if the platform starts us as root.
# Required at runtime (set on the service): ANTHROPIC_API_KEY, GH_TOKEN, RAILWAY_TOKEN, SUPABASE_ACCESS_TOKEN
ENV PYTHONUNBUFFERED=1 SF_BIND=0.0.0.0 HOME=/home/factory
CMD ["/app/entrypoint.sh"]
