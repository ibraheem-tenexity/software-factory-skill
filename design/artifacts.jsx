// artifacts.jsx — DocViewer modal that opens an artifact produced by a node,
// plus the ArtifactList the Concierge surfaces with open-links. Mock but real-
// feeling content (PRD.md, research md, architecture.svg, the repo).

function Md({ children }) { return <div style={{ display: 'flex', flexDirection: 'column', gap: 13 }}>{children}</div>; }
function MdH({ children }) { return <h3 style={{ font: `700 16px/1.3 ${T.display}`, letterSpacing: '-0.01em', color: T.fg, margin: '6px 0 0' }}>{children}</h3>; }
function MdP({ children }) { return <p style={{ font: `400 13.5px/1.65 ${T.sans}`, color: T.secondary, margin: 0 }}>{children}</p>; }
function MdLi({ children }) {
  return <li style={{ font: `400 13.5px/1.6 ${T.sans}`, color: T.secondary, marginBottom: 5 }}>{children}</li>;
}
function MdUl({ children }) { return <ul style={{ margin: 0, paddingLeft: 20 }}>{children}</ul>; }

const DOC_CONTENT = {
  repo: () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: 'hidden' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '13px 16px', borderBottom: `1px solid ${T.borderSubtle}`, background: T.sunken }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
            <Icon name="link" size={16} color={T.secondary} />
            <span style={{ font: `600 14px/1 ${T.sans}`, color: T.fg }}>tenexity-factory / acme-quote-to-erp</span>
            <StatusPill tone="neutral" dot={false}>private</StatusPill>
          </div>
          <Btn variant="secondary" size="sm">Open on GitHub <Icon name="arrowRight" size={13} /></Btn>
        </div>
        <div style={{ padding: '12px 16px' }}>
          <MdP>Provisioned by the Provision agent · main branch · 3 agents pushing.</MdP>
          <div style={{ marginTop: 12, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rMd, overflow: 'hidden' }}>
            {[['📁', 'src/', 'app, components, lib'], ['📁', 'supabase/', 'schema + migrations'], ['📁', 'docs/', 'PRD.md, architecture.svg'], ['📄', 'README.md', 'setup & env'], ['📄', '.env.example', 'EPICOR / OPENAI / SUPABASE']].map((r, i, arr) => (
              <div key={r[1]} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 13px', borderBottom: i < arr.length - 1 ? `1px solid ${T.borderSubtle}` : 'none' }}>
                <span style={{ font: `400 13px/1 ${T.sans}` }}>{r[0]}</span>
                <span style={{ font: `500 13px/1 ${T.mono}`, color: T.fg, width: 150 }}>{r[1]}</span>
                <span style={{ font: `400 12px/1 ${T.sans}`, color: T.tertiary }}>{r[2]}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  ),
  prd: () => (
    <Md>
      <MdP><b style={{ color: T.fg }}>Product council</b> (3 agents) reconciled research, the company profile, and the process notes into this PRD. Confidence: <ConfidencePill band="high" score={84} />.</MdP>
      <MdH>1 · Problem</MdH>
      <MdP>Acme builds ~120 quotes/week by hand in spreadsheets, then re-keys them into Epicor. Re-keying is error-prone and the &gt;15% discount approval is an email scramble, slowing turnaround and risking margin.</MdP>
      <MdH>2 · Goals (v1)</MdH>
      <MdUl>
        <MdLi>Build quotes against live Epicor SKUs &amp; the standard price book — no re-keying.</MdLi>
        <MdLi>Route any line over a 15% discount to a sales manager for one-click approval.</MdLi>
        <MdLi>Write the won quote straight back into Epicor as an order.</MdLi>
      </MdUl>
      <MdH>3 · Primary users</MdH>
      <MdUl><MdLi>Inside-sales reps (quote authors)</MdLi><MdLi>Sales managers (approvers)</MdLi><MdLi>Operations (visibility)</MdLi></MdUl>
      <MdH>4 · In scope</MdH>
      <MdUl><MdLi>Quote builder · pricing rules engine · approval workflow · Epicor read + write-back · manager dashboard · PDF export.</MdLi></MdUl>
      <MdH>5 · Out of scope (v1)</MdH>
      <MdUl><MdLi>Multi-currency, CPQ configurator, customer self-service portal.</MdLi></MdUl>
      <MdH>6 · Success metrics</MdH>
      <MdUl><MdLi>Quote turnaround −60% · re-key errors → 0 · approvals under 1 hour.</MdLi></MdUl>
    </Md>
  ),
  arch: () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <MdP>Architecture diagram produced by the Architect agent.</MdP>
      <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, background: T.sunken, padding: 18 }}>
        <svg viewBox="0 0 640 300" style={{ width: '100%', height: 'auto' }} fontFamily={T.sans}>
          <defs>
            <marker id="ah" markerWidth="9" markerHeight="9" refX="7" refY="3" orient="auto"><path d="M0 0L7 3L0 6" fill="none" stroke={T.tertiary} strokeWidth="1.4" /></marker>
          </defs>
          {[[20, 120, 'Quote Builder', 'React UI', T.brand], [200, 60, 'Pricing Engine', 'rules + price book', T.fg], [200, 180, 'Approval Service', '>15% → manager', T.fg], [400, 120, 'Epicor Connector', 'read SKUs · write order', T.fg], [400, 12, 'Supabase', 'quotes · audit', T.cHigh]].map((b, i) => (
            <g key={i}>
              <rect x={b[0]} y={b[1]} width={150} height={58} rx={10} fill={T.raised} stroke={b[4]} strokeWidth="1.6" />
              <text x={b[0] + 75} y={b[1] + 26} textAnchor="middle" fontSize="14" fontWeight="600" fill={T.fg}>{b[2]}</text>
              <text x={b[0] + 75} y={b[1] + 44} textAnchor="middle" fontSize="11" fill={T.tertiary}>{b[3]}</text>
            </g>
          ))}
          {[[170, 149, 200, 89], [170, 149, 200, 209], [350, 89, 400, 140], [350, 209, 400, 160], [475, 120, 475, 70]].map((l, i) => (
            <line key={i} x1={l[0]} y1={l[1]} x2={l[2]} y2={l[3]} stroke={T.tertiary} strokeWidth="1.4" markerEnd="url(#ah)" />
          ))}
          <line x1="550" y1="149" x2="600" y2="149" stroke={T.tertiary} strokeWidth="1.4" markerEnd="url(#ah)" />
          <text x="612" y="153" fontSize="11" fill={T.tertiary}>ERP</text>
        </svg>
      </div>
    </div>
  ),
  fig: () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <MdP>Screen designs produced by the Design agent — the step that was missing from the pipeline.</MdP>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
        {['Quote builder', 'Approval queue', 'Manager dashboard'].map((s) => (
          <div key={s} style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rMd, overflow: 'hidden' }}>
            <div style={{ height: 130, background: `repeating-linear-gradient(135deg, ${T.sunken}, ${T.sunken} 8px, ${T.bg} 8px, ${T.bg} 16px)`, display: 'grid', placeItems: 'center' }}>
              <span style={{ font: `400 10px/1 ${T.mono}`, color: T.tertiary }}>frame</span>
            </div>
            <div style={{ padding: '8px 10px', font: `500 12px/1 ${T.sans}`, color: T.fg }}>{s}</div>
          </div>
        ))}
      </div>
    </div>
  ),
};
const MD_GENERIC = {
  'r-market': { intro: 'Web research on quoting in industrial & MRO distribution.', bullets: ['Distributors quote 80–150×/week; most still author in Excel.', 'Re-key into ERP (Epicor/SAP/Epicor) is the top cited error source.', 'Margin leakage concentrated in ad-hoc discounting without approval.'] },
  'r-existing': { intro: 'Existing solutions scanned and scored against Acme’s needs.', bullets: ['CPQ suites: powerful but heavy setup, priced for enterprise.', 'ERP-native quoting: clunky UX, reps avoid it.', 'Gap: lightweight quote builder that writes back to Epicor.'] },
  'r-fit': { intro: 'Requirement-to-capability fit derived from the intake.', bullets: ['Must read Epicor SKUs + price book in real time.', '>15% discount → manager approval gate (hard requirement).', 'Write-back of won quote as Epicor order eliminates re-keying.'] },
  datamodel: { intro: 'Core entities for the quote-to-ERP flow.', bullets: ['quote(id, customer, status, total, discount_pct, approver)', 'quote_line(quote_id, sku, qty, unit_price, list_price)', 'approval(quote_id, manager, decision, ts)', 'epicor_sync(quote_id, order_no, synced_at)'] },
  designspec: { intro: 'Design decisions handed to the build agents.', bullets: ['Tenexity system: brand #1A7BFF, Hanken Grotesk, confidence cascade.', 'Quote builder uses Catalog + Processing-Queue archetypes.', 'Approval uses the Approval-Stack archetype with keyboard Y/E/N.'] },
  tickets: { intro: '11 tickets generated by the Planner agent and grouped for the build swarm.', bullets: ['SF-01…03 foundation (auth, Epicor read, data model)', 'SF-04…07 core (pricing, approval, write-back)', 'SF-08…11 polish & QA (dashboard, PDF, Playwright)'] },
};

// Flattened, in-order list of produced artifacts (with agent + node label).
function artifactFeed() {
  const out = [];
  producedArtifacts().forEach((g) => g.items.forEach((a) => out.push({ ...a, agent: g.agent, nodeLabel: g.nodeLabel })));
  return out;
}

// "Concierge is working" — animated typing bubble with a rotating status label.
function TypingIndicator({ label }) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 9 }}>
      <span style={{ width: 26, height: 26, flexShrink: 0, borderRadius: '50%', display: 'grid', placeItems: 'center', background: T.brandSoft, color: T.brand, boxShadow: `inset 0 0 0 1px ${T.brand}33` }}><Sparkle size={12} color={T.brand} /></span>
      <div style={{ display: 'inline-flex', alignItems: 'center', gap: 9, padding: '9px 12px', borderRadius: '4px 12px 12px 12px', background: T.sunken, border: `1px solid ${T.borderSubtle}` }}>
        <span style={{ display: 'inline-flex', gap: 4 }}>
          {[0, 1, 2].map((i) => <span key={i} style={{ width: 6, height: 6, borderRadius: '50%', background: T.brand, animation: 'sfDot 1.2s ease-in-out infinite', animationDelay: i * 0.16 + 's' }} />)}
        </span>
        {label && <span style={{ font: `400 12px/1.3 ${T.sans}`, color: T.tertiary }}>{label}</span>}
      </div>
    </div>
  );
}

// Live "working" header chip (used while the build is in progress).
function WorkingPill({ label }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, padding: '4px 9px 4px 8px', borderRadius: 9999, background: T.brandSoft, border: `1px solid ${T.brand}33` }}>
      <span style={{ position: 'relative', width: 7, height: 7 }}>
        <span style={{ position: 'absolute', inset: 0, borderRadius: '50%', background: T.brand, animation: 'sfPulse 1.5s ease-in-out infinite' }} />
      </span>
      <span style={{ font: `600 10px/1 ${T.mono}`, letterSpacing: '0.06em', textTransform: 'uppercase', color: T.brandDeep }}>{label || 'Working'}</span>
    </span>
  );
}

// Three ways to surface produced artifacts in the concierge panel.
//  feed     — inline timeline of produced-file events (recommended)
//  tray     — collapsible "N files" tray, grouped on expand
//  spotlight— latest artifact as a rich card + "view all"
function ConciergeArtifacts({ onOpen, defaultMode = 'feed' }) {
  const [mode, setMode] = React.useState(defaultMode);
  const feed = artifactFeed();
  const groups = producedArtifacts();
  const [open, setOpen] = React.useState(false);
  const latest = feed[feed.length - 1];

  const Switch = (
    <div style={{ display: 'inline-flex', padding: 2, borderRadius: 7, background: T.sunken, border: `1px solid ${T.borderSubtle}` }}>
      {[['feed', 'Feed'], ['tray', 'Tray'], ['spotlight', 'Latest']].map(([id, label]) => (
        <button key={id} onClick={() => setMode(id)} style={{ font: `600 9.5px/1 ${T.mono}`, letterSpacing: '0.04em', padding: '5px 8px', borderRadius: 5, cursor: 'pointer', border: 'none', background: mode === id ? T.raised : 'transparent', color: mode === id ? T.brandDeep : T.tertiary, boxShadow: mode === id ? T.shadowXs : 'none' }}>{label}</button>
      ))}
    </div>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <CategoryLabel>Artifacts · {feed.length}</CategoryLabel>
        {Switch}
      </div>

      {mode === 'feed' && (
        <div style={{ position: 'relative', paddingLeft: 16 }}>
          <span style={{ position: 'absolute', left: 4, top: 6, bottom: 6, width: 1.5, background: T.borderSubtle }} />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
            {feed.map((a) => {
              const k = (typeof KIND_BADGE !== 'undefined' && (KIND_BADGE[a.kind] || KIND_BADGE.md)) || ['MD', T.brandSoft, T.brandDeep];
              return (
                <button key={a.id} onClick={() => onOpen && onOpen(a)} className="sf-artchip" title={`Open ${a.label}`} style={{ position: 'relative', textAlign: 'left', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 9, padding: '8px 10px', borderRadius: T.rMd, border: `1px solid ${T.borderSubtle}`, background: T.raised }}>
                  <span style={{ position: 'absolute', left: -15, top: '50%', marginTop: -3.5, width: 7, height: 7, borderRadius: '50%', background: T.brand, boxShadow: `0 0 0 3px ${T.raised}` }} />
                  <span style={{ font: `700 8px/1 ${T.mono}`, letterSpacing: '0.04em', color: k[2], background: k[1], padding: '3px 4px', borderRadius: 3, flexShrink: 0 }}>{k[0]}</span>
                  <span style={{ flex: 1, minWidth: 0 }}>
                    <span style={{ display: 'block', font: `600 12px/1.3 ${T.mono}`, color: T.fg, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{a.label}</span>
                    <span style={{ display: 'block', font: `400 10.5px/1.3 ${T.sans}`, color: T.tertiary, marginTop: 2 }}>{a.agent}</span>
                  </span>
                  <Icon name="arrowRight" size={13} color={T.tertiary} />
                </button>
              );
            })}
          </div>
        </div>
      )}

      {mode === 'tray' && (
        <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: 'hidden', background: T.raised }}>
          <button onClick={() => setOpen((o) => !o)} style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 9, padding: '10px 12px', border: 'none', background: T.sunken, cursor: 'pointer', textAlign: 'left' }}>
            <Icon name="layers" size={14} color={T.secondary} />
            <span style={{ flex: 1, font: `600 12px/1 ${T.sans}`, color: T.fg }}>{feed.length} files produced</span>
            {latest && <span style={{ font: `400 10.5px/1 ${T.mono}`, color: T.tertiary }}>latest · {latest.label}</span>}
            <Icon name={open ? 'chevronDown' : 'chevronRight'} size={14} color={T.tertiary} />
          </button>
          {open && (
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {groups.map((g) => (
                <div key={g.node} style={{ padding: '9px 12px', borderTop: `1px solid ${T.borderSubtle}` }}>
                  <div style={{ font: `500 10px/1 ${T.mono}`, color: T.tertiary, marginBottom: 6 }}>{g.nodeLabel} · {g.agent}</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>{g.items.map((a) => <ArtifactChip key={a.id} a={{ ...a, agent: g.agent }} onOpen={onOpen} small />)}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {mode === 'spotlight' && latest && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <button onClick={() => onOpen && onOpen(latest)} className="sf-artchip" style={{ textAlign: 'left', cursor: 'pointer', border: `1px solid ${T.brand}44`, borderRadius: T.rLg, background: T.brandSoft + '55', padding: '13px 14px', display: 'flex', flexDirection: 'column', gap: 9 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <WorkingPill label="Just produced" />
              <span style={{ flex: 1 }} />
              <span style={{ font: `400 10.5px/1 ${T.sans}`, color: T.tertiary }}>{latest.nodeLabel}</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
              <Icon name="file" size={17} color={T.brandDeep} />
              <span style={{ flex: 1, minWidth: 0 }}>
                <span style={{ display: 'block', font: `600 14px/1.2 ${T.mono}`, color: T.fg }}>{latest.label}</span>
                <span style={{ display: 'block', font: `400 11px/1.3 ${T.sans}`, color: T.secondary, marginTop: 2 }}>{latest.agent}</span>
              </span>
              <Icon name="arrowRight" size={15} color={T.brandDeep} />
            </div>
          </button>
          {feed.length > 1 && <button onClick={() => onOpen && onOpen(feed[0])} style={{ alignSelf: 'flex-start', font: `600 11px/1 ${T.mono}`, color: T.brandDeep, background: 'none', border: 'none', cursor: 'pointer', padding: '2px 0' }}>View all {feed.length} files →</button>}
        </div>
      )}
    </div>
  );
}

function DocViewer({ artifact, onClose }) {
  if (!artifact) return null;
  const k = KIND_BADGE[artifact.kind] || KIND_BADGE.md;
  const custom = DOC_CONTENT[artifact.id];
  const gen = MD_GENERIC[artifact.id];
  return (
    <div onClick={onClose} style={{ position: 'absolute', inset: 0, zIndex: 50, background: 'rgba(9,12,18,0.42)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 28, animation: 'sfRise .18s ease both' }}>
      <div onClick={(e) => e.stopPropagation()} style={{ width: 'min(640px, 100%)', maxHeight: '100%', background: T.raised, borderRadius: T.rXl, boxShadow: T.shadowMd, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 18px', borderBottom: `1px solid ${T.borderSubtle}` }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
            <span style={{ font: `700 9px/1 ${T.mono}`, letterSpacing: '0.04em', color: k[2], background: k[1], padding: '4px 5px', borderRadius: 3 }}>{k[0]}</span>
            <span style={{ font: `600 14px/1 ${T.mono}`, color: T.fg }}>{artifact.label}</span>
            <span style={{ font: `400 12px/1 ${T.sans}`, color: T.tertiary }}>· produced by {artifact.agent || 'agent'}</span>
          </div>
          <button onClick={onClose} title="Close" style={{ width: 28, height: 28, display: 'grid', placeItems: 'center', borderRadius: T.rMd, border: 'none', background: 'transparent', color: T.tertiary, cursor: 'pointer' }}><Icon name="x" size={16} /></button>
        </div>
        <div style={{ padding: '20px 22px', overflow: 'auto' }}>
          {custom ? custom() : gen ? (
            <Md><MdP>{gen.intro}</MdP><MdUl>{gen.bullets.map((b, i) => <MdLi key={i}>{b}</MdLi>)}</MdUl></Md>
          ) : <MdP>Document preview.</MdP>}
        </div>
      </div>
    </div>
  );
}

// Concierge-surfaced list of produced artifacts, grouped by the node that made them.
function ArtifactList({ onOpen }) {
  const groups = producedArtifacts();
  return (
    <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: 'hidden' }}>
      <div style={{ padding: '9px 12px', borderBottom: `1px solid ${T.borderSubtle}`, background: T.sunken, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <CategoryLabel>Artifacts produced</CategoryLabel>
        <span style={{ font: `500 10px/1 ${T.mono}`, color: T.tertiary }}>{groups.reduce((n, g) => n + g.items.length, 0)} files</span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        {groups.map((g) => (
          <div key={g.node} style={{ padding: '10px 12px', borderBottom: `1px solid ${T.borderSubtle}` }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 7 }}>
              <span style={{ font: `500 11px/1 ${T.mono}`, color: T.tertiary }}>{g.nodeLabel}</span>
              <span style={{ font: `400 11px/1 ${T.sans}`, color: T.tertiary }}>· {g.agent}</span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {g.items.map((a) => <ArtifactChip key={a.id} a={{ ...a, agent: g.agent }} onOpen={onOpen} small />)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

Object.assign(window, { DocViewer, ArtifactList, ConciergeArtifacts, TypingIndicator, WorkingPill, artifactFeed });
