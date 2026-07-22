// projectknowledge.jsx — the customer project shell after the project exists.
// Extends the existing ProjectDashboard entry point with clearer project knowledge:
// Product brief (customer direction), Factory outputs (agent work), Files (source material),
// the existing Factory console, and the same persistent Concierge on every view.

const PROJECT_TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'brief', label: 'Product brief' },
  { id: 'outputs', label: 'Factory outputs' },
  { id: 'build', label: 'Factory console' },
  { id: 'files', label: 'Files' },
];

const PRODUCT_BRIEF_SECTIONS = [
  { id: 'overview', title: 'Project overview', body: 'Build a feature-rich quote-to-ERP system for Acme Industrial Supply that gives sales teams one reliable path from request to approved order.' },
  { id: 'problem', title: 'Business problem', body: 'Quotes are assembled in spreadsheets, pricing approvals happen over email, and won quotes are re-keyed into Epicor. The handoffs slow turnaround, introduce errors, and make margin decisions difficult to audit.' },
  { id: 'goal', title: 'Product goal', bullets: ['Build quotes against live Epicor SKUs and the standard price book.', 'Route discounts over 15% to a sales manager.', 'Write an approved quote back to Epicor without re-keying.'] },
  { id: 'users', title: 'Audience and users', body: 'Inside-sales representatives create quotes, sales managers approve exceptions, and operations leaders need visibility into throughput and margin.' },
  { id: 'needs', title: 'User needs', bullets: ['Find the right SKU and current price quickly.', 'Understand when approval is required and who owns it.', 'See the state of every quote without searching email threads.'] },
  { id: 'scope', title: 'First release scope', body: 'Quote builder, pricing rules, approval workflow, Epicor read and write-back, manager dashboard, and branded PDF export.' },
  { id: 'constraints', title: 'Constraints', body: 'Epicor remains the system of record. Existing organization secrets are referenced, never exposed. The first release uses Acme’s current price book and approval policy.' },
  { id: 'questions', title: 'Open questions', body: 'Should customer-specific price overrides be included in the first release, or follow after the standard-price workflow is proven?' },
];

function KnowledgeButton({ children, onClick, primary = false, disabled = false }) {
  return <button onClick={onClick} disabled={disabled} style={{ height: 32, padding: '0 11px', borderRadius: T.rMd,
    border: primary ? '1px solid transparent' : `1px solid ${T.borderDefault}`,
    background: primary ? T.brand : T.raised, color: primary ? '#fff' : T.fg,
    font: `600 12px/1 ${T.sans}`, cursor: disabled ? 'not-allowed' : 'pointer', opacity: disabled ? .55 : 1,
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>{children}</button>;
}

function ProjectTabs({ tab, onTab, onOpenBuild, isDone }) {
  const tabs = isDone ? [...PROJECT_TABS, { id: 'maintenance', label: 'Maintenance' }] : PROJECT_TABS;
  return <div style={{ display: 'flex', gap: 2, padding: '0 24px', overflowX: 'auto' }}>
    {tabs.map((t) => {
      const on = tab === t.id;
      return <button key={t.id} onClick={() => t.id === 'build' ? onOpenBuild() : onTab(t.id)} style={{ position: 'relative', padding: '11px 13px', background: 'none', border: 'none', cursor: 'pointer', whiteSpace: 'nowrap',
        font: `${on ? 600 : 500} 13px/1 ${T.sans}`, color: on ? T.fg : T.secondary }}>
        {t.label}
        {on && <span style={{ position: 'absolute', left: 9, right: 9, bottom: -1, height: 2, background: T.brand, borderRadius: 2 }} />}
      </button>;
    })}
  </div>;
}

function ProjectOverview({ project, onTab, onOpenBuild, onResume, budget, onBudgetChange, ingesting }) {
  const groups = producedArtifacts();
  const latest = groups.flatMap((g) => g.items.map((a) => ({ ...a, agent: g.agent, nodeLabel: g.nodeLabel }))).slice(0, 3);
  const isDraft = project.status === 'draft';
  const [cap, setCap] = React.useState(budget);
  const [editingCap, setEditingCap] = React.useState(false);
  const [capDraft, setCapDraft] = React.useState(budget);
  const saveCap = () => { const next = Math.max(1, Number(capDraft) || cap); setCap(next); setEditingCap(false); onBudgetChange && onBudgetChange(next); };
  return <div style={{ padding: '22px 24px 38px', maxWidth: 1060, margin: '0 auto' }}>
    <section style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 14, padding: '13px 15px', borderRadius: T.rXl, border: `1px solid ${isDraft ? T.warning : T.brand}44`, background: isDraft ? T.warningSoft : T.brandSoft + '88', boxShadow: T.shadowXs }}>
      <span style={{ width: 30, height: 30, borderRadius: '50%', background: T.raised, border: `1px solid ${isDraft ? T.warning : T.brand}44`, display: 'grid', placeItems: 'center' }}>{isDraft ? <Icon name="edit" size={13} color={T.warning} /> : <Sparkle size={13} color={T.brand} />}</span>
      <div style={{ flex: 1 }}>
        <div style={{ font: `700 14px/1.25 ${T.display}`, color: T.fg }}>{isDraft ? 'Finish the project conversation before the factory starts.' : ingesting ? 'Your files are still being processed in the background.' : 'Research is complete. The product plan is ready, and architecture is being prepared now.'}</div>
        <div style={{ font: `400 12px/1.45 ${T.sans}`, color: T.secondary, marginTop: 3 }}>{isDraft ? 'Return to the Concierge to refine the brief, review what it learned, and hand off when you agree.' : ingesting ? 'You can keep using the project and resume the interview whenever you are ready.' : 'Nothing needs your attention. The next useful checkpoint is the architecture output.'}</div>
      </div>
      {isDraft ? <KnowledgeButton primary onClick={onResume}>Resume conversation <Icon name="arrowRight" size={13} color="#fff" /></KnowledgeButton> : <KnowledgeButton onClick={() => onTab('outputs')}>See what the factory produced <Icon name="arrowRight" size={13} /></KnowledgeButton>}
    </section>

    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.55fr) minmax(260px, .75fr)', gap: 14 }}>
      <Panel title="Product brief" accent action={<button onClick={() => onTab('brief')} style={{ border: 0, background: 'none', color: T.brandDeep, cursor: 'pointer', font: `600 11.5px/1 ${T.sans}` }}>Open brief →</button>}>
        <CategoryLabel>What you asked the factory to build</CategoryLabel>
        <GoalMarkdown style={{ marginTop: 8, font: `400 14px/1.6 ${T.sans}`, color: T.fg }}>{project.goal}</GoalMarkdown>
        <button onClick={() => onTab('brief')} className="sf-artchip" style={{ width: '100%', marginTop: 14, display: 'flex', alignItems: 'center', gap: 11, textAlign: 'left', padding: '11px 12px', borderRadius: T.rLg, border: `1px solid ${T.brand}33`, background: T.brandSoft + '55', cursor: 'pointer' }}>
          <span style={{ width: 34, height: 38, display: 'grid', placeItems: 'center', borderRadius: 7, background: T.raised, color: T.brandDeep, font: `700 9px/1 ${T.mono}` }}>BRIEF</span>
          <span style={{ flex: 1 }}><b style={{ display: 'block', font: `600 13px/1.2 ${T.sans}`, color: T.fg }}>Quote-to-Epicor product brief</b><span style={{ display: 'block', marginTop: 3, font: `400 11px/1.3 ${T.sans}`, color: T.tertiary }}>Created with the Concierge · updated today · headings adapt to this project</span></span>
          <Icon name="arrowRight" size={14} color={T.brandDeep} />
        </button>
      </Panel>

      <Panel title="Build status">
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}><span style={{ font: `700 30px/1 ${T.display}`, color: isDraft ? T.tertiary : T.brandDeep }}>{isDraft ? 'Not started' : `${project.pct}%`}</span>{!isDraft && <span style={{ font: `500 11px/1 ${T.mono}`, color: T.tertiary }}>complete</span>}</div>
        {!isDraft && <span style={{ display: 'block', height: 7, borderRadius: 4, background: T.sunken, overflow: 'hidden', margin: '12px 0 13px' }}><span style={{ display: 'block', height: '100%', width: project.pct + '%', background: T.brand }} /></span>}
        {[['Current phase', isDraft ? 'Draft' : 'Architecture'], ['Tickets', isDraft ? '—' : '5 / 11'], ['Agents working', isDraft ? '—' : '3'], ['Spend', isDraft ? '$0.00' : `${project.spend} / $${cap}`]].map(([k, v]) => <div key={k} style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8 }}><span style={{ font: `400 12px/1 ${T.sans}`, color: T.secondary }}>{k}</span><b style={{ font: `600 11.5px/1 ${T.mono}`, color: T.fg }}>{v}</b></div>)}
        {!isDraft && <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 11, paddingTop: 10, borderTop: `1px solid ${T.borderSubtle}` }}><span style={{ font: `400 12px/1 ${T.sans}`, color: T.secondary }}>Budget cap</span>{editingCap ? <span style={{ display: 'flex', gap: 5 }}><input autoFocus type="number" min="1" value={capDraft} onChange={(e) => setCapDraft(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && saveCap()} style={{ width: 64, height: 27, padding: '0 7px', border: `1px solid ${T.brand}`, borderRadius: T.rSm, font: `600 11px/1 ${T.mono}` }} /><button onClick={saveCap} style={{ width: 27, height: 27, border: 0, borderRadius: T.rSm, background: T.brand, cursor: 'pointer' }}><Icon name="check" size={12} color="#fff" /></button></span> : <button onClick={() => { setCapDraft(cap); setEditingCap(true); }} style={{ display: 'inline-flex', gap: 5, alignItems: 'center', border: `1px solid ${T.borderSubtle}`, background: T.raised, borderRadius: T.rMd, padding: '5px 8px', cursor: 'pointer', font: `600 11px/1 ${T.mono}` }}>${cap} total <Icon name="edit" size={11} color={T.tertiary} /></button>}</div>}
        <div style={{ marginTop: 12 }}>{isDraft ? <KnowledgeButton primary onClick={onResume}><span style={{ minWidth: 190 }}>Complete setup</span><Icon name="arrowRight" size={13} color="#fff" /></KnowledgeButton> : <KnowledgeButton primary onClick={onOpenBuild}><span style={{ minWidth: 190 }}>Open factory console</span><Icon name="arrowRight" size={13} color="#fff" /></KnowledgeButton>}</div>
      </Panel>
    </div>

    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginTop: 14 }}>
      <Panel title="Inside the brief" action={<button onClick={() => onTab('brief')} style={{ border: 0, background: 'none', color: T.brandDeep, cursor: 'pointer', font: `600 11.5px/1 ${T.sans}` }}>Read and edit →</button>}>
        {PRODUCT_BRIEF_SECTIONS.slice(0, 3).map((s, i) => <button key={s.id} onClick={() => onTab('brief')} style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 10, padding: '10px 0', border: 0, borderTop: i ? `1px solid ${T.borderSubtle}` : 'none', background: 'none', cursor: 'pointer', textAlign: 'left' }}>
          <span style={{ width: 28, height: 28, borderRadius: 7, display: 'grid', placeItems: 'center', background: T.sunken, color: T.brandDeep, font: `700 9px/1 ${T.mono}` }}>{String(i + 1).padStart(2, '0')}</span>
          <span style={{ flex: 1 }}><b style={{ display: 'block', font: `600 12.5px/1.2 ${T.sans}`, color: T.fg }}>{s.title}</b><span style={{ font: `400 11px/1.35 ${T.sans}`, color: T.tertiary }}>From the current Product Brief</span></span>
          <Icon name="chevronRight" size={13} color={T.tertiary} />
        </button>)}
      </Panel>
      <Panel title="Factory outputs" count={isDraft ? 0 : groups.reduce((n, g) => n + g.items.length, 0)} action={!isDraft && <button onClick={() => onTab('outputs')} style={{ border: 0, background: 'none', color: T.brandDeep, cursor: 'pointer', font: `600 11.5px/1 ${T.sans}` }}>View outputs →</button>}>
        {isDraft ? <div style={{ minHeight: 112, display: 'grid', placeItems: 'center', textAlign: 'center', padding: 12 }}><div><Icon name="layers" size={22} color={T.tertiary} /><b style={{ display: 'block', marginTop: 7, font: `600 12.5px/1.2 ${T.sans}` }}>Outputs begin after handoff</b><p style={{ maxWidth: 300, margin: '5px auto 0', font: `400 11px/1.45 ${T.sans}`, color: T.tertiary }}>Research reports, product plans, architecture, designs, and build records appear here as the factory completes them.</p></div></div> : latest.map((a, i) => <button key={a.id} onClick={() => onTab('outputs')} style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 10, padding: '10px 0', border: 0, borderTop: i ? `1px solid ${T.borderSubtle}` : 'none', background: 'none', cursor: 'pointer', textAlign: 'left' }}>
          <TypeBadge type={a.kind === 'fig' ? 'fig' : a.kind === 'svg' ? 'svg' : 'md'} />
          <span style={{ flex: 1 }}><b style={{ display: 'block', font: `600 12.5px/1.2 ${T.sans}`, color: T.fg }}>{a.label}</b><span style={{ font: `400 11px/1.35 ${T.sans}`, color: T.tertiary }}>{a.nodeLabel} · {a.agent}</span></span>
          <Icon name="chevronRight" size={13} color={T.tertiary} />
        </button>)}
      </Panel>
    </div>
  </div>;
}

function ProductBriefView({ onSelected }) {
  const [sections, setSections] = React.useState(PRODUCT_BRIEF_SECTIONS);
  const [selected, setSelected] = React.useState(sections[0].id);
  const [editing, setEditing] = React.useState(false);
  const [history, setHistory] = React.useState(false);
  const [saved, setSaved] = React.useState('Saved');
  const refs = React.useRef({});
  React.useEffect(() => { onSelected && onSelected(sections.find((s) => s.id === selected)?.title || 'Product brief'); }, [selected]);
  const jump = (id) => { setSelected(id); refs.current[id] && refs.current[id].scrollIntoView({ behavior: 'smooth', block: 'start' }); };
  const addSection = () => {
    const id = `section-${sections.length + 1}`;
    setSections([...sections, { id, title: 'New section', body: 'Add the project detail that belongs here.' }]);
    setSelected(id); setEditing(true); setSaved('Unsaved changes');
    setTimeout(() => jump(id), 0);
  };
  const save = () => { setSaved('Saving…'); setTimeout(() => { setSaved('Saved just now'); setEditing(false); }, 500); };
  return <div style={{ height: '100%', display: 'grid', gridTemplateColumns: '218px minmax(0, 1fr)', background: T.raised }}>
    <nav style={{ borderRight: `1px solid ${T.borderSubtle}`, background: '#F8FAFD', padding: '20px 13px', overflow: 'auto' }}>
      <h2 style={{ font: `700 16px/1.2 ${T.display}`, margin: 0, color: T.fg }}>Product brief</h2>
      <p style={{ font: `400 11.5px/1.45 ${T.sans}`, color: T.tertiary, margin: '5px 0 18px' }}>One readable document created with the Concierge. Its headings follow this project.</p>
      <CategoryLabel>Document contents</CategoryLabel>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2, marginTop: 8 }}>
        {sections.map((s, i) => <button key={s.id} onClick={() => jump(s.id)} style={{ display: 'flex', alignItems: 'center', gap: 8, width: '100%', padding: '8px 9px', border: 0, borderRadius: T.rMd, background: selected === s.id ? T.brandSoft : 'transparent', color: selected === s.id ? T.brandDeep : T.secondary, cursor: 'pointer', textAlign: 'left', font: `${selected === s.id ? 600 : 500} 11.5px/1.25 ${T.sans}` }}><span style={{ width: 16, font: `500 9px/1 ${T.mono}`, color: T.tertiary }}>{String(i + 1).padStart(2, '0')}</span>{s.title}</button>)}
      </div>
      <button onClick={addSection} style={{ width: '100%', marginTop: 12, height: 32, borderRadius: T.rMd, border: `1px dashed ${T.borderDefault}`, background: T.raised, color: T.secondary, cursor: 'pointer', font: `500 11.5px/1 ${T.sans}` }}>+ Add section</button>
    </nav>

    <main style={{ position: 'relative', overflow: 'auto', padding: '24px 34px 70px' }}>
      <div style={{ maxWidth: 760, margin: '0 auto' }}>
        <div style={{ position: 'sticky', top: -24, zIndex: 4, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, padding: '14px 0', background: 'rgba(255,255,255,.96)', borderBottom: `1px solid ${T.borderSubtle}` }}>
          <div><span style={{ font: `500 10.5px/1 ${T.mono}`, color: T.tertiary }}>Product brief / {sections.find((s) => s.id === selected)?.title}</span><span style={{ display: 'block', marginTop: 4, font: `500 10px/1 ${T.mono}`, color: saved.startsWith('Saved') ? T.success : T.warning }}>{saved}</span></div>
          <div style={{ display: 'flex', gap: 7 }}><KnowledgeButton onClick={() => setHistory(true)}>History</KnowledgeButton>{editing ? <><KnowledgeButton onClick={() => { setEditing(false); setSaved('Saved'); }}>Cancel</KnowledgeButton><KnowledgeButton primary onClick={save}>Save changes</KnowledgeButton></> : <KnowledgeButton primary onClick={() => { setEditing(true); setSaved('Editing'); }}><Icon name="edit" size={13} color="#fff" /> Edit document</KnowledgeButton>}</div>
        </div>
        {editing && <div style={{ position: 'sticky', top: 57, zIndex: 3, display: 'flex', alignItems: 'center', gap: 4, padding: '7px 9px', border: `1px solid ${T.borderSubtle}`, borderTop: 0, background: T.sunken, borderRadius: `0 0 ${T.rMd} ${T.rMd}` }}>
          {['Undo', 'Redo', 'Heading', 'Bold', 'Italic', 'List', 'Link'].map((x) => <button key={x} onMouseDown={(e) => e.preventDefault()} style={{ height: 26, padding: '0 8px', border: 0, borderRight: x === 'Redo' || x === 'Italic' ? `1px solid ${T.borderDefault}` : 0, background: 'transparent', color: T.secondary, cursor: 'pointer', font: `600 10.5px/1 ${T.sans}` }}>{x}</button>)}
          <span style={{ marginLeft: 'auto', font: `500 10px/1 ${T.mono}`, color: T.tertiary }}>Document-style editor · Markdown underneath</span>
        </div>}
        <article style={{ padding: '30px 8px' }}>
          <h1 contentEditable={editing} suppressContentEditableWarning onInput={() => setSaved('Unsaved changes')} style={{ font: `700 31px/1.15 ${T.display}`, letterSpacing: '-.025em', color: T.fg, margin: '0 0 7px', outline: 'none' }}>Quote-to-Epicor automation</h1>
          <div style={{ display: 'flex', alignItems: 'center', gap: 7, font: `400 11px/1.4 ${T.sans}`, color: T.tertiary, marginBottom: 25 }}><Sparkle size={10} color={T.brand} /> Created by the Concierge from onboarding · updated today · current version</div>
          {sections.map((s) => <section key={s.id} ref={(el) => refs.current[s.id] = el} onClick={() => setSelected(s.id)} style={{ scrollMarginTop: 105, padding: '5px 0 9px', borderRadius: T.rMd, boxShadow: selected === s.id && editing ? `0 0 0 2px ${T.brand}22` : 'none' }}>
            <h2 contentEditable={editing} suppressContentEditableWarning onInput={() => setSaved('Unsaved changes')} style={{ font: `700 18px/1.25 ${T.display}`, color: T.fg, margin: '20px 0 8px', outline: 'none' }}>{s.title}</h2>
            {s.body && <p contentEditable={editing} suppressContentEditableWarning onInput={() => setSaved('Unsaved changes')} style={{ font: `400 14px/1.7 ${T.sans}`, color: T.secondary, margin: 0, outline: 'none' }}>{s.body}</p>}
            {s.bullets && <ul contentEditable={editing} suppressContentEditableWarning onInput={() => setSaved('Unsaved changes')} style={{ margin: 0, paddingLeft: 20, color: T.secondary }}>{s.bullets.map((b) => <li key={b} style={{ font: `400 14px/1.65 ${T.sans}`, marginBottom: 4 }}>{b}</li>)}</ul>}
          </section>)}
        </article>
      </div>
      {history && <div onClick={() => setHistory(false)} style={{ position: 'absolute', inset: 0, zIndex: 10, background: 'rgba(9,12,18,.18)', display: 'flex', justifyContent: 'flex-end' }}><aside onClick={(e) => e.stopPropagation()} style={{ width: 310, height: '100%', background: T.raised, borderLeft: `1px solid ${T.borderSubtle}`, boxShadow: T.shadowMd, padding: 18 }}><div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}><h3 style={{ font: `700 17px/1.2 ${T.display}`, margin: 0 }}>Brief history</h3><button onClick={() => setHistory(false)} style={{ border: 0, background: 'none', cursor: 'pointer' }}><Icon name="x" size={16} /></button></div><p style={{ font: `400 11.5px/1.5 ${T.sans}`, color: T.tertiary }}>Each save is another version of the same Product Brief artifact.</p>{[['Current', 'Today, 12:31 · you'], ['Previous', 'Today, 11:48 · Concierge'], ['Initial', 'Today, 10:12 · Concierge']].map(([k, v], i) => <div key={k} style={{ padding: '12px 0', borderTop: `1px solid ${T.borderSubtle}` }}><div style={{ display: 'flex', justifyContent: 'space-between' }}><b style={{ font: `600 12px/1.2 ${T.sans}` }}>{k}</b>{i === 0 && <StatusPill tone="success">current</StatusPill>}</div><span style={{ font: `400 11px/1.4 ${T.sans}`, color: T.tertiary }}>{v}</span>{i > 0 && <button style={{ display: 'block', marginTop: 7, border: 0, background: 'none', color: T.brandDeep, padding: 0, cursor: 'pointer', font: `600 11px/1 ${T.sans}` }}>View version</button>}</div>)}</aside></div>}
    </main>
  </div>;
}

function OutputBody({ artifact }) {
  const custom = DOC_CONTENT[artifact.id];
  const generic = MD_GENERIC[artifact.id];
  if (custom) return custom();
  if (generic) return <Md><MdP>{generic.intro}</MdP><MdUl>{generic.bullets.map((b) => <MdLi key={b}>{b}</MdLi>)}</MdUl></Md>;
  return <Md><MdP>This output is recorded by the factory and opens with the existing artifact renderer.</MdP></Md>;
}

function FactoryOutputsView({ onSelected }) {
  const groups = producedArtifacts();
  const feed = groups.flatMap((g) => g.items.map((a) => ({ ...a, agent: g.agent, nodeLabel: g.nodeLabel })));
  const [selected, setSelected] = React.useState(feed.find((a) => a.id === 'prd') || feed[0]);
  React.useEffect(() => { onSelected && onSelected(selected); }, [selected]);
  return <div style={{ height: '100%', display: 'grid', gridTemplateColumns: '238px minmax(0, 1fr)', background: T.raised }}>
    <nav style={{ borderRight: `1px solid ${T.borderSubtle}`, background: '#F8FAFD', padding: '20px 13px', overflow: 'auto' }}>
      <h2 style={{ font: `700 16px/1.2 ${T.display}`, margin: 0, color: T.fg }}>Factory outputs</h2>
      <p style={{ font: `400 11.5px/1.45 ${T.sans}`, color: T.tertiary, margin: '5px 0 17px' }}>Research, plans, designs, and delivery records produced from your brief.</p>
      {groups.map((g) => <div key={g.node} style={{ marginTop: 15 }}><CategoryLabel>{g.nodeLabel}</CategoryLabel><div style={{ display: 'flex', flexDirection: 'column', gap: 2, marginTop: 6 }}>{g.items.map((a) => <button key={a.id} onClick={() => setSelected({ ...a, agent: g.agent, nodeLabel: g.nodeLabel })} style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 8, padding: '8px 9px', border: 0, borderRadius: T.rMd, background: selected.id === a.id ? T.brandSoft : 'transparent', color: selected.id === a.id ? T.brandDeep : T.secondary, cursor: 'pointer', textAlign: 'left', font: `${selected.id === a.id ? 600 : 500} 11.5px/1.25 ${T.sans}` }}><Icon name="file" size={12} color={selected.id === a.id ? T.brandDeep : T.tertiary} />{a.label}</button>)}</div></div>)}
    </nav>
    <main style={{ overflow: 'auto', padding: '24px 34px 70px' }}>
      <div style={{ maxWidth: 820, margin: '0 auto' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingBottom: 14, borderBottom: `1px solid ${T.borderSubtle}` }}><div><span style={{ font: `500 10.5px/1 ${T.mono}`, color: T.tertiary }}>Factory outputs / {selected.nodeLabel}</span><span style={{ display: 'block', marginTop: 5, font: `400 11px/1.3 ${T.sans}`, color: T.tertiary }}>Produced by {selected.agent} · versioned factory artifact</span></div><KnowledgeButton onClick={() => openArtifact(selected.id)}>Open in new tab <Icon name="arrowRight" size={13} /></KnowledgeButton></div>
        <article style={{ padding: '30px 6px' }}><div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 18 }}><TypeBadge type={selected.kind === 'fig' ? 'fig' : selected.kind === 'svg' ? 'svg' : 'md'} /><h1 style={{ font: `700 29px/1.15 ${T.display}`, letterSpacing: '-.02em', color: T.fg, margin: 0 }}>{selected.label}</h1></div><OutputBody artifact={selected} /></article>
      </div>
    </main>
  </div>;
}

function ProjectFilesView() {
  return <div style={{ height: '100%', overflow: 'auto', padding: '26px 30px 60px', background: T.bg }}><div style={{ maxWidth: 930, margin: '0 auto' }}>
    <CategoryLabel>Source material</CategoryLabel><h1 style={{ font: `700 25px/1.2 ${T.display}`, letterSpacing: '-.02em', margin: '7px 0 5px', color: T.fg }}>Files the factory works from</h1><p style={{ font: `400 12.5px/1.5 ${T.sans}`, color: T.secondary, margin: '0 0 23px' }}>Uploads and organization knowledge stay here. Factory-produced documents live separately in Factory outputs.</p>
    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}><h2 style={{ font: `600 14px/1 ${T.sans}`, margin: 0 }}>Uploaded by you</h2><KnowledgeButton><Icon name="plus" size={13} /> Add file</KnowledgeButton></div><div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 28 }}>{PROJ_MATERIALS.map((m) => <FileTile key={m.name} {...m} />)}</div>
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 10 }}><h2 style={{ font: `600 14px/1 ${T.sans}`, margin: 0 }}>From your organization</h2><span style={{ font: `400 11.5px/1 ${T.sans}`, color: T.tertiary }}>· reusable knowledge base</span></div><div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>{ORG_DOCS.map((d) => <FileTile key={d.name} {...d} />)}</div>
  </div></div>;
}

function ProjectMaintenanceView() {
  return <div style={{ height: '100%', overflow: 'auto', padding: '28px 32px', background: T.bg }}><div style={{ maxWidth: 760, margin: '0 auto' }}><CategoryLabel>Post-delivery</CategoryLabel><h1 style={{ font: `700 25px/1.2 ${T.display}`, margin: '7px 0' }}>Maintenance</h1><p style={{ font: `400 13px/1.6 ${T.sans}`, color: T.secondary }}>The existing maintenance workflow remains available after deployment. This project-knowledge change does not alter its controls or lifecycle.</p></div></div>;
}

function ProjectKnowledgeDashboard({ project, tab, onTab, onBack, onOpenBuild, onResume, budget, onBudgetChange, loading = false, ingesting = false, onResumeInterview, conciergeCollapsed, onConciergeCollapsedChange }) {
  const p = project || PROJECTS[0];
  const isDone = p.status === 'deployed' || p.phase === 'Done';
  const st = (typeof STATUS !== 'undefined' && STATUS[p.status]) || { label: 'Building', tone: 'info' };
  const cap = typeof budget === 'number' ? budget : (p.budget || 30);
  const groups = producedArtifacts();
  const artifacts = groups.flatMap((g) => g.items.map((a) => ({ ...a, agent: g.agent, nodeLabel: g.nodeLabel })));
  const [selectedBriefHeading, setSelectedBriefHeading] = React.useState('Project overview');
  const [selectedOutput, setSelectedOutput] = React.useState(artifacts.find((a) => a.id === 'prd') || artifacts[0]);
  const context = tab === 'brief' ? 'brief' : tab === 'outputs' ? 'outputs' : tab === 'files' ? 'files' : tab === 'maintenance' ? 'maintenance' : ingesting ? 'ingesting' : 'overview';
  return <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: T.bg, fontFamily: T.sans }}>
    <header style={{ background: T.raised, borderBottom: `1px solid ${T.borderSubtle}`, flexShrink: 0 }}>
      <div style={{ height: 55, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 24px' }}><div style={{ display: 'flex', alignItems: 'center', gap: 13, minWidth: 0 }}>{onBack && <Btn variant="ghost" size="sm" onClick={onBack}><Icon name="arrowLeft" size={14} /> Projects</Btn>}<Wordmark size={17} /><span style={{ font: `400 13px/1 ${T.mono}`, color: T.tertiary }}>/</span><span style={{ font: `600 13px/1 ${T.sans}`, color: T.fg, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.name}</span><StatusPill tone={st.tone}>{st.label}</StatusPill></div><Avatar name="Ibraheem K" size={28} tone="brand" /></div>
      <ProjectTabs tab={tab} onTab={onTab} onOpenBuild={onOpenBuild} isDone={isDone} />
    </header>
    <div style={{ position: 'relative', flex: 1, minHeight: 0, display: 'flex' }}>
      <div style={{ flex: 1, minWidth: 0, minHeight: 0, overflow: 'hidden', backgroundImage: tab === 'overview' ? `radial-gradient(circle, ${T.borderSubtle} 1px, transparent 1px)` : 'none', backgroundSize: '22px 22px' }}>
        {loading ? <div style={{ padding: 24 }}><ProjectDashboardSkel tab={tab === 'files' ? 'docs' : 'overview'} /></div> : tab === 'brief' ? <ProductBriefView onSelected={setSelectedBriefHeading} /> : tab === 'outputs' ? <FactoryOutputsView onSelected={setSelectedOutput} /> : tab === 'files' ? <ProjectFilesView /> : tab === 'maintenance' && isDone ? <ProjectMaintenanceView /> : <ProjectOverview project={p} onTab={onTab} onOpenBuild={onOpenBuild} onResume={onResumeInterview || onResume} budget={cap} onBudgetChange={onBudgetChange} ingesting={ingesting} />}
      </div>
      <ProjectConcierge context={context} onOpen={(a) => openArtifact(a)} docChips={context === 'files' ? ['What’s in the walkthrough?', 'Summarize the RFQ example', 'What does the discount matrix say?'] : undefined} selectedLabel={tab === 'brief' ? selectedBriefHeading : tab === 'outputs' ? selectedOutput?.label : undefined} collapsed={conciergeCollapsed} onCollapsedChange={onConciergeCollapsedChange} />
    </div>
  </div>;
}

window.ProjectKnowledgeDashboard = ProjectKnowledgeDashboard;
