// loadingshowcase.jsx — the loading-system reference: every skeleton / field /
// list / table / card type the factory uses, shown live. Loaded last so it can
// reference both the skeleton kit and the real screen components.

function LoadingShowcase() {
  const Section = ({ title, sub, children, cols = 2 }) => (
    <section style={{ marginBottom: 26 }}>
      <div style={{ marginBottom: 12 }}>
        <CategoryLabel tone="brand">{title}</CategoryLabel>
        {sub && <p style={{ font: `400 12.5px/1.5 ${T.sans}`, color: T.tertiary, margin: '4px 0 0' }}>{sub}</p>}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: 12, alignItems: 'start' }}>{children}</div>
    </section>
  );
  const Demo = ({ label, children, pad = 16 }) => (
    <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: 'hidden', background: T.raised, boxShadow: T.shadowXs }}>
      <div style={{ padding: '7px 12px', borderBottom: `1px solid ${T.borderSubtle}`, background: T.sunken }}><span style={{ font: `500 10px/1 ${T.mono}`, letterSpacing: '0.04em', color: T.tertiary }}>{label}</span></div>
      <div style={{ padding: pad }}>{children}</div>
    </div>
  );

  return (
    <div style={{ height: '100%', overflow: 'auto', background: T.bg, fontFamily: T.sans }}>
      <div style={{ maxWidth: 1080, margin: '0 auto', padding: '30px 32px 48px' }}>
        <div style={{ marginBottom: 24 }}>
          <CategoryLabel style={{ marginBottom: 9 }}>Design system · loading</CategoryLabel>
          <h1 style={{ font: `700 30px/1.12 ${T.display}`, letterSpacing: '-0.02em', color: T.fg, margin: 0 }}>Loading &amp; fetch states</h1>
          <p style={{ font: `400 14px/1.55 ${T.sans}`, color: T.secondary, margin: '8px 0 0', maxWidth: 640 }}>
            Every value read from the database shows a skeleton while it loads, then swaps to real data. Each skeleton mirrors the exact shape and size of what it replaces, so layout never shifts. One shimmer treatment, applied across fields, lists, tables, cards, and messages.
          </p>
        </div>

        <Section title="Primitives" sub="The shimmer block and the atoms built from it. Sizes match the real type ramp." cols={2}>
          <Demo label="text lines"><SkelText lines={3} /></Demo>
          <Demo label="line · heading · value · bar">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <SkelLine w="100%" /><Skel w="50%" h={20} r={6} /><Skel w={64} h={26} r={6} /><SkelBar w={140} />
            </div>
          </Demo>
          <Demo label="avatar · pill · chip · badge">
            <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
              <SkelCircle size={36} /><SkelPill w={64} /><SkelChip w={84} /><SkelBadge w={42} />
            </div>
          </Demo>
          <Demo label="inline spinner · button (action-level)">
            <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
              <Spinner size={20} /><Spinner size={16} color={T.secondary} /><SkelBtn w={110} />
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, height: 36, padding: '0 14px', borderRadius: T.rMd, background: T.brand, color: '#fff', font: `600 12.5px/1 ${T.sans}` }}><Spinner size={14} color="#fff" /> Saving…</span>
            </div>
          </Demo>
        </Section>

        <Section title="Field types" sub="One labelled value, a form field, and a key/value cell — the building blocks of every detail view." cols={3}>
          <Demo label="form field"><SkelField labelW={70} /></Demo>
          <Demo label="key / value"><SkelKV /></Demo>
          <Demo label="profile grid (KV ×6)" pad={0}><KVGridSkel rows={6} cols={2} /></Demo>
        </Section>

        <Section title="Lists & rows" sub="Project list, connected-systems / team rows, and the generic compact list row." cols={1}>
          <Demo label="project list row (dashboard)" pad={0}><ProjectRowSkel first /><ProjectRowSkel /></Demo>
          <Demo label="compact list row (systems · team · agents)" pad={0}><ListRowSkel first /><ListRowSkel trailing="meta" /></Demo>
        </Section>

        <Section title="Cards & tiles" sub="Metric cards, document tiles, and Kanban ticket cards." cols={4}>
          <MetricCardSkel /><FileTileSkel /><FileTileSkel />
          <div style={{ background: T.bg }}><KanbanCardSkel /></div>
        </Section>

        <Section title="Tables" sub="Generic data-table skeleton — pass the column template and per-cell shapes. Shown here as the master users table." cols={1}>
          <Demo label="data table (users)" pad={0}>
            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.5fr) minmax(0,1.1fr) 92px 150px 96px 110px 40px', gap: 12, padding: '11px 18px', borderBottom: `1px solid ${T.borderSubtle}`, background: T.sunken }}>
              {['User', 'Organization', 'Role', 'Sign-in method', 'Status', 'Last active', ''].map((h, i) => <span key={i} style={{ font: `600 10px/1 ${T.mono}`, letterSpacing: '0.08em', textTransform: 'uppercase', color: T.tertiary }}>{h}</span>)}
            </div>
            {Array.from({ length: 5 }).map((_, i) => <TableRowSkel key={i} grid="minmax(0,1.5fr) minmax(0,1.1fr) 92px 150px 96px 110px 40px" cells={['user', '72%', 'badge', 100, 'pill', 64, 'menu']} first={i === 0} />)}
          </Demo>
        </Section>

        <Section title="Messages & panels" sub="Concierge chat bubbles and generic zone-panel bodies." cols={2}>
          <Demo label="concierge message"><div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}><MessageSkel /><MessageSkel /></div></Demo>
          <Demo label="panel body"><PanelBodySkel lines={4} /></Demo>
        </Section>
      </div>
    </div>
  );
}

Object.assign(window, { LoadingShowcase });
