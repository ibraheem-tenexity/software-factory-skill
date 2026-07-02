// orgproject.jsx — two context hubs:
//  • OrgAdmin: organization admin dashboard — company context + org-scoped
//    documents (knowledge base), connected systems, team, billing.
//  • ProjectDashboard: a project's canvas — everything uploaded + every
//    service working + context + produced documents + agents.

const ORG = {
  name: 'Acme Industrial Supply', industry: 'Industrial Distribution', sub: 'MRO / maintenance',
  hq: 'Cleveland, OH', founded: '1974', scale: '51–200 people', revenue: '$10M–$50M',
  website: 'acme-industrial.com', branches: '6 branches',
};
const ORG_DOCS = [
  { name: 'standard-pricing.xlsx', kind: 'xlsx', size: '142 KB', tag: 'Price book', used: '4 projects', updated: 'Mar 12' },
  { name: 'line-card.pdf', kind: 'pdf', size: '1.1 MB', tag: 'Product lines', used: '4 projects', updated: 'Jan 8' },
  { name: 'credit-policy.docx', kind: 'doc', size: '88 KB', tag: 'Policy', used: '2 projects', updated: 'Feb 2' },
  { name: 'terms-and-conditions.pdf', kind: 'pdf', size: '210 KB', tag: 'Legal', used: '3 projects', updated: 'Nov 4' },
  { name: 'brand-guidelines.pdf', kind: 'pdf', size: '4.4 MB', tag: 'Brand', used: 'all projects', updated: 'Sep 1' },
  { name: 'rfq-sop.pdf', kind: 'pdf', size: '320 KB', tag: 'Process', used: '1 project', updated: 'Apr 19' },
];
const ORG_SYSTEMS = [
  { id: 'epicor', label: 'Epicor', kind: 'ERP', connected: true, scope: 'SKUs · price book · orders', note: 'Primary system of record' },
  { id: 'sf', label: 'Salesforce', kind: 'CRM', connected: false },
  { id: 'qb', label: 'QuickBooks', kind: 'Accounting', connected: false },
];
const TEAM = [
  { name: 'Ibraheem K', role: 'Owner · Admin', email: 'ibraheem@acme-industrial.com', you: true, tone: 'brand' },
  { name: 'Maya Reeves', role: 'Operations', email: 'maya@acme-industrial.com', tone: 'success' },
  { name: 'Sam Knox', role: 'Sales', email: 'sam@acme-industrial.com', tone: 'warning' },
  { name: 'Jordan T.', role: 'Procurement', email: 'jordan@acme-industrial.com', tone: 'neutral' },
];
const FILE_KIND = {
  pdf: ['PDF', '#fbe3e3', '#c0392f'], xlsx: ['XLS', '#e4f8ef', '#1f8a5b'], csv: ['CSV', '#e4f8ef', '#1f8a5b'],
  doc: ['DOC', '#e8f1ff', '#1A7BFF'], video: ['MP4', '#f3e9fb', '#7a3ea8'], img: ['IMG', '#fbefdc', '#b06f12'],
};

function FileTile({ name, kind, size, tag, used, updated, onClick }) {
  const k = FILE_KIND[kind] || FILE_KIND.doc;
  return (
    <button onClick={onClick} className="sf-artchip" style={{ textAlign: 'left', cursor: 'pointer', background: T.raised, border: `1px solid ${T.borderSubtle}`,
      borderRadius: T.rLg, padding: '13px 14px', display: 'flex', flexDirection: 'column', gap: 10, boxShadow: T.shadowXs }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ font: `700 9px/1 ${T.mono}`, letterSpacing: '0.05em', color: k[2], background: k[1], padding: '4px 6px', borderRadius: 4 }}>{k[0]}</span>
        {tag && <CategoryLabel style={{ fontSize: 9.5 }}>{tag}</CategoryLabel>}
      </div>
      <span style={{ font: `600 13px/1.3 ${T.sans}`, color: T.fg, wordBreak: 'break-word' }}>{name}</span>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', font: `400 11px/1 ${T.mono}`, color: T.tertiary }}>
        <span>{size}</span>{used && <span>{used}</span>}
      </div>
    </button>
  );
}

/* ============================ ORG ADMIN ============================ */
function OrgAdmin({ onBack }) {
  const [sec, setSec] = React.useState('profile');
  const SECTIONS = [
    { id: 'profile', label: 'Company profile' },
    { id: 'knowledge', label: 'Knowledge base' },
    { id: 'systems', label: 'Connected systems' },
    { id: 'team', label: 'Team & access' },
    { id: 'billing', label: 'Usage & billing' },
  ];
  const profileRows = [
    ['Legal name', ORG.name], ['Industry', ORG.industry], ['Sub-focus', ORG.sub], ['Headquarters', ORG.hq],
    ['Founded', ORG.founded], ['Headcount', ORG.scale], ['Annual revenue', ORG.revenue], ['Website', ORG.website], ['Footprint', ORG.branches],
  ];
  const SecHead = ({ title, desc, action }) => (
    <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 14, marginBottom: 18 }}>
      <div>
        <h2 style={{ font: `700 22px/1.2 ${T.display}`, letterSpacing: '-0.015em', color: T.fg, margin: 0 }}>{title}</h2>
        {desc && <p style={{ font: `400 13px/1.5 ${T.sans}`, color: T.secondary, margin: '6px 0 0' }}>{desc}</p>}
      </div>
      {action}
    </div>
  );

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: T.bg, fontFamily: T.sans }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '13px 24px', background: T.raised, borderBottom: `1px solid ${T.borderSubtle}`, flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {onBack && <Btn variant="ghost" size="sm" onClick={onBack}><Icon name="arrowLeft" size={14} /> Projects</Btn>}
          <Wordmark size={17} />
          <span style={{ font: `400 13px/1 ${T.mono}`, color: T.tertiary }}>/</span>
          <span style={{ font: `600 13px/1 ${T.sans}`, color: T.fg }}>Organization</span>
        </div>
        <Avatar name="Ibraheem K" size={30} tone="brand" />
      </div>

      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        {/* sub nav */}
        <div style={{ width: 224, flexShrink: 0, borderRight: `1px solid ${T.borderSubtle}`, background: T.raised, padding: '22px 16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '0 10px 16px' }}>
            <Avatar name={ORG.name} size={34} tone="neutral" />
            <div style={{ minWidth: 0 }}>
              <div style={{ font: `600 13px/1.2 ${T.sans}`, color: T.fg, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{ORG.name}</div>
              <CategoryLabel style={{ fontSize: 10 }}>Admin</CategoryLabel>
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {SECTIONS.map((s) => {
              const on = sec === s.id;
              return <button key={s.id} onClick={() => setSec(s.id)} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 11px', borderRadius: T.rMd, width: '100%',
                cursor: 'pointer', background: on ? T.brandSoft : 'transparent', border: 'none', textAlign: 'left',
                font: `${on ? 600 : 500} 13px/1.2 ${T.sans}`, color: on ? T.brandDeep : T.secondary }}>{s.label}</button>;
            })}
          </div>
        </div>

        {/* content */}
        <div style={{ flex: 1, minWidth: 0, overflow: 'auto', padding: '28px 32px' }}>
          <div style={{ maxWidth: 760 }}>
            <CategoryLabel style={{ marginBottom: 12 }}>Organization · context</CategoryLabel>

            {sec === 'profile' && (
              <React.Fragment>
                <SecHead title="Company profile" desc="The canonical context every project inherits — set once, reused everywhere." action={<Btn variant="secondary" size="sm">Edit profile</Btn>} />
                <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: 'hidden', background: T.raised, boxShadow: T.shadowXs }}>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1px', background: T.borderSubtle }}>
                    {profileRows.map(([k, v]) => (
                      <div key={k} style={{ background: T.raised, padding: '13px 18px' }}>
                        <CategoryLabel style={{ display: 'block', marginBottom: 5 }}>{k}</CategoryLabel>
                        <span style={{ font: `500 13.5px/1.35 ${T.sans}`, color: T.fg }}>{v}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div style={{ marginTop: 14, display: 'flex', alignItems: 'flex-start', gap: 10, padding: '13px 15px', borderRadius: T.rLg, border: `1px solid ${T.brand}33`, background: T.brandSoft + '55' }}>
                  <Sparkle size={13} color={T.brand} style={{ marginTop: 2 }} />
                  <p style={{ margin: 0, font: `400 12.5px/1.55 ${T.sans}`, color: T.secondary }}>The Concierge reuses this profile to skip questions on every new project. Keep it current and onboarding stays one-click.</p>
                </div>
              </React.Fragment>
            )}

            {sec === 'knowledge' && (
              <React.Fragment>
                <SecHead title="Knowledge base" desc="Org-scoped documents the factory can draw on for any project." action={<Btn variant="primary" size="sm"><Icon name="upload" size={14} color="#fff" /> Upload</Btn>} />
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
                  {ORG_DOCS.map((d) => <FileTile key={d.name} {...d} />)}
                </div>
              </React.Fragment>
            )}

            {sec === 'systems' && (
              <React.Fragment>
                <SecHead title="Connected systems" desc="Linked once at the org level — every project reuses these connections." action={<Btn variant="secondary" size="sm"><Icon name="plus" size={14} /> Connect</Btn>} />
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {ORG_SYSTEMS.map((s) => (
                    <div key={s.id} style={{ display: 'flex', alignItems: 'center', gap: 13, padding: '14px 16px', borderRadius: T.rLg, border: `1px solid ${s.connected ? T.brand + '55' : T.borderSubtle}`, background: s.connected ? T.brandSoft + '44' : T.raised }}>
                      <span style={{ width: 38, height: 38, borderRadius: 9, flexShrink: 0, display: 'grid', placeItems: 'center', background: s.connected ? T.brand : T.sunken, color: s.connected ? '#fff' : T.secondary, font: `700 13px/1 ${T.mono}` }}>{s.label.slice(0, 2).toUpperCase()}</span>
                      <div style={{ flex: 1 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                          <span style={{ font: `600 14px/1.2 ${T.sans}`, color: T.fg }}>{s.label}</span>
                          <CategoryLabel style={{ fontSize: 10 }}>{s.kind}</CategoryLabel>
                          {s.connected && <StatusPill tone="success">Connected</StatusPill>}
                        </div>
                        <p style={{ margin: '4px 0 0', font: `400 12px/1.4 ${T.sans}`, color: T.tertiary }}>{s.connected ? `${s.scope} · ${s.note}` : 'Not connected'}</p>
                      </div>
                      <Btn variant={s.connected ? 'ghost' : 'secondary'} size="sm">{s.connected ? 'Manage' : 'Link'}</Btn>
                    </div>
                  ))}
                </div>
              </React.Fragment>
            )}

            {sec === 'team' && (
              <React.Fragment>
                <SecHead title="Team & access" desc="Who can see and steer projects in this organization." action={<Btn variant="primary" size="sm"><Icon name="plus" size={14} color="#fff" /> Invite</Btn>} />
                <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: 'hidden', background: T.raised, boxShadow: T.shadowXs }}>
                  {TEAM.map((m, i) => (
                    <div key={m.email} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '13px 16px', borderTop: i ? `1px solid ${T.borderSubtle}` : 'none' }}>
                      <Avatar name={m.name} size={34} tone={m.tone} />
                      <div style={{ flex: 1 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <span style={{ font: `600 13.5px/1.2 ${T.sans}`, color: T.fg }}>{m.name}</span>
                          {m.you && <span style={{ font: `500 10px/1 ${T.sans}`, color: T.brandDeep, background: T.brandSoft, padding: '2px 6px', borderRadius: 4 }}>You</span>}
                        </div>
                        <span style={{ font: `400 12px/1 ${T.sans}`, color: T.tertiary }}>{m.email}</span>
                      </div>
                      <StatusPill tone="neutral" dot={false}>{m.role}</StatusPill>
                    </div>
                  ))}
                </div>
              </React.Fragment>
            )}

            {sec === 'billing' && (
              <React.Fragment>
                <SecHead title="Usage & billing" desc="Spend across every project in this organization." action={<Btn variant="secondary" size="sm">Manage plan</Btn>} />
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 16 }}>
                  <MetricCard label="Plan" value="Team" hint="$120 / mo budget cap" accent />
                  <MetricCard label="Spent this month" value="$33.15" hint="28% of cap" />
                  <MetricCard label="Active projects" value="5" hint="2 building now" />
                </div>
                <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: 'hidden', background: T.raised, boxShadow: T.shadowXs }}>
                  <div style={{ padding: '10px 16px', borderBottom: `1px solid ${T.borderSubtle}`, background: T.sunken }}><CategoryLabel>Spend by project</CategoryLabel></div>
                  {[['Quote-to-Epicor automation', '$4.20', 18], ['AP invoice matching', '$26.10', 80], ['Customer returns portal', '$2.05', 9], ['Inventory reorder agent', '$0.80', 4]].map((r, i) => (
                    <div key={r[0]} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px', borderTop: i ? `1px solid ${T.borderSubtle}` : 'none' }}>
                      <span style={{ flex: 1, font: `500 13px/1.2 ${T.sans}`, color: T.fg }}>{r[0]}</span>
                      <span style={{ width: 120, height: 6, borderRadius: 3, background: T.sunken, overflow: 'hidden' }}><span style={{ display: 'block', height: '100%', width: r[2] + '%', background: T.brand }} /></span>
                      <span style={{ width: 56, textAlign: 'right', font: `500 12px/1 ${T.mono}`, color: T.secondary }}>{r[1]}</span>
                    </div>
                  ))}
                </div>
              </React.Fragment>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ====================== PROJECT DASHBOARD (canvas) ====================== */
const PROJ_SERVICES = [
  { label: 'Epicor', kind: 'ERP', tone: 'success', status: 'Syncing', detail: 'Reading SKUs & price book · write-back ready', metric: '2,418 SKUs' },
  { label: 'OpenAI', kind: 'LLM', tone: 'success', status: 'Active', detail: 'Drafting quotes & line matching', metric: 'gpt-4 · key set' },
  { label: 'Supabase', kind: 'Database', tone: 'success', status: 'Provisioned', detail: 'Quotes, approvals & audit log', metric: '4 tables' },
  { label: 'Playwright', kind: 'Testing', tone: 'info', status: 'Running', detail: 'End-to-end suite on every ticket', metric: '38 checks' },
  { label: 'Vercel', kind: 'Hosting', tone: 'neutral', status: 'Pending', detail: 'Deploy target · unlocks at 100%', metric: 'preview' },
];
const PROJ_MATERIALS = [
  { name: 'process-walkthrough.mp4', kind: 'video', size: '86 MB', tag: 'Walkthrough', used: '4:12' },
  { name: 'sample-rfq-email.pdf', kind: 'pdf', size: '92 KB', tag: 'Example' },
  { name: 'discount-matrix.xlsx', kind: 'xlsx', size: '54 KB', tag: 'Rules' },
];

function Panel({ title, count, action, children, span = 1, accent }) {
  return (
    <section style={{ gridColumn: `span ${span}`, background: T.raised, border: `1px solid ${accent ? T.brand + '44' : T.borderSubtle}`, borderRadius: T.rXl, boxShadow: T.shadowXs, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px', borderBottom: `1px solid ${T.borderSubtle}` }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <CategoryLabel tone={accent ? 'brand' : 'tertiary'}>{title}</CategoryLabel>
          {count != null && <span style={{ font: `500 10px/1 ${T.mono}`, color: T.tertiary, background: T.sunken, borderRadius: 9, padding: '2px 6px' }}>{count}</span>}
        </div>
        {action}
      </header>
      <div style={{ padding: 16, flex: 1 }}>{children}</div>
    </section>
  );
}

function ProjectDashboard({ project, tab, onTab, onBack, onOpenBuild }) {
  const [doc, setDoc] = React.useState(null);
  const p = project || PROJECTS[0];
  const st = (typeof STATUS !== 'undefined' && STATUS[p.status]) || { label: 'Building', tone: 'info' };
  const groups = producedArtifacts();
  const allArt = groups.flatMap((g) => g.items.map((a) => ({ ...a, agent: g.agent, nodeLabel: g.nodeLabel })));

  return (
    <div style={{ height: '100%', position: 'relative', display: 'flex', flexDirection: 'column', background: T.bg, fontFamily: T.sans }}>
      {/* top bar + tabs */}
      <div style={{ background: T.raised, borderBottom: `1px solid ${T.borderSubtle}`, flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '13px 24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 13 }}>
            {onBack && <Btn variant="ghost" size="sm" onClick={onBack}><Icon name="arrowLeft" size={14} /> Projects</Btn>}
            <Wordmark size={17} />
            <span style={{ font: `400 13px/1 ${T.mono}`, color: T.tertiary }}>/</span>
            <span style={{ font: `600 13px/1 ${T.sans}`, color: T.fg }}>{p.name}</span>
            <StatusPill tone={st.tone}>{st.label}</StatusPill>
          </div>
          <Avatar name="Ibraheem K" size={28} tone="brand" />
        </div>
        <div style={{ display: 'flex', gap: 2, padding: '0 24px' }}>
          {[{ id: 'overview', label: 'Overview' }, { id: 'build', label: 'Factory console' }, { id: 'docs', label: 'Documents' }].map((t) => {
            const on = tab === t.id;
            return <button key={t.id} onClick={() => t.id === 'build' ? onOpenBuild() : onTab(t.id)} style={{ position: 'relative', padding: '11px 14px', background: 'none', border: 'none', cursor: 'pointer',
              font: `${on ? 600 : 500} 13px/1 ${T.sans}`, color: on ? T.fg : T.secondary }}>
              {t.label}
              {on && <span style={{ position: 'absolute', left: 10, right: 10, bottom: -1, height: 2, background: T.brand, borderRadius: 2 }} />}
            </button>;
          })}
        </div>
      </div>

      {/* canvas */}
      <div style={{ flex: 1, overflow: 'auto', backgroundImage: `radial-gradient(circle, ${T.borderSubtle} 1px, transparent 1px)`, backgroundSize: '22px 22px' }}>
        <div style={{ padding: '22px 24px 36px' }}>
          {tab === 'docs' ? (
            <div style={{ maxWidth: 920, margin: '0 auto' }}>
              <CategoryLabel style={{ marginBottom: 12 }}>Project documents · {allArt.length + PROJ_MATERIALS.length}</CategoryLabel>
              <h3 style={{ font: `600 13px/1 ${T.sans}`, color: T.secondary, margin: '0 0 10px' }}>Uploaded by you</h3>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 22 }}>
                {PROJ_MATERIALS.map((m) => <FileTile key={m.name} {...m} />)}
              </div>
              <h3 style={{ font: `600 13px/1 ${T.sans}`, color: T.secondary, margin: '0 0 10px' }}>Produced by the factory</h3>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
                {allArt.map((a) => <FileTile key={a.id} name={a.label} kind={a.kind} size={a.nodeLabel} tag={a.agent} onClick={() => setDoc(a)} />)}
              </div>
            </div>
          ) : (
            <div style={{ maxWidth: 1080, margin: '0 auto', display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14, alignItems: 'start' }}>
              {/* project brief */}
              <Panel title="Project brief" span={2} accent>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                  <div>
                    <CategoryLabel style={{ marginBottom: 6 }}>Goal</CategoryLabel>
                    <p style={{ margin: 0, font: `400 14px/1.55 ${T.sans}`, color: T.fg }}>{p.goal}</p>
                  </div>
                  <div>
                    <CategoryLabel style={{ marginBottom: 7 }}>Scope</CategoryLabel>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7 }}>
                      {['Quoting / RFQ', 'Pricing & approvals', 'Epicor write-back', 'Manager dashboard'].map((s) => (
                        <span key={s} style={{ font: `500 12px/1 ${T.sans}`, color: T.brandDeep, background: T.brandSoft, padding: '6px 11px', borderRadius: 9999 }}>{s}</span>
                      ))}
                    </div>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10, paddingTop: 4 }}>
                    {[['Owner', 'Ibraheem K'], ['Created', 'Jun 14, 2026'], ['Phase', p.phase]].map(([k, v]) => (
                      <div key={k}><CategoryLabel style={{ display: 'block', marginBottom: 4 }}>{k}</CategoryLabel><span style={{ font: `500 12.5px/1.3 ${T.sans}`, color: T.fg }}>{v}</span></div>
                    ))}
                  </div>
                </div>
              </Panel>

              {/* progress */}
              <Panel title="Build status">
                <div style={{ display: 'flex', flexDirection: 'column', gap: 13 }}>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                    <span style={{ font: `700 30px/1 ${T.display}`, color: T.brandDeep }}>{p.pct}%</span>
                    <span style={{ font: `500 12px/1 ${T.mono}`, color: T.tertiary }}>complete</span>
                  </div>
                  <span style={{ height: 7, borderRadius: 4, background: T.sunken, overflow: 'hidden' }}><span style={{ display: 'block', height: '100%', width: p.pct + '%', background: T.brand }} /></span>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                    {[['Tickets done', '5 / 11'], ['Agents working', '3'], ['Spend', p.spend + ' / $30']].map(([k, v]) => (
                      <div key={k} style={{ display: 'flex', justifyContent: 'space-between' }}><span style={{ font: `400 12.5px/1 ${T.sans}`, color: T.secondary }}>{k}</span><span style={{ font: `500 12.5px/1 ${T.mono}`, color: T.fg }}>{v}</span></div>
                    ))}
                  </div>
                  <Btn variant="primary" size="sm" full onClick={onOpenBuild}>Open factory console <Icon name="arrowRight" size={13} color="#fff" /></Btn>
                </div>
              </Panel>

              {/* services working */}
              <Panel title="Services at work" count={PROJ_SERVICES.length} span={2}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10 }}>
                  {PROJ_SERVICES.map((s) => (
                    <div key={s.label} style={{ display: 'flex', gap: 11, padding: '11px 12px', borderRadius: T.rLg, border: `1px solid ${T.borderSubtle}`, background: T.bg }}>
                      <span style={{ width: 32, height: 32, flexShrink: 0, borderRadius: 8, display: 'grid', placeItems: 'center', background: T.raised, border: `1px solid ${T.borderSubtle}`, color: T.secondary, font: `700 11px/1 ${T.mono}` }}>{s.label.slice(0, 2).toUpperCase()}</span>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                          <span style={{ font: `600 13px/1.2 ${T.sans}`, color: T.fg }}>{s.label}</span>
                          <StatusPill tone={s.tone} dot={s.tone !== 'neutral'}>{s.status}</StatusPill>
                        </div>
                        <p style={{ margin: '3px 0 0', font: `400 11.5px/1.4 ${T.sans}`, color: T.tertiary }}>{s.detail}</p>
                        <span style={{ font: `500 10.5px/1 ${T.mono}`, color: T.secondary }}>{s.metric}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </Panel>

              {/* agents */}
              <Panel title="Agents on this project" count={3}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
                  {[['opus', 'Discount approval workflow'], ['sonnet', 'Pricing rules engine'], ['qa', 'E2E: quote builder']].map(([a, task]) => (
                    <div key={a} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <Avatar name={AGENTS[a].name} size={26} tone={AGENTS[a].tone} />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <span style={{ display: 'block', font: `600 12.5px/1.2 ${T.sans}`, color: T.fg }}>{AGENTS[a].name}</span>
                        <span style={{ display: 'block', font: `400 11px/1.3 ${T.sans}`, color: T.tertiary, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{task}</span>
                      </div>
                      <span style={{ width: 6, height: 6, borderRadius: '50%', background: T.success }} />
                    </div>
                  ))}
                </div>
              </Panel>

              {/* uploaded materials */}
              <Panel title="Uploaded materials" count={PROJ_MATERIALS.length} action={<button style={{ font: `500 11.5px/1 ${T.sans}`, color: T.brandDeep, background: 'none', border: 'none', cursor: 'pointer' }}>+ Add</button>}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
                  {PROJ_MATERIALS.map((m) => {
                    const k = FILE_KIND[m.kind] || FILE_KIND.doc;
                    return (
                      <div key={m.name} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <span style={{ font: `700 9px/1 ${T.mono}`, color: k[2], background: k[1], padding: '4px 5px', borderRadius: 4 }}>{k[0]}</span>
                        <span style={{ flex: 1, font: `500 12.5px/1.3 ${T.sans}`, color: T.fg, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{m.name}</span>
                        <span style={{ font: `400 11px/1 ${T.mono}`, color: T.tertiary }}>{m.size}</span>
                      </div>
                    );
                  })}
                </div>
              </Panel>

              {/* produced documents */}
              <Panel title="Produced documents" count={allArt.length} span={2} action={<button onClick={() => onTab('docs')} style={{ font: `500 11.5px/1 ${T.sans}`, color: T.brandDeep, background: 'none', border: 'none', cursor: 'pointer' }}>View all →</button>}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 9 }}>
                  {allArt.map((a) => <ArtifactChip key={a.id} a={a} onOpen={setDoc} small />)}
                </div>
              </Panel>

              {/* org context inherited */}
              <Panel title="Inherited org context">
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {[['Company', ORG.name], ['Industry', ORG.industry], ['System', 'Epicor'], ['Price book', 'standard-pricing.xlsx']].map(([k, v]) => (
                    <div key={k} style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
                      <CategoryLabel>{k}</CategoryLabel>
                      <span style={{ font: `500 12px/1.3 ${T.sans}`, color: T.fg, textAlign: 'right' }}>{v}</span>
                    </div>
                  ))}
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, marginTop: 2, font: `400 11px/1 ${T.sans}`, color: T.tertiary }}><Sparkle size={10} color={T.brand} /> reused from organization</span>
                </div>
              </Panel>
            </div>
          )}
        </div>
      </div>
      <DocViewer artifact={doc} onClose={() => setDoc(null)} />
    </div>
  );
}

Object.assign(window, { ORG, ORG_DOCS, OrgAdmin, ProjectDashboard, ProjectViewStandalone, FileTile, PROJ_SERVICES });

// Self-contained wrapper for the showcase artboard: holds its own tab state
// and swaps to the factory console (with peer tabs) — no external nav props.
function ProjectViewStandalone() {
  const [tab, setTab] = React.useState('overview');
  const project = (typeof PROJECTS !== 'undefined' && PROJECTS[0]) || { name: 'Quote-to-Epicor automation', goal: '', status: 'building', phase: 'Build · stage 3', pct: 58, spend: '$4.20' };
  if (tab === 'build') {
    return <BuildProgress projectName={`Acme Industrial · ${project.name}`}
      peerTabs={{ onSwitch: (id) => setTab(id === 'build' ? 'build' : id === 'exit' ? 'overview' : id) }} />;
  }
  return <ProjectDashboard project={project} tab={tab} onTab={setTab} onOpenBuild={() => setTab('build')} />;
}
window.ProjectViewStandalone = ProjectViewStandalone;
