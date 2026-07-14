# software-factory-skill

Project memory (pgvector search) embeds via `google/gemini-embedding-2` over OpenRouter — see `docs/ARCHITECTURE.md`.

## Agent instructions: `CLAUDE.md` is canonical

`CLAUDE.md` holds this repo's agent instructions. Codex reads `AGENTS.md` instead — so rather than
maintain two files, `AGENTS.md` is a **symlink to `CLAUDE.md`**. It is **git-ignored and not
tracked**, so it does not exist in a fresh clone.

**After cloning, if you plan to use Codex and Claude Code together, recreate the symlink** so both
tools read the same instructions:

```sh
ln -s CLAUDE.md AGENTS.md
```

Claude Code reads `CLAUDE.md` directly and needs no symlink.
