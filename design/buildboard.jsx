// buildboard.jsx — process model + views. PIPELINE nodes (incl. the new
// "product" PRD-council node), per-node sub-agents & produced artifacts
// (children of each node), the tickets Kanban, and a GraphView process tree.

const PIPELINE = [
  { id: 'extract', label: 'extract', done: true },
  { id: 'provision', label: 'provision', done: true },
  { id: 'research', label: 'research', done: true },
  { id: 'product', label: 'product', done: true, isNew: true },
  { id: 'g1', label: 'Stage 1 gate', gate: true },
  { id: 'architect', label: 'architect', done: true },
  { id: 'design', label: 'design', done: true, isNew: true },
  { id: 'tickets', label: 'tickets', done: true },
  { id: 'g2', label: 'Stage 2 gate', gate: true },
  { id: 'deps', label: 'wait for deps', deps: true, done: true },
  { id: 'build', label: 'build', active: true },
  { id: 'test', label: 'test' },
  { id: 'deploy', label: 'deploy' },
];

// Per-node spawned sub-agent(s) + the artifacts they produced (node children).
const NODE_DETAIL = {
  provision: { agent: 'Provision agent', artifacts: [{ id: 'repo', kind: 'repo', label: 'acme-quote-to-erp', sub: 'GitHub repository' }] },
  research: { agent: 'Research agent', artifacts: [
    { id: 'r-market', kind: 'md', label: 'market-scan.md' },
    { id: 'r-existing', kind: 'md', label: 'existing-solutions.md' },
    { id: 'r-fit', kind: 'md', label: 'requirements-fit.md' } ] },
  product: { agent: 'Product council', council: 3, artifacts: [{ id: 'prd', kind: 'md', label: 'PRD.md', primary: true }] },
  architect: { agent: 'Architect agent', artifacts: [
    { id: 'arch', kind: 'svg', label: 'architecture.svg' },
    { id: 'datamodel', kind: 'md', label: 'data-model.md' } ] },
  design: { agent: 'Design agent', artifacts: [
    { id: 'screens', kind: 'fig', label: 'screens.fig' },
    { id: 'designspec', kind: 'md', label: 'design-spec.md' } ] },
  tickets: { agent: 'Planner agent', artifacts: [{ id: 'tickets', kind: 'md', label: 'tickets.md', note: '11 tickets' }] },
  build: { agent: 'Build swarm', council: 3, artifacts: [] },
};

// Flat list of produced artifacts from completed nodes (for the concierge rail).
function producedArtifacts() {
  const out = [];
  PIPELINE.forEach((n) => {
    const det = NODE_DETAIL[n.id];
    if (det && n.done && det.artifacts.length) out.push({ node: n.id, nodeLabel: n.label, agent: det.agent, items: det.artifacts });
  });
  return out;
}

const AGENTS = {
  opus: { name: 'Opus', tone: 'brand' },
  sonnet: { name: 'Sonnet', tone: 'warning' },
  qa: { name: 'Playwright', tone: 'success' },
};

const COLS = [
  { id: 'backlog', label: 'Backlog', tone: 'neutral' },
  { id: 'claimed', label: 'Claimed', tone: 'info' },
  { id: 'building', label: 'Building', tone: 'warning', wipMax: 4 },
  { id: 'testing', label: 'Testing', tone: 'brand' },
  { id: 'done', label: 'Done', tone: 'success' },
];

const SEED_TICKETS = [
  { id: 'SF-01', title: 'Auth & org workspace setup', col: 'done', agent: 'opus' },
  { id: 'SF-02', title: 'Epicor connector — read orders & SKUs', col: 'done', agent: 'sonnet' },
  { id: 'SF-03', title: 'Quote data model + schema', col: 'done', agent: 'opus' },
  { id: 'SF-10', title: 'Quote builder — line items & SKU search', col: 'testing', agent: 'sonnet', tag: 'e2e' },
  { id: 'SF-04', title: 'Pricing rules engine', col: 'building', agent: 'sonnet', conf: 'high' },
  { id: 'SF-11', title: 'Fix: tax rounding on multi-line quotes', col: 'building', agent: 'sonnet', tag: 'bug' },
  { id: 'SF-05', title: 'Discount approval workflow (>15%)', col: 'claimed', agent: 'opus' },
  { id: 'SF-07', title: 'Epicor write-back of approved quote', col: 'claimed', agent: 'opus', tag: 'deps' },
  { id: 'SF-06', title: 'Manager visibility dashboard', col: 'backlog', agentTagged: true },
  { id: 'SF-08', title: 'Quote PDF export & email', col: 'backlog' },
  { id: 'SF-09', title: 'Re-key elimination QA pass', col: 'backlog' },
];

const TONE_DOT = { neutral: T.tertiary, info: T.brand, warning: T.warning, brand: T.brand, success: T.success, danger: T.danger };
const KIND_BADGE = {
  md: ['MD', T.brandSoft, T.brandDeep], repo: ['REPO', '#eceef1', '#30363d'],
  svg: ['SVG', T.cHighSoft, T.cHigh], fig: ['FIG', '#f3e9fb', '#7a3ea8'],
};

function StageRail({ runState, onRewind }) {
  const status = runState ? runState.status : 'running';
  const halted = status === 'crashed' || status === 'paused';
  const haltIdx = runState && runState.haltId ? PIPELINE.findIndex((s) => s.id === runState.haltId) : -1;
  const activeIdx = runState && runState.activeId ? PIPELINE.findIndex((s) => s.id === runState.activeId) : PIPELINE.findIndex((s) => s.active);
  const cut = halted ? haltIdx : activeIdx;
  return (
    <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', rowGap: 9 }}>
      {PIPELINE.map((s, i) => {
        const conn = i > 0 ? <span key={s.id + 'c'} style={{ width: 13, height: 1.5, background: T.borderDefault, flexShrink: 0 }} /> : null;
        const past = cut >= 0 && i < cut;
        const atCut = i === cut;
        const future = cut >= 0 && i > cut;
        if (s.gate) return (
          <React.Fragment key={s.id}>{conn}
            <span title={s.label} style={{ width: 12, height: 12, background: future ? T.borderDefault : T.brand, transform: 'rotate(45deg)', borderRadius: 2, flexShrink: 0, opacity: future ? 0.6 : 1 }} />
          </React.Fragment>
        );
        // resolve visual state
        let state = 'idle';
        if (atCut && halted) state = status; // crashed | paused
        else if (atCut && !halted) state = 'active';
        else if (past) state = 'done';
        else if (future) state = 'queued';
        else if (s.done) state = 'done';
        else if (s.active) state = 'active';
        else if (s.deps) state = 'deps';

        const STYLES = {
          done: { bg: T.brandSoft, bd: 'transparent', col: T.brandDeep },
          active: { bg: T.raised, bd: T.brand, col: T.brandDeep },
          crashed: { bg: T.dangerSoft, bd: T.danger, col: T.danger },
          paused: { bg: T.warningSoft, bd: T.warning, col: T.warning },
          deps: { bg: T.warningSoft, bd: T.warning, col: T.warning },
          queued: { bg: T.sunken, bd: T.borderSubtle, col: T.tertiary },
          idle: { bg: T.sunken, bd: T.borderSubtle, col: T.tertiary },
        };
        const st = STYLES[state];
        const rewindable = state === 'done' && halted && onRewind;
        return (
          <React.Fragment key={s.id}>{conn}
            <span onClick={rewindable ? () => onRewind(s.id) : undefined}
              title={rewindable ? 'Rewind the run to here (re-run from this node)' : s.label}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 11px', borderRadius: T.rMd, background: st.bg, border: `1px solid ${st.bd}`, flexShrink: 0,
                opacity: state === 'queued' ? 0.65 : 1, cursor: rewindable ? 'pointer' : 'default',
                boxShadow: state === 'active' ? `0 0 0 3px ${T.brand}1f` : state === 'crashed' ? `0 0 0 3px ${T.danger}1f` : 'none' }}>
              {state === 'active' && <span style={{ width: 6, height: 6, borderRadius: '50%', background: T.brand, animation: 'sfPulse 1.4s ease-in-out infinite' }} />}
              {state === 'crashed' && <Icon name="alert" size={12} color={T.danger} />}
              {state === 'paused' && <Icon name="pause" size={11} color={T.warning} />}
              {state === 'done' && <Icon name="check" size={12} color={T.success} />}
              <span style={{ font: `500 12px/1 ${T.mono}`, color: st.col }}>{s.label}</span>
              {rewindable && <Icon name="rewind" size={10} color={T.tertiary} />}
              {s.isNew && state !== 'queued' && <span style={{ font: `600 9px/1 ${T.sans}`, letterSpacing: '0.06em', color: '#fff', background: T.brand, padding: '2px 5px', borderRadius: 3 }}>NEW</span>}
            </span>
          </React.Fragment>
        );
      })}
    </div>
  );
}

// Recovery affordance: shown when a run is paused or crashed. Resume from the
// halt node (reusing upstream checkpoints), retry just that node, or rewind to
// an earlier checkpoint. Nothing upstream is recomputed.
function RecoveryBar({ runState, onResume, onRetry, onRewind }) {
  if (!runState || (runState.status !== 'crashed' && runState.status !== 'paused')) return null;
  const crashed = runState.status === 'crashed';
  const tone = crashed ? T.danger : T.warning;
  const toneSoft = crashed ? T.dangerSoft : T.warningSoft;
  const lbl = (id) => { const n = PIPELINE.find((s) => s.id === id); return n ? n.label : id; };
  const haltIdx = PIPELINE.findIndex((s) => s.id === runState.haltId);
  const checkpoints = PIPELINE.filter((s, i) => !s.gate && i < haltIdx);
  return (
    <div style={{ border: `1px solid ${tone}66`, background: toneSoft + '66', borderRadius: T.rLg, padding: '12px 14px', display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
      <span style={{ width: 30, height: 30, flexShrink: 0, borderRadius: '50%', display: 'grid', placeItems: 'center', background: toneSoft, border: `1px solid ${tone}44` }}>
        <Icon name={crashed ? 'alert' : 'pause'} size={15} color={tone} />
      </span>
      <div style={{ flex: 1, minWidth: 200 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ font: `700 13px/1.2 ${T.display}`, letterSpacing: '-0.01em', color: T.fg }}>Run {crashed ? 'crashed' : 'paused'} at</span>
          <span style={{ font: `600 11px/1 ${T.mono}`, color: tone, background: toneSoft, border: `1px solid ${tone}33`, padding: '3px 6px', borderRadius: 4 }}>{lbl(runState.haltId)}</span>
        </div>
        <p style={{ margin: '4px 0 0', font: `400 11.5px/1.5 ${T.sans}`, color: T.secondary }}>
          {runState.reason || (crashed ? 'A node failed mid-run.' : 'Run held for input.')} Last good checkpoint: <b style={{ color: T.fg }}>{lbl(runState.checkpointId)}</b>. Upstream artifacts are preserved — resuming re-runs <b style={{ color: T.fg }}>{lbl(runState.haltId)}</b> onward only.
        </p>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 9, flexShrink: 0 }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, height: 32, padding: '0 4px 0 10px', borderRadius: T.rMd, border: `1px solid ${T.borderDefault}`, background: T.raised }}>
          <Icon name="rewind" size={12} color={T.tertiary} />
          <select onChange={(e) => e.target.value && onRewind && onRewind(e.target.value)} defaultValue=""
            style={{ border: 'none', outline: 'none', background: 'transparent', font: `500 11.5px/1 ${T.mono}`, color: T.secondary, cursor: 'pointer', height: 30 }}>
            <option value="" disabled>Rewind to…</option>
            {checkpoints.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select>
        </span>
        <Btn variant="secondary" size="sm" onClick={() => onRetry && onRetry()}><Icon name="refresh" size={13} /> Retry {lbl(runState.haltId)}</Btn>
        <Btn variant="primary" size="sm" onClick={() => onResume && onResume()}><Icon name="play" size={12} color="#fff" /> Resume from {lbl(runState.haltId)}</Btn>
      </div>
    </div>
  );
}

function StageRailLegacy() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', rowGap: 9 }}>
      {PIPELINE.map((s, i) => {
        const conn = i > 0 ? <span key={s.id + 'c'} style={{ width: 13, height: 1.5, background: T.borderDefault, flexShrink: 0 }} /> : null;
        if (s.gate) return (
          <React.Fragment key={s.id}>{conn}
            <span title={s.label} style={{ width: 12, height: 12, background: T.brand, transform: 'rotate(45deg)', borderRadius: 2, flexShrink: 0 }} />
          </React.Fragment>
        );
        const bg = s.active ? T.raised : s.deps ? T.warningSoft : s.done ? T.brandSoft : T.sunken;
        const bd = s.active ? T.brand : s.deps ? T.warning : s.done ? 'transparent' : T.borderSubtle;
        const col = s.active ? T.brandDeep : s.deps ? T.warning : s.done ? T.brandDeep : T.tertiary;
        return (
          <React.Fragment key={s.id}>{conn}
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 11px', borderRadius: T.rMd,
              background: bg, border: `1px solid ${bd}`, flexShrink: 0, boxShadow: s.active ? `0 0 0 3px ${T.brand}1f` : 'none' }}>
              {s.active && <span style={{ width: 6, height: 6, borderRadius: '50%', background: T.brand, animation: 'sfPulse 1.4s ease-in-out infinite' }} />}
              {s.done && <Icon name="check" size={12} color={T.success} />}
              <span style={{ font: `500 12px/1 ${T.mono}`, color: col }}>{s.label}</span>
              {s.isNew && <span style={{ font: `600 9px/1 ${T.sans}`, letterSpacing: '0.06em', color: '#fff', background: T.brand, padding: '2px 5px', borderRadius: 3 }}>NEW</span>}
            </span>
          </React.Fragment>
        );
      })}
    </div>
  );
}

/* ---------- Graph view: process tree (node → sub-agent → artifacts) ---------- */
function ArtifactChip({ a, onOpen, small }) {
  const k = KIND_BADGE[a.kind] || KIND_BADGE.md;
  return (
    <button onClick={() => onOpen && onOpen(a)} className="sf-artchip" title={`Open ${a.label}`} style={{ display: 'inline-flex', alignItems: 'center', gap: 7, cursor: 'pointer',
      padding: small ? '5px 8px' : '6px 9px', borderRadius: T.rMd, border: `1px solid ${a.primary ? T.brand : T.borderSubtle}`,
      background: a.primary ? T.brandSoft : T.raised, transition: 'all .12s', maxWidth: '100%' }}>
      <span style={{ font: `700 8.5px/1 ${T.mono}`, letterSpacing: '0.04em', color: k[2], background: k[1], padding: '3px 4px', borderRadius: 3, flexShrink: 0 }}>{k[0]}</span>
      <span style={{ font: `500 12px/1.1 ${T.sans}`, color: T.fg, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{a.label}</span>
      {a.note && <span style={{ font: `400 10px/1 ${T.mono}`, color: T.tertiary, flexShrink: 0 }}>{a.note}</span>}
      <Icon name="arrowRight" size={12} color={a.primary ? T.brandDeep : T.tertiary} style={{ flexShrink: 0 }} />
    </button>
  );
}

function GraphNode({ node, last, onOpen, sim, onViewTickets }) {
  const det = NODE_DETAIL[node.id];
  const state = node.gate ? 'gate' : node.active ? 'active' : node.deps ? 'deps' : node.done ? 'done' : 'todo';
  const dotColor = state === 'done' ? T.success : state === 'active' ? T.brand : state === 'deps' ? T.warning : state === 'gate' ? T.brand : T.borderDefault;
  return (
    <div style={{ display: 'flex', gap: 14, alignItems: 'stretch' }}>
      {/* spine */}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: 18, flexShrink: 0 }}>
        {node.gate
          ? <span style={{ width: 13, height: 13, background: T.brand, transform: 'rotate(45deg)', borderRadius: 2, marginTop: 4 }} />
          : <span style={{ width: 14, height: 14, borderRadius: '50%', marginTop: 3, background: state === 'todo' ? T.raised : dotColor, border: `2px solid ${dotColor}`,
              boxShadow: state === 'active' ? `0 0 0 4px ${T.brand}22` : 'none', display: 'grid', placeItems: 'center', animation: state === 'active' ? 'sfPulse 1.6s ease-in-out infinite' : 'none' }}>
              {state === 'done' && <Icon name="check" size={9} color="#fff" strokeWidth={3} />}
            </span>}
        {!last && <span style={{ flex: 1, width: 2, background: T.borderSubtle, marginTop: 4, minHeight: 14 }} />}
      </div>
      {/* body */}
      <div style={{ flex: 1, minWidth: 0, paddingBottom: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
          <span style={{ font: `${node.gate ? 500 : 600} 14px/1.2 ${node.gate ? T.mono : T.sans}`, color: node.gate ? T.tertiary : T.fg }}>
            {node.gate ? node.label : node.label}
          </span>
          {node.isNew && <span style={{ font: `600 9px/1 ${T.sans}`, letterSpacing: '0.06em', color: '#fff', background: T.brand, padding: '2px 5px', borderRadius: 3 }}>NEW</span>}
          {state === 'done' && <StatusPill tone="success">done</StatusPill>}
          {state === 'active' && <StatusPill tone="brand">running</StatusPill>}
          {state === 'deps' && <StatusPill tone="warning">waiting</StatusPill>}
          {state === 'todo' && <StatusPill tone="neutral" dot={false}>queued</StatusPill>}
        </div>

        {det && (state === 'done' || state === 'active') && (
          <div style={{ marginTop: 9, paddingLeft: 14, borderLeft: `2px dashed ${T.borderSubtle}`, display: 'flex', flexDirection: 'column', gap: 9 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
              <span style={{ width: 20, height: 20, borderRadius: '50%', display: 'grid', placeItems: 'center', background: T.brandSoft, color: T.brand, boxShadow: `inset 0 0 0 1px ${T.brand}33` }}><Sparkle size={10} color={T.brand} /></span>
              <span style={{ font: `500 12.5px/1.2 ${T.sans}`, color: T.secondary }}>{det.agent}{det.council ? ` · ${det.council} agents` : ''} spawned</span>
            </div>
            {det.artifacts.length > 0 && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7 }}>
                {det.artifacts.map((a) => <ArtifactChip key={a.id} a={a} onOpen={onOpen} />)}
              </div>
            )}
            {node.id === 'build' && sim && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: -2 }}>
                  {['opus', 'sonnet', 'qa'].map((k, i) => <span key={k} style={{ marginLeft: i ? -6 : 0 }}><Avatar name={AGENTS[k].name} size={22} tone={AGENTS[k].tone} /></span>)}
                </div>
                <span style={{ font: `500 12px/1.2 ${T.sans}`, color: T.secondary }}>building {sim.total} tickets · {sim.done} done</span>
                <button onClick={onViewTickets} style={{ font: `500 12px/1 ${T.sans}`, color: T.brandDeep, background: 'none', border: 'none', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 3 }}>View board <Icon name="arrowRight" size={12} color={T.brandDeep} /></button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function GraphView({ onOpen, sim, onViewTickets, engineLabel = 'Claude' }) {
  return (
    <div style={{ height: '100%', overflow: 'auto', padding: '4px 6px 4px 2px' }}>
      <div style={{ maxWidth: 720 }}>
        {/* orchestrator root */}
        <div style={{ display: 'flex', gap: 14, alignItems: 'flex-start' }}>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: 18, flexShrink: 0 }}>
            <span style={{ width: 16, height: 16, borderRadius: '50%', marginTop: 2, background: '#16243f', display: 'grid', placeItems: 'center' }}><span style={{ width: 6, height: 6, borderRadius: '50%', background: '#2f4a78' }} /></span>
            <span style={{ flex: 1, width: 2, background: T.borderSubtle, marginTop: 4, minHeight: 16 }} />
          </div>
          <div style={{ flex: 1, minWidth: 0, paddingBottom: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
              <span style={{ font: `600 14px/1.2 ${T.sans}`, color: T.fg }}>{engineLabel} · software-factory</span>
              <StatusPill tone="neutral" dot={false}>orchestrator</StatusPill>
            </div>
            <p style={{ font: `400 12px/1.4 ${T.sans}`, color: T.tertiary, margin: '4px 0 0' }}>Spawns and supervises every node below; each node spins up its own sub-agents.</p>
          </div>
        </div>
        {PIPELINE.map((n, i) => <GraphNode key={n.id} node={n} last={i === PIPELINE.length - 1} onOpen={onOpen} sim={sim} onViewTickets={onViewTickets} />)}
      </div>
    </div>
  );
}

/* ---------- Kanban view ---------- */
function TagBadge({ tag }) {
  const map = { bug: ['bug', T.dangerSoft, T.danger], deps: ['needs key', T.warningSoft, T.warning], e2e: ['e2e', T.brandSoft, T.brandDeep] };
  const m = map[tag]; if (!m) return null;
  return <span style={{ font: `600 9.5px/1 ${T.mono}`, letterSpacing: '0.04em', textTransform: 'uppercase', color: m[2], background: m[1], padding: '3px 6px', borderRadius: 4 }}>{m[0]}</span>;
}

function TicketCard({ t, moving }) {
  const a = AGENTS[t.agent];
  return (
    <article style={{ background: T.bg, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rMd, padding: 9, boxShadow: T.shadowXs,
      display: 'flex', flexDirection: 'column', gap: 7, animation: moving ? 'sfRise .4s var(--ease-out, ease) both' : 'none' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 6 }}>
        <span style={{ font: `500 12.5px/1.35 ${T.sans}`, color: T.fg }}>{t.title}</span>
        {(t.tag || t.agentTagged) && (t.tag ? <TagBadge tag={t.tag} /> : <Sparkle size={11} color={T.brand} />)}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderTop: `1px solid ${T.borderSubtle}`, paddingTop: 7 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ font: `500 10px/1 ${T.mono}`, color: T.tertiary }}>{t.id}</span>
          {a && <Avatar name={a.name} size={18} tone={a.tone} />}
        </div>
        {t.col === 'building' && (t.conf ? <ConfidencePill band={t.conf} /> : <span style={{ font: `500 10px/1 ${T.mono}`, color: T.warning }}>● working</span>)}
        {t.col === 'testing' && <span style={{ font: `500 10px/1 ${T.mono}`, color: T.brandDeep }}>● testing</span>}
        {t.col === 'done' && <Icon name="check" size={14} color={T.success} />}
      </div>
    </article>
  );
}

function Kanban({ tickets, justMoved }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: `repeat(${COLS.length}, 1fr)`, gap: 12, alignItems: 'start' }}>
      {COLS.map((c) => {
        const list = tickets.filter((t) => t.col === c.id);
        const over = c.wipMax && list.length > c.wipMax;
        return (
          <div key={c.id} style={{ display: 'flex', flexDirection: 'column', border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, background: T.raised, minHeight: 180 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '9px 11px', borderBottom: `1px solid ${T.borderSubtle}` }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: TONE_DOT[c.tone] }} />
                <span style={{ font: `600 13px/1 ${T.display}`, letterSpacing: '-0.01em', color: T.fg }}>{c.label}</span>
                <span style={{ font: `500 10px/1 ${T.mono}`, color: T.tertiary }}>{list.length}</span>
              </div>
              {c.wipMax && (
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                  <span style={{ width: 34, height: 4, borderRadius: 2, background: T.sunken, overflow: 'hidden', display: 'inline-block' }}>
                    <span style={{ display: 'block', height: '100%', width: Math.min(100, (list.length / c.wipMax) * 100) + '%', background: over ? T.danger : T.brand }} />
                  </span>
                  <span style={{ font: `500 9.5px/1 ${T.mono}`, color: over ? T.danger : T.tertiary }}>{list.length}/{c.wipMax}</span>
                </span>
              )}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: 9, flex: 1 }}>
              {list.map((t) => <TicketCard key={t.id} t={t} moving={t.id === justMoved} />)}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function useBuildSim() {
  const order = ['backlog', 'claimed', 'building', 'testing', 'done'];
  const [tickets, setTickets] = React.useState(SEED_TICKETS);
  const [justMoved, setJustMoved] = React.useState(null);
  const [playing, setPlaying] = React.useState(false);
  React.useEffect(() => {
    if (!playing) return;
    const iv = setInterval(() => {
      setTickets((prev) => {
        for (let ci = order.length - 2; ci >= 0; ci--) {
          const cand = prev.find((t) => t.col === order[ci]);
          if (cand) {
            setJustMoved(cand.id);
            return prev.map((t) => t.id === cand.id ? { ...t, col: order[ci + 1],
              agent: t.agent || (order[ci + 1] === 'testing' ? 'qa' : 'sonnet'),
              tag: order[ci + 1] === 'done' ? undefined : t.tag } : t);
          }
        }
        setPlaying(false); return prev;
      });
    }, 1000);
    return () => clearInterval(iv);
  }, [playing]);
  const done = tickets.filter((t) => t.col === 'done').length;
  return { tickets, justMoved, playing, setPlaying, done, total: tickets.length };
}

Object.assign(window, { PIPELINE, NODE_DETAIL, producedArtifacts, AGENTS, COLS, SEED_TICKETS, KIND_BADGE,
  StageRail, RecoveryBar, ArtifactChip, GraphNode, GraphView, TagBadge, TicketCard, Kanban, useBuildSim });
