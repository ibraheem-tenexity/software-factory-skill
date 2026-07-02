// dashboard.jsx — the login landing page. Lists the org's Software Factory
// projects; opening one goes to its factory (build board), "New project"
// launches the Option C onboarding. FactoryApp wires the navigation.

const PROJECTS = [
  { id: 'quote', name: 'Quote-to-Epicor automation', goal: 'Build quotes against Epicor SKUs, route >15% discounts, write won quotes back.',
    status: 'building', phase: 'Build · stage 3', pct: 58, agents: ['opus', 'sonnet', 'qa'], updated: '4m ago', spend: '$4.20', open: 'build' },
  { id: 'ap', name: 'AP invoice matching', goal: '3-way match POs, receipts, and supplier invoices; flag exceptions for review.',
    status: 'deployed', phase: 'Live', pct: 100, agents: [], updated: '2d ago', spend: '$26.10', open: 'build' },
  { id: 'rma', name: 'Customer returns portal (RMA)', goal: 'Self-serve returns with auto-approval rules and Epicor credit memos.',
    status: 'needs-input', phase: 'Wait for deps', pct: 34, agents: ['opus'], updated: '1h ago', spend: '$2.05', open: 'build' },
  { id: 'reorder', name: 'Inventory reorder agent', goal: 'Predict stock-outs across branches and draft replenishment POs.',
    status: 'researching', phase: 'Research · stage 1', pct: 12, agents: ['sonnet'], updated: '22m ago', spend: '$0.80', open: 'build' },
  { id: 'commission', name: 'Sales commission calculator', goal: 'Tiered commission runs from booked orders with rep statements.',
    status: 'draft', phase: 'Context incomplete', pct: 0, agents: [], updated: '5d ago', spend: '—', open: 'new' },
];

const STATUS = {
  building: { label: 'Building', tone: 'info' },
  deployed: { label: 'Deployed', tone: 'success' },
  'needs-input': { label: 'Needs input', tone: 'warning' },
  researching: { label: 'Researching', tone: 'brand' },
  draft: { label: 'Draft', tone: 'neutral' },
};

function MetricCard({ label, value, hint, accent }) {
  return (
    <div style={{ background: T.raised, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, padding: '14px 16px', boxShadow: T.shadowXs }}>
      <CategoryLabel>{label}</CategoryLabel>
      <div style={{ font: `700 26px/1.1 ${T.display}`, letterSpacing: '-0.02em', color: accent ? T.brandDeep : T.fg, marginTop: 8 }}>{value}</div>
      {hint && <div style={{ font: `400 11.5px/1.3 ${T.sans}`, color: T.tertiary, marginTop: 4 }}>{hint}</div>}
    </div>
  );
}

function AgentDots({ agents }) {
  if (!agents.length) return <span style={{ font: `400 11.5px/1 ${T.sans}`, color: T.tertiary }}>—</span>;
  return (
    <div style={{ display: 'flex', alignItems: 'center' }}>
      {agents.map((a, i) => (
        <span key={a} style={{ marginLeft: i ? -6 : 0, border: `1.5px solid ${T.raised}`, borderRadius: '50%' }}>
          <Avatar name={AGENTS[a] ? AGENTS[a].name : a} size={20} tone={AGENTS[a] ? AGENTS[a].tone : 'neutral'} />
        </span>
      ))}
    </div>
  );
}

function ProjectRow({ p, onClick, first }) {
  const st = STATUS[p.status];
  const live = p.status === 'building' || p.status === 'researching';
  return (
    <button onClick={onClick} style={{ width: '100%', textAlign: 'left', cursor: 'pointer', background: T.raised, border: 'none',
      borderTop: first ? 'none' : `1px solid ${T.borderSubtle}`, padding: '16px 18px', display: 'grid',
      gridTemplateColumns: 'minmax(0,1fr) 132px 150px 96px 24px', alignItems: 'center', gap: 16, transition: 'background .12s' }}
      onMouseEnter={(e) => e.currentTarget.style.background = T.sunken} onMouseLeave={(e) => e.currentTarget.style.background = T.raised}>
      <div style={{ minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
          <span style={{ font: `600 14.5px/1.2 ${T.sans}`, color: T.fg, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.name}</span>
          <StatusPill tone={st.tone} dot={live}>{st.label}</StatusPill>
        </div>
        <p style={{ margin: '5px 0 0', font: `400 12.5px/1.4 ${T.sans}`, color: T.secondary, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.goal}</p>
      </div>
      <div>
        <div style={{ font: `500 11.5px/1 ${T.mono}`, color: T.secondary, marginBottom: 6 }}>{p.phase}</div>
        {p.status !== 'draft' && (
          <span style={{ display: 'block', width: 110, height: 5, borderRadius: 3, background: T.sunken, overflow: 'hidden' }}>
            <span style={{ display: 'block', height: '100%', width: p.pct + '%', background: p.status === 'deployed' ? T.success : p.status === 'needs-input' ? T.warning : T.brand }} />
          </span>
        )}
      </div>
      <div><AgentDots agents={p.agents} /></div>
      <div style={{ font: `400 11.5px/1.3 ${T.sans}`, color: T.tertiary }}>{p.updated}<div style={{ font: `400 11px/1 ${T.mono}`, color: T.tertiary, marginTop: 3 }}>{p.spend}</div></div>
      <Icon name="chevronRight" size={16} color={T.tertiary} />
    </button>
  );
}

function Dashboard({ onOpen, onNew, onOrg, isAdmin = true }) {
  const active = PROJECTS.filter((p) => p.status !== 'deployed');
  const shipped = PROJECTS.filter((p) => p.status === 'deployed');
  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: T.bg, fontFamily: T.sans }}>
      {/* top bar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '13px 26px', background: T.raised, borderBottom: `1px solid ${T.borderSubtle}`, flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Wordmark />
          <span style={{ font: `400 13px/1 ${T.mono}`, color: T.tertiary }}>/</span>
          <button onClick={onOrg} style={{ display: 'inline-flex', alignItems: 'center', gap: 7, background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
            <Avatar name="Acme Industrial Supply" size={22} tone="neutral" />
            <span style={{ font: `600 13px/1 ${T.sans}`, color: T.fg }}>Acme Industrial Supply</span>
            <Icon name="chevronDown" size={14} color={T.tertiary} />
          </button>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <button style={{ display: 'grid', placeItems: 'center', width: 32, height: 32, borderRadius: '50%', border: `1px solid ${T.borderSubtle}`, background: T.raised, cursor: 'pointer' }}><Icon name="search" size={15} color={T.secondary} /></button>
          <Avatar name="Ibraheem K" size={30} tone="brand" />
        </div>
      </div>

      {/* scroll body */}
      <div style={{ flex: 1, overflow: 'auto', padding: '26px 26px 36px' }}>
        <div style={{ maxWidth: 1080, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 22 }}>

          {/* header row */}
          <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
            <div>
              <CategoryLabel style={{ marginBottom: 9 }}>Workspace</CategoryLabel>
              <h1 style={{ font: `700 30px/1.1 ${T.display}`, letterSpacing: '-0.02em', color: T.fg, margin: 0 }}>Your projects</h1>
              <p style={{ font: `400 14px/1.5 ${T.sans}`, color: T.secondary, margin: '7px 0 0' }}>Pick up where the factory left off, or start something new.</p>
            </div>
            <Btn variant="primary" size="lg" onClick={onNew}><Icon name="plus" size={15} color="#fff" /> New project</Btn>
          </div>

          {/* pulse strip */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
            <MetricCard label="Active projects" value="4" hint="2 with agents working now" accent />
            <MetricCard label="In build" value="1" hint="58% · stage 3" />
            <MetricCard label="Deployed" value="1" hint="AP invoice matching · live" />
            <MetricCard label="Spend this month" value="$33.15" hint="of $120 plan cap" />
          </div>

          {/* org admin preview — visible to org admins only; nothing in its place for non-admins */}
          {isAdmin && (() => {
            const org = window.ORG || {}; const docs = (window.ORG_DOCS || []);
            const stats = [['Industry', org.industry || 'Industrial Distribution'], ['Scale', org.scale || '51–200 people'], ['Knowledge base', docs.length + ' documents'], ['Connected systems', 'Epicor'], ['Team', '4 members']];
            return (
              <button onClick={onOrg} style={{ width: '100%', textAlign: 'left', cursor: 'pointer', border: `1px solid ${T.borderSubtle}`, background: T.raised, borderRadius: T.rLg, overflow: 'hidden', boxShadow: T.shadowXs }}
                onMouseEnter={(e) => e.currentTarget.style.borderColor = T.brand} onMouseLeave={(e) => e.currentTarget.style.borderColor = T.borderSubtle}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px', borderBottom: `1px solid ${T.borderSubtle}`, background: T.sunken }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                    <Avatar name={org.name || 'Acme Industrial Supply'} size={24} tone="neutral" />
                    <CategoryLabel style={{ color: T.fg }}>Organization</CategoryLabel>
                    <span style={{ font: `500 10px/1 ${T.mono}`, letterSpacing: '0.06em', color: T.brandDeep, background: T.brandSoft, padding: '3px 6px', borderRadius: 4 }}>ADMIN</span>
                  </div>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, font: `500 12.5px/1 ${T.sans}`, color: T.brandDeep }}>Manage organization <Icon name="arrowRight" size={13} color={T.brandDeep} /></span>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: `repeat(${stats.length}, 1fr)`, gap: '1px', background: T.borderSubtle }}>
                  {stats.map(([k, v]) => (
                    <div key={k} style={{ background: T.raised, padding: '11px 16px' }}>
                      <CategoryLabel style={{ display: 'block', marginBottom: 4 }}>{k}</CategoryLabel>
                      <span style={{ font: `500 12.5px/1.3 ${T.sans}`, color: T.fg }}>{v}</span>
                    </div>
                  ))}
                </div>
              </button>
            );
          })()}

          {/* active projects list */}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
              <CategoryLabel>In progress · {active.length}</CategoryLabel>
              <span style={{ font: `400 11.5px/1 ${T.sans}`, color: T.tertiary }}>Sorted by last activity</span>
            </div>
            <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: 'hidden', boxShadow: T.shadowXs }}>
              {active.map((p, i) => <ProjectRow key={p.id} p={p} first={i === 0} onClick={() => onOpen(p)} />)}
            </div>
          </div>

          {/* shipped */}
          <div>
            <CategoryLabel style={{ marginBottom: 10 }}>Deployed · {shipped.length}</CategoryLabel>
            <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: 'hidden', boxShadow: T.shadowXs }}>
              {shipped.map((p, i) => <ProjectRow key={p.id} p={p} first={i === 0} onClick={() => onOpen(p)} />)}
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}

// Connected experience: dashboard ⇄ org admin ⇄ project (overview/build) ⇄ new project.
function FactoryApp() {
  const [route, setRoute] = React.useState({ view: 'dashboard', project: null, tab: 'overview' });
  const go = (r) => setRoute((prev) => ({ ...prev, ...r }));
  if (route.view === 'org') return <OrgAdmin onBack={() => go({ view: 'dashboard' })} />;
  if (route.view === 'new') return <OptionC onExit={() => go({ view: 'dashboard' })} />;
  if (route.view === 'build') return <BuildProgress projectName={`Acme Industrial · ${route.project ? route.project.name : 'Project'}`}
    peerTabs={{ onSwitch: (id) => id === 'exit' ? go({ view: 'dashboard' }) : id === 'build' ? null : go({ view: 'project', tab: id }) }} />;
  if (route.view === 'project') {
    const p = route.project;
    if (p && p.open === 'new') return <OptionC onExit={() => go({ view: 'dashboard' })} />;
    return <ProjectDashboard project={p} tab={route.tab} onTab={(t) => go({ tab: t })} onBack={() => go({ view: 'dashboard' })} onOpenBuild={() => go({ view: 'build' })} />;
  }
  return <Dashboard onNew={() => go({ view: 'new' })} onOpen={(p) => go({ view: 'project', project: p, tab: 'overview' })} onOrg={() => go({ view: 'org' })} />;
}

Object.assign(window, { PROJECTS, Dashboard, FactoryApp, MetricCard, ProjectRow });
