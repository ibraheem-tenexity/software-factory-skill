#!/usr/bin/env node
/**
 * Auto Memory Hook — claude-flow bridge removed (#136).
 *
 * This hook PREVIOUSLY loaded the `@claude-flow/memory` package to bridge the
 * file-based auto-memory (MEMORY.md) into a claude-flow backend store under
 * `.claude-flow/data` (import on SessionStart, sync on Stop). claude-flow has
 * been excised from .claude/, so the bridge — and every claude-flow require/
 * import — is gone.
 *
 * IMPORTANT: MEMORY.md *recall* is a Claude Code native feature (the auto-memory
 * injected into context at session start). It does NOT depend on this hook and
 * keeps working unchanged. This hook only ever mirrored MEMORY.md into the
 * claude-flow store; with claude-flow gone there is nothing to mirror.
 *
 * The file is retained as a wired no-op so the settings.json SessionStart/Stop
 * entries resolve and exit cleanly. It performs no action and references no
 * claude-flow.
 *
 * Usage: node auto-memory-hook.mjs <import|sync|status>
 */

const command = process.argv[2] || 'status';

if (command === 'status') {
  console.log('[AutoMemory] claude-flow bridge removed (#136); MEMORY.md recall is native and unaffected.');
}
// import / sync: intentionally silent no-ops (nothing to bridge without claude-flow).

process.exit(0);
