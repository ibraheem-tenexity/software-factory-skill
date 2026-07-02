// buildprogress.jsx — shared downstream screen. Concierge rail (LEFT) +
// main column: pipeline stage-rail, wait-for-deps (3 options/dep),
// Graph ⇄ Kanban toggle, and the produced-artifact doc viewer.

function Segmented({ options, value, onChange }) {
  return (
    <div style={{ display: 'inline-flex', padding: 2, borderRadius: T.rMd, background: T.sunken, border: `1px solid ${T.borderSubtle}` }}>
      {options.map((o) => {
        const on = value === o.id;
        return (
          <button key={o.id} onClick={() => onChange(o.id)} style={{ font: `500 11.5px/1 ${T.sans}`, padding: '6px 10px', borderRadius: 6, cursor: 'pointer',
            border: 'none', background: on ? T.raised : 'transparent', color: on ? T.fg : T.tertiary, boxShadow: on ? T.shadowXs : 'none', transition: 'all .12s' }}>{o.label}</button>
        );
      })}
    </div>
  );
}

function DepRow({ dep, mode, keyVal, onMode, onKey }) {
  const resolved = mode === 'mcp' || mode === 'mock' || (mode === 'input' && keyVal);
  return (
    <div style={{ border: `1px solid ${resolved ? T.borderSubtle : T.warning}`, borderRadius: T.rLg, background: T.raised, padding: '12px 13px', display: 'flex', flexDirection: 'column', gap: 9 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, minWidth: 0 }}>
          <span style={{ font: `600 12.5px/1 ${T.sans}`, color: T.fg }}>{dep.label}</span>
          <span style={{ font: `400 10.5px/1 ${T.mono}`, color: T.tertiary, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{dep.hint}</span>
        </div>
        {resolved
          ? <Icon name="check" size={14} color={T.success} />
          : <span style={{ width: 6, height: 6, borderRadius: '50%', background: T.warning, flexShrink: 0 }} />}
      </div>
      <Segmented value={mode} onChange={onMode} options={[{ id: 'mcp', label: 'Get from MCP' }, { id: 'mock', label: 'Mock it' }, { id: 'input', label: 'Input key' }]} />
      {mode === 'mcp' && <div style={{ font: `400 11.5px/1.4 ${T.sans}`, color: T.success, display: 'flex', alignItems: 'center', gap: 5 }}><Icon name="link" size={12} color={T.success} /> Pulled from the {dep.label} MCP server — no key to manage.</div>}
      {mode === 'mock' && <div style={{ font: `400 11.5px/1.4 ${T.sans}`, color: T.secondary, display: 'flex', alignItems: 'center', gap: 5 }}><Sparkle size={11} color={T.brand} /> Mocked responses — build &amp; test now, wire the real service later.</div>}
      {mode === 'input' && <TextInput mono size="sm" value={keyVal} onChange={onKey} placeholder="paste API key" type={keyVal ? 'password' : 'text'} style={keyVal ? { borderColor: T.brand, background: T.brandSoft } : {}} />}
    </div>
  );
}

// Dependencies are discovered from the project's architecture — count varies by
// factory & app design. Scalable: the grid wraps to any number.
const DEPENDENCIES = [
  { id: 'epicor', label: 'Epicor API', hint: 'order & SKU sync', mode: 'mcp' },
  { id: 'openai', label: 'OpenAI', hint: 'quote drafting', mode: 'input' },
  { id: 'supabase', label: 'Supabase', hint: 'app database', mode: 'mock' },
  { id: 'sendgrid', label: 'SendGrid', hint: 'quote emails', mode: 'mcp' },
];

function depsStage() {
  const d = (typeof PIPELINE !== 'undefined') && PIPELINE.find((n) => n.id === 'deps');
  return { reached: !!(d && (d.done || d.active)) };
}

function DepsBar({ deps = DEPENDENCIES }) {
  // Only surfaces once the build pipeline reaches the wait-for-deps stage —
  // it is NOT shown for the rest of the run.
  if (!depsStage().reached) return null;
  const [st, setSt] = React.useState(() => Object.fromEntries(deps.map((d) => [d.id, { mode: d.mode, key: '' }])));
  const isResolved = (d) => { const s = st[d.id]; return s.mode === 'mcp' || s.mode === 'mock' || (s.mode === 'input' && s.key); };
  const resolved = deps.filter(isResolved).length;
  const allResolved = resolved === deps.length;
  const set = (id, patch) => setSt((p) => ({ ...p, [id]: { ...p[id], ...patch } }));
  return (
    <div style={{ border: `1px solid ${allResolved ? T.success : T.warning}`, background: allResolved ? T.successSoft + '66' : T.warningSoft, borderRadius: T.rLg, padding: '13px 15px', animation: 'sfRise .3s var(--ease-out, ease) both' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, marginBottom: 11, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
          <span style={{ width: 12, height: 12, background: allResolved ? T.success : T.warning, transform: 'rotate(45deg)', borderRadius: 2, flexShrink: 0 }} />
          <span style={{ font: `600 13px/1.3 ${T.sans}`, color: T.fg }}>{allResolved ? 'Dependencies resolved — build unblocked' : 'Wait for dependencies'}</span>
          <span style={{ font: `500 9.5px/1 ${T.mono}`, letterSpacing: '0.06em', color: allResolved ? T.success : T.warning, background: allResolved ? T.successSoft : T.warningSoft, border: `1px solid ${(allResolved ? T.success : T.warning)}55`, padding: '4px 6px', borderRadius: 4 }}>STAGE-TRIGGERED</span>
        </div>
        <span style={{ font: `500 11px/1 ${T.mono}`, color: allResolved ? T.success : T.warning }}>{resolved}/{deps.length} resolved</span>
      </div>
      <p style={{ margin: '0 0 12px', font: `400 11.5px/1.5 ${T.sans}`, color: T.secondary }}>
        Surfaced now because the build reached the <b style={{ color: T.fg }}>wait-for-deps</b> stage. This architecture needs <b style={{ color: T.fg }}>{deps.length}</b> external service{deps.length === 1 ? '' : 's'} — the set is derived from the design, so it grows or shrinks per project. For each: pull from MCP, mock it, or paste a key.
      </p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(228px, 1fr))', gap: 10 }}>
        {deps.map((d) => <DepRow key={d.id} dep={d} mode={st[d.id].mode} keyVal={st[d.id].key} onMode={(m) => set(d.id, { mode: m })} onKey={(k) => set(d.id, { key: k })} />)}
      </div>
    </div>
  );
}

function ConciergeRail({ done, total, allDone, onOpen }) {
  const updates = allDone
    ? [{ text: 'All ' + total + ' tickets are green and the app is deployed. Want me to walk you through the live build?' }]
    : [{ text: 'Build is underway — ' + done + '/' + total + ' tickets done. The Architect, Research, and Product agents have all filed their work (left).' },
       { text: 'Heads up: Playwright caught a tax-rounding bug on SF-11. Sonnet already pulled it back into Building to fix.' }];
  return (
    <div style={{ width: 326, flexShrink: 0, borderRight: `1px solid ${T.borderSubtle}`, background: T.raised, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '14px 18px', borderBottom: `1px solid ${T.borderSubtle}` }}>
        <span style={{ width: 30, height: 30, borderRadius: '50%', display: 'grid', placeItems: 'center', background: T.brandSoft, color: T.brand, boxShadow: `inset 0 0 0 1px ${T.brand}33` }}><Sparkle size={14} color={T.brand} /></span>
        <div style={{ flex: 1 }}><span style={{ display: 'block', font: `600 13px/1.2 ${T.sans}`, color: T.fg }}>Concierge</span><CategoryLabel style={{ fontSize: 10 }}>Relaying the build</CategoryLabel></div>
        <StatusPill tone="success">online</StatusPill>
      </div>
      <div style={{ flex: 1, overflow: 'auto', padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
        {updates.map((m, i) => <Message key={i} who="agent" text={m.text} confidence={i === 0 && allDone ? 'exact' : undefined} anim={i === 0} />)}
        <ArtifactList onOpen={onOpen} />
        <div style={{ padding: 11, borderRadius: T.rLg, border: `1px solid ${T.brand}33`, background: T.brandSoft + '66' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 5 }}><Sparkle size={11} color={T.brandDeep} /><CategoryLabel tone="brand">Steer the build</CategoryLabel></div>
          <p style={{ font: `400 12px/1.5 ${T.sans}`, color: T.secondary, margin: 0 }}>Ask me to reprioritize a ticket, change scope, or pause an agent — I'll pass it straight to the build team.</p>
        </div>
      </div>
      <div style={{ flexShrink: 0, padding: '12px 16px', borderTop: `1px solid ${T.borderSubtle}` }}>
        <Composer placeholder="Ask or steer the build team…" />
      </div>
    </div>
  );
}

function BuildProgress({ onBack, backLabel = 'Intake', projectName = 'Acme Industrial · Quote-to-ERP', peerTabs }) {
  const sim = useBuildSim();
  const [view, setView] = React.useState('kanban');
  const [doc, setDoc] = React.useState(null);
  const pct = Math.round((sim.done / sim.total) * 100);
  const allDone = sim.done === sim.total;
  return (
    <div style={{ height: '100%', position: 'relative', display: 'flex', flexDirection: 'column', background: T.bg, fontFamily: T.sans }}>
      <div style={{ background: T.raised, borderBottom: `1px solid ${T.borderSubtle}` }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '13px 22px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          {onBack && !peerTabs && <Btn variant="ghost" size="sm" onClick={onBack}><Icon name="arrowLeft" size={14} /> {backLabel}</Btn>}
          {peerTabs && <Btn variant="ghost" size="sm" onClick={() => peerTabs.onSwitch('exit')}><Icon name="arrowLeft" size={14} /> Projects</Btn>}
          <Wordmark size={17} />
          <span style={{ font: `400 13px/1 ${T.mono}`, color: T.tertiary }}>/</span>
          <span style={{ font: `600 13px/1 ${T.sans}`, color: T.fg }}>{projectName}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <StatusPill tone="warning">phase build · stage 3</StatusPill>
          <span style={{ font: `500 12px/1 ${T.mono}`, color: T.secondary }}>spent <b style={{ color: T.fg }}>$4.20</b> / $30 cap</span>
        </div>
      </div>
      {peerTabs && (
        <div style={{ display: 'flex', gap: 2, padding: '0 22px' }}>
          {[{ id: 'overview', label: 'Overview' }, { id: 'build', label: 'Factory console' }, { id: 'docs', label: 'Documents' }].map((t) => {
            const on = t.id === 'build';
            return <button key={t.id} onClick={() => peerTabs.onSwitch(t.id)} style={{ position: 'relative', padding: '11px 14px', background: 'none', border: 'none', cursor: 'pointer',
              font: `${on ? 600 : 500} 13px/1 ${T.sans}`, color: on ? T.fg : T.secondary }}>
              {t.label}
              {on && <span style={{ position: 'absolute', left: 10, right: 10, bottom: -1, height: 2, background: T.brand, borderRadius: 2 }} />}
            </button>;
          })}
        </div>
      )}
      </div>

      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        <ConciergeRail done={sim.done} total={sim.total} allDone={allDone} onOpen={setDoc} />

        <div style={{ flex: 1, minWidth: 0, padding: '18px 22px', display: 'flex', flexDirection: 'column', gap: 15 }}>
          <StageRail />
          <DepsBar />

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <span style={{ font: `700 16px/1 ${T.display}`, letterSpacing: '-0.015em', color: T.fg }}>{view === 'kanban' ? 'Build board' : view === 'tree' ? 'Process tree' : 'Process graph'}</span>
              <span style={{ font: `500 11px/1 ${T.mono}`, color: T.secondary }}>{sim.done}/{sim.total} tickets · {pct}%</span>
              <span style={{ width: 110, height: 6, borderRadius: 3, background: T.sunken, overflow: 'hidden', display: 'inline-block' }}>
                <span style={{ display: 'block', height: '100%', width: pct + '%', background: allDone ? T.success : T.brand, transition: 'width .5s' }} />
              </span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <Segmented value={view} onChange={setView} options={[{ id: 'kanban', label: 'Kanban' }, { id: 'tree', label: 'Tree' }, { id: 'map', label: 'Map' }]} />
              {!allDone && view === 'kanban' && (
                <Btn variant={sim.playing ? 'secondary' : 'primary'} size="sm" onClick={() => sim.setPlaying(!sim.playing)}>
                  <Icon name={sim.playing ? 'pause' : 'play'} size={13} color={sim.playing ? T.fg : '#fff'} /> {sim.playing ? 'Pause agents' : 'Run agents'}
                </Btn>
              )}
              {allDone && <StatusPill tone="success">all shipped</StatusPill>}
            </div>
          </div>

          <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
            {view === 'kanban'
              ? <div style={{ height: '100%', overflow: 'auto', paddingRight: 2 }}><Kanban tickets={sim.tickets} justMoved={sim.justMoved} /></div>
              : view === 'tree'
              ? <GraphView onOpen={setDoc} sim={sim} onViewTickets={() => setView('kanban')} />
              : <NodeMap onOpen={setDoc} />}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '11px 15px', borderRadius: T.rLg,
            background: allDone ? T.successSoft : T.raised, border: `1px solid ${allDone ? T.success : T.borderSubtle}` }}>
            {allDone ? (
              <React.Fragment>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, font: `600 13px/1.3 ${T.sans}`, color: T.success }}>
                  <Icon name="check" size={15} color={T.success} /> Deployed · green across the Playwright suite
                </span>
                <div style={{ display: 'flex', gap: 9 }}>
                  <Btn variant="secondary" size="sm" onClick={() => setDoc({ id: 'repo', kind: 'repo', label: 'acme-quote-to-erp', agent: 'Provision agent' })}>Repository</Btn>
                  <Btn variant="primary" size="sm">Open live app <Icon name="arrowRight" size={13} color="#fff" /></Btn>
                </div>
              </React.Fragment>
            ) : (
              <React.Fragment>
                <span style={{ font: `400 12.5px/1.4 ${T.sans}`, color: T.secondary }}>Bugs found in <b style={{ color: T.fg }}>Testing</b> loop back to <b style={{ color: T.fg }}>Building</b> before a ticket reaches <b style={{ color: T.fg }}>Done</b>.</span>
                <span style={{ font: `500 11px/1 ${T.mono}`, color: T.tertiary }}>deploy unlocks at 100%</span>
              </React.Fragment>
            )}
          </div>
        </div>
      </div>

      <DocViewer artifact={doc} onClose={() => setDoc(null)} />
    </div>
  );
}

Object.assign(window, { BuildProgress, DepsBar, ConciergeRail, Segmented });
