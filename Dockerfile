# Factory RUNNER image — everything the skill needs to run a full build in the cloud.
# Software only; SECRETS are runtime env vars on the service (never baked into an image).
FROM node:20-bookworm

# System deps: python (server + many target apps), git, curl, ca-certs
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Orchestrator runtime + deploy CLI + browser-test MCP, all global
RUN npm install -g @anthropic-ai/claude-code @railway/cli @playwright/mcp playwright

# Chromium + its OS libraries for the Playwright happy-flow gate
RUN npx -y playwright install --with-deps chromium

# GitHub CLI (repo + PRs)
RUN curl -fsSL https://github.com/cli/cli/releases/download/v2.62.0/gh_2.62.0_linux_amd64.tar.gz \
        | tar -xz -C /tmp \
    && mv /tmp/gh_2.62.0_linux_amd64/bin/gh /usr/local/bin/gh \
    && rm -rf /tmp/gh_2.62.0_linux_amd64

WORKDIR /app
COPY . /app

# Make the skill discoverable to the headless `claude` the console spawns,
# register the Playwright MCP server, and auto-enable project MCP servers (headless).
RUN mkdir -p /root/.claude/skills \
    && ln -sfn /app /root/.claude/skills/software-factory \
    && printf '%s\n' '{"mcpServers":{"playwright":{"command":"npx","args":["-y","@playwright/mcp@latest","--headless","--browser","chromium"]}}}' > /app/.mcp.json \
    && printf '%s\n' '{"enableAllProjectMcpServers":true}' > /root/.claude/settings.json

# Required at runtime (set on the service, NOT here):
#   ANTHROPIC_API_KEY, GH_TOKEN, RAILWAY_TOKEN, SUPABASE_ACCESS_TOKEN
ENV PYTHONUNBUFFERED=1 SF_BIND=0.0.0.0
CMD ["python3", "console/server.py"]
