// shared.jsx — Tenexity design system tokens, data, icons, and primitives
// for the Software Factory onboarding. Faithful to tenexity-design-master:
// brand #1A7BFF, Hanken Grotesk / Georgia / JetBrains Mono, confidence
// cascade, ai-tint, single-bubble conversation. Exported to window.

const T = {
  bg: '#FAFAFA', raised: '#FFFFFF', sunken: '#F4F4F5', ink: '#060709',
  fg: '#18181B', secondary: '#52525B', tertiary: '#8A8A92',
  borderSubtle: '#E7E7E9', borderDefault: '#D4D4D8',
  brand: '#1A7BFF', brandSoft: '#E8F1FF', brandDeep: '#0958C9',
  success: '#059669', successSoft: '#E4F8EF',
  warning: '#D97706', warningSoft: '#FBEFDC',
  danger: '#DC2626', dangerSoft: '#FBE3E3',
  // confidence cascade
  cExact: '#059669', cExactSoft: '#E4F8EF',
  cHigh: '#11A0B8', cHighSoft: '#E0F4F7',
  cMed: '#F2A516', cMedSoft: '#FBEFDC',
  cLow: '#DC2626', cLowSoft: '#FBE3E3',
  cNone: '#8A8A92', cNoneSoft: '#EDEDEF',
  sans: "'Hanken Grotesk', ui-sans-serif, system-ui, -apple-system, sans-serif",
  display: "Georgia, 'Times New Roman', serif",
  mono: "'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, monospace",
  rSm: '6px', rMd: '8px', rLg: '12px', rXl: '16px',
  shadowXs: '0 1px 2px 0 hsl(240 6% 10% / 0.04)',
  shadowSm: '0 2px 6px -2px hsl(240 6% 10% / 0.06), 0 1px 2px hsl(240 6% 10% / 0.04)',
  shadowMd: '0 8px 24px -8px hsl(240 6% 10% / 0.10), 0 2px 6px -2px hsl(240 6% 10% / 0.06)',
};

// ---------- icons (lucide-style, 24-grid stroke) ----------
const PATHS = {
  upload: 'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4 M17 8l-5-5-5 5 M12 3v12',
  check: 'M20 6L9 17l-5-5',
  plus: 'M12 5v14 M5 12h14',
  arrowRight: 'M5 12h14 M12 5l7 7-7 7',
  arrowLeft: 'M19 12H5 M12 19l-7-7 7-7',
  x: 'M18 6L6 18 M6 6l12 12',
  mic: 'M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z M19 10v2a7 7 0 0 1-14 0v-2 M12 19v4',
  paperclip: 'M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48',
  chevronRight: 'M9 18l6-6-6-6',
  chevronDown: 'M6 9l6 6 6-6',
  dots: 'M12 13a1 1 0 1 0 0-2 1 1 0 0 0 0 2z M19 13a1 1 0 1 0 0-2 1 1 0 0 0 0 2z M5 13a1 1 0 1 0 0-2 1 1 0 0 0 0 2z',
  play: 'M5 3l14 9-14 9V3z',
  pause: 'M6 4h4v16H6z M14 4h4v16h-4z',
  link: 'M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71 M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71',
  video: 'M23 7l-7 5 7 5V7z M14 5H3a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2z',
  file: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z M14 2v6h6',
  building: 'M3 21h18 M5 21V7l8-4v18 M19 21V11l-6-3',
  layers: 'M12 2L2 7l10 5 10-5-10-5z M2 17l10 5 10-5 M2 12l10 5 10-5',
  bot: 'M12 8V4H8 M4 8h16a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2z M2 14h2 M20 14h2 M15 13v2 M9 13v2',
  search: 'M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16z M21 21l-4.35-4.35',
  send: 'M22 2L11 13 M22 2l-7 20-4-9-9-4 20-7z',
};
function Icon({ name, size = 16, color = 'currentColor', strokeWidth = 2, style }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color}
      strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0, ...style }}>
      {PATHS[name].split(' M').map((seg, i) => <path key={i} d={(i === 0 ? seg : 'M' + seg)} />)}
    </svg>
  );
}
function Sparkle({ size = 11, color = 'currentColor', style }) {
  return (
    <svg width={size} height={size} viewBox="0 0 12 12" fill={color} aria-hidden="true" style={{ flexShrink: 0, ...style }}>
      <path d="M6 0 L7 5 L12 6 L7 7 L6 12 L5 7 L0 6 L5 5 Z" />
    </svg>
  );
}

// ---------- data (aligned to tenexity catalog domain) ----------
const INDUSTRIES = [
  { id: 'eng', label: 'Engineering & Design', hint: 'Design firms, consultancies' },
  { id: 'mfg', label: 'Parts Manufacturing', hint: 'Machined & fabricated parts' },
  { id: 'dist', label: 'Industrial Distribution', hint: 'MRO, multi-line distributors' },
  { id: 'pipe', label: 'Pipe, Valves & Fittings', hint: 'PVF, flanges, couplings' },
  { id: 'elec', label: 'Electrical Supply', hint: 'Components, wholesale' },
  { id: 'fab', label: 'Fabrication & Machining', hint: 'Job shops, CNC' },
  { id: 'ithw', label: 'IT Hardware Distribution', hint: 'Networking, devices, VARs' },
  { id: 'whse', label: 'Wholesale & Supply Chain', hint: 'Logistics, 3PL' },
];
const SIZES = ['1–10', '11–50', '51–200', '201–1,000', '1,000+'];
const REVENUE = ['< $1M', '$1M–$10M', '$10M–$50M', '$50M–$250M', '$250M+'];
const ROLES = ['Owner / Exec', 'Operations', 'Engineering', 'IT / Systems', 'Sales / Procurement'];
const INTEGRATIONS = [
  { id: 'epicor', label: 'Epicor', kind: 'ERP' },
  { id: 'sap', label: 'SAP', kind: 'ERP' },
  { id: 'netsuite', label: 'NetSuite', kind: 'ERP' },
  { id: 'qb', label: 'QuickBooks', kind: 'Accounting' },
  { id: 'sf', label: 'Salesforce', kind: 'CRM' },
  { id: 'site', label: 'Existing website', kind: 'Web' },
];
// conversation: single bubble, avatar + name, no alternation
const CHAT = [
  { who: 'agent', text: "I read your profile and the process notes. Acme runs RFQ-heavy quoting on Epicor — I've drafted assumptions below. A few questions to sharpen the build." },
  { who: 'agent', text: "Walk me through what happens from the moment a customer requests a quote to when the order ships. Where does it slow down today?" },
  { who: 'user', text: "Quotes are built by hand in spreadsheets, then re-keyed into Epicor. The re-keying and pricing approvals are the bottleneck." },
  { who: 'agent', text: "Got it — manual re-entry between quoting and Epicor, plus a pricing-approval gate. Roughly how many quotes per week, and who signs off on pricing?" },
  { who: 'user', text: "About 120 a week. Anything over a 15% discount goes to a sales manager." },
  { who: 'agent', text: "Clear. Last one — for v1, what matters most: faster quoting, fewer errors into Epicor, or manager visibility?" },
];

// ---------- primitives ----------
function CategoryLabel({ children, tone = 'tertiary', style }) {
  return <span style={{ font: `500 11px/1 ${T.sans}`, letterSpacing: '0.12em', textTransform: 'uppercase',
    color: tone === 'brand' ? T.brand : T.tertiary, display: 'inline-block', ...style }}>{children}</span>;
}

function Btn({ children, variant = 'secondary', size = 'md', onClick, disabled, style, full, title }) {
  const sizes = { sm: { h: 32, px: 10, fs: 13 }, md: { h: 36, px: 12, fs: 13 }, lg: { h: 40, px: 16, fs: 14 } }[size];
  const variants = {
    primary: { background: T.brand, color: '#fff', border: '1px solid transparent' },
    secondary: { background: T.raised, color: T.fg, border: `1px solid ${T.borderDefault}` },
    ghost: { background: 'transparent', color: T.secondary, border: '1px solid transparent' },
    danger: { background: T.danger, color: '#fff', border: '1px solid transparent' },
  }[variant];
  return (
    <button onClick={disabled ? undefined : onClick} title={title} data-variant={variant} disabled={disabled}
      style={{ height: sizes.h, padding: `0 ${sizes.px}px`, font: `500 ${sizes.fs}px/1 ${T.sans}`, borderRadius: T.rMd,
        cursor: disabled ? 'not-allowed' : 'pointer', opacity: disabled ? 0.5 : 1, transition: 'background .18s, border-color .18s, color .18s',
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 6, whiteSpace: 'nowrap', width: full ? '100%' : 'auto',
        ...variants, ...style }}>
      {children}
    </button>
  );
}

function TextInput({ value, onChange, placeholder, type = 'text', style, mono, onKeyDown, size = 'md' }) {
  const h = size === 'sm' ? 32 : 36;
  return (
    <input type={type} value={value || ''} onChange={(e) => onChange && onChange(e.target.value)} placeholder={placeholder} onKeyDown={onKeyDown}
      style={{ width: '100%', boxSizing: 'border-box', height: h, padding: '0 10px', borderRadius: T.rMd,
        border: `1px solid ${T.borderDefault}`, background: T.bg, color: T.fg,
        font: `400 13px/1 ${mono ? T.mono : T.sans}`, outline: 'none', ...style }} />
  );
}

function TextArea({ value, onChange, placeholder, rows = 4, style, onKeyDown }) {
  return (
    <textarea value={value || ''} onChange={(e) => onChange && onChange(e.target.value)} placeholder={placeholder} rows={rows} onKeyDown={onKeyDown}
      style={{ width: '100%', boxSizing: 'border-box', padding: '10px 12px', borderRadius: T.rMd, resize: 'none',
        border: `1px solid ${T.borderDefault}`, background: T.bg, color: T.fg,
        font: `400 13px/1.55 ${T.sans}`, outline: 'none', ...style }} />
  );
}

function Field({ label, optional, hint, children, style }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, ...style }}>
      {(label || optional) && (
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 8 }}>
          {label && <label style={{ font: `500 13px/1.2 ${T.sans}`, color: T.fg }}>{label}</label>}
          {optional && <CategoryLabel style={{ fontSize: 10 }}>Optional</CategoryLabel>}
        </div>
      )}
      {children}
      {hint && <p style={{ margin: 0, font: `400 12px/1.4 ${T.sans}`, color: T.tertiary }}>{hint}</p>}
    </div>
  );
}

function Chip({ children, selected, onClick }) {
  return (
    <button onClick={onClick} style={{ font: `500 13px/1 ${T.sans}`, padding: '8px 13px', borderRadius: 9999, cursor: 'pointer',
      border: `1px solid ${selected ? T.brand : T.borderSubtle}`, background: selected ? T.brandSoft : T.sunken,
      color: selected ? T.brandDeep : T.secondary, transition: 'all .12s' }}>{children}</button>
  );
}
function Chips({ options, value, onChange, multi }) {
  const isOn = (o) => multi ? (value || []).includes(o) : value === o;
  const toggle = (o) => { if (!onChange) return; if (multi) { const s = value || []; onChange(isOn(o) ? s.filter((x) => x !== o) : [...s, o]); } else onChange(o); };
  return <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>{options.map((o) => <Chip key={o} selected={isOn(o)} onClick={() => toggle(o)}>{o}</Chip>)}</div>;
}

function IndustryTile({ item, selected, onClick, compact }) {
  return (
    <button onClick={onClick} style={{ textAlign: 'left', cursor: 'pointer', background: selected ? T.brandSoft : T.raised,
      border: `1px solid ${selected ? T.brand : T.borderDefault}`, borderRadius: T.rLg, padding: compact ? '11px 13px' : '14px 15px',
      transition: 'all .12s', display: 'flex', flexDirection: 'column', gap: 4, boxShadow: selected ? 'none' : T.shadowXs }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <Icon name="building" size={15} color={selected ? T.brandDeep : T.tertiary} />
        <span style={{ font: `600 ${compact ? 13 : 14}px/1.2 ${T.sans}`, color: selected ? T.brandDeep : T.fg }}>{item.label}</span>
      </div>
      {!compact && <span style={{ font: `400 12px/1.3 ${T.sans}`, color: T.tertiary, paddingLeft: 23 }}>{item.hint}</span>}
    </button>
  );
}

const AI_SUMMARIES = {
  'process-walkthrough.mp4': 'Screen recording of a rep building a quote in Excel and re-keying it into Epicor; captures the >15% discount approval email step.',
  'standard-pricing.xlsx': 'Standard price book — list prices and tiered discounts by product line and customer class.',
  'rfq-sop.pdf': 'Standard operating procedure for handling an inbound RFQ end to end.',
  'line-card.pdf': 'Catalog of product lines Acme carries, with manufacturers and categories.',
  'sample-rfq-email.pdf': 'A representative customer RFQ email — the input format reps work from.',
  'discount-matrix.xlsx': 'Approval thresholds and discount tiers by role and order size.',
};

function ScopeToggle({ scope, onChange }) {
  return (
    <span style={{ display: 'inline-flex', padding: 2, borderRadius: 7, background: T.sunken, border: `1px solid ${T.borderSubtle}` }}>
      {[['project', 'Project'], ['org', 'Org-wide']].map(([id, label]) => {
        const on = scope === id;
        return <button key={id} onClick={(e) => { e.stopPropagation(); onChange(id); }} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, font: `600 10px/1 ${T.mono}`, letterSpacing: '0.03em', padding: '4px 7px', borderRadius: 5, cursor: 'pointer', border: 'none',
          background: on ? T.raised : 'transparent', color: on ? (id === 'org' ? T.brandDeep : T.fg) : T.tertiary, boxShadow: on ? T.shadowXs : 'none' }}>{id === 'org' && <Sparkle size={8} color={on ? T.brandDeep : T.tertiary} />}{label}</button>;
      })}
    </span>
  );
}

function FileDescRow({ file, last, describe, scopable }) {
  const [name, size, type] = file;
  const [desc, setDesc] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const [scope, setScope] = React.useState('project');
  const autofill = () => {
    setBusy(true);
    setTimeout(() => { setDesc(AI_SUMMARIES[name] || 'Auto-generated summary of this file’s contents and how it informs the build.'); setBusy(false); }, 650);
  };
  return (
    <div style={{ padding: '10px 12px', borderBottom: last ? 'none' : `1px solid ${T.borderSubtle}` }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={{ display: 'grid', placeItems: 'center', width: 30, height: 30, flexShrink: 0, borderRadius: 6, border: `1px solid ${T.borderSubtle}`, background: T.sunken }}>
          <Icon name={type === 'video' ? 'video' : 'file'} size={14} color={T.tertiary} />
        </span>
        <span style={{ flex: 1, font: `500 13px/1.2 ${T.sans}`, color: T.fg }}>{name}</span>
        <span style={{ font: `400 12px/1 ${T.mono}`, color: T.tertiary }}>{size}</span>
        {scopable && <ScopeToggle scope={scope} onChange={setScope} />}
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, font: `400 12px/1 ${T.sans}`, color: T.success }}>
          <Icon name="check" size={13} color={T.success} /> Uploaded
        </span>
      </div>
      {scopable && scope === 'org' && (
        <div style={{ marginTop: 7, marginLeft: 42, display: 'inline-flex', alignItems: 'center', gap: 6, font: `400 11.5px/1.4 ${T.sans}`, color: T.brandDeep }}>
          <Sparkle size={10} color={T.brandDeep} /> Saved to the organization knowledge base — reused across every project.
        </div>
      )}
      {describe && (
        <div style={{ marginTop: 9, marginLeft: 42, position: 'relative' }}>
          <textarea value={desc} onChange={(e) => setDesc(e.target.value)} rows={2}
            placeholder="Describe this file in your own words — what it is and why it matters…"
            style={{ width: '100%', boxSizing: 'border-box', padding: '8px 10px 26px', borderRadius: T.rMd, resize: 'none',
              border: `1px solid ${desc ? T.brand + '66' : T.borderDefault}`, background: desc ? T.brandSoft + '40' : T.bg, color: T.fg, font: `400 12.5px/1.5 ${T.sans}`, outline: 'none' }} />
          <button onClick={autofill} disabled={busy} style={{ position: 'absolute', left: 8, bottom: 8, display: 'inline-flex', alignItems: 'center', gap: 5,
            font: `500 11px/1 ${T.sans}`, color: T.brandDeep, background: T.raised, border: `1px solid ${T.borderSubtle}`, borderRadius: 6, padding: '4px 8px', cursor: busy ? 'wait' : 'pointer' }}>
            <Sparkle size={10} color={T.brandDeep} /> {busy ? 'Summarizing…' : desc ? 'Regenerate' : 'Auto-summarize'}
          </button>
        </div>
      )}
    </div>
  );
}

function Dropzone({ kind, filled, onToggle, compact, describe }) {
  const isVideo = kind === 'video';
  const files = isVideo ? [['process-walkthrough.mp4', '86.4 MB', 'video']] : [['standard-pricing.xlsx', '142 KB', 'csv'], ['rfq-sop.pdf', '320 KB', 'pdf'], ['line-card.pdf', '1.1 MB', 'pdf']];
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <button onClick={onToggle} style={{ width: '100%', boxSizing: 'border-box', cursor: 'pointer',
        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 12, textAlign: 'center',
        border: `2px dashed ${filled ? T.brand : T.borderDefault}`, borderRadius: T.rLg,
        background: filled ? T.brandSoft : T.sunken, padding: compact ? '10px 14px' : '22px 16px', transition: 'all .14s' }}>
        <Icon name={isVideo ? 'video' : 'upload'} size={20} color={filled ? T.brand : T.tertiary} />
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
          <span style={{ font: `500 14px/1.3 ${T.sans}`, color: T.fg }}>
            {filled ? (isVideo ? 'process-walkthrough.mp4' : 'Add more files') : (isVideo ? 'Record or drop a process walkthrough' : 'Drag files here or click to browse')}
          </span>
          <span style={{ marginTop: 2, font: `400 12px/1.3 ${T.sans}`, color: T.tertiary }}>
            {isVideo ? 'screen recording · mp4, mov — up to 500 MB' : 'SOPs, price lists, specs — pdf, xlsx, docx up to 25 MB'}
          </span>
        </div>
      </button>
      {filled && (
        <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, background: T.raised, overflow: 'hidden' }}>
          {files.map((f, i, arr) => <FileDescRow key={f[0]} file={f} last={i === arr.length - 1} describe={describe} scopable={describe} />)}
        </div>
      )}
    </div>
  );
}

function IntegrationRow({ item, connected, onToggle }) {
  return (
    <button onClick={onToggle} style={{ width: '100%', boxSizing: 'border-box', display: 'flex', alignItems: 'center', gap: 12, cursor: 'pointer',
      padding: '10px 13px', borderRadius: T.rMd, border: `1px solid ${connected ? T.brand : T.borderDefault}`,
      background: connected ? T.brandSoft : T.raised, transition: 'all .12s', textAlign: 'left' }}>
      <span style={{ width: 30, height: 30, borderRadius: 7, flexShrink: 0, display: 'grid', placeItems: 'center',
        background: connected ? T.brand : T.sunken, color: connected ? '#fff' : T.secondary, font: `700 11px/1 ${T.mono}` }}>
        {item.label.slice(0, 2).toUpperCase()}
      </span>
      <span style={{ flex: 1 }}>
        <span style={{ display: 'block', font: `600 13px/1.2 ${T.sans}`, color: T.fg }}>{item.label}</span>
        <CategoryLabel style={{ fontSize: 10, marginTop: 2 }}>{item.kind}</CategoryLabel>
      </span>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, font: `500 12px/1 ${T.sans}`, color: connected ? T.success : T.brandDeep }}>
        {connected ? <React.Fragment><Icon name="check" size={13} color={T.success} /> Linked</React.Fragment> : <React.Fragment><Icon name="link" size={13} color={T.brandDeep} /> Link</React.Fragment>}
      </span>
    </button>
  );
}

function StatusPill({ tone = 'neutral', children, dot = true }) {
  const tones = {
    neutral: [T.sunken, T.secondary], success: [T.successSoft, T.success], warning: [T.warningSoft, T.warning],
    danger: [T.dangerSoft, T.danger], info: [T.brandSoft, T.brandDeep], brand: [T.brandSoft, T.brandDeep],
  }[tone];
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '3px 9px', borderRadius: 9999,
      font: `500 11px/1.3 ${T.sans}`, background: tones[0], color: tones[1] }}>
      {dot && <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'currentColor' }} />}{children}
    </span>
  );
}

function ConfidencePill({ band, score }) {
  const map = { exact: ['Exact', T.cExactSoft, T.cExact], high: ['High', T.cHighSoft, T.cHigh], medium: ['Medium', T.cMedSoft, T.cMed], low: ['Low', T.cLowSoft, T.cLow], none: ['Unknown', T.cNoneSoft, T.cNone] }[band];
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 7px', borderRadius: 9999,
      font: `500 11px/1.3 ${T.mono}`, background: map[1], color: map[2] }}>
      <Sparkle size={10} color={map[2]} /> {map[0]}{score != null && <span style={{ opacity: 0.7 }}>·{score}</span>}
    </span>
  );
}

function Avatar({ name, size = 28, tone }) {
  const tones = { neutral: [T.sunken, T.secondary], brand: [T.brandSoft, T.brandDeep], success: [T.successSoft, T.success], warning: [T.warningSoft, T.warning] };
  const order = ['neutral', 'brand', 'success', 'warning'];
  let h = 0; for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  const t = tones[tone || order[h % 4]];
  const parts = name.trim().split(/\s+/);
  const init = parts.length === 1 ? parts[0].slice(0, 2).toUpperCase() : (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  return <span title={name} style={{ width: size, height: size, borderRadius: '50%', display: 'inline-grid', placeItems: 'center',
    background: t[0], color: t[1], font: `600 ${Math.round(size * 0.38)}px/1 ${T.sans}`, flexShrink: 0 }}>{init}</span>;
}

// AI-derived value: faint brand tint + inset brand bar + sparkle (the system "tell")
function AiTint({ children, style }) {
  return <span className="ai-tint" style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '2px 7px', borderRadius: 5,
    font: `500 13px/1.3 ${T.sans}`, color: T.fg, ...style }}><Sparkle size={10} color={T.brand} />{children}</span>;
}

// Conversation item — ONE bubble shape, identified by avatar+name, never alignment.
function Message({ who, persona, text, confidence, anim, badge }) {
  const isAgent = who === 'agent';
  return (
    <article style={{ display: 'flex', gap: 10, animation: anim ? 'sfRise .35s var(--ease-out, ease) both' : 'none' }}>
      {isAgent ? (
        <span style={{ marginTop: 1, width: 28, height: 28, flexShrink: 0, borderRadius: '50%', display: 'grid', placeItems: 'center',
          background: T.brandSoft, color: T.brand, boxShadow: `inset 0 0 0 1px ${T.brand}33` }}><Sparkle size={13} color={T.brand} /></span>
      ) : <Avatar name="Ibraheem K" size={28} />}
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 6,
        border: `1px solid ${isAgent ? T.brand + '33' : T.borderSubtle}`, background: isAgent ? T.brandSoft + '4d' : T.raised,
        borderRadius: T.rLg, padding: '10px 13px' }}>
        <header style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ font: `600 13px/1 ${T.sans}`, color: T.fg }}>{isAgent ? (persona || 'Concierge') : 'You'}</span>
          {isAgent && <span style={{ font: `500 10px/1 ${T.sans}`, letterSpacing: '0.08em', textTransform: 'uppercase',
            background: T.brandSoft, color: T.brandDeep, padding: '3px 6px', borderRadius: 4 }}>{badge || 'Concierge'}</span>}
          {confidence && <ConfidencePill band={confidence} />}
        </header>
        <p style={{ margin: 0, font: `400 13.5px/1.5 ${T.sans}`, color: isAgent ? T.secondary : T.fg }}>{text}</p>
      </div>
    </article>
  );
}

function Composer({ placeholder = 'Reply…', onSend, value, onChange }) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8, border: `1px solid ${T.borderDefault}`, borderRadius: T.rLg, background: T.raised, padding: 8 }}>
      <textarea value={value || ''} onChange={(e) => onChange && onChange(e.target.value)} placeholder={placeholder} rows={1}
        style={{ flex: 1, minWidth: 0, resize: 'none', border: 'none', outline: 'none', background: 'transparent', padding: '6px', font: `400 13px/1.4 ${T.sans}`, color: T.fg }} />
      <button title="Dictate" style={{ width: 30, height: 30, display: 'grid', placeItems: 'center', borderRadius: T.rMd, border: 'none', background: 'transparent', color: T.tertiary, cursor: 'pointer' }}><Icon name="mic" size={15} /></button>
      <Btn variant="primary" size="sm" onClick={onSend} style={{ height: 30 }}><Icon name="send" size={13} color="#fff" /> Send</Btn>
    </div>
  );
}

function Wordmark({ size = 19 }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
      <span style={{ width: 24, height: 24, borderRadius: 6, background: T.brand, display: 'grid', placeItems: 'center', flexShrink: 0 }}>
        <Icon name="layers" size={14} color="#fff" strokeWidth={2.2} />
      </span>
      <span style={{ font: `700 ${size}px/1 ${T.display}`, letterSpacing: '-0.015em', color: T.fg }}>Software Factory</span>
    </div>
  );
}

function SectionDivider({ label, sub, icon }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, margin: '6px 0 2px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
        {icon && <span style={{ width: 22, height: 22, borderRadius: 6, display: 'grid', placeItems: 'center', background: T.sunken, border: `1px solid ${T.borderSubtle}`, color: T.secondary }}><Icon name={icon} size={13} color={T.secondary} /></span>}
        <CategoryLabel style={{ color: T.fg }}>{label}</CategoryLabel>
        {sub && <span style={{ font: `400 12px/1 ${T.sans}`, color: T.tertiary }}>{sub}</span>}
      </div>
      <span style={{ flex: 1, height: 1, background: T.borderSubtle }} />
    </div>
  );
}

Object.assign(window, {
  T, Icon, Sparkle, INDUSTRIES, SIZES, REVENUE, ROLES, INTEGRATIONS, CHAT,
  CategoryLabel, Btn, TextInput, TextArea, Field, Chip, Chips, IndustryTile, Dropzone, IntegrationRow,
  StatusPill, ConfidencePill, Avatar, AiTint, Message, Composer, Wordmark, ScopeToggle, SectionDivider,
});
