#!/usr/bin/env node
/**
 * SF Statusline — local-only.
 *
 * Renders a single line from local probes + the Claude Code session JSON (stdin):
 *   git state · model · elapsed · context% · test-file count · session cost.
 * No external tools, no network.
 *
 * Usage: node statusline.cjs [--json | --compact]
 */
/* eslint-disable @typescript-eslint/no-var-requires */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const CWD = process.cwd();

// Session-cost display. Claude Code's total_cost_usd is a client-side estimate
// that "may differ from your actual bill"; these let each user tune the segment.
//   SF_STATUSLINE_COST_SYMBOL  override the leading '$' (e.g. ⚡, €); '' = number only.
//   SF_STATUSLINE_HIDE_COST    1/true/yes/on removes the cost segment entirely.
const CONFIG = {
  costSymbol: process.env.SF_STATUSLINE_COST_SYMBOL ?? '$',
  hideCost: /^(1|true|yes|on)$/i.test(process.env.SF_STATUSLINE_HIDE_COST || ''),
};

// ANSI colors
const c = {
  reset: '\x1b[0m', bold: '\x1b[1m', dim: '\x1b[2m',
  brightRed: '\x1b[1;31m', brightGreen: '\x1b[1;32m', brightYellow: '\x1b[1;33m',
  brightBlue: '\x1b[1;34m', brightPurple: '\x1b[1;35m', brightCyan: '\x1b[1;36m',
  purple: '\x1b[0;35m', cyan: '\x1b[0;36m',
};

// Safe execSync with strict timeout (returns '' on failure)
function safeExec(cmd, timeoutMs) {
  try {
    return execSync(cmd, { encoding: 'utf-8', timeout: timeoutMs || 2000, stdio: ['pipe', 'pipe', 'pipe'] }).trim();
  } catch {
    return '';
  }
}

// ─── Git info (single batched exec) ──────────────────────────────
function getGitInfo() {
  const result = { name: 'user', gitBranch: '', modified: 0, untracked: 0, staged: 0, ahead: 0, behind: 0 };
  const script = [
    'git config user.name 2>/dev/null || echo user', 'echo "---SEP---"',
    'git branch --show-current 2>/dev/null', 'echo "---SEP---"',
    'git status --porcelain 2>/dev/null', 'echo "---SEP---"',
    'git rev-list --left-right --count HEAD...@{upstream} 2>/dev/null || echo "0 0"',
  ].join('; ');
  const raw = safeExec("sh -c '" + script + "'", 3000);
  if (!raw) return result;
  const parts = raw.split('---SEP---').map(function (s) { return s.trim(); });
  if (parts.length >= 4) {
    result.name = parts[0] || 'user';
    result.gitBranch = parts[1] || '';
    if (parts[2]) {
      for (const line of parts[2].split('\n')) {
        if (!line || line.length < 2) continue;
        const x = line[0], y = line[1];
        if (x === '?' && y === '?') { result.untracked++; continue; }
        if (x !== ' ' && x !== '?') result.staged++;
        if (y !== ' ' && y !== '?') result.modified++;
      }
    }
    const ab = (parts[3] || '0 0').split(/\s+/);
    result.ahead = parseInt(ab[0]) || 0;
    result.behind = parseInt(ab[1]) || 0;
  }
  return result;
}

// ─── Test-file count (bounded dir walk, no file reads) ───────────
function countTestFiles() {
  let n = 0;
  function walk(dir, depth) {
    if (depth > 4) return;
    try {
      if (!fs.existsSync(dir)) return;
      for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
        if (e.isDirectory() && !e.name.startsWith('.') && e.name !== 'node_modules') {
          walk(path.join(dir, e.name), depth + 1);
        } else if (e.isFile() && (e.name.includes('.test.') || e.name.includes('.spec.') || e.name.startsWith('test_') || e.name.startsWith('spec_'))) {
          n++;
        }
      }
    } catch { /* ignore */ }
  }
  for (const d of ['tests', 'test', '__tests__', 'src']) walk(path.join(CWD, d), 0);
  return n;
}

// ─── Claude Code session JSON (piped on stdin) ───────────────────
let _stdin;
function getStdinData() {
  if (_stdin !== undefined) return _stdin;
  _stdin = null;
  try {
    if (process.stdin.isTTY) return _stdin;
    const chunks = []; const buf = Buffer.alloc(4096); let nread;
    try { while ((nread = fs.readSync(0, buf, 0, buf.length, null)) > 0) chunks.push(buf.slice(0, nread)); } catch { /* EOF */ }
    const raw = Buffer.concat(chunks).toString('utf-8').trim();
    if (raw && raw.startsWith('{')) _stdin = JSON.parse(raw);
  } catch { _stdin = null; }
  return _stdin;
}

// ─── Render ──────────────────────────────────────────────────────
function generateStatusline() {
  const d = getStdinData() || {};
  const git = getGitInfo();
  const model = (d.model && d.model.display_name) || 'Claude Code';
  const ctxPct = d.context_window ? Math.floor(d.context_window.used_percentage || 0) : 0;
  let duration = '', cost = 0;
  if (d.cost) {
    const ms = d.cost.total_duration_ms || 0;
    const m = Math.floor(ms / 60000), s = Math.floor((ms % 60000) / 1000);
    duration = m > 0 ? (m + 'm' + s + 's') : (s + 's');
    cost = d.cost.total_cost_usd || 0;
  }
  const tests = countTestFiles();
  const sep = '  ' + c.dim + '│' + c.reset + '  ';

  let line = c.bold + c.brightPurple + '▊ SF' + c.reset;
  line += sep + c.brightBlue + '⏇ ' + (git.gitBranch || 'detached') + c.reset;
  const changes = git.modified + git.staged + git.untracked;
  if (changes > 0) {
    let ind = '';
    if (git.staged > 0) ind += c.brightGreen + '+' + git.staged + c.reset;
    if (git.modified > 0) ind += c.brightYellow + '~' + git.modified + c.reset;
    if (git.untracked > 0) ind += c.dim + '?' + git.untracked + c.reset;
    line += ' ' + ind;
  }
  if (git.ahead > 0) line += ' ' + c.brightGreen + '↑' + git.ahead + c.reset;
  if (git.behind > 0) line += ' ' + c.brightRed + '↓' + git.behind + c.reset;
  line += sep + c.purple + model + c.reset;
  if (duration) line += sep + c.cyan + '⏱ ' + duration + c.reset;
  if (ctxPct > 0) {
    const col = ctxPct >= 90 ? c.brightRed : ctxPct >= 70 ? c.brightYellow : c.brightGreen;
    line += sep + col + '● ' + ctxPct + '% ctx' + c.reset;
  }
  if (tests > 0) line += sep + c.brightCyan + '✓ ' + tests + ' tests' + c.reset;
  if (!CONFIG.hideCost && cost > 0) line += sep + c.brightYellow + CONFIG.costSymbol + cost.toFixed(2) + c.reset;
  return line;
}

function generateJSON() {
  const git = getGitInfo();
  const d = getStdinData() || {};
  return {
    user: { name: git.name, gitBranch: git.gitBranch },
    git: { modified: git.modified, untracked: git.untracked, staged: git.staged, ahead: git.ahead, behind: git.behind },
    model: (d.model && d.model.display_name) || 'Claude Code',
    contextPct: d.context_window ? Math.floor(d.context_window.used_percentage || 0) : 0,
    tests: countTestFiles(),
    lastUpdated: new Date().toISOString(),
  };
}

// ─── Main ─────────────────────────────────────────────────────────
if (process.argv.includes('--json')) {
  console.log(JSON.stringify(generateJSON(), null, 2));
} else if (process.argv.includes('--compact')) {
  console.log(JSON.stringify(generateJSON()));
} else {
  console.log(generateStatusline());
}
