// nodemap.jsx — force-graph-style process map (like the reference): an
// orchestrator root, process nodes along a flowing path, sub-agents (green)
// and produced artifacts (purple) as satellite children, gates as teal
// diamonds. Artifact nodes open the DocViewer. Exported to window.

const MAP_W = 1060, MAP_H = 700;
function mapCurve(a, b) {
  const dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy) || 1;
  const k = Math.min(34, len * 0.13);
  const cx = (a.x + b.x) / 2 + (-dy / len) * k, cy = (a.y + b.y) / 2 + (dx / len) * k;
  return `M${a.x} ${a.y} Q${cx.toFixed(1)} ${cy.toFixed(1)} ${b.x} ${b.y}`;
}

// main pipeline nodes laid out on a flowing diagonal path
const MAP_MAIN = [
  { id: 'orch', x: 470, y: 46, kind: 'orch', label: 'software-factory' },
  { id: 'extract', x: 470, y: 124, kind: 'proc', state: 'done', label: 'extract' },
  { id: 'provision', x: 432, y: 198, kind: 'proc', state: 'done', label: 'provision' },
  { id: 'research', x: 478, y: 286, kind: 'proc', state: 'done', label: 'research' },
  { id: 'product', x: 566, y: 338, kind: 'proc', state: 'done', label: 'product', isNew: true },
  { id: 'g1', x: 470, y: 386, kind: 'gate', label: 'Stage 1' },
  { id: 'architect', x: 598, y: 420, kind: 'proc', state: 'done', label: 'architect' },
  { id: 'design', x: 712, y: 386, kind: 'proc', state: 'done', label: 'design', isNew: true },
  { id: 'tickets', x: 470, y: 462, kind: 'proc', state: 'done', label: 'tickets' },
  { id: 'g2', x: 376, y: 500, kind: 'gate', label: 'Stage 2' },
  { id: 'deps', x: 286, y: 538, kind: 'proc', state: 'deps', label: 'wait for deps' },
  { id: 'build', x: 190, y: 582, kind: 'proc', state: 'active', label: 'build' },
  { id: 'test', x: 320, y: 632, kind: 'proc', state: 'todo', label: 'test' },
  { id: 'deploy', x: 172, y: 656, kind: 'proc', state: 'todo', label: 'deploy' },
];
const MAP_PATH = ['orch', 'extract', 'provision', 'research', 'product', 'g1', 'architect', 'design', 'tickets', 'g2', 'deps', 'build', 'test', 'deploy'];

const MAP_SATS = [
  { p: 'provision', kind: 'agent', x: 300, y: 168, label: 'Provision agent' },
  { p: 'provision', kind: 'art', x: 296, y: 220, label: 'acme-quote-to-erp', art: { id: 'repo', kind: 'repo', label: 'acme-quote-to-erp', agent: 'Provision agent' } },
  { p: 'research', kind: 'agent', x: 612, y: 224, label: 'Research agent' },
  { p: 'research', kind: 'art', x: 706, y: 188, label: 'market-scan.md', art: { id: 'r-market', kind: 'md', label: 'market-scan.md', agent: 'Research agent' } },
  { p: 'research', kind: 'art', x: 800, y: 232, label: 'existing-solutions.md', art: { id: 'r-existing', kind: 'md', label: 'existing-solutions.md', agent: 'Research agent' } },
  { p: 'research', kind: 'art', x: 724, y: 272, label: 'requirements-fit.md', art: { id: 'r-fit', kind: 'md', label: 'requirements-fit.md', agent: 'Research agent' } },
  { p: 'product', kind: 'agent', x: 650, y: 308, label: 'Product council · 3' },
  { p: 'product', kind: 'art', primary: true, x: 760, y: 332, label: 'PRD.md', art: { id: 'prd', kind: 'md', label: 'PRD.md', agent: 'Product council' } },
  { p: 'architect', kind: 'agent', x: 700, y: 458, label: 'Architect agent' },
  { p: 'architect', kind: 'art', x: 806, y: 440, label: 'architecture.svg', art: { id: 'arch', kind: 'svg', label: 'architecture.svg', agent: 'Architect agent' } },
  { p: 'architect', kind: 'art', x: 806, y: 486, label: 'data-model.md', art: { id: 'datamodel', kind: 'md', label: 'data-model.md', agent: 'Architect agent' } },
  { p: 'design', kind: 'agent', x: 820, y: 372, label: 'Design agent' },
  { p: 'design', kind: 'art', x: 906, y: 352, label: 'screens.fig', art: { id: 'screens', kind: 'fig', label: 'screens.fig', agent: 'Design agent' } },
  { p: 'design', kind: 'art', x: 906, y: 402, label: 'design-spec.md', art: { id: 'designspec', kind: 'md', label: 'design-spec.md', agent: 'Design agent' } },
  { p: 'build', kind: 'agent', x: 98, y: 552, label: 'Opus' },
  { p: 'build', kind: 'agent', x: 80, y: 592, label: 'Sonnet' },
  { p: 'build', kind: 'agent', x: 100, y: 632, label: 'Playwright' },
  { p: 'deps', kind: 'dep', x: 374, y: 548, label: 'mcp' },
  { p: 'deps', kind: 'dep', x: 396, y: 590, label: 'mock' },
  { p: 'deps', kind: 'dep', x: 372, y: 626, label: 'user' },
];

const PROC_FILL = { done: '#059669', active: '#1A7BFF', deps: '#D97706', todo: '#ECECEE' };
const PROC_TEXT = { done: '#fff', active: '#fff', deps: '#fff', todo: '#6B727D' };
const SAT_FILL = { agent: '#059669', art: '#8B5CF6', dep: '#9AA1AC' };

function nodeById(id) { return MAP_MAIN.find((n) => n.id === id); }

function NodeMap({ onOpen }) {
  const procW = (l) => Math.max(52, l.length * 6.4 + 22);
  return (
    <div style={{ height: '100%', overflow: 'auto', background: T.bg, borderRadius: T.rLg, border: `1px solid ${T.borderSubtle}`, position: 'relative' }}>
      {/* legend */}
      <div style={{ position: 'absolute', top: 12, left: 12, zIndex: 2, display: 'flex', flexWrap: 'wrap', gap: 12, padding: '8px 12px', background: T.raised + 'e6', border: `1px solid ${T.borderSubtle}`, borderRadius: T.rMd, backdropFilter: 'blur(4px)' }}>
        {[['#16243f', 'orchestrator', 'dot'], ['#059669', 'done · agent', 'dot'], ['#1A7BFF', 'active', 'dot'], ['#D97706', 'deps', 'dot'], ['#8B5CF6', 'artifact', 'dot'], ['#11A0B8', 'gate', 'diamond']].map((l) => (
          <span key={l[1]} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: 9, height: 9, background: l[0], borderRadius: l[2] === 'diamond' ? 2 : '50%', transform: l[2] === 'diamond' ? 'rotate(45deg)' : 'none' }} />
            <span style={{ font: `500 10.5px/1 ${T.sans}`, color: T.secondary }}>{l[1]}</span>
          </span>
        ))}
      </div>

      <svg viewBox={`0 0 ${MAP_W} ${MAP_H}`} width={MAP_W} height={MAP_H} fontFamily={T.sans} style={{ display: 'block' }}>
        <defs>
          <pattern id="nmgrid" width="26" height="26" patternUnits="userSpaceOnUse">
            <circle cx="1" cy="1" r="1" fill="#e6e6e2" />
          </pattern>
        </defs>
        <rect x="0" y="0" width={MAP_W} height={MAP_H} fill="url(#nmgrid)" />

        {/* main path edges (curved, active path highlighted) */}
        {MAP_PATH.slice(1).map((id, i) => {
          const a = nodeById(MAP_PATH[i]), b = nodeById(id);
          const hot = a.id === 'build' || b.id === 'build';
          return <path key={'e' + id} d={mapCurve(a, b)} fill="none" stroke={hot ? '#1A7BFF' : '#C7C9CF'} strokeWidth={hot ? 2 : 1.6} opacity={hot ? 0.7 : 1} />;
        })}
        {/* satellite edges */}
        {MAP_SATS.map((s, i) => {
          const p = nodeById(s.p);
          return <path key={'se' + i} d={mapCurve(p, s)} fill="none" stroke="#DCDCD8" strokeWidth="1.2" />;
        })}

        {/* satellites */}
        {MAP_SATS.map((s, i) => {
          const r = s.primary ? 9 : 6;
          const clickable = !!s.art;
          const labelRight = s.kind !== 'dep' && s.x < 520;
          return (
            <g key={'s' + i} className="nm-node" data-art={clickable ? '1' : undefined} style={{ cursor: clickable ? 'pointer' : 'default' }} onClick={clickable ? () => onOpen(s.art) : undefined}>
              {s.primary && <circle cx={s.x} cy={s.y} r={r + 4} fill="none" stroke={SAT_FILL.art} strokeWidth="1.4" opacity="0.5" />}
              <circle cx={s.x} cy={s.y} r={r} fill={SAT_FILL[s.kind]} />
              {s.kind === 'art' && <text x={s.x} y={s.y + 0.5} textAnchor="middle" dominantBaseline="middle" fontSize="8" fill="#fff" fontWeight="700">↗</text>}
              <text x={labelRight ? s.x - r - 6 : s.x + r + 6} y={s.y + 3.5} textAnchor={labelRight ? 'end' : 'start'}
                fontSize={s.primary ? 11.5 : 10.5} fontWeight={s.primary ? 700 : 500} fill={s.kind === 'art' ? '#3f2c63' : '#3f4a44'}>{s.label}</text>
            </g>
          );
        })}

        {/* main nodes */}
        {MAP_MAIN.map((n) => {
          if (n.kind === 'orch') return (
            <g key={n.id}>
              <circle cx={n.x} cy={n.y} r="19" fill="#16243f" />
              <circle cx={n.x} cy={n.y} r="7" fill="#2f4a78" />
              <text x={n.x} y={n.y + 38} textAnchor="middle" fontSize="11" fontWeight="600" fill={T.fg}>Claude · software-factory</text>
            </g>
          );
          if (n.kind === 'gate') return (
            <g key={n.id}>
              <rect x={n.x - 9} y={n.y - 9} width="18" height="18" rx="3" transform={`rotate(45 ${n.x} ${n.y})`} fill="#11A0B8" />
              <text x={n.x} y={n.y + 26} textAnchor="middle" fontSize="10" fontWeight="500" fill={T.tertiary}>{n.label}</text>
            </g>
          );
          const w = procW(n.label), active = n.state === 'active';
          return (
            <g key={n.id}>
              {active && <rect className="nm-pulse" x={n.x - w / 2 - 3} y={n.y - 16} width={w + 6} height="32" rx="9" fill="none" stroke="#1A7BFF" strokeWidth="2" />}
              <rect x={n.x - w / 2} y={n.y - 13} width={w} height="26" rx="7" fill={PROC_FILL[n.state]} stroke={n.state === 'todo' ? '#D4D4D8' : 'none'} strokeWidth="1" style={n.state === 'todo' ? null : { filter: 'drop-shadow(0 1px 1.5px rgba(20,30,50,0.14))' }} />
              <text x={n.x} y={n.y + 4} textAnchor="middle" fontSize="12" fontWeight="600" fill={PROC_TEXT[n.state]} fontFamily={T.mono}>{n.label}</text>
              {n.isNew && <g><rect x={n.x + w / 2 + 4} y={n.y - 11} width="30" height="14" rx="3" fill="#1A7BFF" /><text x={n.x + w / 2 + 19} y={n.y - 0.5} textAnchor="middle" fontSize="8" fontWeight="700" fill="#fff">NEW</text></g>}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

Object.assign(window, { NodeMap, MAP_MAIN, MAP_SATS });
