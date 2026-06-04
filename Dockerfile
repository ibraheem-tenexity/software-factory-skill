# Factory RUNNER image: the hosted console that can actually run the skill.
# Unlike the bare web image, this bakes in Claude Code + the deploy CLIs + the skill,
# so a submitted run spawns a real headless `claude` in the container.
FROM node:20-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Claude Code (the orchestrator runtime) + Railway CLI (deploy)
RUN npm install -g @anthropic-ai/claude-code @railway/cli

# GitHub CLI (repo + PRs)
RUN curl -fsSL https://github.com/cli/cli/releases/download/v2.62.0/gh_2.62.0_linux_amd64.tar.gz \
        | tar -xz -C /tmp \
    && mv /tmp/gh_2.62.0_linux_amd64/bin/gh /usr/local/bin/gh \
    && rm -rf /tmp/gh_2.62.0_linux_amd64

WORKDIR /app
COPY . /app

# Make the skill discoverable to the headless `claude` the console spawns.
RUN mkdir -p /root/.claude/skills && ln -sfn /app /root/.claude/skills/software-factory

ENV PYTHONUNBUFFERED=1 SF_BIND=0.0.0.0
# PORT is provided by Railway and read by the server.
CMD ["python3", "console/server.py"]
