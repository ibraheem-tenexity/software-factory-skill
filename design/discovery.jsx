// discovery.jsx — "the factory comes to you": web enrichment, codebase
// discovery, org development conventions, and brand theme. All four reuse the
// same interaction contract: the agent does VISIBLE work (MiniLog), then
// presents ai-tint findings with a SOURCE LABEL per field (never an asserted
// confidence level — we have no evidence-derived backing for one) — the user
// confirms before anything is saved. Nothing writes silently.
//
//   • MiniLog            — compact streaming agent log (dark panel, mono).
//   • EnrichFromWeb      — the "We already know you" lookup: website → log →
//                          confirm card. Used by first-time intake (optionC)
//                          and Org admin → Company profile ("Enrich from web").
//   • DiscoverySection   — codebase discovery: crawl a repo → generated
//                          AGENTS.md / CLAUDE.md / integrations.md → knowledge base.
//   • ConventionsSection — repo / framework / standards → compiled into the
//                          org's AGENTS.md, injected into every build agent.
//   • ThemeSection       — Brand & theme: process a website → token pack
//                          (colors / fonts / logo) applied to every generated app.

// ---- compact streaming log ---------------------------------------------------
// Same contract as ProcessingScreen's ingest log, shrunk for in-card use:
// ONE state var (n); everything derived. Lines appear on an interval; onDone
// fires once, ~650ms after the last line.
function MiniLog({ lines, label = 'Agent log', speed = 560, maxHeight = 148, onDone }) {
  const [n, setN] = React.useState(0);
  const fired = React.useRef(false);
  const ref = React.useRef(null);
  React.useEffect(() => {
    const t = setInterval(() => setN((x) => (x >= lines.length ? x : x + 1)), speed);
    return () => clearInterval(t);
  }, [lines.length]);
  React.useEffect(() => { const el = ref.current; if (el) el.scrollTop = el.scrollHeight; }, [n]);
  const done = n >= lines.length;
  React.useEffect(() => { if (done && !fired.current) { fired.current = true; const t = setTimeout(() => onDone && onDone(), 650); return () => clearTimeout(t); } }, [done]);
  return (
    <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, background: T.ink, overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '8px 12px', borderBottom: '1px solid #2a2a30' }}>
        <span style={{ width: 7, height: 7, borderRadius: '50%', background: done ? T.success : T.brand }} />
        <CategoryLabel style={{ color: '#a8a8b0' }}>{label}</CategoryLabel>
      </div>
      <div ref={ref} style={{ maxHeight, overflow: 'auto', padding: '10px 13px', display: 'flex', flexDirection: 'column', gap: 6 }}>
        {lines.slice(0, n).map((l, i) => (
          <div key={i} style={{ display: 'flex', gap: 9, font: `400 12px/1.5 ${T.mono}`, color: i === n - 1 && !done ? '#fff' : '#9a9aa2', animation: 'sfRise .25s var(--ease-out, ease) both' }}>
            <span style={{ color: T.success, flexShrink: 0 }}>{i === n - 1 && !done ? '›' : '✓'}</span>
            <span>{l}</span>
          </div>
        ))}
        {!done && <div style={{ display: 'flex', gap: 9, font: `400 12px/1.5 ${T.mono}`, color: '#6a6a72' }}><span className="sf-spin" style={{ display: 'inline-flex' }}><Icon name="refresh" size={12} color="#6a6a72" /></span><span>working…</span></div>}
      </div>
    </div>
  );
}

// ---- "We already know you" — company prefill from web search -----------------
// One source label per field — unconfirmed values keep the ai-tint treatment
// until the user accepts. The demo data stands in for the live enrich endpoint
// (Exa quick / Fusion deep — see design/TICKETS.md CBT-1).
const LOOKUP_LINES = (domain) => [
  `Reading ${domain}…`,
  'About page parsed — company profile found.',
  'Checking the careers page for systems in use…',
  'Epicor referenced in 2 job posts — likely the ERP.',
  'Cross-checking linkedin.com/company…',
  'Pulling brand assets (logo, palette)…',
];
const FOUND_ROWS = [
  { key: 'name', label: 'Company', value: 'Acme Industrial Supply', src: 'acme-industrial.com' },
  { key: 'industry', label: 'Industry', value: 'Industrial Distribution · MRO / maintenance', src: 'acme-industrial.com/about' },
  { key: 'hq', label: 'Headquarters', value: 'Cleveland, OH · 6 branches', src: 'linkedin.com' },
  { key: 'size', label: 'Headcount', value: '51–200 people', src: 'linkedin.com' },
  { key: 'systems', label: 'Systems in use', value: 'Epicor (ERP) — referenced in 2 job posts', src: 'acme-industrial.com/careers' },
];
const FOUND_COLORS = ['#1447A8', '#E8A13D', '#1C1E21'];
// Values the parent form applies on accept (optionC fresh-mode shape).
const FOUND_VALUES = { name: 'Acme Industrial Supply', industry: 'dist', sub: ['MRO / maintenance'], size: '51–200', revenue: '$10M–$50M', site: 'acme-industrial.com', ints: ['epicor'] };

function FoundCompanyCard({ onAccept, onRetry }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
        <Sparkle size={12} color={T.brand} /><CategoryLabel tone="brand">What we found on the web</CategoryLabel>
        <span style={{ font: `400 11.5px/1.3 ${T.sans}`, color: T.tertiary }}>· confirm what’s right — nothing saves until you do</span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {FOUND_ROWS.map((r) => (
          <div key={r.key} className="ai-tint" style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 12px', borderRadius: T.rMd }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <CategoryLabel style={{ display: 'block', marginBottom: 3, fontSize: 9.5 }}>{r.label}</CategoryLabel>
              <span style={{ font: `500 13px/1.35 ${T.sans}`, color: T.fg }}>{r.value}</span>
            </div>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, flexShrink: 0, font: `400 10.5px/1 ${T.mono}`, color: T.tertiary }}><Icon name="link" size={10} color={T.tertiary} />{r.src}</span>
          </div>
        ))}
        <div className="ai-tint" style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 12px', borderRadius: T.rMd }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <CategoryLabel style={{ display: 'block', marginBottom: 4, fontSize: 9.5 }}>Brand palette</CategoryLabel>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              {FOUND_COLORS.map((c) => <span key={c} title={c} style={{ width: 18, height: 18, borderRadius: 5, background: c, border: `1px solid ${T.borderSubtle}` }} />)}
              <span style={{ font: `400 11px/1.3 ${T.sans}`, color: T.tertiary, marginLeft: 4 }}>pulled too — applied under Brand &amp; theme</span>
            </span>
          </div>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, flexShrink: 0, font: `400 10.5px/1 ${T.mono}`, color: T.tertiary }}><Icon name="link" size={10} color={T.tertiary} />site css</span>
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <button onClick={onRetry} style={{ font: `500 12px/1 ${T.sans}`, color: T.tertiary, background: 'none', border: 'none', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 5 }}>
          <Icon name="refresh" size={12} color={T.tertiary} /> Not right — look again
        </button>
        <Btn variant="primary" onClick={onAccept}><Icon name="check" size={14} color="#fff" /> Use these details</Btn>
      </div>
    </div>
  );
}

function EnrichFromWeb({ domain = 'acme-industrial.com', onAccept, onSkip }) {
  const [stage, setStage] = React.useState('idle'); // idle | running | found
  const [site, setSite] = React.useState(domain);
  const canLook = site.trim().length > 3;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {stage === 'idle' && (
        <React.Fragment>
          <div style={{ display: 'flex', gap: 9, alignItems: 'flex-end', flexWrap: 'wrap' }}>
            <div style={{ flex: 1, minWidth: 220 }}>
              <Field label="Company website" hint="We’ll pull the public profile — you confirm before anything saves.">
                <TextInput value={site} onChange={setSite} placeholder="yourcompany.com" />
              </Field>
            </div>
            <Btn variant="primary" onClick={() => setStage('running')} disabled={!canLook} title={canLook ? 'Look up this company on the web' : 'Enter a website first'}>
              <Icon name="globe" size={14} color="#fff" /> Find my company
            </Btn>
          </div>
          {onSkip && <button onClick={onSkip} style={{ alignSelf: 'flex-start', font: `500 12px/1 ${T.sans}`, color: T.tertiary, background: 'none', border: 'none', cursor: 'pointer' }}>Skip — I’ll type everything myself</button>}
        </React.Fragment>
      )}
      {stage === 'running' && <MiniLog lines={LOOKUP_LINES(site.trim())} label="Looking your company up" onDone={() => setStage('found')} />}
      {stage === 'found' && <FoundCompanyCard onAccept={() => onAccept && onAccept({ ...FOUND_VALUES, site: site.trim() })} onRetry={() => setStage('idle')} />}
    </div>
  );
}

// ---- Codebase discovery (org admin) ------------------------------------------
// For companies already doing custom dev: point discovery agents at the repo,
// they generate the agent files (AGENTS.md / CLAUDE.md / integrations.md) that
// teach the factory how to extend what the company already has. Read-only.
const CRAWL_LINES = (repo) => [
  `Cloning ${repo} (shallow)…`,
  'Mapped 214 files · Next.js 14 + FastAPI services.',
  'Read package manifests & CI workflows…',
  'Detected integrations: Epicor (REST), Stripe, SendGrid.',
  'Drafting AGENTS.md from repo conventions…',
  'Drafting CLAUDE.md — build, test & deploy commands…',
  'Wrote integrations.md — 3 external systems documented.',
];
const DISCOVERY_DOCS = [
  { name: 'AGENTS.md', desc: 'Repo architecture, conventions & extension points — how agents should extend this codebase.', src: 'repo tree + manifests' },
  { name: 'CLAUDE.md', desc: 'Build / test / deploy commands for coding agents, read from CI.', src: 'CI workflows' },
  { name: 'integrations.md', desc: 'Epicor REST, Stripe, SendGrid — endpoints, auth & environments.', src: 'import graph' },
];

function DiscoverySection() {
  const [stage, setStage] = React.useState('idle'); // idle | running | done
  const [repo, setRepo] = React.useState('github.com/acme-industrial/order-desk');
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {stage === 'idle' && (
        <React.Fragment>
          <div style={{ display: 'flex', gap: 9, alignItems: 'flex-end', flexWrap: 'wrap' }}>
            <div style={{ flex: 1, minWidth: 240 }}>
              <Field label="Repository" hint="Access tokens live in Secrets — discovery agents read only, never write.">
                <TextInput mono value={repo} onChange={setRepo} placeholder="github.com/your-org/your-repo" />
              </Field>
            </div>
            <Btn variant="primary" onClick={() => setStage('running')} disabled={repo.trim().length < 8}><Icon name="github" size={14} color="#fff" /> Run discovery</Btn>
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 9, padding: '11px 13px', borderRadius: T.rLg, border: `1px solid ${T.borderSubtle}`, background: T.sunken }}>
            <Icon name="bot" size={14} color={T.tertiary} style={{ marginTop: 1, flexShrink: 0 }} />
            <p style={{ margin: 0, font: `400 12px/1.55 ${T.sans}`, color: T.secondary }}>Discovery agents walk the repo — framework, manifests, CI, integrations — and write the agent files (<b style={{ color: T.fg }}>AGENTS.md</b>, <b style={{ color: T.fg }}>CLAUDE.md</b>, <b style={{ color: T.fg }}>integrations.md</b>) straight into your knowledge base. That’s how the factory learns to build to <i>your</i> conventions.</p>
          </div>
        </React.Fragment>
      )}
      {stage === 'running' && <MiniLog lines={CRAWL_LINES(repo.trim())} label="Discovery agents in your repo" onDone={() => setStage('done')} />}
      {stage === 'done' && (
        <React.Fragment>
          <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
            <Icon name="check" size={14} color={T.success} /><CategoryLabel style={{ color: T.success }}>Generated &amp; saved to knowledge base</CategoryLabel>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {DISCOVERY_DOCS.map((d) => (
              <div key={d.name} className="ai-tint" style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', borderRadius: T.rMd }}>
                <Icon name="file" size={15} color={T.brandDeep} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <span style={{ font: `600 12.5px/1.2 ${T.mono}`, color: T.fg }}>{d.name}</span>
                  <span style={{ display: 'block', font: `400 11.5px/1.4 ${T.sans}`, color: T.secondary, marginTop: 2 }}>{d.desc}</span>
                </div>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, flexShrink: 0, font: `400 10.5px/1 ${T.mono}`, color: T.tertiary }}><Icon name="link" size={10} color={T.tertiary} />{d.src}</span>
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
            <span style={{ font: `400 11.5px/1.4 ${T.sans}`, color: T.tertiary }}>Review them under Knowledge base — reused on every project.</span>
            <div style={{ display: 'flex', gap: 8 }}>
              <Btn variant="ghost" size="sm" onClick={() => setStage('idle')}>Add another repo</Btn>
              <Btn variant="secondary" size="sm" onClick={() => setStage('running')}><Icon name="refresh" size={13} /> Re-run discovery</Btn>
            </div>
          </div>
        </React.Fragment>
      )}
    </div>
  );
}

// ---- Development conventions (org admin) -------------------------------------
// Technical users tell the factory HOW to build: their repo, framework,
// commands, and standards. Compiled into the org's AGENTS.md and injected into
// every build agent's context — the factory builds to their conventions.
function ConventionsSection() {
  const [v, setV] = React.useState({
    repo: 'github.com/acme-industrial/order-desk',
    stack: 'Next.js 14 · FastAPI · Postgres',
    commands: 'pnpm i · pnpm test · pytest -q',
    standards: 'ESLint strict · conventional commits · no default exports · small PRs',
  });
  const [saved, setSaved] = React.useState(false);
  const timer = React.useRef(null);
  const save = () => { setSaved(true); clearTimeout(timer.current); timer.current = setTimeout(() => setSaved(false), 2200); };
  const set = (k) => (x) => setV((p) => ({ ...p, [k]: x }));
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <Field label="Primary repository"><TextInput mono value={v.repo} onChange={set('repo')} placeholder="github.com/your-org/your-repo" /></Field>
        <Field label="Framework & runtime"><TextInput value={v.stack} onChange={set('stack')} placeholder="e.g. Next.js · FastAPI · Postgres" /></Field>
        <Field label="Install / test commands" style={{ gridColumn: '1 / -1' }}><TextInput mono value={v.commands} onChange={set('commands')} placeholder="pnpm i · pnpm test · pytest -q" /></Field>
        <Field label="Coding standards" hint="Or drop a standards doc into the Knowledge base — the factory reads it." style={{ gridColumn: '1 / -1' }}>
          <TextArea rows={2} value={v.standards} onChange={set('standards')} placeholder="Lint rules, commit style, review expectations…" />
        </Field>
      </div>
      <div className="ai-tint" style={{ borderRadius: T.rLg, padding: '13px 15px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 9 }}>
          <Sparkle size={11} color={T.brandDeep} /><CategoryLabel tone="brand">What every build agent receives</CategoryLabel>
        </div>
        <pre style={{ margin: 0, font: `400 11.5px/1.7 ${T.mono}`, color: T.secondary, whiteSpace: 'pre-wrap' }}>
{`# AGENTS.md — ${'Acme Industrial Supply'} (org conventions)
Repo:       ${v.repo || '—'}
Stack:      ${v.stack || '—'}
Commands:   ${v.commands || '—'}
Standards:  ${v.standards || '—'}`}
        </pre>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
        <span style={{ font: `400 11.5px/1.4 ${T.sans}`, color: saved ? T.success : T.tertiary }}>{saved ? '✓ Saved — applied to the next build' : 'Injected into every build agent’s context. Edit anytime.'}</span>
        <Btn variant="primary" size="sm" onClick={save}>{saved ? <React.Fragment><Icon name="check" size={13} color="#fff" /> Saved</React.Fragment> : 'Save conventions'}</Btn>
      </div>
    </div>
  );
}

// ---- Brand & theme (org admin) -----------------------------------------------
// "Process theme from my website": crawl the site → token pack (colors, type,
// logo) with sources + confidence. Applied to Kimi K3 mockups and every app
// the factory builds for this org. Manual fallback: brand book in the KB.
const THEME_LINES = (domain) => [
  `Reading ${domain}…`,
  'Extracted palette from site stylesheets (4 colors).',
  'Identified type stack: Barlow Semi Condensed / Inter.',
  'Pulled logo from the site header (SVG).',
  'Cross-checked brand-guidelines.pdf in your knowledge base…',
];
const THEME_COLORS = [
  { role: 'Primary', hex: '#1447A8', src: 'site css' },
  { role: 'Accent', hex: '#E8A13D', src: 'site css' },
  { role: 'Background', hex: '#FAFAF8', src: 'site css' },
  { role: 'Ink', hex: '#1C1E21', src: 'site css' },
];
const THEME_FONTS = [
  { role: 'Headings', name: 'Barlow Semi Condensed', src: 'site css' },
  { role: 'Body', name: 'Inter', src: 'site css' },
];

function ThemeSection() {
  const [stage, setStage] = React.useState('idle'); // idle | running | found
  const [site, setSite] = React.useState('acme-industrial.com');
  const primary = THEME_COLORS[0].hex, accent = THEME_COLORS[1].hex, ink = THEME_COLORS[3].hex;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {stage === 'idle' && (
        <div style={{ display: 'flex', gap: 9, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 220 }}>
            <Field label="Website to read" hint="Palette, type, and logo — pulled with sources, applied to every app we build you.">
              <TextInput value={site} onChange={setSite} placeholder="yourcompany.com" />
            </Field>
          </div>
          <Btn variant="primary" onClick={() => setStage('running')} disabled={site.trim().length < 4}><Icon name="palette" size={14} color="#fff" /> Process theme from my website</Btn>
        </div>
      )}
      {stage === 'running' && <MiniLog lines={THEME_LINES(site.trim())} label="Reading your brand" onDone={() => setStage('found')} />}
      {stage === 'found' && (
        <React.Fragment>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            {/* palette */}
            <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, background: T.raised, padding: '13px 14px' }}>
              <CategoryLabel style={{ display: 'block', marginBottom: 10 }}>Palette</CategoryLabel>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {THEME_COLORS.map((c) => (
                  <div key={c.role} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span style={{ width: 22, height: 22, borderRadius: 6, background: c.hex, border: `1px solid ${T.borderSubtle}`, flexShrink: 0 }} />
                    <span style={{ width: 74, font: `500 12px/1 ${T.sans}`, color: T.fg }}>{c.role}</span>
                    <span style={{ flex: 1, font: `400 11px/1 ${T.mono}`, color: T.tertiary }}>{c.hex}</span>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, flexShrink: 0, font: `400 10.5px/1 ${T.mono}`, color: T.tertiary }}><Icon name="link" size={10} color={T.tertiary} />{c.src}</span>
                  </div>
                ))}
              </div>
            </div>
            {/* type + logo */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, background: T.raised, padding: '13px 14px' }}>
                <CategoryLabel style={{ display: 'block', marginBottom: 10 }}>Type</CategoryLabel>
                {THEME_FONTS.map((f) => (
                  <div key={f.role} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 7 }}>
                    <span style={{ width: 74, font: `500 12px/1 ${T.sans}`, color: T.fg }}>{f.role}</span>
                    <span style={{ flex: 1, font: `500 12.5px/1 ${T.sans}`, color: T.secondary }}>{f.name}</span>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, flexShrink: 0, font: `400 10.5px/1 ${T.mono}`, color: T.tertiary }}><Icon name="link" size={10} color={T.tertiary} />{f.src}</span>
                  </div>
                ))}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, background: T.raised, padding: '10px 14px' }}>
                <span style={{ width: 34, height: 34, borderRadius: 8, display: 'grid', placeItems: 'center', background: `repeating-linear-gradient(45deg, ${T.sunken}, ${T.sunken} 6px, ${T.bg} 6px, ${T.bg} 12px)` }}><Icon name="image" size={15} color={T.tertiary} /></span>
                <span style={{ flex: 1, font: `400 11.5px/1.4 ${T.sans}`, color: T.secondary }}><b style={{ color: T.fg }}>logo.svg</b></span>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, flexShrink: 0, font: `400 10.5px/1 ${T.mono}`, color: T.tertiary }}><Icon name="link" size={10} color={T.tertiary} />site header</span>
              </div>
            </div>
          </div>
          {/* live preview — the found theme on a generated app shell */}
          <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: 'hidden', background: T.raised }}>
            <CategoryLabel style={{ display: 'block', padding: '10px 14px 0' }}>Preview · your theme on a generated app</CategoryLabel>
            <div style={{ margin: 14, borderRadius: T.rMd, border: `1px solid ${T.borderSubtle}`, overflow: 'hidden' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '9px 13px', background: primary }}>
                <span style={{ width: 18, height: 18, borderRadius: 5, background: '#ffffff33', border: '1px solid #ffffff55' }} />
                <span style={{ font: `600 12.5px/1 ${T.display}`, color: '#fff' }}>Vendor Scorecard</span>
                <span style={{ flex: 1 }} />
                <span style={{ font: `500 10.5px/1 ${T.sans}`, color: '#ffffffcc' }}>Dashboard</span>
                <span style={{ font: `500 10.5px/1 ${T.sans}`, color: '#ffffffcc' }}>Vendors</span>
              </div>
              <div style={{ padding: '12px 13px', background: THEME_COLORS[2].hex, display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ font: `600 13px/1 ${T.sans}`, color: ink }}>On-time delivery</span>
                <span style={{ flex: 1 }} />
                <span style={{ font: `600 10.5px/1 ${T.mono}`, color: '#fff', background: accent, padding: '5px 9px', borderRadius: 6 }}>94.2% · Q2</span>
                <span style={{ font: `500 11px/1 ${T.sans}`, color: '#fff', background: primary, padding: '6px 11px', borderRadius: 7 }}>Export report</span>
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
            <span style={{ font: `400 11.5px/1.4 ${T.sans}`, color: T.tertiary }}>Applied to every Kimi K3 mockup and every app the factory builds for you. Have a brand book? <b style={{ color: T.secondary }}>brand-guidelines.pdf</b> is already in your Knowledge base as fallback.</span>
            <Btn variant="secondary" size="sm" onClick={() => setStage('idle')}><Icon name="refresh" size={13} /> Re-process</Btn>
          </div>
        </React.Fragment>
      )}
    </div>
  );
}

Object.assign(window, { MiniLog, EnrichFromWeb, DiscoverySection, ConventionsSection, ThemeSection });
