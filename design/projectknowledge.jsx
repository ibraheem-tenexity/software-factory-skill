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

const SOURCE_FILE_META = {
  'process-walkthrough.mp4': { summary: 'A narrated walkthrough of the current quote intake, Epicor re-keying, and manager approval handoff.', updated: 'Today, 10:04', summaryStatus: 'ready' },
  'sample-rfq-email.pdf': { summary: 'A representative customer RFQ showing the product, quantity, due-date, and delivery details sales receives.', updated: 'Today, 10:06', summaryStatus: 'ready' },
  'discount-matrix.xlsx': { summary: 'Discount thresholds and the approval owner required for each customer and margin band.', updated: 'Today, 10:08', summaryStatus: 'pending' },
  'standard-pricing.xlsx': { summary: 'The organization-wide standard price book used as the baseline for quote calculations.', updated: 'Mar 12', summaryStatus: 'ready' },
  'line-card.pdf': { summary: 'Product lines and manufacturers Acme can quote, organized by category.', updated: 'Jan 8', summaryStatus: 'ready' },
  'credit-policy.docx': { summary: 'Credit limits, payment terms, and escalation rules for new or high-risk accounts.', updated: 'Feb 2', summaryStatus: 'ready' },
  'terms-and-conditions.pdf': { summary: 'The legal terms that accompany a customer quote and approved order.', updated: 'Nov 4', summaryStatus: 'ready' },
  'brand-guidelines.pdf': { summary: 'Approved logo use, typography, colors, and document presentation rules.', updated: 'Sep 1', summaryStatus: 'ready' },
  'rfq-sop.pdf': { summary: 'The prior summary is still available, but its latest refresh failed after this file changed.', updated: 'Apr 19', summaryStatus: 'failed' },
};

const SOURCE_DIRECTORIES = {
  root: {
    id: 'root', name: 'Files', scope: 'Virtual overview', virtual: true, status: 'Needs refresh', refreshed: 'Last ready 2 minutes ago',
    summary: 'The last complete overview organizes source material into project-only evidence and reusable organization knowledge. Pricing is re-indexing and the policies branch has a failed refresh, so agents see the incomplete coverage before choosing a subtree.',
    routes: ['current quoting workflow', 'pricing and approval rules', 'product catalog', 'company policies'],
    dirs: ['project', 'organization'], files: [], recent: ['sample-rfq-email.pdf', 'discount-matrix.xlsx', 'standard-pricing.xlsx'],
  },
  project: {
    id: 'project', parent: 'root', name: 'Project files', scope: 'Project', status: 'Needs refresh', refreshed: 'Last ready 2 minutes ago',
    summary: 'The last complete summary covers the process recording, representative RFQ, and discount matrix. The pricing branch is re-indexing, so agents verify that file before relying on its rules.',
    routes: ['how quotes work today', 'real RFQ input shape', 'when approval is required'],
    dirs: ['process', 'pricing'], files: [],
  },
  process: {
    id: 'process', parent: 'project', name: 'Process & examples', scope: 'Project', status: 'Ready', refreshed: 'Updated 4 minutes ago',
    summary: 'The clearest evidence of the current sales workflow. The walkthrough shows the end-to-end handoffs; the sample RFQ captures the customer input that starts the process.',
    routes: ['map the current workflow', 'inspect an inbound RFQ', 'identify manual handoffs'],
    dirs: [], files: ['process-walkthrough.mp4', 'sample-rfq-email.pdf'],
  },
  pricing: {
    id: 'pricing', parent: 'project', name: 'Pricing & approvals', scope: 'Project', status: 'Needs refresh', refreshed: 'Last ready 3 minutes ago',
    summary: 'The last successful summary covers project-specific discount bands and approval ownership. discount-matrix.xlsx is being re-indexed, so agents see this summary as stale until refresh completes.',
    routes: ['discount thresholds', 'approval ownership', 'margin exceptions'],
    dirs: [], files: ['discount-matrix.xlsx'],
  },
  organization: {
    id: 'organization', parent: 'root', name: 'Organization knowledge', scope: 'Org-wide', status: 'Failed', refreshed: 'Last ready Mar 12',
    summary: 'The last complete summary covers Acme catalog data, standard prices, policies, legal terms, and brand rules. The policies branch failed its latest refresh, so agents see that its coverage may be incomplete.',
    routes: ['standard product and price data', 'company-wide operating rules', 'legal or brand requirements'],
    dirs: ['catalog', 'policies'], files: [],
  },
  catalog: {
    id: 'catalog', parent: 'organization', name: 'Catalog & price book', scope: 'Org-wide', status: 'Summarizing', refreshed: 'Last ready Mar 12',
    summary: 'Canonical product and standard-pricing references. Agents should query this directory for carried manufacturers, product categories, SKUs, and baseline prices.',
    routes: ['available products', 'standard prices', 'manufacturers and categories'],
    dirs: [], files: ['standard-pricing.xlsx', 'line-card.pdf'],
  },
  policies: {
    id: 'policies', parent: 'organization', name: 'Policies & brand', scope: 'Org-wide', status: 'Failed', refreshed: 'Last ready Apr 19',
    summary: 'The last successful summary covers the RFQ procedure, credit policy, customer terms, and brand rules. The latest rfq-sop.pdf refresh failed, so agents are told that this coverage may be incomplete.',
    routes: ['RFQ procedure', 'credit and payment rules', 'quote terms', 'brand presentation'],
    dirs: [], files: ['credit-policy.docx', 'terms-and-conditions.pdf', 'brand-guidelines.pdf', 'rfq-sop.pdf'],
  },
};

function sourceFile(name) {
  const source = [...PROJ_MATERIALS, ...ORG_DOCS].find((f) => f.name === name) || { name, kind: 'doc', size: '' };
  return { id: `blob-${name.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`, ...source, ...(SOURCE_FILE_META[name] || {}) };
}

function staleSummaryAncestors(directories, startId) {
  const next = { ...directories };
  let id = startId;
  while (id) {
    const dir = next[id];
    if (!dir) break;
    const lastReady = dir.refreshed.replace(/^Updated |^Last ready /, '');
    next[id] = { ...dir, status: dir.status === 'Failed' ? 'Failed' : 'Needs refresh', refreshed: `Last ready ${lastReady}` };
    id = dir.parent;
  }
  return next;
}

const DIRECTORY_SUMMARY_STATUS = {
  Ready: { color: T.success, tone: 'success' },
  Summarizing: { color: T.warning, tone: 'warning' },
  'Needs refresh': { color: T.warning, tone: 'warning' },
  Failed: { color: T.danger, tone: 'danger' },
};
const FILE_SUMMARY_STATUS = {
  ready: { label: 'Ingested', color: T.success, tone: 'success' },
  pending: { label: 'Processing', color: T.warning, tone: 'warning' },
  failed: { label: 'Failed', color: T.danger, tone: 'danger' },
};

function SourceFolderIcon({ scope = 'Project', size = 48 }) {
  const org = scope === 'Org-wide';
  return <svg width={size} height={Math.round(size * .78)} viewBox="0 0 64 50" aria-hidden="true" style={{ flexShrink: 0, filter: 'drop-shadow(0 4px 5px rgba(24,24,27,.08))' }}>
    <path d="M4 12a6 6 0 0 1 6-6h15l6 7h23a6 6 0 0 1 6 6v5H4V12z" fill={org ? '#B9D6FF' : '#A9CDFD'} />
    <path d="M4 20h56v21a6 6 0 0 1-6 6H10a6 6 0 0 1-6-6V20z" fill={org ? '#DCEAFF' : '#CFE3FF'} stroke={org ? '#8AB9F8' : '#91BFFB'} />
    <path d="M11 27h22" stroke="#fff" strokeWidth="3" strokeLinecap="round" opacity=".9" />
  </svg>;
}

function SourceFileIcon({ kind = 'doc', size = 52 }) {
  const styles = {
    pdf: ['#FBE3E3', '#C0392F', 'PDF'], xlsx: ['#E4F8EF', '#1F8A5B', 'XLS'], csv: ['#E4F8EF', '#1F8A5B', 'CSV'],
    doc: ['#E8F1FF', '#1A7BFF', 'DOC'], video: ['#F3E9FB', '#7A3EA8', 'MP4'], img: ['#FBEFDC', '#B06F12', 'IMG'],
  };
  const k = styles[kind] || styles.doc;
  return <svg width={size} height={Math.round(size * 1.18)} viewBox="0 0 52 62" aria-hidden="true" style={{ flexShrink: 0, filter: 'drop-shadow(0 5px 6px rgba(24,24,27,.09))' }}>
    <path d="M7 2h25l13 13v40a5 5 0 0 1-5 5H7a5 5 0 0 1-5-5V7a5 5 0 0 1 5-5z" fill="#fff" stroke="#D4D4D8" />
    <path d="M32 2v10a3 3 0 0 0 3 3h10" fill={k[0]} stroke="#D4D4D8" />
    <rect x="8" y="34" width="36" height="18" rx="4" fill={k[0]} />
    {kind === 'video' && <path d="M21 16l12 7-12 7V16z" fill={k[1]} />}
    {kind !== 'video' && <><path d="M10 18h17M10 24h22M10 29h14" stroke={k[1]} strokeWidth="2" strokeLinecap="round" opacity=".72" /></>}
    <text x="26" y="46" textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize="8.5" fontWeight="700" fill={k[1]}>{k[2]}</text>
  </svg>;
}

function DirectoryTreeRow({ dir, current, depth, onOpen }) {
  const active = current === dir.id;
  return <button onClick={() => onOpen(dir.id)} style={{ width: '100%', height: 34, display: 'flex', alignItems: 'center', gap: 8, padding: `0 8px 0 ${9 + depth * 15}px`, border: 0, borderRadius: T.rMd, background: active ? T.brandSoft : 'transparent', color: active ? T.brandDeep : T.secondary, cursor: 'pointer', textAlign: 'left', font: `${active ? 600 : 500} 11.5px/1 ${T.sans}` }}>
    <SourceFolderIcon scope={dir.scope} size={21} /><span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{dir.name}</span><span style={{ marginLeft: 'auto', color: T.tertiary, font: `500 9px/1 ${T.mono}` }}>{dir.dirs.length + dir.files.length}</span>
  </button>;
}

function SourceFolderCard({ dir, onOpen }) {
  const state = DIRECTORY_SUMMARY_STATUS[dir.status] || DIRECTORY_SUMMARY_STATUS.Ready;
  return <button onClick={() => onOpen(dir.id)} className="sf-artchip" style={{ minWidth: 0, textAlign: 'left', cursor: 'pointer', background: T.raised, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, padding: '14px 15px', boxShadow: T.shadowXs, display: 'grid', gridTemplateColumns: '54px minmax(0, 1fr)', gap: 12, alignItems: 'center' }}>
    <SourceFolderIcon scope={dir.scope} size={52} />
    <span style={{ minWidth: 0 }}><span style={{ display: 'flex', alignItems: 'center', gap: 7 }}><b style={{ font: `650 13px/1.2 ${T.sans}`, color: T.fg, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{dir.name}</b><Icon name="chevronRight" size={12} color={T.tertiary} /></span><span style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 5, font: `400 10.5px/1.35 ${T.sans}`, color: T.tertiary }}><span>{dir.dirs.length + dir.files.length} items · {dir.scope}</span><span style={{ width: 5, height: 5, borderRadius: '50%', background: state.color }} /><span style={{ color: state.color }}>{dir.status}</span></span><span style={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden', marginTop: 7, font: `400 11px/1.38 ${T.sans}`, color: T.secondary }}>{dir.summary}</span></span>
  </button>;
}

function SourceFileCard({ file, selected, onSelect }) {
  const state = FILE_SUMMARY_STATUS[file.summaryStatus] || FILE_SUMMARY_STATUS.ready;
  return <button onClick={() => onSelect(file)} style={{ minWidth: 0, textAlign: 'center', cursor: 'pointer', background: selected ? T.brandSoft + '99' : 'transparent', border: `1px solid ${selected ? T.brand + '66' : 'transparent'}`, borderRadius: T.rLg, padding: '13px 9px 11px', display: 'flex', flexDirection: 'column', alignItems: 'center', transition: 'background .12s, border-color .12s' }}>
    <SourceFileIcon kind={file.kind} />
    <b style={{ width: '100%', marginTop: 9, font: `600 11.5px/1.3 ${T.sans}`, color: T.fg, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{file.name}</b>
    <span style={{ marginTop: 4, font: `400 9.5px/1 ${T.mono}`, color: T.tertiary }}>{file.size}{file.used ? ` · ${file.used}` : ''}</span><span style={{ marginTop: 4, font: `400 9px/1 ${T.mono}`, color: T.tertiary }}>{file.updated}</span><span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, marginTop: 6, color: state.color, font: `500 9px/1 ${T.sans}` }}><span style={{ width: 5, height: 5, borderRadius: '50%', background: state.color }} />{state.label}</span>
  </button>;
}

function DirectorySummary({ dir }) {
  const state = DIRECTORY_SUMMARY_STATUS[dir.status] || DIRECTORY_SUMMARY_STATUS.Ready;
  return <section style={{ position: 'relative', overflow: 'hidden', background: T.raised, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rXl, boxShadow: T.shadowXs, padding: '16px 18px 15px 20px' }}>
    <span style={{ position: 'absolute', inset: '0 auto 0 0', width: 3, background: state.color }} />
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}><div style={{ display: 'flex', alignItems: 'center', gap: 7 }}><Sparkle size={11} color={T.brand} /><CategoryLabel tone="brand">{dir.virtual ? 'Generated source overview' : 'Generated directory summary'}</CategoryLabel></div><span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, font: `500 9.5px/1 ${T.mono}`, color: state.color }}><span style={{ width: 6, height: 6, borderRadius: '50%', background: state.color }} />{dir.status} · {dir.refreshed}</span></div>
    <p style={{ font: `400 12.5px/1.55 ${T.sans}`, color: T.secondary, margin: '10px 0 12px' }}>{dir.summary}</p>
    <div style={{ display: 'flex', alignItems: 'center', gap: 7, flexWrap: 'wrap' }}><span style={{ font: `600 10px/1 ${T.sans}`, color: T.tertiary }}>Agents query this directory for</span>{dir.routes.map((route) => <span key={route} style={{ padding: '5px 8px', borderRadius: 999, background: T.sunken, color: T.secondary, font: `500 10px/1 ${T.sans}` }}>{route}</span>)}</div>
  </section>;
}

function DirectoryTreeBranch({ id, directories, current, depth = 0, onOpen }) {
  const dir = directories[id];
  if (!dir) return null;
  return <React.Fragment><DirectoryTreeRow dir={dir} current={current} depth={depth} onOpen={onOpen} />{dir.dirs.map((childId) => <DirectoryTreeBranch key={childId} id={childId} directories={directories} current={current} depth={depth + 1} onOpen={onOpen} />)}</React.Fragment>;
}

function ProjectFilesView({ onSelected }) {
  const [directories, setDirectories] = React.useState(() => Object.fromEntries(Object.entries(SOURCE_DIRECTORIES).map(([id, dir]) => [id, { ...dir, dirs: [...dir.dirs], files: [...dir.files] }])));
  const [currentId, setCurrentId] = React.useState('root');
  const [selectedFile, setSelectedFile] = React.useState(null);
  const [query, setQuery] = React.useState('');
  const [extraFiles, setExtraFiles] = React.useState({});
  const [creatingFolder, setCreatingFolder] = React.useState(false);
  const [folderName, setFolderName] = React.useState('');
  const uploadRef = React.useRef(null);
  const current = directories[currentId];
  const openDir = (id) => { setCurrentId(id); setSelectedFile(null); setQuery(''); setCreatingFolder(false); };
  const ancestors = [];
  let cursor = current;
  while (cursor) { ancestors.unshift(cursor); cursor = cursor.parent ? directories[cursor.parent] : null; }
  const context = selectedFile ? { type: 'file', id: selectedFile.id, scope: current.scope, name: selectedFile.name, summary_md: selectedFile.summary, summary_status: selectedFile.summaryStatus }
    : { type: current.virtual ? 'overview' : 'directory', id: current.virtual ? null : current.id, scope: current.scope, name: current.name, summary_md: current.summary, summary_status: current.status };
  React.useEffect(() => { onSelected && onSelected(context); }, [currentId, selectedFile, current.status]);
  const needle = query.trim().toLowerCase();
  const listedNames = current.virtual ? current.recent : current.files;
  const files = [...listedNames.map(sourceFile), ...(extraFiles[currentId] || [])].filter((file) => !needle || `${file.name} ${file.summary}`.toLowerCase().includes(needle));
  const dirs = current.dirs.map((id) => directories[id]).filter((dir) => !needle || `${dir.name} ${dir.summary}`.toLowerCase().includes(needle));
  const folderNameTaken = current.dirs.some((id) => directories[id].name.toLowerCase() === folderName.trim().toLowerCase());
  const createFolder = () => {
    const name = folderName.trim();
    if (!name || current.virtual || folderNameTaken) return;
    const id = `folder-${Date.now()}`;
    const dir = { id, parent: currentId, name, scope: current.scope, status: 'Summarizing', refreshed: 'No completed summary yet', summary: 'This directory contains no indexed material yet. Its generated summary will appear after a file is added or moved here.', routes: [], dirs: [], files: [] };
    setDirectories((all) => staleSummaryAncestors({ ...all, [id]: dir, [currentId]: { ...all[currentId], dirs: [...all[currentId].dirs, id] } }, currentId));
    setFolderName(''); setCreatingFolder(false);
  };
  const addFiles = (list) => {
    if (!list || !list.length || current.virtual) return;
    const next = Array.from(list).map((file) => { const ext = (file.name.split('.').pop() || 'doc').toLowerCase(); const kind = ext === 'mp4' || ext === 'mov' ? 'video' : ext === 'xls' || ext === 'xlsx' ? 'xlsx' : ext === 'pdf' ? 'pdf' : ext === 'png' || ext === 'jpg' || ext === 'jpeg' ? 'img' : 'doc'; return { name: file.name, kind, size: file.size > 1048576 ? `${(file.size / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(file.size / 1024))} KB`, updated: 'Just now', summary: 'Processing this file. The directory summary will refresh after ingestion completes.', summaryStatus: 'pending' }; });
    setExtraFiles((all) => ({ ...all, [currentId]: [...(all[currentId] || []), ...next] }));
    setDirectories((all) => staleSummaryAncestors(all, currentId));
    setSelectedFile(next[0]);
  };
  return <div style={{ height: '100%', display: 'grid', gridTemplateColumns: '210px minmax(0, 1fr)', background: T.bg }}>
    <nav style={{ borderRight: `1px solid ${T.borderSubtle}`, background: '#F8FAFD', padding: '19px 11px', overflow: 'auto' }}>
      <div style={{ padding: '0 8px 12px' }}><h2 style={{ font: `700 16px/1.2 ${T.display}`, color: T.fg, margin: 0 }}>Files</h2><p style={{ font: `400 10.8px/1.4 ${T.sans}`, color: T.tertiary, margin: '4px 0 0' }}>Directories help people and agents find the right source.</p></div>
      <CategoryLabel style={{ margin: '5px 8px 7px' }}>Directory tree</CategoryLabel>
      <DirectoryTreeBranch id="root" directories={directories} current={currentId} onOpen={openDir} />
      <div style={{ margin: '15px 8px 0', padding: '11px', borderRadius: T.rLg, background: T.brandSoft + '80', border: `1px solid ${T.brand}22` }}><div style={{ display: 'flex', alignItems: 'center', gap: 6 }}><Sparkle size={10} color={T.brand} /><b style={{ font: `600 10.5px/1 ${T.sans}`, color: T.brandDeep }}>Agent retrieval</b></div><p style={{ margin: '6px 0 0', font: `400 10.5px/1.42 ${T.sans}`, color: T.secondary }}>Directory summaries help you navigate. For this delivery, agents continue using flat semantic search across all project-readable source material.</p></div>
    </nav>
    <main style={{ minWidth: 0, overflow: 'auto', padding: '22px 26px 55px' }}><div style={{ maxWidth: 980, margin: '0 auto' }}>
      <input ref={uploadRef} type="file" multiple style={{ display: 'none' }} onChange={(e) => { addFiles(e.target.files); e.target.value = ''; }} />
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 18, marginBottom: 15 }}>
        <div><div style={{ display: 'flex', alignItems: 'center', gap: 5, minHeight: 18 }}>{ancestors.map((dir, i) => <React.Fragment key={dir.id}><button onClick={() => openDir(dir.id)} style={{ border: 0, background: 'none', padding: 0, cursor: 'pointer', color: i === ancestors.length - 1 ? T.fg : T.brandDeep, font: `${i === ancestors.length - 1 ? 600 : 500} 10.5px/1 ${T.mono}` }}>{dir.name}</button>{i < ancestors.length - 1 && <Icon name="chevronRight" size={11} color={T.tertiary} />}</React.Fragment>)}</div><h1 style={{ font: `700 24px/1.2 ${T.display}`, letterSpacing: '-.02em', margin: '6px 0 3px', color: T.fg }}>{current.name}</h1><span style={{ font: `400 11.5px/1.4 ${T.sans}`, color: T.tertiary }}>{current.virtual ? `${current.dirs.length} scoped roots · recent files are linked, not duplicated` : `${current.scope} · ${current.dirs.length} folders · ${current.files.length + (extraFiles[currentId] || []).length} files`}</span></div>
        <div style={{ display: 'flex', gap: 7 }}><label style={{ height: 32, width: 190, display: 'flex', alignItems: 'center', gap: 7, padding: '0 9px', background: T.raised, border: `1px solid ${T.borderDefault}`, borderRadius: T.rMd }}><Icon name="search" size={13} color={T.tertiary} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search this directory" style={{ minWidth: 0, flex: 1, border: 0, outline: 0, background: 'transparent', color: T.fg, font: `500 11px/1 ${T.sans}` }} /></label>{!current.virtual && <><KnowledgeButton onClick={() => setCreatingFolder(true)}><SourceFolderIcon scope={current.scope} size={19} /> New folder</KnowledgeButton><KnowledgeButton primary onClick={() => uploadRef.current && uploadRef.current.click()}><Icon name="plus" size={13} color="#fff" /> Add file</KnowledgeButton></>}</div>
      </div>
      {creatingFolder && <div style={{ display: 'flex', alignItems: 'center', gap: 7, margin: '-3px 0 12px', padding: 10, borderRadius: T.rLg, border: `1px solid ${T.brand}44`, background: T.brandSoft + '66' }}><SourceFolderIcon scope={current.scope} size={25} /><span style={{ flex: 1 }}><input autoFocus value={folderName} onChange={(e) => setFolderName(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && createFolder()} placeholder="Folder name" style={{ width: '100%', height: 30, boxSizing: 'border-box', border: `1px solid ${folderNameTaken ? T.danger : T.borderDefault}`, borderRadius: T.rMd, padding: '0 9px', outline: 0, font: `500 11.5px/1 ${T.sans}` }} />{folderNameTaken && <span style={{ display: 'block', marginTop: 4, color: T.danger, font: `500 9.5px/1 ${T.sans}` }}>A folder with this name already exists here.</span>}</span><KnowledgeButton onClick={() => { setCreatingFolder(false); setFolderName(''); }}>Cancel</KnowledgeButton><KnowledgeButton primary disabled={!folderName.trim() || folderNameTaken} onClick={createFolder}>Create folder</KnowledgeButton></div>}
      <DirectorySummary dir={current} />
      <div style={{ display: 'grid', gridTemplateColumns: selectedFile ? 'minmax(0, 1fr) 270px' : 'minmax(0, 1fr)', gap: 16, marginTop: 19, alignItems: 'start' }}>
        <div style={{ minWidth: 0 }}>
          {!!dirs.length && <section style={{ marginBottom: 23 }}><div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 9 }}><h2 style={{ font: `650 12.5px/1 ${T.sans}`, color: T.fg, margin: 0 }}>Folders</h2><span style={{ font: `500 9.5px/1 ${T.mono}`, color: T.tertiary }}>{dirs.length}</span></div><div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 10 }}>{dirs.map((dir) => <SourceFolderCard key={dir.id} dir={dir} onOpen={openDir} />)}</div></section>}
          {!!files.length && <section><div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 5 }}><h2 style={{ font: `650 12.5px/1 ${T.sans}`, color: T.fg, margin: 0 }}>{current.virtual ? 'Recently used files' : 'Files'}</h2><span style={{ font: `500 9.5px/1 ${T.mono}`, color: T.tertiary }}>{files.length}</span></div><div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(125px, 1fr))', gap: 4 }}>{files.map((file) => <SourceFileCard key={file.name} file={file} selected={selectedFile?.name === file.name} onSelect={setSelectedFile} />)}</div></section>}
        </div>
        {selectedFile && (() => { const state = FILE_SUMMARY_STATUS[selectedFile.summaryStatus] || FILE_SUMMARY_STATUS.ready; return <aside style={{ position: 'sticky', top: 0, background: T.raised, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rXl, boxShadow: T.shadowSm, padding: '17px' }}><div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}><SourceFileIcon kind={selectedFile.kind} size={43} /><button onClick={() => setSelectedFile(null)} title="Close file details" style={{ width: 26, height: 26, display: 'grid', placeItems: 'center', border: 0, borderRadius: T.rMd, background: T.sunken, cursor: 'pointer' }}><Icon name="x" size={13} color={T.tertiary} /></button></div><h3 style={{ font: `700 15px/1.3 ${T.display}`, color: T.fg, margin: '13px 0 5px', wordBreak: 'break-word' }}>{selectedFile.name}</h3><span style={{ font: `500 9.5px/1.3 ${T.mono}`, color: T.tertiary }}>{selectedFile.size} · {selectedFile.updated}</span><div style={{ marginTop: 15, paddingTop: 13, borderTop: `1px solid ${T.borderSubtle}` }}><CategoryLabel>Document summary</CategoryLabel><p style={{ margin: '7px 0 14px', font: `400 11.5px/1.5 ${T.sans}`, color: T.secondary }}>{selectedFile.summary}</p><StatusPill tone={state.tone}>{state.label}</StatusPill></div><p style={{ margin: '13px 0 0', font: `400 10.5px/1.45 ${T.sans}`, color: T.tertiary }}>This summary contributes to its generated directory summary and is available to agent retrieval.</p></aside>; })()}
      </div>
    </div></main>
  </div>;
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
  const [selectedSource, setSelectedSource] = React.useState({ type: 'overview', id: null, scope: 'Virtual overview', name: 'Files', summary_md: 'Project and organization source material.', summary_status: 'Needs refresh' });
  const context = tab === 'brief' ? 'brief' : tab === 'outputs' ? 'outputs' : tab === 'files' ? 'files' : tab === 'maintenance' ? 'maintenance' : ingesting ? 'ingesting' : 'overview';
  return <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: T.bg, fontFamily: T.sans }}>
    <header style={{ background: T.raised, borderBottom: `1px solid ${T.borderSubtle}`, flexShrink: 0 }}>
      <div style={{ height: 55, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 24px' }}><div style={{ display: 'flex', alignItems: 'center', gap: 13, minWidth: 0 }}>{onBack && <Btn variant="ghost" size="sm" onClick={onBack}><Icon name="arrowLeft" size={14} /> Projects</Btn>}<Wordmark size={17} /><span style={{ font: `400 13px/1 ${T.mono}`, color: T.tertiary }}>/</span><span style={{ font: `600 13px/1 ${T.sans}`, color: T.fg, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.name}</span><StatusPill tone={st.tone}>{st.label}</StatusPill></div><Avatar name="Ibraheem K" size={28} tone="brand" /></div>
      <ProjectTabs tab={tab} onTab={onTab} onOpenBuild={onOpenBuild} isDone={isDone} />
    </header>
    <div style={{ position: 'relative', flex: 1, minHeight: 0, display: 'flex' }}>
      <div style={{ flex: 1, minWidth: 0, minHeight: 0, overflow: 'hidden', backgroundImage: tab === 'overview' ? `radial-gradient(circle, ${T.borderSubtle} 1px, transparent 1px)` : 'none', backgroundSize: '22px 22px' }}>
        {loading ? <div style={{ padding: 24 }}><ProjectDashboardSkel tab={tab === 'files' ? 'docs' : 'overview'} /></div> : tab === 'brief' ? <ProductBriefView onSelected={setSelectedBriefHeading} /> : tab === 'outputs' ? <FactoryOutputsView onSelected={setSelectedOutput} /> : tab === 'files' ? <ProjectFilesView onSelected={setSelectedSource} /> : tab === 'maintenance' && isDone ? <ProjectMaintenanceView /> : <ProjectOverview project={p} onTab={onTab} onOpenBuild={onOpenBuild} onResume={onResumeInterview || onResume} budget={cap} onBudgetChange={onBudgetChange} ingesting={ingesting} />}
      </div>
      <ProjectConcierge context={context} onOpen={(a) => openArtifact(a)} docChips={context === 'files' ? [`What is in ${selectedSource.name}?`, 'Which directory covers approvals?', 'Where should an agent look first?'] : undefined} selectedLabel={tab === 'brief' ? selectedBriefHeading : tab === 'outputs' ? selectedOutput?.label : tab === 'files' ? selectedSource.name : undefined} collapsed={conciergeCollapsed} onCollapsedChange={onConciergeCollapsedChange} />
    </div>
  </div>;
}

window.ProjectKnowledgeDashboard = ProjectKnowledgeDashboard;
