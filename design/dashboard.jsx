// dashboard.jsx — the login landing page. Lists the org's Software Factory
// projects; opening one goes to its factory (build board), "New project"
// launches the Option C onboarding. FactoryApp wires the navigation.

const PROJECTS = [
  { id: 'quote', name: 'Quote-to-Epicor automation', goal: 'Replace the manual quoting spreadsheet:\n- Build quotes against **live Epicor SKUs** and the standard price book\n- Route any line over a **15% discount** to a sales manager\n- Write the won quote straight back to Epicor — no re-keying.', owner: 'Ibraheem K',
    status: 'building', phase: 'Build · stage 3', pct: 58, agents: ['opus', 'sonnet', 'qa'], updated: '4m ago', spend: '$4.20', budget: 30, open: 'build' },
  { id: 'ap', name: 'AP invoice matching', goal: '3-way match POs, receipts, and supplier invoices; flag exceptions for review.', owner: 'Maya R',
    status: 'deployed', phase: 'Live', pct: 100, agents: [], updated: '2d ago', spend: '$26.10', budget: 120, open: 'build' },
  { id: 'rma', name: 'Customer returns portal (RMA)', goal: 'Self-serve returns with auto-approval rules and Epicor credit memos.', owner: 'Ibraheem K',
    status: 'needs-input', phase: 'Wait for deps', pct: 34, agents: ['opus'], updated: '1h ago', spend: '$2.05', budget: 30, open: 'build' },
  { id: 'reorder', name: 'Inventory reorder agent', goal: 'Predict stock-outs across branches and draft replenishment POs.', owner: 'Maya R',
    status: 'researching', phase: 'Research · stage 1', pct: 12, agents: ['sonnet'], updated: '22m ago', spend: '$0.80', budget: 15, open: 'build' },
  { id: 'commission', name: 'Sales commission calculator', goal: 'Tiered commission runs from booked orders with rep statements.', owner: 'Ibraheem K',
    status: 'draft', phase: 'Context incomplete', pct: 0, agents: [], updated: '5d ago', spend: '—', budget: 30, open: 'new' },
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

// Per-row overflow menu. Actions vary by whether the project is archived.
function ProjectRowMenu({ archived, onArchive, onRestore, onDelete }) {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef(null);
  React.useEffect(() => {
    if (!open) return;
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [open]);
  const items = archived
    ? [{ label: 'Restore project', icon: 'restore', onClick: onRestore },
       { label: 'Delete permanently', icon: 'trash', danger: true, onClick: onDelete }]
    : [{ label: 'Archive project', icon: 'archive', onClick: onArchive }];
  return (
    <div ref={ref} style={{ position: 'relative', justifySelf: 'end' }} onClick={(e) => e.stopPropagation()}>
      <button title="More actions" onClick={(e) => { e.stopPropagation(); setOpen((v) => !v); }}
        style={{ display: 'grid', placeItems: 'center', width: 28, height: 28, borderRadius: T.rMd, border: 'none', cursor: 'pointer',
          background: open ? T.sunken : 'transparent' }}
        onMouseEnter={(e) => e.currentTarget.style.background = T.sunken} onMouseLeave={(e) => { if (!open) e.currentTarget.style.background = 'transparent'; }}>
        <Icon name="dots" size={16} color={T.secondary} />
      </button>
      {open && (
        <div style={{ position: 'absolute', top: 32, right: 0, zIndex: 60, minWidth: 188, padding: 5, borderRadius: T.rLg,
          background: T.raised, border: `1px solid ${T.borderSubtle}`, boxShadow: T.shadowMd }}>
          {items.map((it) => (
            <button key={it.label} onClick={(e) => { e.stopPropagation(); setOpen(false); it.onClick(); }}
              style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 10, padding: '9px 10px', borderRadius: T.rMd, border: 'none', cursor: 'pointer',
                background: 'transparent', textAlign: 'left', font: `500 13px/1 ${T.sans}`, color: it.danger ? T.danger : T.fg }}
              onMouseEnter={(e) => e.currentTarget.style.background = it.danger ? T.dangerSoft : T.sunken} onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}>
              <Icon name={it.icon} size={15} color={it.danger ? T.danger : T.secondary} /> {it.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function ProjectRow({ p, onClick, first, archived, onArchive, onRestore, onDelete }) {
  const st = STATUS[p.status];
  const live = p.status === 'building' || p.status === 'researching';
  return (
    <div onClick={onClick} role="button" tabIndex={0} style={{ width: '100%', textAlign: 'left', cursor: 'pointer', background: T.raised,
      borderTop: first ? 'none' : `1px solid ${T.borderSubtle}`, padding: '16px 18px', display: 'grid',
      gridTemplateColumns: 'minmax(0,1fr) 132px 150px 96px 28px', alignItems: 'center', gap: 16, transition: 'background .12s', opacity: archived ? 0.78 : 1 }}
      onMouseEnter={(e) => e.currentTarget.style.background = T.sunken} onMouseLeave={(e) => e.currentTarget.style.background = T.raised}>
      <div style={{ minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
          <span title={`Owner · ${p.owner}`} style={{ flexShrink: 0 }}><Avatar name={p.owner} size={22} tone="brand" /></span>
          <span style={{ font: `600 14.5px/1.2 ${T.sans}`, color: T.fg, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.name}</span>
          {archived ? <StatusPill tone="neutral">Archived</StatusPill> : <StatusPill tone={st.tone} dot={live}>{st.label}</StatusPill>}
        </div>
        <p style={{ margin: '5px 0 0 31px', font: `400 12.5px/1.4 ${T.sans}`, color: T.secondary, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.goal.replace(/[*_`#>]/g, '').replace(/\[([^\]]+)\]\([^)]+\)/g, '$1').replace(/\s*\n\s*[-*]?\s*/g, ' · ').trim()}</p>
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
      <ProjectRowMenu archived={archived} onArchive={onArchive} onRestore={onRestore} onDelete={onDelete} />
    </div>
  );
}

// Confirmation modal for archive / delete. Centered overlay; names the project
// and explains the consequence. Delete is guarded as a destructive (danger) action.
function ConfirmModal({ modal, onCancel, onConfirm }) {
  if (!modal) return null;
  const isDelete = modal.kind === 'delete';
  const p = modal.project;
  const live = p.status === 'building' || p.status === 'researching' || p.status === 'deployed';
  const copy = isDelete
    ? { title: 'Delete project permanently?', body: <React.Fragment><b style={{ color: T.fg }}>{p.name}</b> and its build history will be permanently removed. This cannot be undone.</React.Fragment>, cta: 'Delete permanently', icon: 'trash' }
    : { title: 'Archive this project?', body: <React.Fragment><b style={{ color: T.fg }}>{p.name}</b> will move to Archived. {live ? 'Any running agents stop and the automation is paused. ' : ''}You can restore it anytime.</React.Fragment>, cta: 'Archive project', icon: 'archive' };
  return (
    <div onClick={onCancel} style={{ position: 'absolute', inset: 0, zIndex: 200, background: 'rgba(17,18,20,0.42)', display: 'grid', placeItems: 'center', padding: 24, backdropFilter: 'blur(2px)' }}>
      <div onClick={(e) => e.stopPropagation()} style={{ width: 'min(440px, 100%)', background: T.raised, borderRadius: T.rXl, boxShadow: T.shadowLg || T.shadowMd, overflow: 'hidden' }}>
        <div style={{ padding: '22px 24px 18px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 13 }}>
            <span style={{ width: 38, height: 38, borderRadius: '50%', display: 'grid', placeItems: 'center', flexShrink: 0, background: isDelete ? T.dangerSoft : T.warningSoft }}>
              <Icon name={copy.icon} size={18} color={isDelete ? T.danger : T.warning} />
            </span>
            <h3 style={{ font: `700 17px/1.25 ${T.display}`, color: T.fg, margin: 0 }}>{copy.title}</h3>
          </div>
          <p style={{ font: `400 13.5px/1.55 ${T.sans}`, color: T.secondary, margin: '0 0 0 50px' }}>{copy.body}</p>
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, padding: '14px 20px', borderTop: `1px solid ${T.borderSubtle}`, background: T.sunken }}>
          <Btn variant="ghost" onClick={onCancel}>Cancel</Btn>
          <Btn variant={isDelete ? 'danger' : 'primary'} onClick={onConfirm}><Icon name={copy.icon} size={14} color="#fff" /> {copy.cta}</Btn>
        </div>
      </div>
    </div>
  );
}

function Dashboard({ onOpen, onNew, onOrg, onExplore, isAdmin = true, loading = false }) {
  const [owner, setOwner] = React.useState('');
  const [archivedIds, setArchivedIds] = React.useState([]);
  const [deletedIds, setDeletedIds] = React.useState([]);
  const [modal, setModal] = React.useState(null); // { kind: 'archive'|'delete', project }
  const [collapsed, setCollapsed] = React.useState({}); // { deployed, active, archived }
  const toggle = (k) => setCollapsed((c) => ({ ...c, [k]: !c[k] }));
  const owners = Array.from(new Set(PROJECTS.map((p) => p.owner))).sort();
  const visible = PROJECTS.filter((p) => !deletedIds.includes(p.id) && (!owner || p.owner === owner));
  const isArch = (p) => archivedIds.includes(p.id);
  const active = visible.filter((p) => !isArch(p) && p.status !== 'deployed');
  const shipped = visible.filter((p) => !isArch(p) && p.status === 'deployed');
  const archived = visible.filter(isArch);
  const confirmModal = () => {
    if (modal.kind === 'archive') setArchivedIds((a) => [...a, modal.project.id]);
    else if (modal.kind === 'delete') { setDeletedIds((d) => [...d, modal.project.id]); setArchivedIds((a) => a.filter((id) => id !== modal.project.id)); }
    setModal(null);
  };
  const restore = (p) => setArchivedIds((a) => a.filter((id) => id !== p.id));
  const SectionHeader = ({ k, label, count, aside }) => (
    <button onClick={() => toggle(k)} style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 10, padding: 0, background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left' }}>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
        <span style={{ display: 'inline-flex', transform: collapsed[k] ? 'rotate(-90deg)' : 'none', transition: 'transform .15s ease', color: T.tertiary }}>
          <Icon name="chevronDown" size={14} color={T.tertiary} />
        </span>
        <CategoryLabel>{label} · {count}</CategoryLabel>
      </span>
      {aside && !collapsed[k] && <span style={{ font: `400 11.5px/1 ${T.sans}`, color: T.tertiary }}>{aside}</span>}
    </button>
  );
  return (
    <div style={{ height: '100%', position: 'relative', display: 'flex', flexDirection: 'column', background: T.bg, fontFamily: T.sans }}>
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
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, height: 40, padding: '0 8px 0 12px', borderRadius: T.rMd, border: `1px solid ${owner ? T.brand : T.borderDefault}`, background: owner ? T.brandSoft : T.raised }}>
                <Icon name="bot" size={14} color={owner ? T.brandDeep : T.tertiary} />
                <select value={owner} onChange={(e) => setOwner(e.target.value)} style={{ border: 'none', outline: 'none', background: 'transparent', font: `500 13px/1 ${T.sans}`, color: owner ? T.brandDeep : T.secondary, cursor: 'pointer', height: 38 }}>
                  <option value="">All team members</option>
                  {owners.map((o) => <option key={o} value={o}>{o}</option>)}
                </select>
              </span>
              <Btn variant="secondary" size="lg" onClick={onExplore} title="Browse the recipe library for inspiration"><Icon name="compass" size={15} /> Explore</Btn>
              <Btn variant="primary" size="lg" onClick={onNew}><Icon name="plus" size={15} color="#fff" /> New project</Btn>
            </div>
          </div>

          {/* pulse strip */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
            {loading ? [0, 1, 2, 3].map((i) => <MetricCardSkel key={i} />) : (
            <React.Fragment>
            <MetricCard label="Active projects" value="4" hint="2 with agents working now" accent />
            <MetricCard label="In build" value="1" hint="58% · stage 3" />
            <MetricCard label="Deployed" value="1" hint="AP invoice matching · live" />
            <MetricCard label="Spend this month" value="$33.15" hint="of $120 plan cap" />
            </React.Fragment>
            )}
          </div>

          {/* org admin preview — visible to org admins only; nothing in its place for non-admins */}
          {isAdmin && loading && (
            <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: 'hidden', boxShadow: T.shadowXs }}>
              <div style={{ padding: '12px 16px', borderBottom: `1px solid ${T.borderSubtle}`, background: T.sunken, display: 'flex', alignItems: 'center', gap: 9 }}><SkelCircle size={24} /><SkelLine w={90} h={9} /></div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 1, background: T.borderSubtle }}>
                {[0, 1, 2, 3, 4].map((i) => <div key={i} style={{ background: T.raised, padding: '11px 16px' }}><SkelKV valueW="66%" /></div>)}
              </div>
            </div>
          )}
          {isAdmin && !loading && (() => {
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

          {/* shipped */}
          <div>
            <SectionHeader k="deployed" label="Deployed" count={shipped.length} />
            {!collapsed.deployed && (
            <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: 'hidden', boxShadow: T.shadowXs }}>
              {loading ? <ProjectRowSkel first /> : shipped.map((p, i) => <ProjectRow key={p.id} p={p} first={i === 0} onClick={() => onOpen(p)} onArchive={() => setModal({ kind: 'archive', project: p })} />)}
            </div>
            )}
          </div>

          {/* active projects list */}
          <div>
            <SectionHeader k="active" label="In progress" count={active.length} aside="Sorted by last activity" />
            {!collapsed.active && (
            <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: 'hidden', boxShadow: T.shadowXs }}>
              {loading ? [0, 1, 2, 3].map((i) => <ProjectRowSkel key={i} first={i === 0} />) : active.map((p, i) => <ProjectRow key={p.id} p={p} first={i === 0} onClick={() => onOpen(p)} onArchive={() => setModal({ kind: 'archive', project: p })} />)}
            </div>
            )}
          </div>

          {/* archived — only shown once something is archived */}
          {!loading && archived.length > 0 && (
          <div>
            <SectionHeader k="archived" label="Archived" count={archived.length} />
            {!collapsed.archived && (
            <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: 'hidden', boxShadow: T.shadowXs }}>
              {archived.map((p, i) => <ProjectRow key={p.id} p={p} first={i === 0} archived onClick={() => onOpen(p)} onRestore={() => restore(p)} onDelete={() => setModal({ kind: 'delete', project: p })} />)}
            </div>
            )}
          </div>
          )}

        </div>
      </div>
      <ConfirmModal modal={modal} onCancel={() => setModal(null)} onConfirm={confirmModal} />
    </div>
  );
}

// Connected experience: dashboard ⇄ org admin ⇄ project (overview/build) ⇄ new project.
function FactoryApp() {
  const [route, setRoute] = React.useState({ view: 'dashboard', project: null, tab: 'overview' });
  const [budget, setBudget] = React.useState(30);
  const go = (r) => setRoute((prev) => ({ ...prev, ...r }));
  if (route.view === 'org') return <OrgAdmin onBack={() => go({ view: 'dashboard' })} />;
  if (route.view === 'explore') return <ExploreRecipes onBack={() => go({ view: 'dashboard' })} onStart={(id) => go({ view: 'new', recipe: id == null ? undefined : id })} />;
  if (route.view === 'new') return <OptionC onExit={() => go({ view: 'dashboard' })} initialRecipe={route.recipe} />;
  if (route.view === 'build') return <BuildProgress projectName={`Acme Industrial · ${route.project ? route.project.name : 'Project'}`} budget={budget}
    peerTabs={{ onSwitch: (id) => id === 'exit' ? go({ view: 'dashboard' }) : id === 'build' ? null : go({ view: 'project', tab: id }) }} />;
  if (route.view === 'project') {
    const p = route.project;
    return <ProjectDashboard project={p} tab={route.tab} onTab={(t) => go({ tab: t })} onBack={() => go({ view: 'dashboard' })} onOpenBuild={() => go({ view: 'build' })} onResume={() => go({ view: 'new' })} budget={budget} onBudgetChange={setBudget} />;
  }
  return <Dashboard onNew={() => go({ view: 'new' })} onOpen={(p) => { setBudget(p.budget || 30); go({ view: 'project', project: p, tab: 'overview' }); }} onOrg={() => go({ view: 'org' })} onExplore={() => go({ view: 'explore' })} />;
}

Object.assign(window, { PROJECTS, Dashboard, FactoryApp, MetricCard, ProjectRow, ProjectRowMenu, ConfirmModal });
