// skeletons.jsx — Tenexity loading system.
// A single shimmer treatment (`.sf-skel`, defined in the page <style>) under a
// set of typed placeholders. The rule: anything fetched from the database
// renders its skeleton while in flight, then swaps to real content. Skeletons
// mirror the exact shape/size of what they replace so layout never jumps.
//
// Primitives → typed field placeholders → per-surface composites (rows, tiles,
// table rows, KV grids, cards, messages). Loaded after shared.jsx.

/* ----------------------------- primitives ----------------------------- */
// Base shimmer block. Everything else composes this.
function Skel({ w = '100%', h = 12, r = 6, dark, style, inline }) {
  return <span className={'sf-skel' + (dark ? ' on-dark' : '')} style={{ display: inline ? 'inline-block' : 'block', width: w, height: h, borderRadius: r, flexShrink: 0, ...style }} />;
}
const SkelLine   = ({ w = '100%', h = 11, style }) => <Skel w={w} h={h} r={5} style={style} />;
const SkelCircle = ({ size = 30, style }) => <Skel w={size} h={size} r="50%" style={style} />;
const SkelPill   = ({ w = 64 }) => <Skel w={w} h={20} r={9999} />;
const SkelChip   = ({ w = 78 }) => <Skel w={w} h={26} r={9999} />;
const SkelBar    = ({ w = 110, h = 6 }) => <Skel w={w} h={h} r={3} />;
const SkelInput  = ({ style }) => <Skel w="100%" h={38} r={8} style={style} />;
const SkelBtn    = ({ w = 96 }) => <Skel w={w} h={34} r={8} />;
const SkelBadge  = ({ w = 38 }) => <Skel w={w} h={16} r={4} />;

// Inline circular spinner — for buttons / in-place actions, not list loads.
function Spinner({ size = 16, color, stroke = 2 }) {
  const c = color || (window.T ? T.brand : '#1A7BFF');
  return (
    <span className="sf-spin" style={{ display: 'inline-block', width: size, height: size }}>
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="12" r="9" stroke={c} strokeOpacity="0.2" strokeWidth={stroke} />
        <path d="M21 12a9 9 0 0 0-9-9" stroke={c} strokeWidth={stroke} strokeLinecap="round" />
      </svg>
    </span>
  );
}

/* --------------------------- typed fields ----------------------------- */
// Paragraph / multi-line text. Last line short to read as prose.
function SkelText({ lines = 2, style }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 7, ...style }}>
      {Array.from({ length: lines }).map((_, i) => <SkelLine key={i} w={i === lines - 1 ? '55%' : '100%'} />)}
    </div>
  );
}
// One labelled value (mono label + value line) — the atom of a profile grid.
function SkelKV({ valueW = '70%' }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
      <SkelLine w={52} h={8} />
      <SkelLine w={valueW} h={12} />
    </div>
  );
}
// Form field: label above an input-shaped block.
function SkelField({ labelW = 80, style }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, ...style }}>
      <SkelLine w={labelW} h={9} />
      <SkelInput />
    </div>
  );
}

/* ----------------------- per-surface composites ----------------------- */
const skelCard = (extra) => ({ background: (window.T || {}).raised || '#fff', border: `1px solid ${(window.T || {}).borderSubtle || '#ECECEE'}`, borderRadius: (window.T || {}).rLg || 12, boxShadow: (window.T || {}).shadowXs, ...extra });

// Metric card (dashboard pulse / OS metrics).
function MetricCardSkel({ accent }) {
  return (
    <div style={skelCard({ padding: '14px 16px' })}>
      <SkelLine w={70} h={9} />
      <Skel w={64} h={26} r={6} style={{ margin: '12px 0 8px' }} />
      <SkelLine w={96} h={9} />
    </div>
  );
}
// Project list row — matches dashboard ProjectRow grid.
function ProjectRowSkel({ first }) {
  const T = window.T || {};
  return (
    <div style={{ background: T.raised, borderTop: first ? 'none' : `1px solid ${T.borderSubtle}`, padding: '16px 18px', display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 132px 150px 96px 24px', alignItems: 'center', gap: 16 }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}><SkelCircle size={22} /><SkelLine w={180} h={13} /><SkelPill w={64} /></div>
        <SkelLine w="62%" h={11} style={{ marginTop: 9, marginLeft: 31 }} />
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}><SkelLine w={84} h={9} /><SkelBar w={110} /></div>
      <div style={{ display: 'flex' }}>{[0, 1, 2].map((i) => <SkelCircle key={i} size={20} style={{ marginLeft: i ? -6 : 0 }} />)}</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}><SkelLine w={52} h={9} /><SkelLine w={34} h={8} /></div>
      <Skel w={16} h={16} r={4} />
    </div>
  );
}
// File / document tile — matches FileTile.
function FileTileSkel() {
  return (
    <div style={skelCard({ padding: '13px 14px', display: 'flex', flexDirection: 'column', gap: 12 })}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}><SkelBadge w={30} /><SkelLine w={48} h={8} /></div>
      <SkelLine w="80%" h={13} />
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}><SkelLine w={44} h={9} /><SkelLine w={52} h={9} /></div>
    </div>
  );
}
// Generic data-table row. Pass the column template + an array of cell widths.
function TableRowSkel({ grid, cells, first, pad = '13px 18px' }) {
  const T = window.T || {};
  return (
    <div style={{ display: 'grid', gridTemplateColumns: grid, gap: 12, padding: pad, alignItems: 'center', borderTop: first ? 'none' : `1px solid ${T.borderSubtle}` }}>
      {cells.map((c, i) => {
        if (c === 'user') return <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 11 }}><SkelCircle size={30} /><span style={{ display: 'flex', flexDirection: 'column', gap: 6 }}><SkelLine w={120} h={12} /><SkelLine w={150} h={9} /></span></span>;
        if (c === 'pill') return <SkelPill key={i} w={64} />;
        if (c === 'badge') return <SkelBadge key={i} w={56} />;
        if (c === 'menu') return <Skel key={i} w={20} h={20} r={5} style={{ justifySelf: 'end' }} />;
        return <SkelLine key={i} w={typeof c === 'number' ? c : '70%'} h={11} />;
      })}
    </div>
  );
}
// Key/value grid (company profile, inherited context, drawer meta).
function KVGridSkel({ rows = 6, cols = 2 }) {
  const T = window.T || {};
  return (
    <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: 'hidden', background: T.raised }}>
      <div style={{ display: 'grid', gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: 1, background: T.borderSubtle }}>
        {Array.from({ length: rows }).map((_, i) => <div key={i} style={{ background: T.raised, padding: '13px 18px' }}><SkelKV valueW={['62%', '78%', '50%', '70%'][i % 4]} /></div>)}
      </div>
    </div>
  );
}
// Compact list row: leading mark + two lines + trailing dot/meta.
function ListRowSkel({ first, trailing = 'dot' }) {
  const T = window.T || {};
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '12px 14px', borderTop: first ? 'none' : `1px solid ${T.borderSubtle}` }}>
      <Skel w={32} h={32} r={8} />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}><SkelLine w="40%" h={12} /><SkelLine w="68%" h={9} /></div>
      {trailing === 'dot' ? <SkelCircle size={8} /> : <SkelLine w={40} h={9} />}
    </div>
  );
}
// Kanban ticket card.
function KanbanCardSkel() {
  return (
    <div style={skelCard({ padding: '12px 13px', display: 'flex', flexDirection: 'column', gap: 10 })}>
      <div style={{ display: 'flex', justifyContent: 'space-between' }}><SkelLine w={48} h={9} /><SkelBadge w={28} /></div>
      <SkelLine w="85%" h={12} />
      <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}><SkelCircle size={20} /><SkelChip w={52} /></div>
    </div>
  );
}
// Concierge / chat message bubble.
function MessageSkel() {
  const T = window.T || {};
  return (
    <div style={{ display: 'flex', gap: 9 }}>
      <SkelCircle size={26} />
      <div style={{ flex: 1, padding: '11px 13px', borderRadius: T.rLg, border: `1px solid ${T.borderSubtle}`, background: T.raised, display: 'flex', flexDirection: 'column', gap: 7 }}>
        <SkelLine w="90%" /><SkelLine w="70%" />
      </div>
    </div>
  );
}
// Generic panel body — N text lines, for any zone panel.
function PanelBodySkel({ lines = 3 }) { return <SkelText lines={lines} />; }

/* --------------------- fetch-state demo wrapper ----------------------- */
// Render-prop wrapper that simulates a DB fetch: shows skeletons for `ms`, then
// real content; a small Reload chip replays the load. Used only in showcases.
function FetchDemo({ ms = 2100, label = 'Reload', children }) {
  const [loading, setLoading] = React.useState(true);
  const timer = React.useRef(null);
  const run = React.useCallback(() => { setLoading(true); clearTimeout(timer.current); timer.current = setTimeout(() => setLoading(false), ms); }, [ms]);
  React.useEffect(() => { run(); return () => clearTimeout(timer.current); }, [run]);
  const T = window.T || {};
  return (
    <div style={{ position: 'relative', height: '100%' }}>
      <button onClick={run} disabled={loading} title="Replay the fetch"
        style={{ position: 'absolute', top: 12, right: 14, zIndex: 50, display: 'inline-flex', alignItems: 'center', gap: 6, height: 30, padding: '0 11px', borderRadius: 8, cursor: loading ? 'default' : 'pointer', border: `1px solid ${T.borderDefault}`, background: T.raised, font: `600 11px/1 ${T.mono}`, color: loading ? T.tertiary : T.secondary, boxShadow: T.shadowSm }}>
        {loading ? <Spinner size={13} /> : <Icon name="refresh" size={12} color={T.secondary} />}{loading ? 'Loading…' : label}
      </button>
      {children(loading)}
    </div>
  );
}

Object.assign(window, {
  Skel, SkelLine, SkelCircle, SkelPill, SkelChip, SkelBar, SkelInput, SkelBtn, SkelBadge, Spinner,
  SkelText, SkelKV, SkelField, MetricCardSkel, ProjectRowSkel, FileTileSkel, TableRowSkel,
  KVGridSkel, ListRowSkel, KanbanCardSkel, MessageSkel, PanelBodySkel, FetchDemo,
});
