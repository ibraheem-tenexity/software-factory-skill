// artifactviewer.jsx — the Artifact Viewer. A standalone, full-page file viewer
// for everything the factory produces or that operators author: Markdown,
// SVG diagrams, source/text, JSON, CSV tables, images, and the repo tree.
//
// • `Markdown` — a real markdown→React renderer (headings, lists, tables, code,
//   blockquotes, links, rules, inline bold/italic/code). Exported for reuse
//   (the SOW editor previews with it).
// • `ART` — the artifact registry: one record per file, keyed by id, with real
//   content. Shared by the main app and this viewer.
// • `openArtifact(idOrObj)` — opens ArtifactViewer.html?doc=<id> in a NEW TAB.
// • `ArtifactViewer` — the page: file rail (grouped) + topbar + typed viewer.
//
// Loaded by both Software Factory Onboarding.html (for openArtifact + ART) and
// ArtifactViewer.html (which mounts <ArtifactViewer/> reading ?doc= from URL).

/* ============================ markdown renderer ============================ */

function mdInline(text, kp) {
  // Tokenize inline spans: `code`, **bold**, *italic*/_italic_, [label](url).
  const out = [];
  let i = 0, last = 0, key = 0;
  const push = (node) => out.push(node);
  const flush = (end) => { if (end > last) push(text.slice(last, end)); };
  const re = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*\s][^*]*\*)|(_[^_\s][^_]*_)|(\[[^\]]+\]\([^)]+\))/g;
  let m;
  while ((m = re.exec(text))) {
    flush(m.index);
    const tok = m[0];
    if (tok[0] === '`') push(<code key={kp + 'c' + key++} style={{ font: `500 0.88em/1 ${T.mono}`, background: T.sunken, color: T.brandDeep, padding: '2px 5px', borderRadius: 4, border: `1px solid ${T.borderSubtle}` }}>{tok.slice(1, -1)}</code>);
    else if (tok.startsWith('**')) push(<strong key={kp + 'b' + key++} style={{ fontWeight: 600, color: T.fg }}>{tok.slice(2, -2)}</strong>);
    else if (tok[0] === '*' || tok[0] === '_') push(<em key={kp + 'i' + key++}>{tok.slice(1, -1)}</em>);
    else { const mm = /\[([^\]]+)\]\(([^)]+)\)/.exec(tok); push(<a key={kp + 'a' + key++} href={mm[2]} target="_blank" rel="noopener noreferrer" style={{ color: T.brandDeep, textDecoration: 'underline', textDecorationColor: T.brand + '66' }}>{mm[1]}</a>); }
    last = m.index + tok.length;
  }
  flush(text.length);
  return out;
}

// Parse a markdown string into an array of {type, ...} blocks + heading slugs.
function mdBlocks(src) {
  const lines = (src || '').replace(/\r\n/g, '\n').split('\n');
  const blocks = [];
  let i = 0;
  const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
  while (i < lines.length) {
    let ln = lines[i];
    if (/^```/.test(ln)) { // fenced code
      const lang = ln.slice(3).trim(); const buf = []; i++;
      while (i < lines.length && !/^```/.test(lines[i])) { buf.push(lines[i]); i++; }
      i++; blocks.push({ type: 'code', lang, text: buf.join('\n') }); continue;
    }
    if (/^\s*$/.test(ln)) { i++; continue; }
    const h = /^(#{1,6})\s+(.*)$/.exec(ln);
    if (h) { const lvl = h[1].length, txt = h[2].trim(); blocks.push({ type: 'h', level: lvl, text: txt, id: slug(txt) }); i++; continue; }
    if (/^\s*([-*_])\1{2,}\s*$/.test(ln)) { blocks.push({ type: 'hr' }); i++; continue; }
    if (/^\s*>\s?/.test(ln)) { const buf = []; while (i < lines.length && /^\s*>\s?/.test(lines[i])) { buf.push(lines[i].replace(/^\s*>\s?/, '')); i++; } blocks.push({ type: 'quote', text: buf.join('\n') }); continue; }
    if (/^\s*\|.*\|\s*$/.test(ln) && i + 1 < lines.length && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i + 1])) {
      const row = (s) => s.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim());
      const head = row(ln); i += 2; const rows = [];
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) { rows.push(row(lines[i])); i++; }
      blocks.push({ type: 'table', head, rows }); continue;
    }
    if (/^\s*(?:[-*+]\s+|\d+[.)]\s+)/.test(ln)) {
      const ordered = /^\s*\d+[.)]\s+/.test(ln); const items = [];
      while (i < lines.length && /^\s*(?:[-*+]\s+|\d+[.)]\s+)/.test(lines[i])) { items.push(lines[i].replace(/^\s*(?:[-*+]\s+|\d+[.)]\s+)/, '')); i++; }
      blocks.push({ type: 'list', ordered, items }); continue;
    }
    const buf = [ln]; i++;
    while (i < lines.length && !/^\s*$/.test(lines[i]) && !/^(#{1,6})\s|^```|^\s*>|^\s*\|/.test(lines[i]) && !/^\s*(?:[-*+]\s+|\d+[.)]\s+)/.test(lines[i])) { buf.push(lines[i]); i++; }
    blocks.push({ type: 'p', text: buf.join(' ') });
  }
  return blocks;
}

function Markdown({ source, onHeadings }) {
  const blocks = React.useMemo(() => mdBlocks(source), [source]);
  React.useEffect(() => { if (onHeadings) onHeadings(blocks.filter((b) => b.type === 'h' && b.level <= 3).map((b) => ({ id: b.id, text: b.text, level: b.level }))); }, [blocks]);
  const hSize = { 1: 30, 2: 22, 3: 17, 4: 15, 5: 13.5, 6: 12.5 };
  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      {blocks.map((b, k) => {
        if (b.type === 'h') return (
          <div key={k} id={b.id} style={{ scrollMarginTop: 20, marginTop: b.level === 1 ? 0 : b.level === 2 ? 30 : 20, marginBottom: b.level >= 3 ? 6 : 10, paddingBottom: b.level <= 2 ? 8 : 0, borderBottom: b.level === 1 ? `1px solid ${T.borderSubtle}` : 'none' }}>
            {React.createElement(b.level <= 2 ? 'h' + b.level : 'h4', { style: { margin: 0, font: `${b.level <= 2 ? 400 : 700} ${hSize[b.level]}px/1.25 ${b.level <= 2 ? T.display : T.sans}`, letterSpacing: b.level <= 2 ? '-0.01em' : '0', color: T.fg } }, mdInline(b.text, 'h' + k))}
          </div>
        );
        if (b.type === 'p') return <p key={k} style={{ margin: '0 0 13px', font: `400 14.5px/1.68 ${T.sans}`, color: T.secondary }}>{mdInline(b.text, 'p' + k)}</p>;
        if (b.type === 'hr') return <hr key={k} style={{ border: 'none', borderTop: `1px solid ${T.borderSubtle}`, margin: '20px 0' }} />;
        if (b.type === 'quote') return (
          <blockquote key={k} style={{ margin: '0 0 14px', padding: '10px 16px', borderRadius: '0 8px 8px 0', borderLeft: `3px solid ${T.brand}`, background: T.brandSoft + '55' }}>
            {mdBlocks(b.text).map((bb, j) => <p key={j} style={{ margin: j ? '8px 0 0' : 0, font: `400 14px/1.6 ${T.sans}`, color: T.secondary }}>{mdInline(bb.text || '', 'q' + k + j)}</p>)}
          </blockquote>
        );
        if (b.type === 'list') return React.createElement(b.ordered ? 'ol' : 'ul', { key: k, style: { margin: '0 0 14px', paddingLeft: 22, display: 'flex', flexDirection: 'column', gap: 6 } },
          b.items.map((it, j) => <li key={j} style={{ font: `400 14.5px/1.6 ${T.sans}`, color: T.secondary }}>{mdInline(it, 'li' + k + j)}</li>));
        if (b.type === 'code') return (
          <div key={k} style={{ margin: '0 0 16px', borderRadius: T.rLg, overflow: 'hidden', border: `1px solid ${T.borderSubtle}` }}>
            {b.lang && <div style={{ padding: '7px 13px', borderBottom: `1px solid ${T.borderSubtle}`, background: T.sunken, font: `600 10px/1 ${T.mono}`, letterSpacing: '0.08em', textTransform: 'uppercase', color: T.tertiary }}>{b.lang}</div>}
            <pre style={{ margin: 0, padding: '13px 15px', overflow: 'auto', background: '#0d1117' }}><code style={{ font: `400 12.5px/1.7 ${T.mono}`, color: '#e6edf3', whiteSpace: 'pre' }}>{b.text}</code></pre>
          </div>
        );
        if (b.type === 'table') return (
          <div key={k} style={{ margin: '0 0 16px', borderRadius: T.rLg, border: `1px solid ${T.borderSubtle}`, overflow: 'auto' }}>
            <table style={{ borderCollapse: 'collapse', width: '100%', font: `400 13.5px/1.5 ${T.sans}` }}>
              <thead><tr>{b.head.map((c, j) => <th key={j} style={{ textAlign: 'left', padding: '9px 13px', background: T.sunken, borderBottom: `1px solid ${T.borderDefault}`, font: `600 11px/1 ${T.mono}`, letterSpacing: '0.04em', textTransform: 'uppercase', color: T.secondary, whiteSpace: 'nowrap' }}>{c}</th>)}</tr></thead>
              <tbody>{b.rows.map((r, ri) => <tr key={ri}>{r.map((c, ci) => <td key={ci} style={{ padding: '9px 13px', borderBottom: ri < b.rows.length - 1 ? `1px solid ${T.borderSubtle}` : 'none', color: ci === 0 ? T.fg : T.secondary }}>{mdInline(c, 't' + k + ri + ci)}</td>)}</tr>)}</tbody>
            </table>
          </div>
        );
        return null;
      })}
    </div>
  );
}

/* ============================ artifact registry ============================ */
// type ∈ md | svg | code | json | csv | repo | fig | image
const PROJ_ACME = 'Acme Industrial · Quote-to-Epicor';

const ART = {
  prd: { id: 'prd', name: 'PRD.md', type: 'md', node: 'product', agent: 'Product council · HORIZON', project: PROJ_ACME, conf: 'high', updated: '2h ago', content: `# Quote-to-Epicor Automation — PRD

> Reconciled by the **product council** (3 agents) from research, the company profile, and the customer's process notes. Confidence: **High (84)**.

## 1 · Problem
Acme builds ~120 quotes/week by hand in spreadsheets, then re-keys them into Epicor. Re-keying is error-prone and the >15% discount approval is an email scramble — slowing turnaround and risking margin.

## 2 · Goals (v1)
- Build quotes against **live Epicor SKUs** and the standard price book — no re-keying.
- Route any line over a **15% discount** to a sales manager for one-click approval.
- Write the won quote straight back into Epicor as an order.

## 3 · Primary users
- Inside-sales reps (quote authors)
- Sales managers (approvers)
- Operations (visibility)

## 4 · In scope
Quote builder · pricing rules engine · approval workflow · Epicor read + write-back · manager dashboard · PDF export.

## 5 · Out of scope (v1)
Multi-currency, CPQ configurator, customer self-service portal.

## 6 · Success metrics
| Metric | Today | Target |
| --- | --- | --- |
| Quote turnaround | ~2 days | **−60%** |
| Re-key errors | ~8/wk | **0** |
| Discount approval | hours | **< 1 hour** |
` },
  'r-market': { id: 'r-market', name: 'market-scan.md', type: 'md', node: 'research', agent: 'Research agent', project: PROJ_ACME, updated: '3h ago', content: `# Market scan — quoting in industrial & MRO distribution

Web research on how distributors author and process quotes.

## Findings
- Distributors quote **80–150×/week**; most still author in Excel.
- Re-keying into the ERP (Epicor / SAP) is the **top cited error source**.
- Margin leakage concentrates in **ad-hoc discounting** without an approval gate.

## Implication
A lightweight quote builder that reads the ERP live and writes back the won order removes the two biggest failure points at once.
` },
  'r-existing': { id: 'r-existing', name: 'existing-solutions.md', type: 'md', node: 'research', agent: 'Research agent', project: PROJ_ACME, updated: '3h ago', content: `# Existing solutions — scored against Acme's needs

| Solution | Strength | Weakness |
| --- | --- | --- |
| CPQ suites | Powerful rules | Heavy setup, enterprise pricing |
| ERP-native quoting | Already integrated | Clunky UX — reps avoid it |
| Spreadsheets | Flexible, familiar | No write-back, no approvals |

## Gap
A **lightweight quote builder** that writes back to Epicor and enforces a discount gate — none of the above do all three at Acme's price point.
` },
  'r-fit': { id: 'r-fit', name: 'requirements-fit.md', type: 'md', node: 'research', agent: 'Research agent', project: PROJ_ACME, updated: '3h ago', content: `# Requirement-to-capability fit

Derived from the intake and the connected systems.

- Must **read Epicor SKUs + price book** in real time.
- **>15% discount → manager approval gate** (hard requirement).
- **Write-back** of the won quote as an Epicor order eliminates re-keying.
- Must export a branded **PDF** for the customer.
` },
  datamodel: { id: 'datamodel', name: 'data-model.md', type: 'md', node: 'architect', agent: 'Architect agent · MATRIX', project: PROJ_ACME, updated: '1h ago', content: `# Data model — quote-to-ERP

Core entities for the flow.

\`\`\`
quote(id, customer, status, total, discount_pct, approver)
quote_line(quote_id, sku, qty, unit_price, list_price)
approval(quote_id, manager, decision, ts)
epicor_sync(quote_id, order_no, synced_at)
\`\`\`

## Notes
- Every write to \`epicor_sync\` is **idempotent** on \`quote_id\`.
- \`approval\` is append-only — full audit trail on each decision.
` },
  designspec: { id: 'designspec', name: 'design-spec.md', type: 'md', node: 'design', agent: 'Design agent · CHROMA', project: PROJ_ACME, updated: '1h ago', content: `# Design spec — handed to the build agents

## System
- Tenexity design system: brand \`#1A7BFF\`, Hanken Grotesk / Georgia / JetBrains Mono, the confidence cascade.

## Screens → archetypes
- **Quote builder** → Catalog + Processing-Queue archetypes.
- **Approval queue** → Approval-Stack archetype, keyboard \`Y\` / \`E\` / \`N\`.
- **Manager dashboard** → Metric-grid + Comparator.
` },
  tickets: { id: 'tickets', name: 'tickets.md', type: 'md', node: 'tickets', agent: 'Planner agent', project: PROJ_ACME, updated: '54m ago', content: `# Build backlog — 11 tickets

Generated by the Planner agent and grouped for the build swarm.

## Foundation
- **SF-01** Auth & org workspace setup
- **SF-02** Epicor connector — read orders & SKUs
- **SF-03** Quote data model + schema

## Core
- **SF-04** Pricing rules engine
- **SF-05** Discount approval workflow (>15%)
- **SF-07** Epicor write-back of approved quote

## Polish & QA
- **SF-06** Manager visibility dashboard
- **SF-08** Quote PDF export & email
- **SF-09** Re-key elimination QA pass
- **SF-10..11** Playwright e2e + bug-fix loop
` },
  readme: { id: 'readme', name: 'README.md', type: 'md', node: 'provision', agent: 'Provision agent · FORGE', project: PROJ_ACME, updated: '4h ago', content: `# acme-quote-to-erp

Quote-to-Epicor automation for Acme Industrial Supply. Provisioned by the factory.

## Setup
\`\`\`bash
pnpm install
cp .env.example .env.local   # fill EPICOR_*, OPENAI_*, SUPABASE_*
pnpm dev
\`\`\`

## Stack
- Next.js + React UI (quote builder)
- Supabase (postgres, auth, storage)
- Epicor Kinetic connector (read SKUs · write order)
- Playwright e2e
` },
  arch: { id: 'arch', name: 'architecture.svg', type: 'svg', node: 'architect', agent: 'Architect agent · MATRIX', project: PROJ_ACME, updated: '1h ago' },
  screens: { id: 'screens', name: 'screens.fig', type: 'fig', node: 'design', agent: 'Design agent · CHROMA', project: PROJ_ACME, updated: '1h ago', frames: ['Quote builder', 'Approval queue', 'Manager dashboard'] },
  repo: { id: 'repo', name: 'acme-quote-to-erp', type: 'repo', node: 'provision', agent: 'Provision agent · FORGE', project: PROJ_ACME, updated: '4h ago' },
  schema: { id: 'schema', name: 'schema.sql', type: 'code', lang: 'sql', node: 'architect', agent: 'Architect agent · MATRIX', project: PROJ_ACME, updated: '1h ago', content: `-- quote-to-Epicor schema (excerpt)
create table quote (
  id uuid primary key default gen_random_uuid(),
  customer text not null,
  status text not null default 'draft',
  total numeric(12,2) not null default 0,
  discount_pct numeric(5,2) not null default 0,
  approver text
);

create table quote_line (
  quote_id uuid references quote(id) on delete cascade,
  sku text not null,
  qty integer not null check (qty > 0),
  unit_price numeric(12,2) not null,
  list_price numeric(12,2) not null
);

create table approval (
  quote_id uuid references quote(id),
  manager text not null,
  decision text not null check (decision in ('approved','rejected')),
  ts timestamptz not null default now()
);` },
  env: { id: 'env', name: '.env.example', type: 'code', lang: 'bash', node: 'provision', agent: 'Provision agent · FORGE', project: PROJ_ACME, updated: '4h ago', content: `# Epicor Kinetic
EPICOR_BASE_URL=
EPICOR_API_KEY=
EPICOR_COMPANY=ACME

# OpenAI
OPENAI_API_KEY=

# Supabase
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE=` },
  'pricing-rules': { id: 'pricing-rules', name: 'pricing-rules.csv', type: 'csv', node: 'build', agent: 'Pricing & Margin · PROFIT', project: PROJ_ACME, updated: '40m ago', content: `tier,min_qty,discount_pct,approval_required
Standard,1,0,no
Volume,25,5,no
Contract,100,12,no
Override,1,15,yes
Strategic,250,20,yes` },
  'epicor-sync': { id: 'epicor-sync', name: 'epicor-sync.json', type: 'json', node: 'build', agent: 'ERP Integration · CONDUIT', project: PROJ_ACME, updated: '22m ago', content: `{
  "connector": "epicor-kinetic",
  "mode": "read-write",
  "idempotency_key": "quote_id",
  "endpoints": {
    "skus": "/api/v2/odata/ACME/Erp.BO.PartSvc",
    "price_book": "/api/v2/odata/ACME/Erp.BO.PriceLstSvc",
    "create_order": "/api/v2/odata/ACME/Erp.BO.SalesOrderSvc"
  },
  "writeback": { "requires_approval": true, "retry": 3 }
}` },
};

// SOW artifacts are registered by sow.jsx via registerArtifacts(); this keeps a
// single source of truth so the viewer can open them too.
function registerArtifacts(map) { Object.assign(ART, map); }

function artGroups() {
  const order = ['provision', 'research', 'product', 'architect', 'design', 'tickets', 'build'];
  const byProject = {};
  Object.values(ART).forEach((a) => { (byProject[a.project] = byProject[a.project] || []).push(a); });
  return Object.keys(byProject).map((proj) => ({
    project: proj,
    items: byProject[proj].slice().sort((a, b) => (order.indexOf(a.node) - order.indexOf(b.node)) || a.name.localeCompare(b.name)),
  }));
}

function openArtifact(idOrObj) {
  const id = typeof idOrObj === 'string' ? idOrObj : (idOrObj && idOrObj.id);
  if (!id) return;
  window.open('ArtifactViewer.html?doc=' + encodeURIComponent(id), '_blank', 'noopener');
}

/* ============================ typed file views ============================ */

const TYPE_BADGE = {
  md: ['MD', T.brandSoft, T.brandDeep], svg: ['SVG', '#e7f7f0', '#1f8a5b'], code: ['CODE', '#eceef1', '#30363d'],
  json: ['JSON', '#fff3e0', '#b9770e'], csv: ['CSV', '#f0ecfb', '#7a3ea8'], repo: ['REPO', '#eceef1', '#30363d'],
  fig: ['FIG', '#f3e9fb', '#7a3ea8'], image: ['IMG', '#e8f1ff', '#0958c9'],
};
function TypeBadge({ type, big }) {
  const b = TYPE_BADGE[type] || TYPE_BADGE.md;
  return <span style={{ font: `700 ${big ? 10 : 8.5}px/1 ${T.mono}`, letterSpacing: '0.06em', color: b[2], background: b[1], padding: big ? '5px 7px' : '3px 5px', borderRadius: 4, flexShrink: 0 }}>{b[0]}</span>;
}

function CodeView({ text, lang }) {
  const lines = (text || '').split('\n');
  return (
    <div style={{ borderRadius: T.rLg, overflow: 'hidden', border: `1px solid #1f242c`, background: '#0d1117' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '9px 14px', borderBottom: '1px solid #1f242c', background: '#11161d' }}>
        <span style={{ font: `600 10px/1 ${T.mono}`, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#8b949e' }}>{lang || 'text'}</span>
        <span style={{ font: `400 10.5px/1 ${T.mono}`, color: '#8b949e' }}>{lines.length} lines</span>
      </div>
      <div style={{ display: 'flex', overflow: 'auto', maxHeight: '100%' }}>
        <div style={{ flexShrink: 0, padding: '14px 0', textAlign: 'right', userSelect: 'none', background: '#0d1117', borderRight: '1px solid #1f242c' }}>
          {lines.map((_, i) => <div key={i} style={{ font: `400 12.5px/1.75 ${T.mono}`, color: '#484f58', padding: '0 14px' }}>{i + 1}</div>)}
        </div>
        <pre style={{ margin: 0, padding: '14px 16px', flex: 1 }}><code style={{ font: `400 12.5px/1.75 ${T.mono}`, color: '#e6edf3', whiteSpace: 'pre' }}>{text}</code></pre>
      </div>
    </div>
  );
}

function CsvView({ text }) {
  const rows = (text || '').trim().split('\n').map((r) => r.split(','));
  const head = rows[0] || [];
  return (
    <div style={{ borderRadius: T.rLg, border: `1px solid ${T.borderSubtle}`, overflow: 'auto', background: T.raised }}>
      <table style={{ borderCollapse: 'collapse', width: '100%', font: `400 13px/1.5 ${T.sans}` }}>
        <thead><tr>{head.map((c, j) => <th key={j} style={{ textAlign: 'left', padding: '10px 14px', background: T.sunken, borderBottom: `1px solid ${T.borderDefault}`, font: `600 11px/1 ${T.mono}`, letterSpacing: '0.04em', textTransform: 'uppercase', color: T.secondary, whiteSpace: 'nowrap' }}>{c}</th>)}</tr></thead>
        <tbody>{rows.slice(1).map((r, ri) => <tr key={ri}>{r.map((c, ci) => <td key={ci} style={{ padding: '9px 14px', borderBottom: ri < rows.length - 2 ? `1px solid ${T.borderSubtle}` : 'none', font: ci === 0 ? `500 13px/1.5 ${T.sans}` : `400 13px/1.5 ${T.mono}`, color: ci === 0 ? T.fg : T.secondary }}>{c}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

function JsonView({ text }) { return <CodeView text={text} lang="json" />; }

function ArchSvg() {
  return (
    <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, background: T.raised, padding: 26 }}>
      <svg viewBox="0 0 640 300" style={{ width: '100%', height: 'auto' }} fontFamily={T.sans}>
        <defs><marker id="avah" markerWidth="9" markerHeight="9" refX="7" refY="3" orient="auto"><path d="M0 0L7 3L0 6" fill="none" stroke={T.tertiary} strokeWidth="1.4" /></marker></defs>
        {[[20, 120, 'Quote Builder', 'React UI', T.brand], [200, 60, 'Pricing Engine', 'rules + price book', T.fg], [200, 180, 'Approval Service', '>15% → manager', T.fg], [400, 120, 'Epicor Connector', 'read SKUs · write order', T.fg], [400, 12, 'Supabase', 'quotes · audit', T.cHigh]].map((b, i) => (
          <g key={i}><rect x={b[0]} y={b[1]} width={150} height={58} rx={10} fill={T.raised} stroke={b[4]} strokeWidth="1.6" /><text x={b[0] + 75} y={b[1] + 26} textAnchor="middle" fontSize="14" fontWeight="600" fill={T.fg}>{b[2]}</text><text x={b[0] + 75} y={b[1] + 44} textAnchor="middle" fontSize="11" fill={T.tertiary}>{b[3]}</text></g>
        ))}
        {[[170, 149, 200, 89], [170, 149, 200, 209], [350, 89, 400, 140], [350, 209, 400, 160], [475, 120, 475, 70]].map((l, i) => <line key={i} x1={l[0]} y1={l[1]} x2={l[2]} y2={l[3]} stroke={T.tertiary} strokeWidth="1.4" markerEnd="url(#avah)" />)}
        <line x1="550" y1="149" x2="600" y2="149" stroke={T.tertiary} strokeWidth="1.4" markerEnd="url(#avah)" /><text x="612" y="153" fontSize="11" fill={T.tertiary}>ERP</text>
      </svg>
    </div>
  );
}

function FigView({ frames }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 16 }}>
      {(frames || []).map((s) => (
        <div key={s} style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: 'hidden', background: T.raised }}>
          <div style={{ height: 150, background: `repeating-linear-gradient(135deg, ${T.sunken}, ${T.sunken} 9px, ${T.bg} 9px, ${T.bg} 18px)`, display: 'grid', placeItems: 'center' }}><span style={{ font: `400 10px/1 ${T.mono}`, color: T.tertiary }}>frame</span></div>
          <div style={{ padding: '10px 13px', font: `500 13px/1 ${T.sans}`, color: T.fg }}>{s}</div>
        </div>
      ))}
    </div>
  );
}

function RepoView() {
  const tree = [['📁', 'src/', 'app, components, lib'], ['📁', 'supabase/', 'schema + migrations'], ['📁', 'docs/', 'PRD.md, architecture.svg'], ['📄', 'README.md', 'setup & env'], ['📄', '.env.example', 'EPICOR / OPENAI / SUPABASE']];
  return (
    <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: 'hidden', background: T.raised }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '13px 16px', borderBottom: `1px solid ${T.borderSubtle}`, background: T.sunken }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}><Icon name="link" size={16} color={T.secondary} /><span style={{ font: `600 14px/1 ${T.sans}`, color: T.fg }}>tenexity-factory / acme-quote-to-erp</span><StatusPill tone="neutral" dot={false}>private</StatusPill></div>
        <Btn variant="secondary" size="sm">Open on GitHub <Icon name="arrowRight" size={13} /></Btn>
      </div>
      <div style={{ padding: '12px 16px' }}>
        <p style={{ margin: '0 0 12px', font: `400 13.5px/1.6 ${T.sans}`, color: T.secondary }}>Provisioned by the Provision agent · main branch · 3 agents pushing.</p>
        <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rMd, overflow: 'hidden' }}>
          {tree.map((r, i) => <div key={r[1]} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 13px', borderBottom: i < tree.length - 1 ? `1px solid ${T.borderSubtle}` : 'none' }}><span>{r[0]}</span><span style={{ font: `500 13px/1 ${T.mono}`, color: T.fg, width: 160 }}>{r[1]}</span><span style={{ font: `400 12px/1 ${T.sans}`, color: T.tertiary }}>{r[2]}</span></div>)}
        </div>
      </div>
    </div>
  );
}

// Render an artifact's body by type. md/sow get the reading column + TOC.
function FileBody({ art, onHeadings }) {
  if (!art) return null;
  if (art.type === 'md' || art.type === 'sow') return <Markdown source={art.content} onHeadings={onHeadings} />;
  if (art.type === 'svg') return <ArchSvg />;
  if (art.type === 'code') return <CodeView text={art.content} lang={art.lang} />;
  if (art.type === 'json') return <JsonView text={art.content} />;
  if (art.type === 'csv') return <CsvView text={art.content} />;
  if (art.type === 'repo') return <RepoView />;
  if (art.type === 'fig') return <FigView frames={art.frames} />;
  if (art.type === 'image') return <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: 'hidden', background: T.sunken, display: 'grid', placeItems: 'center', padding: 16 }}><img src={art.src} alt={art.name} style={{ maxWidth: '100%', borderRadius: 6 }} /></div>;
  return <p style={{ font: `400 14px/1.6 ${T.sans}`, color: T.tertiary }}>No preview available for this file type.</p>;
}

/* ============================ the viewer page ============================ */

function ArtifactViewer({ initialId }) {
  const groups = React.useMemo(() => artGroups(), []);
  const first = initialId && ART[initialId] ? initialId : (groups[0] && groups[0].items[0] && groups[0].items[0].id);
  const [active, setActive] = React.useState(first);
  const [headings, setHeadings] = React.useState([]);
  const [q, setQ] = React.useState('');
  const qDict = useDictation(q, setQ);
  const [copied, setCopied] = React.useState(false);
  const art = ART[active];
  const isDoc = art && (art.type === 'md' || art.type === 'sow');

  const select = (id) => {
    setActive(id); setHeadings([]);
    try { const u = new URL(window.location.href); u.searchParams.set('doc', id); window.history.replaceState({}, '', u); } catch (e) {}
  };
  const copy = () => { if (art && art.content) { try { navigator.clipboard.writeText(art.content); } catch (e) {} setCopied(true); setTimeout(() => setCopied(false), 1600); } };
  const filtered = groups.map((g) => ({ ...g, items: g.items.filter((a) => !q || a.name.toLowerCase().includes(q.toLowerCase())) })).filter((g) => g.items.length);

  return (
    <div style={{ height: '100vh', display: 'flex', background: T.bg, fontFamily: T.sans, color: T.fg }}>
      {/* file rail */}
      <aside style={{ width: 290, flexShrink: 0, borderRight: `1px solid ${T.borderSubtle}`, background: T.raised, display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '16px 16px 12px', borderBottom: `1px solid ${T.borderSubtle}` }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 13 }}>
            <span style={{ font: `700 16px/1 ${T.display}`, letterSpacing: '-0.01em', color: T.fg }}>Tenexity</span>
            <span style={{ font: `600 8.5px/1 ${T.mono}`, letterSpacing: '0.1em', color: T.brandDeep, background: T.brandSoft, padding: '3px 5px', borderRadius: 3 }}>OS</span>
            <span style={{ font: `500 11px/1 ${T.mono}`, color: T.tertiary, marginLeft: 2 }}>· Artifacts</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, height: 34, padding: '0 11px', borderRadius: T.rMd, border: `1px solid ${T.borderDefault}`, background: T.bg }}>
            <Icon name="search" size={14} color={T.tertiary} />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a file…" style={{ flex: 1, border: 'none', outline: 'none', background: 'transparent', font: `400 12.5px/1 ${T.sans}`, color: T.fg }} />
            {qDict.supported && <MicButton size={24} listening={qDict.listening} onClick={qDict.toggle} title="Dictate search" />}
          </div>
        </div>
        <div style={{ flex: 1, overflow: 'auto', padding: '10px 10px 24px' }}>
          {filtered.map((g) => (
            <div key={g.project} style={{ marginBottom: 14 }}>
              <div style={{ padding: '6px 8px', font: `600 10px/1 ${T.mono}`, letterSpacing: '0.08em', textTransform: 'uppercase', color: T.tertiary }}>{g.project}</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                {g.items.map((a) => {
                  const on = a.id === active;
                  return (
                    <button key={a.id} onClick={() => select(a.id)} style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '8px 9px', borderRadius: T.rMd, border: 'none', cursor: 'pointer', textAlign: 'left', width: '100%', background: on ? T.brandSoft : 'transparent' }}>
                      <TypeBadge type={a.type} />
                      <span style={{ flex: 1, minWidth: 0, font: `${on ? 600 : 500} 12.5px/1.3 ${T.sans}`, color: on ? T.brandDeep : T.fg, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{a.name}</span>
                      {a.primary && <span style={{ width: 6, height: 6, borderRadius: '50%', background: T.brand, flexShrink: 0 }} />}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </aside>

      {/* main */}
      <main style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <header style={{ flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, padding: '14px 24px', borderBottom: `1px solid ${T.borderSubtle}`, background: T.raised }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, font: `500 11px/1 ${T.mono}`, color: T.tertiary, marginBottom: 5 }}>
              <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{art ? art.project : ''}</span>
              {art && art.node && <React.Fragment><Icon name="chevronRight" size={11} color={T.tertiary} /><span>{art.node}</span></React.Fragment>}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <TypeBadge type={art ? art.type : 'md'} big />
              <h1 style={{ margin: 0, font: `600 17px/1.2 ${T.mono}`, color: T.fg, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{art ? art.name : 'Artifact'}</h1>
              {art && art.agent && <span style={{ font: `400 12px/1 ${T.sans}`, color: T.tertiary }}>· {art.agent}</span>}
              {art && art.conf && typeof ConfidencePill !== 'undefined' && <ConfidencePill band={art.conf} />}
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 9, flexShrink: 0 }}>
            {art && art.updated && <span style={{ font: `400 11.5px/1 ${T.mono}`, color: T.tertiary }}>updated {art.updated}</span>}
            {art && art.content && <Btn variant="secondary" size="sm" onClick={copy}>{copied ? <React.Fragment><Icon name="check" size={13} color={T.success} /> Copied</React.Fragment> : 'Copy'}</Btn>}
            <Btn variant="secondary" size="sm" onClick={() => window.print()}>Download</Btn>
          </div>
        </header>

        <div style={{ flex: 1, overflow: 'auto' }}>
          <div style={{ maxWidth: isDoc ? 1080 : 1000, margin: '0 auto', padding: isDoc ? '34px 40px 80px' : '26px 32px 80px', display: 'flex', gap: 36 }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              {isDoc ? (
                <article style={{ background: T.raised, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rXl, padding: '40px 48px', boxShadow: T.shadowXs }}>
                  <FileBody art={art} onHeadings={setHeadings} />
                </article>
              ) : <FileBody art={art} />}
            </div>
            {isDoc && headings.length > 2 && (
              <nav style={{ width: 188, flexShrink: 0, position: 'sticky', top: 0, alignSelf: 'flex-start', display: 'flex', flexDirection: 'column', gap: 7, paddingTop: 6 }}>
                <span style={{ font: `600 10px/1 ${T.mono}`, letterSpacing: '0.08em', textTransform: 'uppercase', color: T.tertiary, marginBottom: 2 }}>On this page</span>
                {headings.map((h) => (
                  <a key={h.id} href={'#' + h.id} onClick={(e) => { e.preventDefault(); const el = document.getElementById(h.id); if (!el) return; let sc = el.parentElement; while (sc && sc.scrollHeight <= sc.clientHeight) sc = sc.parentElement; if (sc) sc.scrollTo({ top: sc.scrollTop + el.getBoundingClientRect().top - sc.getBoundingClientRect().top - 16, behavior: 'smooth' }); }}
                    style={{ font: `400 12px/1.4 ${T.sans}`, color: T.tertiary, textDecoration: 'none', paddingLeft: h.level === 3 ? 12 : 0 }}>{h.text}</a>
                ))}
              </nav>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

Object.assign(window, { Markdown, ART, openArtifact, registerArtifacts, ArtifactViewer, TypeBadge, artGroups });
