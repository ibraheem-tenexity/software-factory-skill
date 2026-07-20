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
  const [pickOpen, setPickOpen] = React.useState(false);
  const secrets = (typeof window !== 'undefined' && window.ORG_SECRETS) || [];
  const imported = mode === 'input' && typeof keyVal === 'string' && keyVal.indexOf('org:') === 0;
  const importedName = imported ? keyVal.slice(4) : '';
  const resolved = mode === 'mcp' || mode === 'mock' || (mode === 'input' && keyVal);
  const norm = (s) => (s || '').toLowerCase().replace(/[^a-z]/g, '');
  const suggested = (s) => norm(s.label + s.name).indexOf(norm(dep.label)) >= 0 || norm(dep.label).indexOf(norm(s.kind)) >= 0;
  const ordered = [...secrets].sort((a, b) => (suggested(b) ? 1 : 0) - (suggested(a) ? 1 : 0));
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
      <Segmented value={mode} onChange={(m) => { onMode(m); setPickOpen(false); }} options={[{ id: 'mcp', label: 'Get from MCP' }, { id: 'mock', label: 'Mock it' }, { id: 'input', label: 'Input key' }]} />
      {mode === 'mcp' && <div style={{ font: `400 11.5px/1.4 ${T.sans}`, color: T.success, display: 'flex', alignItems: 'center', gap: 5 }}><Icon name="link" size={12} color={T.success} /> Pulled from the {dep.label} MCP server — no key to manage.</div>}
      {mode === 'mock' && <div style={{ font: `400 11.5px/1.4 ${T.sans}`, color: T.secondary, display: 'flex', alignItems: 'center', gap: 5 }}><Sparkle size={11} color={T.brand} /> Mocked responses — build &amp; test now, wire the real service later.</div>}
      {mode === 'input' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {imported ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '9px 11px', borderRadius: T.rMd, border: `1px solid ${T.brand}55`, background: T.brandSoft }}>
              <Icon name="lock" size={13} color={T.brandDeep} />
              <span style={{ flex: 1, minWidth: 0, font: `500 12px/1.3 ${T.sans}`, color: T.brandDeep }}>Imported <span style={{ font: `600 12px/1 ${T.mono}` }}>{importedName}</span> from the org vault</span>
              <button onClick={() => onKey('')} style={{ font: `500 11px/1 ${T.sans}`, color: T.tertiary, background: 'none', border: 'none', cursor: 'pointer' }}>Change</button>
            </div>
          ) : (
            <React.Fragment>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <button onClick={() => setPickOpen((v) => !v)} disabled={!secrets.length} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, font: `500 11.5px/1 ${T.sans}`, color: secrets.length ? T.brandDeep : T.tertiary, background: T.brandSoft, border: `1px solid ${T.brand}44`, borderRadius: T.rMd, padding: '6px 10px', cursor: secrets.length ? 'pointer' : 'default' }}>
                  <Icon name="lock" size={12} color={secrets.length ? T.brandDeep : T.tertiary} /> Import from org secrets <Icon name={pickOpen ? 'chevronDown' : 'chevronRight'} size={12} color={secrets.length ? T.brandDeep : T.tertiary} />
                </button>
                <span style={{ font: `400 11px/1 ${T.sans}`, color: T.tertiary }}>or paste one</span>
              </div>
              {pickOpen && (
                <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rMd, overflow: 'hidden', background: T.raised, boxShadow: T.shadowSm }}>
                  {ordered.map((s, i) => (
                    <button key={s.id} onClick={() => { onKey('org:' + s.name); setPickOpen(false); }} style={{ display: 'flex', alignItems: 'center', gap: 9, width: '100%', textAlign: 'left', cursor: 'pointer', padding: '9px 11px', border: 'none', borderTop: i ? `1px solid ${T.borderSubtle}` : 'none', background: 'transparent' }}>
                      <Icon name="lock" size={12} color={T.tertiary} />
                      <span style={{ flex: 1, minWidth: 0 }}>
                        <span style={{ display: 'block', font: `600 11.5px/1.3 ${T.mono}`, color: T.fg }}>{s.name}</span>
                        <span style={{ display: 'block', font: `400 10.5px/1.3 ${T.sans}`, color: T.tertiary }}>{s.label} · ••••{s.last4}</span>
                      </span>
                      {suggested(s) && <span style={{ font: `600 9px/1 ${T.mono}`, letterSpacing: '0.05em', color: T.success, background: T.successSoft, borderRadius: 4, padding: '3px 5px' }}>MATCH</span>}
                      <span style={{ font: `500 10.5px/1 ${T.sans}`, color: T.brandDeep }}>Import</span>
                    </button>
                  ))}
                </div>
              )}
              <TextInput mono size="sm" value={keyVal} onChange={onKey} placeholder="paste API key" type={keyVal ? 'password' : 'text'} style={keyVal ? { borderColor: T.brand, background: T.brandSoft } : {}} />
            </React.Fragment>
          )}
        </div>
      )}
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

// ---- Design review (stage-triggered) ----------------------------------------
// The pipeline's design node (Kimi K3) generates high-fidelity screens from
// the PRD + the org's brand theme, then WAITS here: the customer approves the
// look or iterates via the Concierge (only affected screens re-generate).
// Surfaces only once the design node has completed — like DepsBar, it is not
// shown for the rest of the run.
function designStage() {
  const d = (typeof PIPELINE !== 'undefined') && PIPELINE.find((n) => n.id === 'design');
  return { reached: !!(d && d.done) };
}
const DESIGN_SCREENS = [
  { name: 'Quote builder', note: 'line items · live Epicor pricing' },
  { name: 'Approval queue', note: '>15% discount gate' },
  { name: 'Manager dashboard', note: 'pipeline · margins' },
  { name: 'Epicor write-back', note: 'won quote → order' },
];
function DesignReviewBar() {
  if (!designStage().reached) return null;
  const [approved, setApproved] = React.useState(false);
  if (approved) {
    return (
      <div style={{ border: `1px solid ${T.success}`, background: T.successSoft + '66', borderRadius: T.rLg, padding: '11px 15px', display: 'flex', alignItems: 'center', gap: 10, animation: 'sfRise .3s var(--ease-out, ease) both' }}>
        <Icon name="check" size={15} color={T.success} />
        <span style={{ flex: 1, font: `500 12.5px/1.4 ${T.sans}`, color: T.fg }}>Design locked — tickets and the build proceed from these {DESIGN_SCREENS.length} screens.</span>
        <button onClick={() => setApproved(false)} style={{ font: `500 11.5px/1 ${T.sans}`, color: T.tertiary, background: 'none', border: 'none', cursor: 'pointer' }}>Re-open review</button>
      </div>
    );
  }
  return (
    <div style={{ border: `1px solid ${T.brand}`, background: T.brandSoft + '55', borderRadius: T.rLg, padding: '13px 15px', animation: 'sfRise .3s var(--ease-out, ease) both' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, marginBottom: 10, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
          <span style={{ width: 12, height: 12, background: T.brand, transform: 'rotate(45deg)', borderRadius: 2, flexShrink: 0 }} />
          <span style={{ font: `600 13px/1.3 ${T.sans}`, color: T.fg }}>Design review — {DESIGN_SCREENS.length} screens generated</span>
          <span style={{ font: `500 9.5px/1 ${T.mono}`, letterSpacing: '0.06em', color: T.brandDeep, background: T.brandSoft, border: `1px solid ${T.brand}44`, padding: '4px 6px', borderRadius: 4 }}>STAGE-TRIGGERED</span>
        </div>
        <span style={{ font: `500 11px/1 ${T.mono}`, color: T.brandDeep }}>design · Kimi K3 · on your brand theme</span>
      </div>
      <p style={{ margin: '0 0 12px', font: `400 11.5px/1.5 ${T.sans}`, color: T.secondary }}>
        Surfaced now because the build reached the <b style={{ color: T.fg }}>design</b> stage. These screens were generated from your PRD and your org’s brand theme. <b style={{ color: T.fg }}>Approve</b> to lock the look — or tell the Concierge what to change and only the affected screens re-generate.
      </p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginBottom: 12 }}>
        {DESIGN_SCREENS.map((s) => (
          <button key={s.name} onClick={() => openArtifact('screens')} title="Open in the artifact viewer" className="sf-artchip" style={{ textAlign: 'left', cursor: 'pointer', border: `1px solid ${T.borderSubtle}`, borderRadius: T.rMd, overflow: 'hidden', background: T.raised, padding: 0 }}>
            <div style={{ height: 74, background: `repeating-linear-gradient(135deg, ${T.sunken}, ${T.sunken} 8px, ${T.bg} 8px, ${T.bg} 16px)`, display: 'grid', placeItems: 'center' }}>
              <span style={{ font: `400 10px/1 ${T.mono}`, color: T.tertiary }}>frame · v1</span>
            </div>
            <div style={{ padding: '8px 10px' }}>
              <div style={{ font: `600 12px/1.2 ${T.sans}`, color: T.fg }}>{s.name}</div>
              <div style={{ font: `400 10.5px/1.3 ${T.sans}`, color: T.tertiary, marginTop: 2 }}>{s.note}</div>
            </div>
          </button>
        ))}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <span style={{ font: `400 11.5px/1.4 ${T.sans}`, color: T.tertiary, display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <Sparkle size={11} color={T.brandDeep} /> Iterate in the Concierge on the right — e.g. “denser quote table” or “approvals first”.
        </span>
        <Btn variant="primary" size="sm" onClick={() => setApproved(true)} style={{ background: T.success }}><Icon name="check" size={13} color="#fff" /> Approve &amp; continue</Btn>
      </div>
    </div>
  );
}

function ConciergeRail({ done, total, allDone, onOpen }) {  const seed = allDone
    ? [{ who: 'agent', text: 'All ' + total + ' tickets are green and the app is deployed. Want me to walk you through the live build?', confidence: 'exact' }]
    : [{ who: 'agent', text: 'Build is underway — ' + done + '/' + total + ' tickets done. The Architect, Research, and Product agents have all filed their work below.' },
       { who: 'agent', text: 'Heads up: Playwright caught a tax-rounding bug on SF-11. Sonnet already pulled it back into Building to fix.' }];

  const [messages, setMessages] = React.useState(seed);
  const [draft, setDraft] = React.useState('');
  const [thinking, setThinking] = React.useState(null); // null | label string
  const scroller = React.useRef(null);
  const timers = React.useRef([]);
  const THINK_LABELS = ['Reading the build state…', 'Checking the ticket board…', 'Pinging the build swarm…', 'Pulling the latest artifacts…'];

  React.useEffect(() => () => timers.current.forEach(clearTimeout), []);
  React.useEffect(() => { const el = scroller.current; if (el) el.scrollTop = el.scrollHeight; }, [messages, thinking]);

  const send = () => {
    const text = draft.trim(); if (!text || thinking) return;
    setMessages((m) => [...m, { who: 'user', text }]); setDraft('');
    let i = 0; setThinking(THINK_LABELS[0]);
    const rot = setInterval(() => { i = (i + 1) % THINK_LABELS.length; setThinking(THINK_LABELS[i]); }, 850);
    timers.current.push(rot);
    const done2 = setTimeout(() => {
      clearInterval(rot);
      setThinking(null);
      setMessages((m) => [...m, { who: 'agent', text: 'On it — I’ve relayed that to the build team and flagged it on the board. I’ll surface any change here as the agents pick it up.' }]);
    }, 2400);
    timers.current.push(done2);
  };

  return (
    <div style={{ width: 326, flexShrink: 0, borderRight: `1px solid ${T.borderSubtle}`, background: T.raised, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '14px 18px', borderBottom: `1px solid ${T.borderSubtle}` }}>
        <span style={{ position: 'relative', width: 30, height: 30, borderRadius: '50%', display: 'grid', placeItems: 'center', background: T.brandSoft, color: T.brand, boxShadow: `inset 0 0 0 1px ${T.brand}33` }}>
          <Sparkle size={14} color={T.brand} />
          {!allDone && <span style={{ position: 'absolute', right: -1, bottom: -1, width: 9, height: 9, borderRadius: '50%', background: T.success, boxShadow: `0 0 0 2px ${T.raised}`, animation: 'sfPulse 1.6s ease-in-out infinite' }} />}
        </span>
        <div style={{ flex: 1 }}><span style={{ display: 'block', font: `600 13px/1.2 ${T.sans}`, color: T.fg }}>Concierge</span><CategoryLabel style={{ fontSize: 10 }}>{thinking ? 'Thinking…' : allDone ? 'Build complete' : 'Relaying the build'}</CategoryLabel></div>
        {thinking || !allDone ? <WorkingPill label={thinking ? 'Thinking' : 'Working'} /> : <StatusPill tone="success">online</StatusPill>}
      </div>
      <div ref={scroller} style={{ flex: 1, overflow: 'auto', padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
        {messages.map((m, i) => <Message key={i} who={m.who} text={m.text} confidence={m.confidence} anim={i >= seed.length} />)}
        <ConciergeArtifacts onOpen={onOpen} />
        {!thinking && (
          <div style={{ padding: 11, borderRadius: T.rLg, border: `1px solid ${T.brand}33`, background: T.brandSoft + '66' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 5 }}><Sparkle size={11} color={T.brandDeep} /><CategoryLabel tone="brand">Steer the build</CategoryLabel></div>
            <p style={{ font: `400 12px/1.5 ${T.sans}`, color: T.secondary, margin: 0 }}>Ask me to reprioritize a ticket, change scope, or pause an agent — I'll pass it straight to the build team.</p>
          </div>
        )}
        {thinking && <TypingIndicator label={thinking} />}
      </div>
      <div style={{ flexShrink: 0, padding: '12px 16px', borderTop: `1px solid ${T.borderSubtle}` }}>
        <Composer placeholder="Ask or steer the build team…" value={draft} onChange={setDraft} onSend={send} />
      </div>
    </div>
  );
}

function BuildProgress({ onBack, backLabel = 'Intake', projectName = 'Acme Industrial · Quote-to-ERP', peerTabs, engine, budget = 30 }) {
  const sim = useBuildSim();
  const [view, setView] = React.useState('kanban');
  const [doc, setDoc] = React.useState(null);
  const engLabel = (typeof engineLabel === 'function') ? engineLabel(engine) : 'Claude Code';
  const engShort = ({ claude: 'Claude Code', codex: 'Codex 5.6', kimi: 'Kimi K3' })[engine && engine.provider] || 'Claude Code';
  const pct = Math.round((sim.done / sim.total) * 100);
  const allDone = sim.done === sim.total;
  const [run, setRun] = React.useState({ status: 'running', haltId: 'build', checkpointId: 'tickets', activeId: null, reason: '' });
  const pauseRun = () => setRun({ status: 'paused', haltId: 'build', checkpointId: 'tickets', activeId: null, reason: 'You paused the run.' });
  const resumeRun = (fromId) => setRun((r) => ({ status: 'running', haltId: r.haltId, checkpointId: r.checkpointId, activeId: fromId || r.haltId, reason: '' }));
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
          <span title={engine && engine.keySource === 'byok' ? 'Running on your own API key' : 'Running on Tenexity’s key'} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '5px 9px', borderRadius: T.rMd, background: T.sunken, border: `1px solid ${T.borderSubtle}` }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: T.brand }} />
            <span style={{ font: `500 11px/1 ${T.mono}`, color: T.secondary }}>engine</span>
            <span style={{ font: `600 11.5px/1 ${T.sans}`, color: T.fg }}>{engLabel}</span>
            <span style={{ font: `600 8.5px/1 ${T.mono}`, letterSpacing: '0.05em', color: T.tertiary, borderLeft: `1px solid ${T.borderDefault}`, paddingLeft: 6 }}>{engine && engine.keySource === 'byok' ? 'BYO KEY' : 'TENEXITY KEY'}</span>
          </span>
          <StatusPill tone={run.status === 'crashed' ? 'danger' : run.status === 'paused' ? 'warning' : 'warning'}>{run.status === 'crashed' ? 'run crashed' : run.status === 'paused' ? 'run paused' : 'phase build · stage 3'}</StatusPill>
          <span style={{ font: `500 12px/1 ${T.mono}`, color: T.secondary }}>spent <b style={{ color: T.fg }}>$4.20</b> / ${budget} cap</span>
          {run.status === 'running'
            ? <button onClick={pauseRun} title="Pause the run" style={{ display: 'inline-flex', alignItems: 'center', gap: 5, height: 28, padding: '0 9px', borderRadius: T.rMd, border: `1px solid ${T.borderDefault}`, background: T.raised, cursor: 'pointer', font: `600 10.5px/1 ${T.mono}`, color: T.secondary }}><Icon name="pause" size={11} color={T.secondary} /> Pause</button>
            : null}
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
        <div style={{ flex: 1, minWidth: 0, padding: '18px 22px', display: 'flex', flexDirection: 'column', gap: 15 }}>
          <StageRail runState={run} onRewind={(id) => resumeRun(id)} />
          <RecoveryBar runState={run} onResume={() => resumeRun()} onRetry={() => resumeRun()} onRewind={(id) => resumeRun(id)} />
          <DesignReviewBar />
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
              ? <GraphView onOpen={(a) => openArtifact(a)} sim={sim} onViewTickets={() => setView('kanban')} engineLabel={engShort} />
              : <NodeMap onOpen={(a) => openArtifact(a)} />}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '11px 15px', borderRadius: T.rLg,
            background: allDone ? T.successSoft : T.raised, border: `1px solid ${allDone ? T.success : T.borderSubtle}` }}>
            {allDone ? (
              <React.Fragment>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, font: `600 13px/1.3 ${T.sans}`, color: T.success }}>
                  <Icon name="check" size={15} color={T.success} /> Deployed · green across the Playwright suite
                </span>
                <div style={{ display: 'flex', gap: 9 }}>
                  <Btn variant="secondary" size="sm" onClick={() => openArtifact('repo')}>Repository</Btn>
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
        <ProjectConcierge context="build" build={{ done: sim.done, total: sim.total, allDone }} onOpen={(a) => openArtifact(a)} />
      </div>
    </div>
  );
}

Object.assign(window, { BuildProgress, DepsBar, DesignReviewBar, ConciergeRail, Segmented });
