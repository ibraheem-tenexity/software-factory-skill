// admin.jsx — Tenexity OS, the internal platform-operator portal (distinct
// mono/terminal aesthetic). Access to all tenants, all projects, every agent
// prompt, and a tool/MCP registry. Faithful to factory.tenexity.ai.

/* ---- local nav icons (operator set) ---- */
const NAV_PATHS = {
  overview: 'M3 3h7v7H3z M14 3h7v7h-7z M14 14h7v7h-7z M3 14h7v7H3z',
  organizations: 'M3 21h18 M5 21V7l8-4v18 M19 21V11l-6-3 M9 9h0 M9 13h0 M9 17h0',
  users: 'M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2 M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M23 21v-2a4 4 0 0 0-3-3.87 M16 3.13a4 4 0 0 1 0 7.75',
  projects: 'M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z',
  newproject: 'M12 5v14 M5 12h14',
  agents: 'M12 8V4H8 M4 8h16a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2z M2 14h2 M20 14h2 M15 13v2 M9 13v2',
  tools: 'M14.7 6.3a4 4 0 0 0 5 5l-9 9a2 2 0 0 1-3-3l9-9a4 4 0 0 0-2-2z',
  factories: 'M2 20h20 M4 20V8l5 4V8l5 4V8l5 4v8',
  book: 'M4 19.5A2.5 2.5 0 0 1 6.5 17H20 M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z',
  artifacts: 'M12 2L2 7l10 5 10-5-10-5z M2 17l10 5 10-5 M2 12l10 5 10-5',
  symphony: 'M6 3v12 M18 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z M6 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6z M18 9V3l-9 2',
  settings: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1V21a2 2 0 1 1-4 0v-.1A1.6 1.6 0 0 0 6.6 19l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0-1.1-2.7H2a2 2 0 1 1 0-4h.1A1.6 1.6 0 0 0 3.2 6.6l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 2.7-1.1V2a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 2.7 1.1l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8',
};
function NavIcon({ name, size = 17, color = 'currentColor' }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    {NAV_PATHS[name].split(' M').map((s, i) => <path key={i} d={i === 0 ? s : 'M' + s} />)}</svg>;
}

/* ---- data ---- */
const ADMIN_CLIENTS = [
  { in: 'ME', name: 'Meridian Industrial Supply', projects: 1, tickets: 742, spend: '$29.31', last: '—' },
  { in: 'VA', name: 'vamac', projects: 3, tickets: 865, spend: '$124.55', last: '—' },
  { in: 'AC', name: 'Acme Corp', projects: 3, tickets: 1600, spend: '$46.31', last: '1 month ago' },
  { in: 'BR', name: 'Brassica Markets', projects: 1, tickets: 1, spend: '$2432.02', last: '—' },
  { in: 'PI', name: 'Pinnacle Foodservice Distributors', projects: 2, tickets: 9, spend: '$4657.55', last: '—' },
  { in: 'NI', name: 'Nick.', projects: 4, tickets: 409, spend: '$1207.23', last: '—' },
  { in: 'CA', name: 'Cardinal Logistics', projects: 1, tickets: 0, spend: '$1963.86', last: '—' },
  { in: 'BE', name: 'Beacon Industrial Supply', projects: 1, tickets: 1, spend: '$5597.28', last: '—' },
  { in: 'HA', name: 'Halcyon Bicycles', projects: 1, tickets: 0, spend: '$807.35', last: '—' },
  { in: 'TE', name: 'test', projects: 2, tickets: 35, spend: '$107.97', last: '—' },
  { in: 'LA', name: 'Lattice Climbing Co.', projects: 1, tickets: 0, spend: '$3460.68', last: '—' },
  { in: 'RI', name: 'Riverbend Hardware Distribution', projects: 1, tickets: 1, spend: '$1.00', last: '—' },
];
const PHASE_TONE = { REVIEW: 'info', PLANNING: 'warning', BUILDING: 'brand', TRIAGE: 'neutral', INTAKE: 'neutral', LIVE: 'success' };
const ADMIN_PROJECTS = [
  { name: 'Beacon Industrial — SAP S/4 Bridge', client: 'Beacon Industrial Supply', owner: 'Harper Nguyen', factory: 'wms-erp', phase: 'REVIEW', tasks: '5/6', f: '1.6', auto: 68, last: '8 seconds ago' },
  { name: 'Halcyon — Insights Dashboard', client: 'Halcyon Bicycles', owner: 'Priya Raman', factory: 'data', phase: 'PLANNING', tasks: '5/5', f: '2.0', auto: 62, last: '12 seconds ago' },
  { name: 'Distributor Intelligence Platform', client: 'Acme Corp', owner: 'Marco Devlin', factory: 'software-factory', phase: 'BUILDING', tasks: '0/0', f: '2.1', auto: 60, last: '44 seconds ago' },
  { name: 'test', client: 'test', owner: 'Harper Nguyen', factory: 'operations', phase: 'TRIAGE', tasks: '36/70', f: '2.4', auto: 55, last: '57 seconds ago' },
  { name: 'Lattice — Member Portal', client: 'Lattice Climbing Co.', owner: 'Sol Adeyemi', factory: 'software', phase: 'REVIEW', tasks: '8/8', f: '1.4', auto: 78, last: '1 minute ago' },
  { name: 'Brassica — Wholesale Order Intake', client: 'Brassica Markets', owner: 'Priya Raman', factory: 'operations', phase: 'REVIEW', tasks: '5/6', f: '2.4', auto: 71, last: '1 minute ago' },
  { name: 'Cardinal 3PL — Carrier Rate Sync', client: 'Cardinal Logistics', owner: 'Marco Devlin', factory: 'integration', phase: 'BUILDING', tasks: '4/4', f: '2.5', auto: 70, last: '1 minute ago' },
  { name: 'order entry', client: 'Nick.', owner: 'Sol Adeyemi', factory: 'edi-trading-partner', phase: 'BUILDING', tasks: '22/27', f: '1.5', auto: 55, last: '2 minutes ago' },
  { name: 'Pinnacle Foods — EDI Backlog', client: 'Pinnacle Foodservice Distributors', owner: 'Harper Nguyen', factory: 'edi-trading-partner', phase: 'BUILDING', tasks: '7/8', f: '2.3', auto: 74, last: '2 minutes ago' },
  { name: 'Northwind Portal', client: 'Acme Corp', owner: 'Marco Devlin', factory: 'software', phase: 'INTAKE', tasks: '1/763', f: '2.1', auto: 55, last: '1 month ago' },
  { name: 'oe', client: 'vamac', owner: 'Priya Raman', factory: 'software', phase: 'INTAKE', tasks: '3/842', f: '1.9', auto: 55, last: '1 month ago' },
  { name: 'RAG model', client: 'Acme Corp', owner: 'Sol Adeyemi', factory: 'software', phase: 'INTAKE', tasks: '4/842', f: '2.0', auto: 55, last: '1 month ago' },
];
const ROSTER = [
  { name: 'Orchestrator', callsign: 'ORCHESTRATOR.MAIN', sign: 'ATLAS', desc: 'Main orchestrator across all factories', model: 'claude-opus-4', cost: 3, success: 97, on: true,
    prompt: 'You are Atlas, the top-level orchestrator for the Tenexity factory. You receive a customer project with its collected context and decompose it across the pipeline: provision → research → product → architect → design → tickets → build → test → deploy. Spawn and supervise specialist sub-agents, enforce the Stage gates, keep spend under the project cap, and surface a single source of truth to the Concierge. Never skip a gate without explicit human approval.' },
  { name: 'Product Manager', callsign: 'PM.LEAD', sign: 'HORIZON', desc: 'Translates conversation into specs', model: 'claude-sonnet-4', cost: 2, success: 94, on: true,
    prompt: 'You are Horizon, the Product Manager. Convene the product council and reconcile research findings, the company profile, and the customer’s process notes into a single PRD.md. State the problem, v1 goals, primary users, in/out of scope, and success metrics. Cite the source for every requirement and attach a confidence band. Prefer the smallest v1 that proves value.' },
  { name: 'Design Lead', callsign: 'DESIGN.LEAD', sign: 'CHROMA', desc: 'Brand, layout, and design system', model: 'gpt-5-thinking', cost: 3, success: 92, on: true,
    prompt: 'You are Chroma, the Design Lead. Produce the screen designs the build agents implement. Always use the Tenexity design system: brand #1A7BFF, Hanken Grotesk / Georgia / JetBrains Mono, the confidence cascade, and the archetype library. Map each screen to an archetype, never invent new patterns, and hand off annotated specs.' },
  { name: 'Marketing Lead', callsign: 'MARKETING.LEAD', sign: 'SIREN', desc: 'Positioning, ads, content', model: 'gpt-5-thinking', cost: 2, success: 90, on: true,
    prompt: 'You are Siren, the Marketing Lead. Craft positioning, launch copy, and in-app content for shipped projects. Match the customer’s voice and industry. Keep claims grounded in what the build actually does.' },
  { name: 'Proposal Lead', callsign: 'PROPOSAL.LEAD', sign: 'TENDER', desc: 'Pricing, contracts, scope', model: 'claude-sonnet-4', cost: 2, success: 93, on: true,
    prompt: 'You are Tender, the Proposal Lead. Turn scoped projects into pricing, SOWs, and contracts. Be explicit about assumptions and out-of-scope items. Flag anything that materially changes cost back to the orchestrator.' },
  { name: 'DevOps Lead', callsign: 'DEVOPS.LEAD', sign: 'FORGE', desc: 'Infra, CI, secrets, deploys', model: 'claude-sonnet-4', cost: 2, success: 95, on: true,
    prompt: 'You are Forge, the DevOps Lead. Provision infrastructure, wire CI, manage secrets, and run deploys. Never print secret values. Block deploy until the Playwright suite is green and the dependency keys are resolved (MCP, mock, or user-provided).' },
  { name: 'Operations Lead', callsign: 'OPS.LEAD', sign: 'GARRISON', desc: 'Internal tools and runbooks', model: 'claude-sonnet-4', cost: 2, success: 93, on: false,
    prompt: 'You are Garrison, the Operations Lead. Build internal tools and author runbooks for the delivered system. Document every operational assumption and escalate gaps.' },
  { name: 'Data Lead', callsign: 'DATA.LEAD', sign: 'MATRIX', desc: 'Pipelines, warehouses, schemas', model: 'claude-sonnet-4', cost: 2, success: 91, on: false,
    prompt: 'You are Matrix, the Data Lead. Design schemas, build pipelines, and model warehouses. Favor normalized models with explicit migrations and an audit trail on every write.' },
  { name: 'EDI Lead', callsign: 'EDI.LEAD', sign: 'LEDGER', desc: 'Trading-partner mappings: 850, 855, 856, 810, 997', model: 'claude-sonnet-4', cost: 2, success: 95, on: true,
    prompt: 'You are Ledger, the EDI Lead. Implement trading-partner mappings for X12 850, 855, 856, 810, and 997. Validate against partner specs, handle acknowledgements, and never silently drop a segment.' },
  { name: 'ERP Integration Lead', callsign: 'ERP.LEAD', sign: 'CONDUIT', desc: 'SAP, NetSuite, Oracle, Epicor bridges', model: 'claude-sonnet-4', cost: 2, success: 90, on: true,
    prompt: 'You are Conduit, the ERP Integration Lead. Build read/write bridges to SAP, NetSuite, Oracle, and Epicor. Respect each ERP’s rate limits, reconcile on idempotency keys, and write back only after human-or-rule approval.' },
  { name: 'WMS Lead', callsign: 'WMS.LEAD', sign: 'CARGO', desc: 'Manhattan, Blue Yonder, High Jump, Körber bridges', model: 'claude-sonnet-4', cost: 2, success: 89, on: false,
    prompt: 'You are Cargo, the WMS Lead. Integrate with Manhattan, Blue Yonder, High Jump, and Körber. Model receiving, putaway, picking, and shipping events with full traceability.' },
  { name: 'Pricing & Margin Lead', callsign: 'PRICING.LEAD', sign: 'PROFIT', desc: 'Tiered pricing, contract pricing, margin leakage', model: 'claude-sonnet-4', cost: 2, success: 91, on: false,
    prompt: 'You are Profit, the Pricing & Margin Lead. Implement tiered and contract pricing and detect margin leakage. Always route discounts past policy thresholds to an approval gate.' },
];
const MCP_TOOLS = [
  { name: 'Epicor MCP', type: 'MCP', provider: 'Epicor Kinetic', scope: 'orders · SKUs · pricing', status: 'connected', used: 14, auth: 'OAuth' },
  { name: 'Supabase', type: 'MCP', provider: 'Supabase', scope: 'postgres · auth · storage', status: 'connected', used: 22, auth: 'service key' },
  { name: 'GitHub', type: 'MCP', provider: 'GitHub', scope: 'repos · PRs · actions', status: 'connected', used: 24, auth: 'App' },
  { name: 'OpenAI', type: 'API', provider: 'OpenAI', scope: 'completions · embeddings', status: 'connected', used: 24, auth: 'API key' },
  { name: 'Stripe', type: 'MCP', provider: 'Stripe', scope: 'payments · invoices', status: 'connected', used: 6, auth: 'restricted key' },
  { name: 'Playwright', type: 'native', provider: 'Tenexity', scope: 'e2e browser testing', status: 'connected', used: 24, auth: 'none' },
  { name: 'Salesforce', type: 'MCP', provider: 'Salesforce', scope: 'CRM · opportunities', status: 'available', used: 0, auth: 'OAuth' },
  { name: 'NetSuite', type: 'MCP', provider: 'Oracle NetSuite', scope: 'ERP · ledger', status: 'available', used: 0, auth: 'TBA' },
  { name: 'X12 EDI Gateway', type: 'HTTP', provider: 'Tenexity', scope: '850/855/856/810/997', status: 'connected', used: 5, auth: 'mTLS' },
  { name: 'Vercel', type: 'MCP', provider: 'Vercel', scope: 'deploys · domains', status: 'connected', used: 19, auth: 'token' },
];

/* ---- shared bits ---- */
function Mono({ children, style }) { return <span style={{ font: `500 11px/1 ${T.mono}`, letterSpacing: '0.04em', color: T.tertiary, ...style }}>{children}</span>; }
function ColHead({ children, style }) { return <span style={{ font: `600 10.5px/1 ${T.mono}`, letterSpacing: '0.08em', textTransform: 'uppercase', color: T.tertiary, ...style }}>{children}</span>; }
function InitSquare({ t }) { return <span style={{ width: 28, height: 28, flexShrink: 0, borderRadius: 6, display: 'grid', placeItems: 'center', border: `1px solid ${T.borderSubtle}`, background: T.sunken, font: `600 10px/1 ${T.mono}`, color: T.secondary }}>{t}</span>; }
function PhasePill({ phase }) {
  const tone = { info: [T.brandSoft, T.brandDeep], warning: [T.warningSoft, T.warning], brand: [T.brandSoft, T.brandDeep], neutral: [T.sunken, T.secondary], success: [T.successSoft, T.success] }[PHASE_TONE[phase] || 'neutral'];
  return <span style={{ font: `600 10px/1 ${T.mono}`, letterSpacing: '0.06em', color: tone[1], background: tone[0], border: `1px solid ${tone[1]}22`, padding: '4px 7px', borderRadius: 4 }}>{phase}</span>;
}
function AdminBtn({ children, primary, onClick, title }) {
  return <button onClick={onClick} title={title} style={{ display: 'inline-flex', alignItems: 'center', gap: 7, height: 36, padding: '0 14px', cursor: 'pointer',
    font: `600 11.5px/1 ${T.mono}`, letterSpacing: '0.05em', textTransform: 'uppercase', borderRadius: T.rMd,
    border: `1px solid ${primary ? 'transparent' : T.borderDefault}`, background: primary ? T.brand : T.raised, color: primary ? '#fff' : T.fg }}>{children}</button>;
}
function PageTitle({ title, sub, actions }) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, marginBottom: 22 }}>
      <div>
        <h1 style={{ font: `400 30px/1.1 ${T.display}`, letterSpacing: '-0.01em', color: T.fg, margin: 0 }}>{title}</h1>
        <p style={{ font: `400 13px/1.5 ${T.mono}`, color: T.tertiary, margin: '8px 0 0' }}>{sub}</p>
      </div>
      <div style={{ display: 'flex', gap: 10 }}>{actions}</div>
    </div>
  );
}
function CostDots({ n }) { return <span style={{ display: 'inline-flex', gap: 2 }}>{[0,1,2].map((i) => <span key={i} style={{ width: 5, height: 5, borderRadius: '50%', background: i < n ? T.fg : T.borderDefault }} />)}</span>; }
function MiniBar({ pct }) { return <span style={{ display: 'block', height: 4, borderRadius: 2, background: T.sunken, overflow: 'hidden' }}><span style={{ display: 'block', height: '100%', width: pct + '%', background: T.success }} /></span>; }

/* ---- views ---- */
function AdminClients() {
  return (
    <React.Fragment>
      <PageTitle title="Organizations" sub="Customer organizations and their portfolios of factory projects." actions={<AdminBtn primary>+ New organization</AdminBtn>} />
      <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: 'hidden', background: T.raised }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 130px 140px 130px 130px', gap: 16, padding: '11px 18px', borderBottom: `1px solid ${T.borderSubtle}`, background: T.sunken }}>
          <ColHead>Organization</ColHead><ColHead>Active projects</ColHead><ColHead>In-flight tickets</ColHead><ColHead>Total spend</ColHead><ColHead style={{ textAlign: 'right' }}>Last activity</ColHead>
        </div>
        {ADMIN_CLIENTS.map((c, i) => (
          <button key={c.name} style={{ width: '100%', textAlign: 'left', cursor: 'pointer', background: T.raised, border: 'none', borderTop: i ? `1px solid ${T.borderSubtle}` : 'none',
            display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 130px 140px 130px 130px', gap: 16, padding: '14px 18px', alignItems: 'center' }}
            onMouseEnter={(e) => e.currentTarget.style.background = T.sunken} onMouseLeave={(e) => e.currentTarget.style.background = T.raised}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 11, minWidth: 0 }}><InitSquare t={c.in} /><span style={{ font: `600 14px/1.2 ${T.sans}`, color: T.fg, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.name}</span></span>
            <Mono style={{ color: T.fg, fontSize: 13 }}>{c.projects}</Mono>
            <Mono style={{ color: T.fg, fontSize: 13 }}>{c.tickets}</Mono>
            <Mono style={{ color: T.fg, fontSize: 13 }}>{c.spend}</Mono>
            <Mono style={{ textAlign: 'right' }}>{c.last}</Mono>
          </button>
        ))}
      </div>
    </React.Fragment>
  );
}

function AdminFilter({ children, w = 150 }) {
  return <div style={{ display: 'inline-flex', alignItems: 'center', gap: 7, height: 36, padding: '0 11px', width: w, justifyContent: 'space-between', borderRadius: T.rMd, border: `1px solid ${T.borderDefault}`, background: T.raised, font: `500 12px/1 ${T.sans}`, color: T.secondary, cursor: 'pointer' }}>{children}<Icon name="chevronDown" size={13} color={T.tertiary} /></div>;
}
function AdminSelectFilter({ value, onChange, options, allLabel, w = 150 }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, height: 36, padding: '0 6px 0 11px', width: w, borderRadius: T.rMd, border: `1px solid ${value ? T.brand : T.borderDefault}`, background: value ? T.brandSoft : T.raised }}>
      <select value={value} onChange={(e) => onChange(e.target.value)} style={{ flex: 1, minWidth: 0, border: 'none', outline: 'none', background: 'transparent', font: `500 12px/1 ${T.sans}`, color: value ? T.brandDeep : T.secondary, cursor: 'pointer', height: 34 }}>
        <option value="">{allLabel}</option>
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </span>
  );
}
function AdminProjectsView({ onOpen }) {
  const [type, setType] = React.useState('REAL');
  const [user, setUser] = React.useState('');
  const owners = Array.from(new Set(ADMIN_PROJECTS.map((p) => p.owner))).sort();
  const rows = ADMIN_PROJECTS.filter((p) => !user || p.owner === user);
  return (
    <React.Fragment>
      <PageTitle title="Projects" sub="Every project across every organization and factory pipeline." actions={<AdminBtn primary>+ New project</AdminBtn>} />
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14, flexWrap: 'wrap' }}>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 36, padding: '0 11px', borderRadius: T.rMd, border: `1px solid ${T.borderDefault}`, background: T.raised, flex: 1, minWidth: 200 }}>
          <Icon name="search" size={14} color={T.tertiary} /><span style={{ font: `400 12.5px/1 ${T.sans}`, color: T.tertiary }}>Search name, organization, user, factory…</span>
        </div>
        <AdminFilter>All organizations</AdminFilter><AdminFilter>All factories</AdminFilter><AdminSelectFilter value={user} onChange={setUser} options={owners} allLabel="All users" w={160} /><AdminFilter w={130}>All statuses</AdminFilter><AdminFilter w={120}>All modes</AdminFilter>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <ColHead>Project type</ColHead>
          <div style={{ display: 'inline-flex', padding: 2, borderRadius: T.rMd, background: T.sunken, border: `1px solid ${T.borderSubtle}` }}>
            {['ALL PROJECTS', 'REAL', 'DEMO/FAKE'].map((t) => <button key={t} onClick={() => setType(t)} style={{ font: `600 10.5px/1 ${T.mono}`, letterSpacing: '0.05em', padding: '6px 9px', borderRadius: 5, cursor: 'pointer', border: 'none', background: type === t ? T.fg : 'transparent', color: type === t ? '#fff' : T.tertiary }}>{t}</button>)}
          </div>
        </div>
        <Mono>{rows.length} of {ADMIN_PROJECTS.length}</Mono>
      </div>
      <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: 'hidden', background: T.raised }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.5fr) minmax(0,1.1fr) 130px 92px 64px 48px 56px 110px', gap: 12, padding: '11px 18px', borderBottom: `1px solid ${T.borderSubtle}`, background: T.sunken }}>
          <ColHead>Project</ColHead><ColHead>Organization</ColHead><ColHead>Factory</ColHead><ColHead>Phase</ColHead><ColHead>Tasks</ColHead><ColHead>F</ColHead><ColHead>Auto</ColHead><ColHead style={{ textAlign: 'right' }}>Last activity</ColHead>
        </div>
        {rows.map((p, i) => (
          <button key={p.name + i} onClick={() => onOpen && onOpen(p)} title={`Open ${p.name}`} style={{ width: '100%', textAlign: 'left', cursor: 'pointer', background: T.raised, border: 'none', borderTop: i ? `1px solid ${T.borderSubtle}` : 'none',
            display: 'grid', gridTemplateColumns: 'minmax(0,1.5fr) minmax(0,1.1fr) 130px 92px 64px 48px 56px 110px', gap: 12, padding: '13px 18px', alignItems: 'center' }}
            onMouseEnter={(e) => e.currentTarget.style.background = T.sunken} onMouseLeave={(e) => e.currentTarget.style.background = T.raised}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
              <span style={{ font: `600 13px/1.3 ${T.sans}`, color: T.fg, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.name}</span>
              <span style={{ font: `600 8.5px/1 ${T.mono}`, letterSpacing: '0.06em', color: T.brandDeep, background: T.brandSoft, padding: '3px 4px', borderRadius: 3, flexShrink: 0 }}>WORKSPACE</span>
            </span>
            <span style={{ minWidth: 0 }}>
              <span style={{ display: 'block', font: `400 12.5px/1.3 ${T.sans}`, color: T.secondary, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.client}</span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 5, marginTop: 3 }}><Avatar name={p.owner} size={14} tone="brand" /><Mono style={{ fontSize: 10, color: T.tertiary, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.owner}</Mono></span>
            </span>
            <Mono style={{ fontSize: 11.5 }}>{p.factory}</Mono>
            <PhasePill phase={p.phase} />
            <Mono style={{ color: T.fg, fontSize: 12 }}>{p.tasks}</Mono>
            <Mono style={{ color: T.fg, fontSize: 12 }}>{p.f}</Mono>
            <Mono style={{ color: T.fg, fontSize: 12 }}>{p.auto}</Mono>
            <Mono style={{ textAlign: 'right', fontSize: 11 }}>{p.last}</Mono>
          </button>
        ))}
      </div>
    </React.Fragment>
  );
}

function AgentCard({ a, onOpen }) {
  return (
    <button onClick={() => onOpen(a)} style={{ textAlign: 'left', cursor: 'pointer', background: T.raised, border: `1px solid ${a.callsign === 'ORCHESTRATOR.MAIN' ? T.brand : T.borderSubtle}`,
      borderRadius: T.rLg, padding: '16px 17px', display: 'flex', flexDirection: 'column', gap: 11, boxShadow: T.shadowXs }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ font: `600 15px/1.2 ${T.sans}`, color: T.brandDeep }}>{a.name}</span>
          <span style={{ width: 7, height: 7, borderRadius: '50%', background: a.on ? T.success : T.borderDefault }} />
        </div>
        <span style={{ font: `600 9.5px/1 ${T.mono}`, letterSpacing: '0.04em', color: T.secondary, background: T.sunken, border: `1px solid ${T.borderSubtle}`, padding: '4px 5px', borderRadius: 4 }}>{a.callsign}</span>
      </div>
      <p style={{ margin: 0, font: `400 13px/1.4 ${T.sans}`, color: T.secondary, minHeight: 36 }}>{a.desc}</p>
      <Mono style={{ fontSize: 10.5 }}>CALLSIGN · {a.sign}</Mono>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderTop: `1px solid ${T.borderSubtle}`, paddingTop: 10 }}>
        <Mono style={{ fontSize: 11, color: T.secondary }}>Model: {a.model}</Mono>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><Mono style={{ fontSize: 11 }}>Cost:</Mono><CostDots n={a.cost} /></span>
      </div>
      <div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 5 }}><ColHead style={{ fontSize: 9.5 }}>Autonomy / Success</ColHead><Mono style={{ fontSize: 11, color: T.fg }}>{a.success}%</Mono></div>
        <MiniBar pct={a.success} />
      </div>
    </button>
  );
}
function AdminAgents({ onOpen }) {
  return (
    <React.Fragment>
      <PageTitle title="Agent Roster" sub="Active autonomous workforce. Click a card to monitor or edit its prompt." actions={<AdminBtn>⌥ Configure repo</AdminBtn>} />
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '12px 16px', borderRadius: T.rLg, border: `1px solid ${T.warning}55`, background: T.warningSoft + '55', marginBottom: 20, flexWrap: 'wrap' }}>
        <span style={{ font: `600 10px/1 ${T.mono}`, letterSpacing: '0.06em', color: T.warning, background: T.warningSoft, border: `1px solid ${T.warning}55`, padding: '4px 7px', borderRadius: 4 }}>⚠ DRIFT DETECTED · 1</span>
        <Mono style={{ fontSize: 11.5 }}>pinned <b style={{ color: T.fg }}>0.0.0</b> · current <b style={{ color: T.fg }}>0.1.0</b> (Δ 1 minor)</Mono>
        <Mono style={{ flex: 1, fontSize: 11.5, color: T.danger }}>[MISSING] .tenexity/lockfile.json — repo never synced with tenexity standards</Mono>
        <Mono style={{ fontSize: 11 }}>ok 0 · missing 1 · modified 0 · outdated 0</Mono>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
        {ROSTER.map((a) => <AgentCard key={a.callsign} a={a} onOpen={onOpen} />)}
      </div>
    </React.Fragment>
  );
}

function AgentPromptPanel({ agent, onClose }) {
  const [prompt, setPrompt] = React.useState(agent.prompt);
  const promptDict = useDictation(prompt, setPrompt);
  const [tab, setTab] = React.useState('prompt');
  const dirty = prompt !== agent.prompt;
  return (
    <div onClick={onClose} style={{ position: 'absolute', inset: 0, zIndex: 60, background: 'rgba(9,12,18,0.45)', display: 'flex', justifyContent: 'flex-end', animation: 'sfRise .18s ease both' }}>
      <div onClick={(e) => e.stopPropagation()} style={{ width: 'min(560px, 100%)', height: '100%', background: T.raised, boxShadow: T.shadowMd, display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 20px', borderBottom: `1px solid ${T.borderSubtle}` }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ font: `600 16px/1.2 ${T.sans}`, color: T.fg }}>{agent.name}</span>
            <span style={{ width: 7, height: 7, borderRadius: '50%', background: agent.on ? T.success : T.borderDefault }} />
            <span style={{ font: `600 9.5px/1 ${T.mono}`, color: T.secondary, background: T.sunken, border: `1px solid ${T.borderSubtle}`, padding: '4px 5px', borderRadius: 4 }}>{agent.callsign}</span>
          </div>
          <button onClick={onClose} title="Close" style={{ width: 28, height: 28, display: 'grid', placeItems: 'center', borderRadius: T.rMd, border: 'none', background: 'transparent', color: T.tertiary, cursor: 'pointer' }}><Icon name="x" size={16} /></button>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 1, background: T.borderSubtle, borderBottom: `1px solid ${T.borderSubtle}` }}>
          {[['Model', agent.model], ['Callsign', agent.sign], ['Success', agent.success + '%']].map(([k, v]) => (
            <div key={k} style={{ background: T.raised, padding: '11px 16px' }}><ColHead style={{ display: 'block', marginBottom: 4 }}>{k}</ColHead><Mono style={{ color: T.fg, fontSize: 12.5 }}>{v}</Mono></div>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 2, padding: '8px 16px 0' }}>
          {[{ id: 'prompt', l: 'System prompt' }, { id: 'tools', l: 'Tools' }, { id: 'activity', l: 'Activity' }].map((t) => {
            const on = tab === t.id;
            return <button key={t.id} onClick={() => setTab(t.id)} style={{ position: 'relative', padding: '9px 12px', background: 'none', border: 'none', cursor: 'pointer', font: `${on ? 600 : 500} 12.5px/1 ${T.sans}`, color: on ? T.fg : T.tertiary }}>{t.l}{on && <span style={{ position: 'absolute', left: 8, right: 8, bottom: -1, height: 2, background: T.brand }} />}</button>;
          })}
        </div>
        <div style={{ flex: 1, overflow: 'auto', padding: '16px 20px' }}>
          {tab === 'prompt' && (
            <React.Fragment>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                <ColHead>System prompt</ColHead>
                <button style={{ display: 'inline-flex', alignItems: 'center', gap: 5, font: `500 11px/1 ${T.sans}`, color: T.brandDeep, background: 'none', border: 'none', cursor: 'pointer' }}><Sparkle size={10} color={T.brandDeep} /> Suggest improvements</button>
              </div>
              <div style={{ position: 'relative' }}>
                <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} style={{ width: '100%', boxSizing: 'border-box', minHeight: 280, padding: '13px 40px 13px 15px', borderRadius: T.rMd, resize: 'vertical', border: `1px solid ${T.borderDefault}`, background: T.bg, color: T.fg, font: `400 13px/1.65 ${T.mono}`, outline: 'none' }} />
                {promptDict.supported && <span style={{ position: 'absolute', right: 8, top: 8 }}><MicButton size={28} listening={promptDict.listening} onClick={promptDict.toggle} /></span>}
              </div>
              <Mono style={{ fontSize: 10.5, marginTop: 8, display: 'block' }}>{prompt.length} chars · version 0.1.0 · last edited by ATLAS</Mono>
            </React.Fragment>
          )}
          {tab === 'tools' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <ColHead style={{ marginBottom: 2 }}>Tools available to {agent.sign}</ColHead>
              {MCP_TOOLS.filter((t) => t.status === 'connected').slice(0, 5).map((t) => (
                <div key={t.name} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', borderRadius: T.rMd, border: `1px solid ${T.borderSubtle}`, background: T.bg }}>
                  <span style={{ font: `600 9px/1 ${T.mono}`, color: T.brandDeep, background: T.brandSoft, padding: '3px 5px', borderRadius: 3 }}>{t.type}</span>
                  <span style={{ flex: 1, font: `500 13px/1.2 ${T.sans}`, color: T.fg }}>{t.name}</span>
                  <Mono style={{ fontSize: 10.5 }}>{t.scope}</Mono>
                </div>
              ))}
            </div>
          )}
          {tab === 'activity' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {[['Claimed SF-05 · Discount approval workflow', '4m ago'], ['Pushed commit a3f91 to acme-quote-to-erp', '11m ago'], ['Opened PR #42 · pricing rules', '18m ago'], ['Prompt edited · +1 guardrail', '2h ago']].map((r, i) => (
                <div key={i} style={{ display: 'flex', gap: 10, paddingBottom: 10, borderBottom: i < 3 ? `1px solid ${T.borderSubtle}` : 'none' }}>
                  <span style={{ marginTop: 5, width: 6, height: 6, borderRadius: '50%', background: T.brand, flexShrink: 0 }} />
                  <span style={{ flex: 1, font: `400 13px/1.4 ${T.sans}`, color: T.secondary }}>{r[0]}</span>
                  <Mono style={{ fontSize: 10.5 }}>{r[1]}</Mono>
                </div>
              ))}
            </div>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '13px 20px', borderTop: `1px solid ${T.borderSubtle}` }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}><span style={{ width: 7, height: 7, borderRadius: '50%', background: agent.on ? T.success : T.borderDefault }} /><Mono style={{ fontSize: 11.5 }}>{agent.on ? 'active' : 'idle'}</Mono></span>
          <div style={{ display: 'flex', gap: 9 }}>
            <AdminBtn onClick={onClose}>Cancel</AdminBtn>
            <AdminBtn primary onClick={onClose}>{dirty ? 'Save prompt' : 'Saved'}</AdminBtn>
          </div>
        </div>
      </div>
    </div>
  );
}

function AdminTools() {
  const TYPE_C = { MCP: [T.brandSoft, T.brandDeep], API: [T.cHighSoft, T.cHigh], native: [T.successSoft, T.success], HTTP: ['#f3e9fb', '#7a3ea8'] };
  return (
    <React.Fragment>
      <PageTitle title="Tool & MCP Registry" sub="Every tool, MCP server, and connector available to the factory’s agents." actions={<React.Fragment><AdminBtn>⟳ Sync registry</AdminBtn><AdminBtn primary>+ Register tool</AdminBtn></React.Fragment>} />
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 20 }}>
        <MetricCard label="Registered" value={MCP_TOOLS.length} hint="across all factories" accent />
        <MetricCard label="Connected" value={MCP_TOOLS.filter((t) => t.status === 'connected').length} hint="live & authenticated" />
        <MetricCard label="MCP servers" value={MCP_TOOLS.filter((t) => t.type === 'MCP').length} hint="model context protocol" />
        <MetricCard label="Available" value={MCP_TOOLS.filter((t) => t.status === 'available').length} hint="ready to connect" />
      </div>
      <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: 'hidden', background: T.raised }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 80px minmax(0,0.9fr) minmax(0,1fr) 120px 70px 90px', gap: 12, padding: '11px 18px', borderBottom: `1px solid ${T.borderSubtle}`, background: T.sunken }}>
          <ColHead>Tool / Server</ColHead><ColHead>Type</ColHead><ColHead>Provider</ColHead><ColHead>Scope</ColHead><ColHead>Auth</ColHead><ColHead>Used by</ColHead><ColHead style={{ textAlign: 'right' }}>Status</ColHead>
        </div>
        {MCP_TOOLS.map((t, i) => {
          const tc = TYPE_C[t.type] || TYPE_C.native;
          const connected = t.status === 'connected';
          return (
            <div key={t.name} style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 80px minmax(0,0.9fr) minmax(0,1fr) 120px 70px 90px', gap: 12, padding: '13px 18px', alignItems: 'center', borderTop: i ? `1px solid ${T.borderSubtle}` : 'none' }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
                <span style={{ width: 26, height: 26, flexShrink: 0, borderRadius: 6, display: 'grid', placeItems: 'center', background: T.sunken, border: `1px solid ${T.borderSubtle}`, font: `700 9px/1 ${T.mono}`, color: T.secondary }}>{t.name.slice(0, 2).toUpperCase()}</span>
                <span style={{ font: `600 13px/1.2 ${T.sans}`, color: T.fg, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{t.name}</span>
              </span>
              <span style={{ font: `600 9.5px/1 ${T.mono}`, letterSpacing: '0.04em', color: tc[1], background: tc[0], padding: '4px 5px', borderRadius: 4, justifySelf: 'start' }}>{t.type}</span>
              <span style={{ font: `400 12.5px/1.3 ${T.sans}`, color: T.secondary, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{t.provider}</span>
              <Mono style={{ fontSize: 11.5, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{t.scope}</Mono>
              <Mono style={{ fontSize: 11 }}>{t.auth}</Mono>
              <Mono style={{ fontSize: 12, color: t.used ? T.fg : T.tertiary }}>{t.used ? t.used + ' agents' : '—'}</Mono>
              <span style={{ justifySelf: 'end' }}>{connected ? <StatusPill tone="success">live</StatusPill> : <button style={{ font: `600 10.5px/1 ${T.mono}`, color: T.brandDeep, background: 'none', border: 'none', cursor: 'pointer' }}>CONNECT →</button>}</span>
            </div>
          );
        })}
      </div>
    </React.Fragment>
  );
}

function AdminOverview({ onNav, onOpenProject }) {
  return (
    <React.Fragment>
      <PageTitle title="Factory Overview" sub="Platform-wide pulse across every organization, project, and agent." actions={<AdminBtn primary onClick={() => onNav('projects')}>View all projects</AdminBtn>} />
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 18 }}>
        <MetricCard label="Organizations" value={ADMIN_CLIENTS.length} hint="active customer orgs" accent />
        <MetricCard label="Projects" value="24" hint="across all factories" />
        <MetricCard label="Agents active" value="27 / 55" hint="autonomous workforce" />
        <MetricCard label="Today burn" value="$0.00" hint="avg friction 1.95" />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1.3fr 1fr', gap: 14 }}>
        <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, background: T.raised, overflow: 'hidden' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '11px 16px', borderBottom: `1px solid ${T.borderSubtle}`, background: T.sunken }}><ColHead>Most active projects</ColHead><button onClick={() => onNav('projects')} style={{ font: `600 10.5px/1 ${T.mono}`, color: T.brandDeep, background: 'none', border: 'none', cursor: 'pointer' }}>ALL →</button></div>
          {ADMIN_PROJECTS.slice(0, 6).map((p, i) => (
            <button key={p.name + i} onClick={() => onOpenProject && onOpenProject(p)} title={`Open ${p.name}`} className="sf-artchip" style={{ width: '100%', textAlign: 'left', cursor: 'pointer', background: 'transparent', display: 'flex', alignItems: 'center', gap: 10, padding: '11px 16px', borderTop: i ? `1px solid ${T.borderSubtle}` : 'none', borderLeft: 'none', borderRight: 'none', borderBottom: 'none' }}>
              <span style={{ flex: 1, font: `500 13px/1.2 ${T.sans}`, color: T.fg, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.name}</span>
              <PhasePill phase={p.phase} /><Mono style={{ fontSize: 10.5, width: 80, textAlign: 'right' }}>{p.last}</Mono>
            </button>
          ))}
        </div>
        <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, background: T.raised, overflow: 'hidden' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '11px 16px', borderBottom: `1px solid ${T.borderSubtle}`, background: T.sunken }}><ColHead>Agent workforce</ColHead><button onClick={() => onNav('agents')} style={{ font: `600 10.5px/1 ${T.mono}`, color: T.brandDeep, background: 'none', border: 'none', cursor: 'pointer' }}>ROSTER →</button></div>
          {ROSTER.slice(0, 6).map((a, i) => (
            <div key={a.callsign} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '11px 16px', borderTop: i ? `1px solid ${T.borderSubtle}` : 'none' }}>
              <span style={{ width: 7, height: 7, borderRadius: '50%', background: a.on ? T.success : T.borderDefault }} />
              <span style={{ flex: 1, font: `500 13px/1.2 ${T.sans}`, color: T.fg }}>{a.name}</span>
              <Mono style={{ fontSize: 10.5 }}>{a.success}%</Mono>
            </div>
          ))}
        </div>
      </div>
    </React.Fragment>
  );
}

/* ---- access / invites ---- */
const ALLOWED = [
  { email: 'ibraheem@acme-industrial.com', type: 'New org', org: 'Acme Industrial Supply', role: 'Org admin', status: 'active' },
  { email: 'maya@acme-industrial.com', type: 'New org', org: 'Acme Industrial Supply', role: 'Member', status: 'active' },
  { email: 'ops@tenexity.ai', type: 'Tenexity', org: 'Tenexity', role: 'Operator', status: 'active' },
  { email: 'dana@brassica.com', type: 'New org', org: 'Brassica Markets', role: 'Org admin', status: 'invited' },
];

function InviteModal({ onClose }) {
  const [email, setEmail] = React.useState('');
  const [type, setType] = React.useState('New org');
  const [org, setOrg] = React.useState('');
  const [list, setList] = React.useState(ALLOWED);
  const valid = /\S+@\S+\.\S+/.test(email);
  const send = () => {
    if (!valid) return;
    setList((l) => [{ email, type, org: type === 'Tenexity' ? 'Tenexity' : (org || 'New organization'), role: type === 'Tenexity' ? 'Operator' : 'Org admin', status: 'invited' }, ...l]);
    setEmail(''); setOrg('');
  };
  return (
    <div onClick={onClose} style={{ position: 'absolute', inset: 0, zIndex: 60, background: 'rgba(9,12,18,0.45)', display: 'grid', placeItems: 'center', padding: 28, animation: 'sfRise .18s ease both' }}>
      <div onClick={(e) => e.stopPropagation()} style={{ width: 'min(620px, 100%)', maxHeight: '100%', background: T.raised, borderRadius: T.rXl, boxShadow: T.shadowMd, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 20px', borderBottom: `1px solid ${T.borderSubtle}` }}>
          <div><h2 style={{ font: `400 19px/1.2 ${T.display}`, color: T.fg, margin: 0 }}>Provide access</h2><Mono style={{ fontSize: 11, marginTop: 4, display: 'block' }}>Add a person to the sign-in allow-list</Mono></div>
          <button onClick={onClose} title="Close" style={{ width: 28, height: 28, display: 'grid', placeItems: 'center', borderRadius: T.rMd, border: 'none', background: 'transparent', color: T.tertiary, cursor: 'pointer' }}><Icon name="x" size={16} /></button>
        </div>
        <div style={{ padding: '18px 20px', display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end' }}>
            <Field label="Email address" style={{ flex: 1 }}><TextInput type="email" value={email} onChange={setEmail} placeholder="person@company.com" mono /></Field>
            <Field label="Access type" style={{ width: 150, flexShrink: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', height: 36, borderRadius: T.rMd, border: `1px solid ${T.borderDefault}`, background: T.raised, position: 'relative' }}>
                <select value={type} onChange={(e) => setType(e.target.value)} style={{ appearance: 'none', WebkitAppearance: 'none', width: '100%', height: '100%', border: 'none', background: 'transparent', outline: 'none', padding: '0 28px 0 11px', font: `500 12.5px/1 ${T.sans}`, color: T.fg, cursor: 'pointer' }}>
                  <option>New org</option><option>Tenexity</option>
                </select>
                <Icon name="chevronDown" size={14} color={T.tertiary} style={{ position: 'absolute', right: 9, pointerEvents: 'none' }} />
              </div>
            </Field>
          </div>
          {type === 'New org' ? (
            <Field label="Organization name" hint="They’ll be created as the admin of this new organization.">
              <TextInput value={org} onChange={setOrg} placeholder="e.g. Northwind Supply Co." />
            </Field>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '11px 13px', borderRadius: T.rMd, background: T.brandSoft + '66', border: `1px solid ${T.brand}33` }}>
              <Sparkle size={12} color={T.brandDeep} /><span style={{ font: `400 12.5px/1.4 ${T.sans}`, color: T.secondary }}>Internal <b style={{ color: T.fg }}>Tenexity operator</b> — full access to every tenant, project, and agent.</span>
            </div>
          )}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 12px', borderRadius: T.rMd, background: T.sunken, border: `1px solid ${T.borderSubtle}` }}>
            <Mono style={{ fontSize: 11 }}>{type === 'New org' ? 'Becomes ORG ADMIN · email added to allow-list' : 'Added to allow-list as OPERATOR'}</Mono>
            <AdminBtn primary onClick={send}>Send invite</AdminBtn>
          </div>
        </div>
        <div style={{ borderTop: `1px solid ${T.borderSubtle}`, overflow: 'auto' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '11px 20px', background: T.sunken, borderBottom: `1px solid ${T.borderSubtle}` }}>
            <ColHead>Allowed sign-ins</ColHead><Mono style={{ fontSize: 10.5 }}>{list.length}</Mono>
          </div>
          {list.map((u, i) => (
            <div key={u.email + i} style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 130px 90px 80px', gap: 10, alignItems: 'center', padding: '11px 20px', borderTop: i ? `1px solid ${T.borderSubtle}` : 'none' }}>
              <span style={{ font: `500 12.5px/1.2 ${T.mono}`, color: T.fg, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{u.email}</span>
              <span style={{ font: `400 12px/1.2 ${T.sans}`, color: T.secondary, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{u.org}</span>
              <span style={{ font: `600 9.5px/1 ${T.mono}`, letterSpacing: '0.04em', color: u.type === 'Tenexity' ? '#7a3ea8' : T.brandDeep, background: u.type === 'Tenexity' ? '#f3e9fb' : T.brandSoft, padding: '4px 6px', borderRadius: 4, justifySelf: 'start' }}>{u.role}</span>
              <span style={{ justifySelf: 'end' }}><StatusPill tone={u.status === 'active' ? 'success' : 'warning'} dot={u.status === 'active'}>{u.status}</StatusPill></span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ---- account menu (top-right) ---- */
const OPERATOR = { name: 'Harper Nguyen', email: 'harper@tenexity.ai', role: 'Platform Operator' };
function AccountMenu({ onSignOut }) {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef(null);
  React.useEffect(() => {
    if (!open) return;
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', h); return () => document.removeEventListener('mousedown', h);
  }, [open]);
  const item = (label, color, onClick, icon) => (
    <button onClick={onClick} style={{ display: 'flex', alignItems: 'center', gap: 9, width: '100%', textAlign: 'left', padding: '8px 10px', borderRadius: 6, border: 'none', background: 'transparent', cursor: 'pointer', font: `500 12.5px/1 ${T.sans}`, color }}
      onMouseEnter={(e) => e.currentTarget.style.background = T.sunken} onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}>
      {icon}{label}
    </button>
  );
  const logoutIcon = <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={T.danger} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/></svg>;
  return (
    <span ref={ref} style={{ position: 'relative' }}>
      <button onClick={() => setOpen((o) => !o)} title="Account" aria-label="Account menu" style={{ display: 'flex', alignItems: 'center', gap: 8, height: 34, padding: '0 6px 0 7px', borderRadius: 9999, cursor: 'pointer',
        border: `1px solid ${open ? T.borderDefault : 'transparent'}`, background: open ? T.sunken : 'transparent' }}>
        <Avatar name={OPERATOR.name} size={26} tone="brand" />
        <Icon name="chevronDown" size={13} color={T.tertiary} />
      </button>
      {open && (
        <div style={{ position: 'absolute', right: 0, top: 40, zIndex: 80, width: 248, padding: 5, borderRadius: T.rLg, background: T.raised, border: `1px solid ${T.borderSubtle}`, boxShadow: T.shadowMd }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 10px 11px' }}>
            <Avatar name={OPERATOR.name} size={36} tone="brand" />
            <span style={{ minWidth: 0 }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ font: `600 13.5px/1.2 ${T.sans}`, color: T.fg, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{OPERATOR.name}</span>
                <span style={{ font: `600 8px/1 ${T.mono}`, letterSpacing: '0.06em', color: '#7a3ea8', background: '#f3e9fb', padding: '2px 4px', borderRadius: 3, flexShrink: 0 }}>OPERATOR</span>
              </span>
              <Mono style={{ fontSize: 10.5, color: T.tertiary, display: 'block', marginTop: 2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{OPERATOR.email}</Mono>
            </span>
          </div>
          <div style={{ height: 1, background: T.borderSubtle, margin: '2px 0 4px' }} />
          {item('Account settings', T.fg, () => setOpen(false), <Icon name="settings" size={14} color={T.secondary} />)}
          {item('Switch to console', T.fg, () => setOpen(false), <Icon name="arrowLeft" size={14} color={T.secondary} />)}
          <div style={{ height: 1, background: T.borderSubtle, margin: '4px 0' }} />
          {item('Sign out', T.danger, () => { setOpen(false); onSignOut(); }, logoutIcon)}
        </div>
      )}
    </span>
  );
}

function SignedOut({ onBack }) {
  return (
    <div style={{ height: '100%', display: 'grid', placeItems: 'center', background: T.bg, fontFamily: T.sans }}>
      <div style={{ textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 18, maxWidth: 360 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ font: `700 22px/1 ${T.display}`, letterSpacing: '-0.01em', color: T.fg }}>Tenexity</span>
          <span style={{ font: `600 10px/1 ${T.mono}`, letterSpacing: '0.1em', color: T.brandDeep, background: T.brandSoft, padding: '4px 6px', borderRadius: 3 }}>OS</span>
        </div>
        <div>
          <h2 style={{ font: `400 24px/1.2 ${T.display}`, color: T.fg, margin: 0 }}>You’ve signed out</h2>
          <p style={{ font: `400 13px/1.5 ${T.sans}`, color: T.tertiary, margin: '8px 0 0' }}>Your operator session has ended. Sign back in to return to the factory.</p>
        </div>
        <AdminBtn primary onClick={onBack}>Sign back in</AdminBtn>
      </div>
    </div>
  );
}

/* ---- artifacts index (every produced file; opens in the viewer, new tab) ---- */
function AdminArtifacts() {
  const groups = (typeof artGroups === 'function') ? artGroups() : [];
  const total = groups.reduce((n, g) => n + g.items.length, 0);
  return (
    <React.Fragment>
      <PageTitle title="Artifacts" sub="Every file the factory has produced or operators authored. Click any to open it in the artifact viewer."
        actions={<AdminBtn onClick={() => groups[0] && openArtifact(groups[0].items[0].id)}>Open viewer ↗</AdminBtn>} />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        {groups.map((g) => (
          <div key={g.project}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 11 }}>
              <ColHead>{g.project}</ColHead>
              <span style={{ flex: 1, height: 1, background: T.borderSubtle }} />
              <Mono style={{ fontSize: 10.5 }}>{g.items.length} files</Mono>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(248px, 1fr))', gap: 10 }}>
              {g.items.map((a) => (
                <button key={a.id} onClick={() => openArtifact(a.id)} className="sf-artchip" title={`Open ${a.name}`} style={{ textAlign: 'left', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 11, padding: '12px 13px', borderRadius: T.rLg, border: `1px solid ${T.borderSubtle}`, background: T.raised }}>
                  <TypeBadge type={a.type} big />
                  <span style={{ flex: 1, minWidth: 0 }}>
                    <span style={{ display: 'block', font: `600 13px/1.25 ${T.mono}`, color: T.fg, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{a.name}</span>
                    <span style={{ display: 'block', font: `400 11px/1.3 ${T.sans}`, color: T.tertiary, marginTop: 3, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{a.agent || a.node || ''}</span>
                  </span>
                  <Icon name="arrowRight" size={14} color={T.tertiary} />
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </React.Fragment>
  );
}

/* ---- shell ---- */
function AdminPortal() {
  const [view, setView] = React.useState('organizations');
  const [agent, setAgent] = React.useState(null);
  const [proj, setProj] = React.useState(null);
  const [signedOut, setSignedOut] = React.useState(false);
  if (signedOut) return <SignedOut onBack={() => setSignedOut(false)} />;
  const openProject = (p) => { setProj(p); setView('projects'); };
  if (proj) return <AdminProjectView project={proj} onBack={() => setProj(null)} />;
  const NAV = [
    { id: 'overview', label: 'Overview', icon: 'overview' }, { id: 'organizations', label: 'Organizations', icon: 'organizations' },
    { id: 'users', label: 'Users', icon: 'users' },
    { id: 'projects', label: 'Projects', icon: 'projects' }, { id: 'newproject', label: 'New Project', icon: 'newproject' },
    { id: 'recipes', label: 'Recipes', icon: 'book' }, { id: 'artifacts', label: 'Artifacts', icon: 'artifacts' },
    { id: 'agents', label: 'Agents', icon: 'agents' }, { id: 'tools', label: 'Tools', icon: 'tools' },
    { id: 'factories', label: 'Factories', icon: 'factories' },
    { id: 'settings', label: 'Settings', icon: 'settings' },
  ];
  const pulse = [['AGENTS_ACTIVE', '27/55'], ['TASKS_RUNNING', '10'], ['AVG_FRICTION', '1.95'], ['TODAY_BURN', '$0.00'], ['PROJECTS', '24']];
  return (
    <div style={{ height: '100%', position: 'relative', display: 'flex', background: T.bg, fontFamily: T.sans }}>
      {/* sidebar */}
      <div style={{ width: 210, flexShrink: 0, borderRight: `1px solid ${T.borderSubtle}`, background: T.raised, display: 'flex', flexDirection: 'column', padding: '18px 14px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '0 8px 18px' }}>
          <span style={{ font: `700 18px/1 ${T.display}`, letterSpacing: '-0.01em', color: T.fg }}>Tenexity</span>
          <span style={{ font: `600 9px/1 ${T.mono}`, letterSpacing: '0.1em', color: T.brandDeep, background: T.brandSoft, padding: '3px 5px', borderRadius: 3 }}>OS</span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          {NAV.map((n) => {
            const on = view === n.id;
            return <button key={n.id} onClick={() => setView(n.id)} style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '9px 10px', borderRadius: T.rMd, width: '100%', cursor: 'pointer',
              background: on ? T.brandSoft : 'transparent', border: 'none', textAlign: 'left', color: on ? T.brandDeep : T.secondary, font: `${on ? 600 : 500} 13px/1 ${T.sans}` }}>
              <NavIcon name={n.icon} size={16} color={on ? T.brandDeep : T.tertiary} />{n.label}</button>;
          })}
        </div>
        <div style={{ marginTop: 'auto', padding: '10px', borderRadius: T.rMd, border: `1px solid ${T.borderSubtle}`, background: T.bg }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}><span style={{ width: 6, height: 6, borderRadius: '50%', background: T.success }} /><Mono style={{ fontSize: 10.5, color: T.success }}>LINEAR · PHI</Mono></div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 6 }}><Mono style={{ fontSize: 10 }}>Sys Status</Mono><Mono style={{ fontSize: 10, color: T.success }}>Nominal</Mono></div>
        </div>
      </div>

      {/* main */}
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        {/* pulse bar */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 26, padding: '12px 26px', borderBottom: `1px solid ${T.borderSubtle}`, background: T.raised, flexShrink: 0, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}><ColHead>Factory Pulse</ColHead><span style={{ width: 7, height: 7, borderRadius: '50%', background: T.success }} /></div>
          {pulse.map(([k, v]) => <span key={k} style={{ display: 'inline-flex', alignItems: 'baseline', gap: 6 }}><Mono style={{ fontSize: 11 }}>{k}:</Mono><span style={{ font: `600 12px/1 ${T.mono}`, color: T.fg }}>{v}</span></span>)}
        </div>
        {/* search row */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, padding: '14px 26px 0', flexShrink: 0 }}>
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 34, padding: '0 11px', borderRadius: T.rMd, border: `1px solid ${T.borderDefault}`, background: T.raised, width: 260 }}>
            <Icon name="search" size={14} color={T.tertiary} /><span style={{ flex: 1, font: `400 12.5px/1 ${T.sans}`, color: T.tertiary }}>Search…</span>
            <span style={{ font: `500 10px/1 ${T.mono}`, color: T.tertiary, border: `1px solid ${T.borderSubtle}`, borderRadius: 4, padding: '2px 4px' }}>⌘K</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <AdminBtn title="Return to the customer console"><Icon name="arrowLeft" size={14} color={T.fg} /> Back to console</AdminBtn>
            <AccountMenu onSignOut={() => setSignedOut(true)} />
          </div>
        </div>
        {/* content */}
        <div style={{ flex: 1, overflow: 'auto', padding: '20px 26px 36px' }}>
          {view === 'overview' && <AdminOverview onNav={setView} onOpenProject={openProject} />}
          {view === 'organizations' && <AdminClients />}
          {view === 'users' && <UsersManagement />}
          {view === 'recipes' && <RecipeLibrary />}
          {view === 'artifacts' && <AdminArtifacts />}
          {(view === 'projects' || view === 'newproject') && <AdminProjectsView onOpen={openProject} />}
          {view === 'agents' && <AdminAgents onOpen={setAgent} />}
          {view === 'tools' && <AdminTools />}
          {(view === 'factories' || view === 'settings') && (
            <div style={{ display: 'grid', placeItems: 'center', height: 320 }}>
              <div style={{ textAlign: 'center' }}><Mono style={{ fontSize: 12, display: 'block', marginBottom: 6 }}>{view.toUpperCase()}</Mono><span style={{ font: `400 14px/1.5 ${T.sans}`, color: T.tertiary }}>Module surface — out of scope for this prototype.</span></div>
            </div>
          )}
        </div>
      </div>
      {agent && <AgentPromptPanel agent={agent} onClose={() => setAgent(null)} />}
    </div>
  );
}

Object.assign(window, { AdminPortal, ROSTER, MCP_TOOLS, ADMIN_CLIENTS, ADMIN_PROJECTS,
  AdminBtn, PageTitle, ColHead, Mono, InitSquare, AdminFilter, PhasePill });
