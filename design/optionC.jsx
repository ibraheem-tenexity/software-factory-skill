// optionC.jsx — Single-Page Intake + Docked Concierge. Two states via a
// header toggle: FIRST-TIME (fresh user, no data on file — set up company
// then first project) and RETURNING (org context already on file, ask only
// project questions). The Concierge persists into the build either way.

function CheckRow({ c }) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 9, padding: '8px 12px', borderBottom: `1px solid ${T.borderSubtle}` }}>
      <span style={{ marginTop: 1, width: 15, height: 15, flexShrink: 0, borderRadius: '50%', display: 'grid', placeItems: 'center', background: c.done ? T.success : 'transparent', border: c.done ? 'none' : `1.5px solid ${T.borderDefault}` }}>{c.done && <Icon name="check" size={10} color="#fff" />}</span>
      <div style={{ flex: 1 }}>
        <span style={{ display: 'block', font: `500 12.5px/1.3 ${T.sans}`, color: c.done ? T.fg : T.secondary }}>{c.label}{c.optional && <span style={{ color: T.tertiary, fontWeight: 400 }}> · optional</span>}</span>
        {!c.done && c.nudge && <span style={{ display: 'block', marginTop: 2, font: `400 11.5px/1.4 ${T.sans}`, color: T.tertiary }}>{c.nudge}</span>}
      </div>
    </div>
  );
}
function GroupHead({ children, tone }) {
  return <div style={{ padding: '8px 12px', borderBottom: `1px solid ${T.borderSubtle}`, background: tone === 'success' ? T.successSoft : T.sunken, display: 'flex', alignItems: 'center', gap: 6 }}>
    {tone === 'success' && <Icon name="check" size={12} color={T.success} />}<CategoryLabel style={tone === 'success' ? { color: T.success } : null}>{children}</CategoryLabel></div>;
}

// One editable cell inside the on-file org grid: label + value, or an inline
// input when the card is in Manage (edit-in-place) mode.
function OrgCell({ label, value, editing, onChange }) {
  const cellDict = useDictation(value, onChange);
  return (
    <div style={{ background: T.raised, padding: '11px 20px' }}>
      <CategoryLabel style={{ display: 'block', marginBottom: editing ? 6 : 4 }}>{label}</CategoryLabel>
      {editing ? (
        <div style={{ position: 'relative' }}>
          <input value={value} onChange={(e) => onChange(e.target.value)} placeholder="—"
            style={{ width: '100%', boxSizing: 'border-box', height: 30, padding: cellDict.supported ? '0 30px 0 9px' : '0 9px', borderRadius: T.rSm, border: `1px solid ${T.borderDefault}`, background: T.bg, color: T.fg, font: `500 13px/1 ${T.sans}`, outline: 'none' }} />
          {cellDict.supported && <span style={{ position: 'absolute', right: 2, top: 1 }}><MicButton size={24} listening={cellDict.listening} onClick={cellDict.toggle} /></span>}
        </div>
      ) : (
        <span style={{ font: `500 13px/1.35 ${T.sans}`, color: value ? T.fg : T.tertiary }}>{value || '—'}</span>
      )}
    </div>
  );
}

// Scope-of-work multi-select with a "+ Add" affordance so the user can type a
// custom scope / type of software that isn't in the preset list.
function ScopeOfWork({ options, value, onChange, onAddOption }) {
  const [adding, setAdding] = React.useState(false);
  const [text, setText] = React.useState('');
  const inputRef = React.useRef(null);
  React.useEffect(() => { if (adding && inputRef.current) inputRef.current.focus(); }, [adding]);
  const sel = value || [];
  const isOn = (o) => sel.includes(o);
  const toggle = (o) => onChange(isOn(o) ? sel.filter((x) => x !== o) : [...sel, o]);
  const commit = () => {
    const t = text.trim();
    if (t) { onAddOption(t); if (!sel.includes(t)) onChange([...sel, t]); }
    setText(''); setAdding(false);
  };
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
      {options.map((o) => <Chip key={o} selected={isOn(o)} onClick={() => toggle(o)}>{o}</Chip>)}
      {adding ? (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '3px 4px 3px 11px', borderRadius: 9999, border: `1px solid ${T.brand}`, background: T.brandSoft }}>
          <input ref={inputRef} value={text} onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); commit(); } else if (e.key === 'Escape') { setText(''); setAdding(false); } }}
            onBlur={commit} placeholder="Custom scope or software…"
            style={{ width: 168, border: 'none', outline: 'none', background: 'transparent', font: `500 13px/1 ${T.sans}`, color: T.brandDeep }} />
          <button onMouseDown={(e) => e.preventDefault()} onClick={commit} title="Add" style={{ width: 24, height: 24, flexShrink: 0, display: 'grid', placeItems: 'center', borderRadius: '50%', border: 'none', background: T.brand, color: '#fff', cursor: 'pointer' }}><Icon name="check" size={12} color="#fff" /></button>
        </span>
      ) : (
        <button onClick={() => setAdding(true)} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, font: `500 13px/1 ${T.sans}`, padding: '8px 13px', borderRadius: 9999, cursor: 'pointer', border: `1px dashed ${T.borderDefault}`, background: T.raised, color: T.secondary }}>
          <Icon name="plus" size={13} color={T.tertiary} /> Add
        </button>
      )}
    </div>
  );
}

// Build engine selection. Both paths look identical downstream — same factory,
// same console — only the underlying coding agent differs.
const ENGINES = [
  { id: 'claude', name: 'Claude', tag: 'Default', desc: 'Anthropic Claude — the factory’s native build agent.' },
  { id: 'opencode', name: 'OpenCode', desc: 'Open-source agent runtime — pick the model below.' },
];
const OC_MODELS = [
  { id: 'kimi', name: 'Kimi K2.7', vendor: 'Moonshot AI' },
  { id: 'glm', name: 'GLM 5.2', vendor: 'Zhipu AI' },
];
function engineLabel(e) {
  if (!e || e.provider === 'claude') return 'Claude';
  const m = OC_MODELS.find((x) => x.id === e.model);
  return `OpenCode · ${m ? m.name : 'OpenCode'}`;
}

function EngineCardBtn({ active, name, desc, tag, onClick }) {
  return (
    <button onClick={onClick} style={{ textAlign: 'left', flex: 1, padding: '14px 15px', borderRadius: T.rLg, cursor: 'pointer',
      border: `1.5px solid ${active ? T.brand : T.borderSubtle}`, background: active ? T.brandSoft : T.raised, transition: 'all .12s', display: 'flex', flexDirection: 'column', gap: 5 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ width: 16, height: 16, borderRadius: '50%', flexShrink: 0, border: `1.5px solid ${active ? T.brand : T.borderDefault}`, background: active ? T.brand : 'transparent', display: 'grid', placeItems: 'center' }}>
          {active && <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#fff' }} />}
        </span>
        <span style={{ font: `600 14px/1.2 ${T.sans}`, color: T.fg }}>{name}</span>
        {tag && <span style={{ font: `600 9px/1 ${T.mono}`, letterSpacing: '0.06em', color: T.brandDeep, background: T.brandSoft, border: `1px solid ${T.brand}44`, padding: '2px 5px', borderRadius: 3 }}>{tag.toUpperCase()}</span>}
      </div>
      <span style={{ font: `400 12px/1.45 ${T.sans}`, color: T.secondary, paddingLeft: 24 }}>{desc}</span>
    </button>
  );
}

function EnginePicker({ value, onChange }) {
  const set = (patch) => onChange({ ...value, ...patch });
  const provLabel = value.provider === 'claude' ? 'Claude' : (OC_MODELS.find((m) => m.id === value.model) || {}).name || 'OpenCode';
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', gap: 10 }}>
        {ENGINES.map((e) => <EngineCardBtn key={e.id} active={value.provider === e.id} name={e.name} desc={e.desc} tag={e.tag} onClick={() => set({ provider: e.id })} />)}
      </div>
      {value.provider === 'opencode' && (
        <Field label="OpenCode model">
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {OC_MODELS.map((m) => {
              const on = value.model === m.id;
              return (
                <button key={m.id} onClick={() => set({ model: m.id })} style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 2, padding: '9px 14px', borderRadius: T.rMd, cursor: 'pointer',
                  border: `1.5px solid ${on ? T.brand : T.borderSubtle}`, background: on ? T.brandSoft : T.raised }}>
                  <span style={{ font: `600 13px/1 ${T.sans}`, color: T.fg }}>{m.name}</span>
                  <span style={{ font: `400 10.5px/1 ${T.mono}`, color: T.tertiary }}>{m.vendor}</span>
                </button>
              );
            })}
          </div>
        </Field>
      )}
      <Field label="API key">
        <Segmented value={value.keySource} onChange={(v) => set({ keySource: v })} options={[{ id: 'tenexity', label: 'Use Tenexity’s key' }, { id: 'byok', label: 'Bring your own key' }]} />
        <div style={{ marginTop: 10 }}>
          {value.keySource === 'tenexity'
            ? <div style={{ display: 'flex', alignItems: 'center', gap: 6, font: `400 11.5px/1.45 ${T.sans}`, color: T.secondary }}><Sparkle size={11} color={T.brandDeep} /> {provLabel} runs on Tenexity’s key — billed through your plan and rolled into the project budget.</div>
            : <TextInput mono value={value.key} onChange={(v) => set({ key: v })} placeholder={value.provider === 'claude' ? 'sk-ant-…' : 'paste provider API key'} type={value.key ? 'password' : 'text'} style={value.key ? { borderColor: T.brand, background: T.brandSoft } : {}} />}
        </div>
      </Field>
    </div>
  );
}
// Pull existing org knowledge-base documents into this project.
function OrgImportPicker() {
  const [open, setOpen] = React.useState(false);
  const [picked, setPicked] = React.useState([]);
  const docs = (window.ORG_DOCS || []);
  const toggle = (n) => setPicked((p) => p.includes(n) ? p.filter((x) => x !== n) : [...p, n]);
  return (
    <div style={{ border: `1px solid ${open ? T.brand + '55' : T.borderSubtle}`, borderRadius: T.rLg, background: open ? T.brandSoft + '33' : T.raised, overflow: 'hidden' }}>
      <button onClick={() => setOpen((v) => !v)} style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 10, padding: '11px 13px', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left' }}>
        <span style={{ width: 28, height: 28, borderRadius: 7, display: 'grid', placeItems: 'center', background: T.brandSoft, color: T.brandDeep, flexShrink: 0 }}><Icon name="building" size={14} color={T.brandDeep} /></span>
        <span style={{ flex: 1 }}>
          <span style={{ display: 'block', font: `600 13px/1.2 ${T.sans}`, color: T.fg }}>Import from organization</span>
          <span style={{ display: 'block', font: `400 11.5px/1.3 ${T.sans}`, color: T.tertiary, marginTop: 2 }}>Reuse documents already on file{picked.length ? ` · ${picked.length} selected` : ''}</span>
        </span>
        <Icon name={open ? 'chevronDown' : 'chevronRight'} size={15} color={T.tertiary} />
      </button>
      {open && (
        <div style={{ borderTop: `1px solid ${T.borderSubtle}` }}>
          {docs.map((d) => {
            const on = picked.includes(d.name);
            const k = (window.FILE_KIND && window.FILE_KIND[d.kind]) || ['DOC', T.brandSoft, T.brandDeep];
            return (
              <button key={d.name} onClick={() => toggle(d.name)} style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 10, padding: '10px 13px', background: on ? T.brandSoft + '55' : 'transparent', border: 'none', borderTop: `1px solid ${T.borderSubtle}`, cursor: 'pointer', textAlign: 'left' }}>
                <span style={{ width: 16, height: 16, flexShrink: 0, borderRadius: 4, display: 'grid', placeItems: 'center', background: on ? T.brand : 'transparent', border: on ? 'none' : `1.5px solid ${T.borderDefault}` }}>{on && <Icon name="check" size={11} color="#fff" />}</span>
                <span style={{ font: `700 9px/1 ${T.mono}`, color: k[2], background: k[1], padding: '3px 5px', borderRadius: 4 }}>{k[0]}</span>
                <span style={{ flex: 1, font: `500 12.5px/1.2 ${T.sans}`, color: T.fg }}>{d.name}</span>
                <span style={{ font: `400 10.5px/1 ${T.mono}`, color: T.tertiary }}>{d.tag}</span>
              </button>
            );
          })}
          <div style={{ display: 'flex', justifyContent: 'flex-end', padding: '10px 13px', borderTop: `1px solid ${T.borderSubtle}` }}>
            <Btn variant="primary" size="sm" disabled={!picked.length}>Attach {picked.length || ''} to project</Btn>
          </div>
        </div>
      )}
    </div>
  );
}

// Per-project budget cap — the absolute spend ceiling for the whole project.
// The build pauses for approval when total spend reaches the cap.
function BudgetPicker({ value, onChange }) {
  const presets = [30, 60, 120, 250];
  const isCustom = !presets.includes(value);
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
      {presets.map((v) => {
        const on = value === v;
        return <button key={v} onClick={() => onChange(v)} style={{ font: `600 13px/1 ${T.sans}`, padding: '8px 14px', borderRadius: 9999, cursor: 'pointer', border: `1.5px solid ${on ? T.brand : T.borderSubtle}`, background: on ? T.brandSoft : T.raised, color: on ? T.brandDeep : T.secondary }}>${v}</button>;
      })}
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, padding: '0 12px', height: 35, borderRadius: 9999, border: `1.5px solid ${isCustom ? T.brand : T.borderSubtle}`, background: isCustom ? T.brandSoft : T.raised }}>
        <span style={{ font: `600 13px/1 ${T.mono}`, color: T.tertiary }}>$</span>
        <input type="number" min="1" value={value} onChange={(e) => onChange(Math.max(0, parseInt(e.target.value, 10) || 0))} placeholder="custom"
          style={{ width: 58, border: 'none', outline: 'none', background: 'transparent', font: `600 13px/1 ${T.mono}`, color: isCustom ? T.brandDeep : T.fg }} />
      </span>
      <span style={{ font: `400 12px/1.4 ${T.sans}`, color: T.tertiary }}>total project ceiling · the build pauses for approval when spend reaches the cap</span>
    </div>
  );
}

function OptionC({ onExit, onBackground }) {
  const [mode, setMode] = React.useState('returning'); // 'fresh' | 'returning'
  const [view, setView] = React.useState('intake'); // intake | processing | interview | build
  const [interviewDone, setInterviewDone] = React.useState(false);
  const onFile = {
    company: 'Acme Industrial Supply', industry: 'Industrial Distribution',
    scale: '51–200 people · $10M–$50M', systems: ['Epicor'], role: 'Operations',
    subFocus: 'MRO / maintenance', website: 'acme-industrial.com',
    files: ['line-card.pdf', 'standard-pricing.xlsx'],
  };
  const [editOrg, setEditOrg] = React.useState(false);
  const [org, setOrg] = React.useState({
    company: onFile.company, industry: onFile.industry, scale: onFile.scale,
    systems: onFile.systems.join(', '), subFocus: onFile.subFocus, website: onFile.website,
  });
  const [scopeOptions, setScopeOptions] = React.useState(['Quoting / RFQ', 'Order entry', 'Pricing & approvals', 'Inventory', 'AP / AR', 'Customer comms']);
  const [saved, setSaved] = React.useState(false);
  const [draftSaved, setDraftSaved] = React.useState(false); // project name/goal committed → draft child created; unlocks the rest
  const saveTimer = React.useRef(null);
  const saveDraft = () => { setSaved(true); clearTimeout(saveTimer.current); saveTimer.current = setTimeout(() => setSaved(false), 2600); };
  // fresh-user company setup (empty — nothing on file yet)
  const [f, setF] = React.useState({ industry: '', sub: [], name: '', size: '', revenue: '', role: '', site: '', ints: [] });
  const setFresh = (k, v) => setF((x) => ({ ...x, [k]: v }));
  // project answers (shared; prefilled so returning is one-click)
  const [p, setP] = React.useState({
    name: 'Quote-to-Epicor automation',
    goal: 'Replace the manual quoting spreadsheet — build quotes against our Epicor SKUs and price book, route >15% discounts to a manager for approval, and write the won quote straight back to Epicor.',
    scope: ['Quoting / RFQ', 'Pricing & approvals'], video: false, docs: false, budget: 30,
  });
  const setProj = (k, v) => setP((x) => ({ ...x, [k]: v }));
  const [engine, setEngine] = React.useState({ provider: 'claude', model: 'kimi', keySource: 'tenexity', key: '' });
  const projectName = `Acme Industrial · ${p.name || 'New project'}`;
  if (view === 'build') return <BuildProgress onBack={() => setView('interview')} backLabel="Interview" projectName={projectName} engine={engine} budget={p.budget} />;
  if (view === 'processing') return <ProcessingScreen projectName={projectName} onDone={() => setView('interview')} onBackground={onBackground ? () => onBackground({ name: p.name, goal: p.goal }) : undefined} />;
  if (view === 'interview') return <InterviewView p={p} engine={engine} onFile={onFile} done={interviewDone} onComplete={() => setInterviewDone(true)} onBack={() => setView('intake')} onHandoff={() => setView('build')} />;

  const fresh = mode === 'fresh';
  const projChecks = [
    { id: 'name', label: 'Project name', done: !!p.name },
    { id: 'goal', label: 'What you’re building', done: p.goal.length > 20 },
    { id: 'scope', label: 'Scope of work', done: p.scope.length > 0 },
  ];
  const companyChecks = [
    { id: 'industry', label: 'Industry', done: !!f.industry },
    { id: 'profile', label: 'Company profile', done: !!f.name && !!f.size },
    { id: 'systems', label: 'Connect a system', done: f.ints.length > 0, optional: true, nudge: 'Optional — lets the factory pull real SKUs & pricing.' },
  ];
  const projReady = projChecks.every((c) => c.done);
  const ready = fresh ? (f.industry && f.name && f.size && projReady) : projReady;
  // Step 0: the project must be created before the rest of intake is usable.
  // Naming it + Save fires a POST that writes the project to the DB in `draft`
  // state; everything after enriches it and advances its state (draft →
  // collecting information → building).
  const canSaveDraft = p.name.trim().length > 0 || p.goal.trim().length > 0;

  const SaveBasics = () => (
    <div style={{ marginTop: 18, paddingTop: 16, borderTop: `1px solid ${T.borderSubtle}` }}>
      {draftSaved ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
          <span style={{ width: 22, height: 22, borderRadius: '50%', background: T.successSoft, display: 'grid', placeItems: 'center', flexShrink: 0 }}><Icon name="check" size={13} color={T.success} /></span>
          <span style={{ font: `400 12.5px/1.45 ${T.sans}`, color: T.secondary }}><b style={{ color: T.success }}>Project created</b> — “{p.name || 'Untitled project'}” is saved. Enrich it below to move it toward build.</span>
        </div>
      ) : (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 14, flexWrap: 'wrap' }}>
          <span style={{ font: `400 12.5px/1.45 ${T.sans}`, color: T.tertiary, maxWidth: 380 }}>Name the project and save to create it. The rest — scope, engine &amp; materials — unlocks once it exists.</span>
          <Btn variant="primary" onClick={() => setDraftSaved(true)} disabled={!canSaveDraft} title={canSaveDraft ? 'Create this project' : 'Enter a project name first'}><Icon name="check" size={14} color="#fff" /> Create project</Btn>
        </div>
      )}
    </div>
  );

  const LockedGroup = ({ children }) => draftSaved ? <React.Fragment>{children}</React.Fragment> : (
    <div style={{ position: 'relative' }}>
      <div aria-hidden="true" style={{ display: 'flex', flexDirection: 'column', gap: 16, opacity: 0.4, filter: 'grayscale(0.5)', pointerEvents: 'none', userSelect: 'none' }}>{children}</div>
      <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'flex-start', justifyContent: 'center', paddingTop: 30 }}>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 9, padding: '11px 17px', borderRadius: 9999, background: T.raised, border: `1px solid ${T.borderDefault}`, boxShadow: T.shadowSm, font: `500 12.5px/1 ${T.sans}`, color: T.secondary }}>
          <Icon name="lock" size={14} color={T.tertiary} /> Create the project above to unlock
        </div>
      </div>
    </div>
  );

  const Card = ({ cat, title, desc, children, accent }) => (
    <section style={{ background: T.raised, border: `1px solid ${accent ? T.brand + '55' : T.borderSubtle}`, borderRadius: T.rXl, padding: '22px 24px', boxShadow: T.shadowXs }}>
      <CategoryLabel style={{ marginBottom: 7 }} tone={accent ? 'brand' : 'tertiary'}>{cat}</CategoryLabel>
      <h3 style={{ font: `700 19px/1.25 ${T.display}`, letterSpacing: '-0.015em', color: T.fg, margin: 0 }}>{title}</h3>
      {desc && <p style={{ font: `400 13px/1.5 ${T.sans}`, color: T.secondary, margin: '6px 0 0' }}>{desc}</p>}
      <div style={{ marginTop: 18 }}>{children}</div>
    </section>
  );

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: T.bg, fontFamily: T.sans }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 24px', background: T.raised, borderBottom: `1px solid ${T.borderSubtle}`, flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {onExit && <Btn variant="ghost" size="sm" onClick={onExit}><Icon name="arrowLeft" size={14} /> Projects</Btn>}
          <Wordmark />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {!fresh && <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Avatar name={onFile.company} size={24} tone="neutral" /><span style={{ font: `500 12.5px/1.2 ${T.sans}`, color: T.secondary }}>{onFile.company}</span></div>}
          <Segmented value={mode} onChange={setMode} options={[{ id: 'fresh', label: 'First-time' }, { id: 'returning', label: 'Returning' }]} />
        </div>
      </div>

      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        {/* scrolling intake column */}
        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          <div style={{ flex: 1, overflow: 'auto', padding: '26px 32px' }}>
            <div style={{ maxWidth: 720, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 16 }}>

              {fresh ? (
                <React.Fragment>
                  <div>
                    <CategoryLabel style={{ marginBottom: 9 }} tone="brand">Welcome to the Software Factory</CategoryLabel>
                    <h1 style={{ font: `700 30px/1.15 ${T.display}`, letterSpacing: '-0.02em', color: T.fg, margin: 0 }}>Let’s set up your company, then your first project</h1>
                    <p style={{ font: `400 14px/1.5 ${T.sans}`, color: T.secondary, margin: '8px 0 0', maxWidth: 560 }}>
                      We’ll remember all of this — next time you start a project we won’t ask again. The Concierge on the right will guide you.
                    </p>
                  </div>

                  <SectionDivider label="Your organization" sub="set up once · reused on every project" icon="building" />

                  <Card cat="Your company" title="What kind of operation is this?" desc="Tuned for industrial & IT distribution.">
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 9 }}>
                      {INDUSTRIES.map((it) => <IndustryTile key={it.id} item={it} compact selected={f.industry === it.id} onClick={() => setFresh('industry', it.id)} />)}
                    </div>
                    <div style={{ marginTop: 16 }}><Field label="Sub-focus" optional><Chips multi options={['MRO / maintenance', 'OEM supply', 'Project / spec', 'E-commerce', 'Field service']} value={f.sub} onChange={(v) => setFresh('sub', v)} /></Field></div>
                  </Card>

                  <Card cat="Your company" title="Company profile">
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                      <Field label="Company name" style={{ gridColumn: '1 / -1' }}><TextInput value={f.name} onChange={(v) => setFresh('name', v)} placeholder="e.g. Acme Industrial Supply" /></Field>
                      <Field label="Headcount"><Chips options={SIZES} value={f.size} onChange={(v) => setFresh('size', v)} /></Field>
                      <Field label="Annual revenue"><Chips options={REVENUE} value={f.revenue} onChange={(v) => setFresh('revenue', v)} /></Field>
                      <Field label="Your role"><Chips options={ROLES} value={f.role} onChange={(v) => setFresh('role', v)} /></Field>
                      <Field label="Website" optional><TextInput value={f.site} onChange={(v) => setFresh('site', v)} placeholder="acme-industrial.com" /></Field>
                    </div>
                  </Card>

                  <Card cat="Your company" title="Connect your systems" desc="Link a system to pull in real SKUs, customers, and pricing. You’ll only do this once.">
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                      {INTEGRATIONS.map((it) => <IntegrationRow key={it.id} item={it} connected={f.ints.includes(it.id)}
                        onToggle={() => setFresh('ints', f.ints.includes(it.id) ? f.ints.filter((x) => x !== it.id) : [...f.ints, it.id])} />)}
                    </div>
                  </Card>

                  <SectionDivider label="This project" sub="specific to what you're building now" icon="layers" />

                  <Card cat="Your first project" title="Project basics" accent>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                      <Field label="Project name"><TextInput value={p.name} onChange={(v) => setProj('name', v)} placeholder="e.g. Quote-to-Epicor automation" /></Field>
                      <Field label="What are you building?" hint="One or two sentences on the outcome you want.">
                        <TextArea rows={3} value={p.goal} onChange={(v) => setProj('goal', v)} placeholder="e.g. Replace the manual quoting spreadsheet and write won quotes back to Epicor…" />
                      </Field>
                      <Field label="Project budget cap"><BudgetPicker value={p.budget} onChange={(v) => setProj('budget', v)} /></Field>
                    </div>
                    <SaveBasics />
                  </Card>
                  <LockedGroup>
                  <Card cat="Your first project" title="Recipe" desc="Start from a proven blueprint the Tenexity team maintains, or choose No template to build purely from your brief.">
                    <RecipePicker value={p.recipe} onChange={(v) => setProj('recipe', v)} />
                  </Card>
                  <Card cat="Your first project" title="Scope of work" desc="Which parts of the business does this project touch?">
                    <ScopeOfWork options={scopeOptions} value={p.scope} onChange={(v) => setProj('scope', v)} onAddOption={(o) => setScopeOptions((s) => s.includes(o) ? s : [...s, o])} />
                  </Card>
                  <Card cat="Your first project" title="Build engine" desc="Choose the coding agent that builds this project. The factory, console, and output look the same either way.">
                    <EnginePicker value={engine} onChange={setEngine} />
                  </Card>
                  <Card cat="Your first project" title="Project materials" desc="A walkthrough recording is the highest-signal input you can give.">
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                      <OrgImportPicker />
                      <Field label="Walkthrough video" optional><Dropzone kind="video" describe filled={p.video} onToggle={() => setProj('video', !p.video)} /></Field>
                      <Field label="Supporting documents" optional><Dropzone kind="docs" describe filled={p.docs} onToggle={() => setProj('docs', !p.docs)} /></Field>
                    </div>
                  </Card>
                  </LockedGroup>
                </React.Fragment>
              ) : (
                <React.Fragment>
                  <div>
                    <CategoryLabel style={{ marginBottom: 9 }}>New project</CategoryLabel>
                    <h1 style={{ font: `700 30px/1.15 ${T.display}`, letterSpacing: '-0.02em', color: T.fg, margin: 0 }}>What are we building this time?</h1>
                    <p style={{ font: `400 14px/1.5 ${T.sans}`, color: T.secondary, margin: '8px 0 0', maxWidth: 560 }}>
                      Your company context is already on file — no need to repeat it. Just tell the Concierge about this project.
                    </p>
                  </div>

                  <SectionDivider label="Your organization" sub="on file · reused automatically" icon="building" />

                  <section style={{ borderRadius: T.rXl, border: `1px solid ${editOrg ? T.brand + '55' : T.borderSubtle}`, background: T.sunken, overflow: 'hidden' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 20px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <Icon name="check" size={15} color={T.success} />
                        <span style={{ font: `600 13.5px/1.2 ${T.sans}`, color: T.fg }}>From {onFile.company} · on file</span>
                        <span style={{ font: `400 12px/1.2 ${T.sans}`, color: T.tertiary }}>· reused automatically</span>
                      </div>
                      <button onClick={() => setEditOrg((v) => !v)} style={{ font: `500 12.5px/1 ${T.sans}`, color: T.brandDeep, background: 'none', border: 'none', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                        {editOrg ? 'Done' : 'Manage'} <Icon name={editOrg ? 'chevronDown' : 'chevronRight'} size={13} color={T.brandDeep} />
                      </button>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1px', background: T.borderSubtle, borderTop: `1px solid ${T.borderSubtle}` }}>
                      <OrgCell label="Company" value={org.company} editing={editOrg} onChange={(v) => setOrg({ ...org, company: v })} />
                      <OrgCell label="Industry" value={org.industry} editing={editOrg} onChange={(v) => setOrg({ ...org, industry: v })} />
                      <OrgCell label="Scale" value={org.scale} editing={editOrg} onChange={(v) => setOrg({ ...org, scale: v })} />
                      <OrgCell label="Connected systems" value={org.systems} editing={editOrg} onChange={(v) => setOrg({ ...org, systems: v })} />
                      <OrgCell label="Sub-focus" value={org.subFocus} editing={editOrg} onChange={(v) => setOrg({ ...org, subFocus: v })} />
                      <OrgCell label="Website" value={org.website} editing={editOrg} onChange={(v) => setOrg({ ...org, website: v })} />
                    </div>
                    {editOrg && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '10px 20px', borderTop: `1px solid ${T.borderSubtle}`, background: T.raised }}>
                        <Sparkle size={11} color={T.brandDeep} />
                        <span style={{ font: `400 11.5px/1.4 ${T.sans}`, color: T.tertiary }}>Edits update your organization profile — reused on every future project.</span>
                      </div>
                    )}
                  </section>

                  <SectionDivider label="This project" sub="specific to what you're building now" icon="layers" />

                  <Card cat="This project" title="Project basics" accent>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                      <Field label="Project name"><TextInput value={p.name} onChange={(v) => setProj('name', v)} placeholder="e.g. Quote-to-Epicor automation" /></Field>
                      <Field label="What are you building?" hint="One or two sentences on the outcome you want.">
                        <TextArea rows={3} value={p.goal} onChange={(v) => setProj('goal', v)} placeholder="e.g. Replace the manual quoting spreadsheet…" />
                      </Field>
                      <Field label="Project budget cap"><BudgetPicker value={p.budget} onChange={(v) => setProj('budget', v)} /></Field>
                    </div>
                    <SaveBasics />
                  </Card>
                  <LockedGroup>
                  <Card cat="This project" title="Recipe" desc="Start from a proven blueprint the Tenexity team maintains, or choose No template to build purely from your brief.">
                    <RecipePicker value={p.recipe} onChange={(v) => setProj('recipe', v)} />
                  </Card>
                  <Card cat="This project" title="Scope of work" desc="Which parts of the business does this project touch?">
                    <ScopeOfWork options={scopeOptions} value={p.scope} onChange={(v) => setProj('scope', v)} onAddOption={(o) => setScopeOptions((s) => s.includes(o) ? s : [...s, o])} />
                  </Card>
                  <Card cat="This project" title="Build engine" desc="Choose the coding agent that builds this project. The factory, console, and output look the same either way.">
                    <EnginePicker value={engine} onChange={setEngine} />
                  </Card>
                  <Card cat="This project" title="Project materials" desc="We already have your line card & pricing on file — only add what's specific to this project.">
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                      <OrgImportPicker />
                      <Field label="Project walkthrough video" optional><Dropzone kind="video" describe filled={p.video} onToggle={() => setProj('video', !p.video)} /></Field>
                      <Field label="Extra documents" optional><Dropzone kind="docs" describe filled={p.docs} onToggle={() => setProj('docs', !p.docs)} /></Field>
                    </div>
                  </Card>
                  </LockedGroup>
                </React.Fragment>
              )}
            </div>
          </div>

          <div style={{ flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, padding: '13px 32px', borderTop: `1px solid ${T.borderSubtle}`, background: T.raised }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
              <Icon name="check" size={14} color={T.success} />
              <span style={{ font: `400 12.5px/1.3 ${T.sans}`, color: T.secondary, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {saved
                  ? <React.Fragment><b style={{ color: T.success }}>Draft saved</b> — resume and run it anytime from your Projects dashboard.</React.Fragment>
                  : fresh
                    ? <React.Fragment>Set up once, reused forever — <b style={{ color: T.fg }}>{[companyChecks[0], companyChecks[1], ...projChecks].filter((c) => c.done).length}/5</b> essentials done</React.Fragment>
                    : <React.Fragment>Company context reused — <b style={{ color: T.fg }}>{projChecks.filter((c) => c.done).length}/{projChecks.length}</b> project questions answered</React.Fragment>}
              </span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
              <Btn variant="secondary" onClick={saveDraft} title="Save your progress and run this project later">
                {saved ? <React.Fragment><Icon name="check" size={14} color={T.success} /> Saved</React.Fragment> : 'Save \u0026 finish later'}
              </Btn>
              <Btn variant="primary" onClick={() => setView('processing')} disabled={!ready} title={ready ? 'Process your materials, then a quick interview' : (fresh ? 'Set up your company & project to continue' : 'Answer the project questions to continue')} style={ready ? { background: T.success } : null}>Continue <Icon name="arrowRight" size={14} color="#fff" /></Btn>
            </div>
          </div>
        </div>

        {/* docked Concierge rail */}
        <div style={{ width: 320, flexShrink: 0, borderLeft: `1px solid ${T.borderSubtle}`, background: T.raised, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '16px 18px', borderBottom: `1px solid ${T.borderSubtle}` }}>
            <span style={{ width: 30, height: 30, borderRadius: '50%', display: 'grid', placeItems: 'center', background: T.brandSoft, color: T.brand, boxShadow: `inset 0 0 0 1px ${T.brand}33` }}><Sparkle size={14} color={T.brand} /></span>
            <div style={{ flex: 1 }}><span style={{ display: 'block', font: `600 13px/1.2 ${T.sans}`, color: T.fg }}>Concierge</span><CategoryLabel style={{ fontSize: 10 }}>{fresh ? 'Setting you up' : 'With you through launch'}</CategoryLabel></div>
            <StatusPill tone="success">online</StatusPill>
          </div>

          <div style={{ flex: 1, overflow: 'auto', padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 12 }}>
            <Message who="agent" text={fresh
              ? "Welcome! I’m your Concierge. First a quick company profile — I’ll remember it so you never re-enter it — then tell me about your first project."
              : `Welcome back. I already have ${onFile.company}'s profile, your Epicor link, and your line card from earlier projects — I'm reusing all of it. Let's just scope this project.`} />

            <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: 'hidden' }}>
              {fresh ? (
                <React.Fragment>
                  <GroupHead>Your company</GroupHead>
                  {companyChecks.map((c) => <CheckRow key={c.id} c={c} />)}
                  <GroupHead>Your first project</GroupHead>
                  {projChecks.map((c) => <CheckRow key={c.id} c={c} />)}
                </React.Fragment>
              ) : (
                <React.Fragment>
                  <GroupHead tone="success">On file · reused</GroupHead>
                  {['Company profile', 'Industry & scale', 'Epicor connection', 'Line card & pricing'].map((l) => (
                    <div key={l} style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '8px 12px', borderBottom: `1px solid ${T.borderSubtle}` }}>
                      <Icon name="check" size={13} color={T.success} /><span style={{ font: `500 12.5px/1.3 ${T.sans}`, color: T.fg }}>{l}</span>
                    </div>
                  ))}
                  <GroupHead>This project · to do</GroupHead>
                  {projChecks.map((c) => <CheckRow key={c.id} c={c} />)}
                </React.Fragment>
              )}
            </div>

            <Message who="agent" anim text={ready
              ? "That’s the setup done. Next I’ll process your uploads, then ask a few quick questions to sharpen the build — hit Continue when you’re ready."
              : fresh
                ? (f.industry ? "Great. Now the company basics — name and size — then we’ll scope your first project." : "Start by picking the kind of operation you run.")
                : (p.scope.length ? "Good. For the parts you picked, is the bottleneck more about speed, errors into Epicor, or manager visibility?" : "To start: what should this project actually do for the team?")} />

            <div style={{ padding: 12, borderRadius: T.rLg, border: `1px solid ${T.brand}33`, background: T.brandSoft + '66' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}><Icon name="arrowRight" size={12} color={T.brandDeep} /><CategoryLabel tone="brand">What’s next</CategoryLabel></div>
              <p style={{ font: `400 12px/1.5 ${T.sans}`, color: T.secondary, margin: 0 }}>When you continue I’ll read your uploads, then interview you to lock the scope. I stay on through the build — you steer the agents by talking to me.</p>
            </div>
          </div>

          <div style={{ flexShrink: 0, padding: '12px 16px', borderTop: `1px solid ${T.borderSubtle}` }}>
            <Composer placeholder="Tell the Concierge…" />
          </div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { OptionC });

// Interview phase — runs after processing. The left/main column is a calm
// "what I learned" review of the assumptions pulled from the uploads; the right
// rail is the active Concierge interview the user must complete before handoff.
const LEARNED = [
  { text: 'Quoting runs on Epicor; quotes are built in spreadsheets and re-keyed by hand.', band: 'exact', src: 'process-walkthrough.mp4' },
  { text: 'Standard price book covers 1,840 SKUs across 6 product lines with tiered discounts.', band: 'high', src: 'standard-pricing.xlsx' },
  { text: 'Discounts over 15% route to a sales manager for approval.', band: 'high', src: 'discount-matrix.xlsx' },
  { text: 'Volume looks like ~120 quotes/week — worth confirming.', band: 'medium', src: 'rfq-sop.pdf' },
];
function InterviewView({ p, engine, onFile, done, onComplete, onBack, onHandoff }) {
  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: T.bg, fontFamily: T.sans }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 24px', background: T.raised, borderBottom: `1px solid ${T.borderSubtle}`, flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Btn variant="ghost" size="sm" onClick={onBack}><Icon name="arrowLeft" size={14} /> Setup</Btn>
          <Wordmark />
          <span style={{ font: `400 13px/1 ${T.mono}`, color: T.tertiary }}>/</span>
          <span style={{ font: `600 13px/1 ${T.sans}`, color: T.fg }}>{p.name || 'New project'}</span>
        </div>
        <span style={{ font: `600 10px/1 ${T.mono}`, letterSpacing: '0.06em', color: T.brandDeep, background: T.brandSoft, border: `1px solid ${T.brand}44`, padding: '5px 8px', borderRadius: 5 }}>STEP 3 OF 3 · INTERVIEW</span>
      </div>

      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          <div style={{ flex: 1, overflow: 'auto', padding: '26px 32px' }}>
            <div style={{ maxWidth: 640, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 18 }}>
              <div>
                <CategoryLabel tone="brand" style={{ marginBottom: 9 }}>Materials processed · interviewing</CategoryLabel>
                <h1 style={{ font: `700 28px/1.18 ${T.display}`, letterSpacing: '-0.02em', color: T.fg, margin: 0 }}>Let’s confirm what I learned</h1>
                <p style={{ font: `400 14px/1.55 ${T.sans}`, color: T.secondary, margin: '8px 0 0', maxWidth: 520 }}>
                  I read everything you gave me and drafted the assumptions below. Answer my questions on the right to confirm or correct them — then we hand off to the factory.
                </p>
              </div>

              <section style={{ background: T.raised, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rXl, padding: '20px 22px', boxShadow: T.shadowXs }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 14 }}>
                  <Sparkle size={12} color={T.brand} /><CategoryLabel tone="brand">What I learned from your materials</CategoryLabel>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 11 }}>
                  {LEARNED.map((l) => (
                    <div key={l.src} className="ai-tint" style={{ display: 'flex', alignItems: 'flex-start', gap: 10, padding: '10px 12px', borderRadius: T.rMd }}>
                      <span style={{ flex: 1, font: `400 13px/1.5 ${T.sans}`, color: T.fg }}>{l.text}
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, marginLeft: 7, font: `400 11px/1 ${T.mono}`, color: T.tertiary }}><Icon name="file" size={11} color={T.tertiary} />{l.src}</span>
                      </span>
                      <ConfidencePill band={l.band} />
                    </div>
                  ))}
                </div>
              </section>

              <section style={{ background: T.sunken, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rXl, padding: '18px 22px' }}>
                <CategoryLabel style={{ marginBottom: 8 }}>This project</CategoryLabel>
                <div style={{ font: `700 16px/1.3 ${T.display}`, color: T.fg, marginBottom: 6 }}>{p.name || 'New project'}</div>
                <GoalMarkdown style={{ font: `400 13px/1.55 ${T.sans}`, color: T.secondary }}>{p.goal}</GoalMarkdown>
              </section>

              <div style={{ display: 'inline-flex', alignItems: 'center', gap: 7, font: `400 12.5px/1.4 ${T.sans}`, color: T.tertiary }}>
                <Icon name="arrowRight" size={14} color={T.brandDeep} /> Answer the Concierge’s questions on the right to continue.
              </div>
            </div>
          </div>

          <div style={{ flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, padding: '13px 32px', borderTop: `1px solid ${T.borderSubtle}`, background: T.raised }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 9, font: `400 12.5px/1.3 ${T.sans}`, color: done ? T.success : T.secondary }}>
              <Icon name={done ? 'check' : 'bot'} size={14} color={done ? T.success : T.tertiary} />
              {done ? <React.Fragment><b style={{ color: T.success }}>Interview complete</b> — ready to hand off to the factory.</React.Fragment> : 'Complete the interview on the right to unlock handoff.'}
            </span>
            <Btn variant="primary" onClick={onHandoff} disabled={!done} title={done ? 'Hand off to the build factory' : 'Finish the interview first'} style={done ? { background: T.success } : null}>Hand off to factory <Icon name="arrowRight" size={14} color="#fff" /></Btn>
          </div>
        </div>

        <InterviewRail onComplete={onComplete} />
      </div>
    </div>
  );
}
Object.assign(window, { InterviewView });

// Standalone wrapper for the onboarding artboard: gives OptionC a real exit
// target (back to the projects dashboard) so the "← Projects" / back affordance
// works even outside the connected FactoryApp flow.
function OnboardingStandalone() {
  const [stage, setStage] = React.useState('onboard'); // onboard | projects | home
  if (stage === 'projects') {
    return <Dashboard onNew={() => setStage('onboard')} onOpen={() => setStage('home')} onOrg={() => setStage('projects')} />;
  }
  if (stage === 'home') {
    return <ProjectViewStandalone ingesting onResumeInterview={() => setStage('onboard')} onBack={() => setStage('projects')} />;
  }
  return <OptionC onExit={() => setStage('projects')} onBackground={() => setStage('home')} />;
}
Object.assign(window, { OnboardingStandalone, BudgetPicker });
