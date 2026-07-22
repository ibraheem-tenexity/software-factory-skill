// users.jsx — Tenexity OS · User management (the master users table).
// One table underneath the whole platform: every person allowed to sign in,
// across every organization + internal Tenexity staff. A user is added with a
// sign-in method (Google / Microsoft / Email & password / Org SSO); until they
// first sign in they sit as `invited` with a copyable invite link, then the
// flag flips to `active`. Tenexity operators have full read/write here.
//
// Reuses OS helpers exported to window from admin.jsx + shared.jsx + dashboard.jsx.

const { T, Icon, Sparkle, StatusPill, Avatar, Field, TextInput, MetricCard,
        AdminBtn, PageTitle, ColHead, Mono, InitSquare, AdminFilter } = window;

/* ---- sign-in methods ---- */
const SIGNIN_METHODS = {
  google:    { label: 'Google',            short: 'Google',         mark: 'G',   tone: ['#E8F1FF', '#0958C9'] },
  microsoft: { label: 'Microsoft',         short: 'Microsoft',      mark: 'MS',  tone: ['#E0F4F7', '#11A0B8'] },
  password:  { label: 'Email & password',  short: 'Email · pass',   mark: '@',   tone: ['#EDEDEF', '#52525B'] },
  sso:       { label: 'Organization SSO',  short: 'SSO',            mark: 'SSO', tone: ['#f3e9fb', '#7a3ea8'] },
};
const METHOD_ORDER = ['google', 'microsoft', 'password', 'sso'];

/* ---- the master users table (mock, one row per allow-listed person) ---- */
const USERS_SEED = [
  { id: 'u1',  name: 'Ibraheem Khalil',  email: 'ibraheem@acme-industrial.com', org: 'Acme Corp',                         role: 'Admin',    method: 'google',    status: 'active',   designation: 'VP Operations',      invitedBy: 'ops@tenexity.ai',   last: '4 minutes ago',  joined: 'Mar 2, 2026' },
  { id: 'u2',  name: 'Maya Restrepo',    email: 'maya@acme-industrial.com',     org: 'Acme Corp',                         role: 'Member',   method: 'google',    status: 'active',   designation: 'Procurement Lead',   invitedBy: 'ibraheem@acme-industrial.com', last: '2 hours ago', joined: 'Mar 4, 2026' },
  { id: 'u3',  name: 'Dana Whitfield',   email: 'dana@brassica.com',            org: 'Brassica Markets',                  role: 'Admin',    method: 'microsoft', status: 'invited',  designation: 'Director of IT',     invitedBy: 'ops@tenexity.ai',   last: '—',              joined: '—' },
  { id: 'u4',  name: 'Theo Vance',       email: 'theo@meridiansupply.com',      org: 'Meridian Industrial Supply',        role: 'Admin',    method: 'password',  status: 'active',   designation: 'Owner',              invitedBy: 'ops@tenexity.ai',   last: 'Yesterday',      joined: 'Feb 18, 2026' },
  { id: 'u5',  name: 'Priya Nadarajah',  email: 'priya@meridiansupply.com',     org: 'Meridian Industrial Supply',        role: 'Member',   method: 'password',  status: 'disabled', designation: 'Systems Analyst',    invitedBy: 'theo@meridiansupply.com', last: '3 weeks ago', joined: 'Feb 20, 2026' },
  { id: 'u6',  name: 'Cole Barrett',     email: 'cole@beaconsupply.com',        org: 'Beacon Industrial Supply',          role: 'Admin',    method: 'google',    status: 'active',   designation: 'Operations Manager', invitedBy: 'ops@tenexity.ai',   last: '8 minutes ago',  joined: 'Apr 11, 2026' },
  { id: 'u7',  name: 'Nick Alvarez',     email: 'nick@nickco.dev',              org: 'Nick.',                             role: 'Admin',    method: 'sso',       status: 'active',   designation: 'Founder',            invitedBy: 'ops@tenexity.ai',   last: '1 hour ago',     joined: 'Jan 9, 2026' },
  { id: 'u8',  name: 'Renata Söder',     email: 'renata@pinnaclefood.com',      org: 'Pinnacle Foodservice Distributors', role: 'Admin',    method: 'microsoft', status: 'active',   designation: 'EDI Manager',        invitedBy: 'ops@tenexity.ai',   last: 'Today',          joined: 'Mar 28, 2026' },
  { id: 'u9',  name: 'Sam Okonkwo',      email: 'sam@pinnaclefood.com',         org: 'Pinnacle Foodservice Distributors', role: 'Member',   method: 'microsoft', status: 'invited',  designation: 'Logistics Coord.',   invitedBy: 'renata@pinnaclefood.com', last: '—',         joined: '—' },
  { id: 'u10', name: 'Bea Lindqvist',    email: 'bea@cardinal3pl.com',          org: 'Cardinal Logistics',                role: 'Admin',    method: 'google',    status: 'active',   designation: 'VP Supply Chain',    invitedBy: 'ops@tenexity.ai',   last: '5 hours ago',    joined: 'Feb 2, 2026' },
  { id: 'u11', name: 'Marcus Feld',      email: 'marcus@latticeclimbing.co',    org: 'Lattice Climbing Co.',              role: 'Admin',    method: 'password',  status: 'invited',  designation: 'Head of Retail',     invitedBy: 'ops@tenexity.ai',   last: '—',              joined: '—' },
  { id: 'u12', name: 'Harper Nguyen',    email: 'harper@tenexity.ai',           org: 'Tenexity',                          role: 'Operator', method: 'google',    status: 'active',   designation: 'Platform Operator',  invitedBy: 'founders@tenexity.ai', last: 'Just now',    joined: 'Nov 1, 2025', internal: true },
  { id: 'u13', name: 'Ops Bot',          email: 'ops@tenexity.ai',              org: 'Tenexity',                          role: 'Operator', method: 'sso',       status: 'active',   designation: 'Operations',         invitedBy: 'founders@tenexity.ai', last: '12 minutes ago', joined: 'Nov 1, 2025', internal: true },
  { id: 'u14', name: 'Dev Onboarding',   email: 'eng-newhire@tenexity.ai',      org: 'Tenexity',                          role: 'Operator', method: 'password',  status: 'invited',  designation: 'Software Engineer',  invitedBy: 'harper@tenexity.ai', last: '—',             joined: '—', internal: true },
];

const ORG_OPTIONS = ['Acme Corp', 'Meridian Industrial Supply', 'Beacon Industrial Supply', 'Brassica Markets', 'Pinnacle Foodservice Distributors', 'Cardinal Logistics', 'Lattice Climbing Co.', 'Halcyon Bicycles', 'Nick.', 'vamac', 'Riverbend Hardware Distribution'];

function initials(t) { const p = t.trim().split(/\s+/); return p.length === 1 ? p[0].slice(0, 2).toUpperCase() : (p[0][0] + p[p.length - 1][0]).toUpperCase(); }
function tokenFor(email) { let h = 0; for (let i = 0; i < email.length; i++) h = (h * 33 + email.charCodeAt(i)) >>> 0; return h.toString(36).padStart(7, '0').slice(0, 7); }

/* ---- small UI atoms ---- */
function MethodBadge({ method }) {
  const m = SIGNIN_METHODS[method];
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, minWidth: 0 }}>
      <span style={{ width: 22, height: 22, flexShrink: 0, borderRadius: 5, display: 'grid', placeItems: 'center', background: m.tone[0], color: m.tone[1], font: `700 8.5px/1 ${T.mono}` }}>{m.mark}</span>
      <Mono style={{ fontSize: 11, color: T.secondary, whiteSpace: 'nowrap' }}>{m.short}</Mono>
    </span>
  );
}
function RoleBadge({ role, internal }) {
  const isInternal = internal || role === 'Operator';
  const tone = isInternal ? ['#f3e9fb', '#7a3ea8'] : role === 'Admin' ? [T.brandSoft, T.brandDeep] : [T.sunken, T.secondary];
  const label = isInternal && role === 'Admin' ? 'Tenexity Admin' : role;
  return <span style={{ font: `600 9.5px/1 ${T.mono}`, letterSpacing: '0.05em', textTransform: 'uppercase', color: tone[1], background: tone[0], border: `1px solid ${tone[1]}22`, padding: '4px 6px', borderRadius: 4, justifySelf: 'start' }}>{label}</span>;
}
function StatusCell({ status }) {
  const map = { active: ['success', 'active'], invited: ['warning', 'invited'], disabled: ['neutral', 'disabled'] }[status];
  return <StatusPill tone={map[0]} dot={status !== 'disabled'}>{map[1]}</StatusPill>;
}
function InviteLink({ email, compact }) {
  const [copied, setCopied] = React.useState(false);
  const url = `tenexity.ai/join/${tokenFor(email)}`;
  const copy = (e) => { e.stopPropagation(); setCopied(true); setTimeout(() => setCopied(false), 1400); };
  return (
    <button onClick={copy} title="Copy invite link" style={{ display: 'inline-flex', alignItems: 'center', gap: 7, height: compact ? 26 : 32, padding: '0 9px', cursor: 'pointer',
      borderRadius: T.rMd, border: `1px dashed ${copied ? T.success : T.borderDefault}`, background: copied ? T.successSoft : T.bg }}>
      <Icon name="link" size={12} color={copied ? T.success : T.tertiary} />
      <Mono style={{ fontSize: 10.5, color: copied ? T.success : T.secondary }}>{copied ? 'Link copied' : url}</Mono>
    </button>
  );
}

/* ---- row kebab menu ---- */
function RowMenu({ user, onAct }) {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef(null);
  React.useEffect(() => {
    if (!open) return;
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', h); return () => document.removeEventListener('mousedown', h);
  }, [open]);
  const items = [
    user.status === 'invited' && ['copy', 'Copy invite link', T.fg],
    user.status === 'invited' && ['resend', 'Resend invite', T.fg],
    user.status === 'active' && ['disable', 'Disable sign-in', T.warning],
    user.status === 'disabled' && ['enable', 'Re-enable', T.success],
    ['edit', 'Edit user', T.fg],
    ['remove', 'Remove user', T.danger],
  ].filter(Boolean);
  return (
    <span ref={ref} style={{ position: 'relative', justifySelf: 'end' }}>
      <button onClick={(e) => { e.stopPropagation(); setOpen((o) => !o); }} title="Actions" style={{ width: 28, height: 28, display: 'grid', placeItems: 'center', borderRadius: T.rMd, border: 'none', background: open ? T.sunken : 'transparent', color: T.tertiary, cursor: 'pointer' }}>
        <Icon name="dots" size={16} />
      </button>
      {open && (
        <div style={{ position: 'absolute', right: 0, top: 32, zIndex: 30, minWidth: 180, padding: 5, borderRadius: T.rLg, background: T.raised, border: `1px solid ${T.borderSubtle}`, boxShadow: T.shadowMd }}>
          {items.map(([id, label, color]) => (
            <button key={id} onClick={(e) => { e.stopPropagation(); setOpen(false); onAct(id, user); }} style={{ display: 'block', width: '100%', textAlign: 'left', padding: '8px 10px', borderRadius: 6, border: 'none', background: 'transparent', cursor: 'pointer', font: `500 12.5px/1 ${T.sans}`, color }}
              onMouseEnter={(e) => e.currentTarget.style.background = T.sunken} onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}>{label}</button>
          ))}
        </div>
      )}
    </span>
  );
}

/* ---- select control (matches AdminFilter look) ---- */
function SelectField({ value, onChange, options, w }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', height: 36, borderRadius: T.rMd, border: `1px solid ${T.borderDefault}`, background: T.raised, position: 'relative', width: w || '100%' }}>
      <select value={value} onChange={(e) => onChange(e.target.value)} style={{ appearance: 'none', WebkitAppearance: 'none', width: '100%', height: '100%', border: 'none', background: 'transparent', outline: 'none', padding: '0 28px 0 11px', font: `500 12.5px/1 ${T.sans}`, color: T.fg, cursor: 'pointer' }}>
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
      <Icon name="chevronDown" size={14} color={T.tertiary} style={{ position: 'absolute', right: 9, pointerEvents: 'none' }} />
    </div>
  );
}

/* ---- Add user modal ---- */
function AddUserModal({ onClose, onCreate }) {
  const [email, setEmail] = React.useState('');
  const [name, setName] = React.useState('');
  const [audience, setAudience] = React.useState('org'); // org | tenexity
  const [org, setOrg] = React.useState(ORG_OPTIONS[0]);
  const [role, setRole] = React.useState('Member');
  const [method, setMethod] = React.useState('google');
  const [designation, setDesignation] = React.useState('');
  const [pw, setPw] = React.useState('');
  const [created, setCreated] = React.useState(null);
  const valid = /\S+@\S+\.\S+/.test(email);
  const isTenexity = audience === 'tenexity';
  const provisioned = method === 'password' && pw.trim().length >= 6;
  const genPw = () => setPw(Math.random().toString(36).slice(2, 10) + 'A1');

  const submit = () => {
    if (!valid) return;
    const u = {
      id: 'u' + Date.now(), email, name: name.trim() || email.split('@')[0].replace(/[._]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
      org: isTenexity ? 'Tenexity' : org, role: role, method, designation: designation.trim(),
      status: provisioned ? 'active' : 'invited', invitedBy: 'you@tenexity.ai', last: provisioned ? 'Never (provisioned)' : '—', joined: provisioned ? 'Today' : '—', internal: isTenexity,
    };
    onCreate(u);
    setCreated({ ...u, provisioned });
  };

  return (
    <div onClick={onClose} style={{ position: 'absolute', inset: 0, zIndex: 70, background: 'rgba(9,12,18,0.45)', display: 'grid', placeItems: 'center', padding: 28, animation: 'sfRise .18s ease both' }}>
      <div onClick={(e) => e.stopPropagation()} style={{ width: 'min(600px, 100%)', maxHeight: '100%', background: T.raised, borderRadius: T.rXl, boxShadow: T.shadowMd, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 20px', borderBottom: `1px solid ${T.borderSubtle}` }}>
          <div>
            <h2 style={{ font: `400 19px/1.2 ${T.display}`, color: T.fg, margin: 0 }}>{created ? 'User added' : 'Add user'}</h2>
            <Mono style={{ fontSize: 11, marginTop: 4, display: 'block' }}>{created ? 'Added to the sign-in allow-list' : 'One record in the master users table'}</Mono>
          </div>
          <button onClick={onClose} title="Close" style={{ width: 28, height: 28, display: 'grid', placeItems: 'center', borderRadius: T.rMd, border: 'none', background: 'transparent', color: T.tertiary, cursor: 'pointer' }}><Icon name="x" size={16} /></button>
        </div>

        {created ? (
          <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <Avatar name={created.name} size={40} tone={created.internal ? 'brand' : undefined} />
              <div style={{ minWidth: 0 }}>
                <div style={{ font: `600 15px/1.2 ${T.sans}`, color: T.fg }}>{created.name}</div>
                <Mono style={{ fontSize: 11.5, color: T.secondary }}>{created.email}</Mono>
              </div>
              <span style={{ marginLeft: 'auto' }}><StatusCell status={created.status} /></span>
            </div>
            {created.provisioned ? (
              <div style={{ display: 'flex', gap: 9, padding: '12px 13px', borderRadius: T.rMd, background: T.successSoft + '88', border: `1px solid ${T.success}33` }}>
                <Icon name="check" size={15} color={T.success} style={{ marginTop: 1 }} />
                <span style={{ font: `400 12.5px/1.5 ${T.sans}`, color: T.secondary }}>Credentials provisioned directly — <b style={{ color: T.fg }}>{created.email}</b> can sign in immediately with the password you set. The flag flips to <b style={{ color: T.fg }}>active</b> on first sign-in.</span>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
                <span style={{ font: `400 12.5px/1.5 ${T.sans}`, color: T.secondary }}>Share this invite link. When they sign in with <b style={{ color: T.fg }}>{SIGNIN_METHODS[created.method].label}</b> for the first time, the flag flips from <b style={{ color: T.fg }}>invited</b> to <b style={{ color: T.fg }}>active</b>.</span>
                <InviteLink email={created.email} />
              </div>
            )}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 9, paddingTop: 4 }}>
              <AdminBtn onClick={() => { setCreated(null); setEmail(''); setName(''); setDesignation(''); setPw(''); }}>Add another</AdminBtn>
              <AdminBtn primary onClick={onClose}>Done</AdminBtn>
            </div>
          </div>
        ) : (
          <React.Fragment>
            <div style={{ padding: '18px 20px', display: 'flex', flexDirection: 'column', gap: 14, overflow: 'auto' }}>
              {/* audience segmented */}
              <div>
                <ColHead style={{ display: 'block', marginBottom: 7 }}>Belongs to</ColHead>
                <div style={{ display: 'inline-flex', padding: 2, borderRadius: T.rMd, background: T.sunken, border: `1px solid ${T.borderSubtle}` }}>
                  {[['org', 'An organization'], ['tenexity', 'Tenexity · internal']].map(([id, label]) => (
                    <button key={id} onClick={() => { setAudience(id); setRole(id === 'tenexity' ? 'Operator' : 'Member'); }} style={{ font: `600 11px/1 ${T.mono}`, letterSpacing: '0.03em', padding: '7px 12px', borderRadius: 5, cursor: 'pointer', border: 'none', background: audience === id ? T.fg : 'transparent', color: audience === id ? '#fff' : T.tertiary }}>{label}</button>
                  ))}
                </div>
              </div>
              <div style={{ display: 'flex', gap: 10 }}>
                <Field label="Email address" style={{ flex: 1 }}><TextInput type="email" value={email} onChange={setEmail} placeholder="person@company.com" mono /></Field>
                <Field label="Full name" optional style={{ flex: 1 }}><TextInput value={name} onChange={setName} placeholder="Jordan Rivera" /></Field>
              </div>
              <div style={{ display: 'flex', gap: 10 }}>
                <Field label={isTenexity ? 'Workspace' : 'Organization'} style={{ flex: 1 }}>
                  {isTenexity ? (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, height: 36, padding: '0 11px', borderRadius: T.rMd, border: `1px solid ${T.borderDefault}`, background: T.sunken }}>
                      <Sparkle size={11} color="#7a3ea8" /><span style={{ font: `500 12.5px/1 ${T.sans}`, color: T.fg }}>Tenexity (cross-tenant access)</span>
                    </div>
                  ) : <SelectField value={org} onChange={setOrg} options={ORG_OPTIONS} />}
                </Field>
                <Field label="Role" style={{ width: 168, flexShrink: 0 }} hint={isTenexity ? (role === 'Admin' ? 'Full platform read/write' : 'Standard operator access') : null}>
                  <SelectField value={role} onChange={setRole} options={isTenexity ? ['Operator', 'Admin'] : ['Admin', 'Member']} />
                </Field>
              </div>
              <Field label="Sign-in method" hint="The same record holds the method. Until first sign-in, the user stays invited.">
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8 }}>
                  {METHOD_ORDER.map((m) => {
                    const on = method === m; const meta = SIGNIN_METHODS[m];
                    return (
                      <button key={m} onClick={() => setMethod(m)} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 7, padding: '12px 6px', borderRadius: T.rMd, cursor: 'pointer',
                        border: `1px solid ${on ? T.brand : T.borderDefault}`, background: on ? T.brandSoft : T.raised }}>
                        <span style={{ width: 26, height: 26, borderRadius: 6, display: 'grid', placeItems: 'center', background: meta.tone[0], color: meta.tone[1], font: `700 9px/1 ${T.mono}` }}>{meta.mark}</span>
                        <span style={{ font: `500 11px/1.1 ${T.sans}`, color: on ? T.brandDeep : T.secondary, textAlign: 'center' }}>{meta.label}</span>
                      </button>
                    );
                  })}
                </div>
              </Field>
              {method === 'password' && (
                <Field label="Initial password" optional hint="Set one to provision the account directly — they can sign in immediately. Leave blank to send a set-password invite link instead.">
                  <div style={{ display: 'flex', gap: 8 }}>
                    <TextInput value={pw} onChange={setPw} placeholder="Auto-generate or type a temporary password" mono style={{ flex: 1 }} />
                    <AdminBtn onClick={genPw}>Generate</AdminBtn>
                  </div>
                </Field>
              )}
              <Field label="Designation" optional hint="Job title stored on the record."><TextInput value={designation} onChange={setDesignation} placeholder="e.g. Operations Manager" /></Field>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, padding: '13px 20px', borderTop: `1px solid ${T.borderSubtle}`, background: T.sunken }}>
              <Mono style={{ fontSize: 11, color: T.tertiary }}>{provisioned ? 'Provisioned · active on first sign-in' : 'Invite link generated · status invited'}</Mono>
              <div style={{ display: 'flex', gap: 9 }}>
                <AdminBtn onClick={onClose}>Cancel</AdminBtn>
                <AdminBtn primary onClick={submit}>{provisioned ? 'Create user' : 'Send invite'}</AdminBtn>
              </div>
            </div>
          </React.Fragment>
        )}
      </div>
    </div>
  );
}

/* ---- user detail / edit drawer ---- */
function UserDrawer({ user, onClose, onAct }) {
  const [role, setRole] = React.useState(user.role);
  const [method, setMethod] = React.useState(user.method);
  const [designation, setDesignation] = React.useState(user.designation || '');
  const dirty = role !== user.role || method !== user.method || designation !== (user.designation || '');
  const isTenexity = user.role === 'Operator' || user.internal;
  return (
    <div onClick={onClose} style={{ position: 'absolute', inset: 0, zIndex: 65, background: 'rgba(9,12,18,0.45)', display: 'flex', justifyContent: 'flex-end', animation: 'sfRise .18s ease both' }}>
      <div onClick={(e) => e.stopPropagation()} style={{ width: 'min(480px, 100%)', height: '100%', background: T.raised, boxShadow: T.shadowMd, display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', padding: '18px 20px', borderBottom: `1px solid ${T.borderSubtle}` }}>
          <div style={{ display: 'flex', gap: 12, minWidth: 0 }}>
            <Avatar name={user.name} size={42} tone={isTenexity ? 'brand' : undefined} />
            <div style={{ minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ font: `600 16px/1.2 ${T.sans}`, color: T.fg }}>{user.name}</span>
                <StatusCell status={user.status} />
              </div>
              <Mono style={{ fontSize: 11.5, color: T.secondary, marginTop: 3, display: 'block' }}>{user.email}</Mono>
            </div>
          </div>
          <button onClick={onClose} title="Close" style={{ width: 28, height: 28, flexShrink: 0, display: 'grid', placeItems: 'center', borderRadius: T.rMd, border: 'none', background: 'transparent', color: T.tertiary, cursor: 'pointer' }}><Icon name="x" size={16} /></button>
        </div>

        <div style={{ flex: 1, overflow: 'auto', padding: '18px 20px', display: 'flex', flexDirection: 'column', gap: 16 }}>
          {user.status === 'invited' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 9, padding: '12px 13px', borderRadius: T.rMd, background: T.warningSoft + '66', border: `1px solid ${T.warning}33` }}>
              <span style={{ font: `400 12.5px/1.5 ${T.sans}`, color: T.secondary }}>Pending first sign-in. Share the invite link — the flag flips to <b style={{ color: T.fg }}>active</b> automatically.</span>
              <div style={{ display: 'flex', gap: 8 }}><InviteLink email={user.email} compact /><AdminBtn onClick={() => onAct('resend', user)}>Resend</AdminBtn></div>
            </div>
          )}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1, background: T.borderSubtle, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rMd, overflow: 'hidden' }}>
            {[['Organization', user.org], ['Joined', user.joined], ['Last active', user.last], ['Invited by', user.invitedBy]].map(([k, v]) => (
              <div key={k} style={{ background: T.raised, padding: '11px 13px' }}><ColHead style={{ display: 'block', marginBottom: 4 }}>{k}</ColHead><span style={{ font: `500 12.5px/1.3 ${T.sans}`, color: T.fg, wordBreak: 'break-word' }}>{v}</span></div>
            ))}
          </div>
          <Field label="Role"><SelectField value={role} onChange={setRole} options={isTenexity ? ['Operator', 'Admin'] : ['Admin', 'Member']} /></Field>
          <Field label="Sign-in method" hint="Switching the method takes effect on the next sign-in.">
            <SelectField value={method} onChange={setMethod} options={METHOD_ORDER.map((m) => SIGNIN_METHODS[m].label)}
              />
          </Field>
          <Field label="Designation"><TextInput value={designation} onChange={setDesignation} placeholder="Job title" /></Field>

          <div style={{ marginTop: 6, paddingTop: 14, borderTop: `1px solid ${T.borderSubtle}` }}>
            <ColHead style={{ display: 'block', marginBottom: 10, color: T.danger }}>Danger zone</ColHead>
            <div style={{ display: 'flex', gap: 9, flexWrap: 'wrap' }}>
              {user.status === 'active' && <AdminBtn onClick={() => onAct('disable', user)}><Icon name="x" size={13} color={T.warning} /> Disable sign-in</AdminBtn>}
              {user.status === 'disabled' && <AdminBtn onClick={() => onAct('enable', user)}><Icon name="check" size={13} color={T.success} /> Re-enable</AdminBtn>}
              <button onClick={() => onAct('remove', user)} style={{ display: 'inline-flex', alignItems: 'center', gap: 7, height: 36, padding: '0 14px', cursor: 'pointer', font: `600 11.5px/1 ${T.mono}`, letterSpacing: '0.05em', textTransform: 'uppercase', borderRadius: T.rMd, border: `1px solid ${T.danger}55`, background: T.dangerSoft, color: T.danger }}>Remove user</button>
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 9, padding: '13px 20px', borderTop: `1px solid ${T.borderSubtle}` }}>
          <AdminBtn onClick={onClose}>Cancel</AdminBtn>
          <AdminBtn primary onClick={onClose}>{dirty ? 'Save changes' : 'Saved'}</AdminBtn>
        </div>
      </div>
    </div>
  );
}

/* ---- main view ---- */
const GRID = 'minmax(0,1.5fr) minmax(0,1.1fr) 92px 150px 96px 110px 40px';
function UsersManagement({ loading = false }) {
  const [users, setUsers] = React.useState(USERS_SEED);
  const [add, setAdd] = React.useState(false);
  const [drawer, setDrawer] = React.useState(null);
  const [audience, setAudience] = React.useState('ALL');
  const [fOrg, setFOrg] = React.useState('All organizations');
  const [fRole, setFRole] = React.useState('All roles');
  const [fStatus, setFStatus] = React.useState('All statuses');
  const [q, setQ] = React.useState('');
  const qDict = useDictation(q, setQ);

  const act = (id, user) => {
    if (id === 'remove') { setUsers((u) => u.filter((x) => x.id !== user.id)); setDrawer(null); }
    else if (id === 'disable') { setUsers((u) => u.map((x) => x.id === user.id ? { ...x, status: 'disabled' } : x)); setDrawer((d) => d && d.id === user.id ? { ...d, status: 'disabled' } : d); }
    else if (id === 'enable') { setUsers((u) => u.map((x) => x.id === user.id ? { ...x, status: 'active' } : x)); setDrawer((d) => d && d.id === user.id ? { ...d, status: 'active' } : d); }
    else if (id === 'edit') { setDrawer(user); }
    // copy / resend are handled inline (no state change needed for the mock)
  };

  const filtered = users.filter((u) => {
    if (audience === 'ORGANIZATIONS' && u.internal) return false;
    if (audience === 'INTERNAL' && !u.internal) return false;
    if (fOrg !== 'All organizations' && u.org !== fOrg) return false;
    if (fRole !== 'All roles' && u.role !== fRole) return false;
    if (fStatus !== 'All statuses' && u.status !== fStatus.toLowerCase()) return false;
    if (q && !(u.name + u.email + u.org).toLowerCase().includes(q.toLowerCase())) return false;
    return true;
  });

  const count = (s) => users.filter((u) => u.status === s).length;

  return (
    <React.Fragment>
      <PageTitle title="Users" sub="The master users table — everyone allowed to sign in, across every organization and internal Tenexity staff."
        actions={<AdminBtn primary onClick={() => setAdd(true)}><Icon name="plus" size={14} color="#fff" /> Add user</AdminBtn>} />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 20 }}>
        {loading ? [0, 1, 2, 3].map((i) => <MetricCardSkel key={i} />) : <React.Fragment>
        <MetricCard label="Total users" value={users.length} hint="across all organizations" accent />
        <MetricCard label="Active" value={count('active')} hint="signed in at least once" />
        <MetricCard label="Pending invites" value={count('invited')} hint="awaiting first sign-in" />
        <MetricCard label="Disabled" value={count('disabled')} hint="sign-in revoked" />
        </React.Fragment>}
      </div>

      {/* filters */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14, flexWrap: 'wrap' }}>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 36, padding: '0 11px', borderRadius: T.rMd, border: `1px solid ${T.borderDefault}`, background: T.raised, flex: 1, minWidth: 200 }}>
          <Icon name="search" size={14} color={T.tertiary} />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name, email, organization…" style={{ flex: 1, border: 'none', outline: 'none', background: 'transparent', font: `400 12.5px/1 ${T.sans}`, color: T.fg }} />
          {qDict.supported && <MicButton size={26} listening={qDict.listening} onClick={qDict.toggle} title="Dictate search" />}
        </div>
        <div style={{ width: 170 }}><SelectField value={fOrg} onChange={setFOrg} options={['All organizations', ...ORG_OPTIONS, 'Tenexity']} /></div>
        <div style={{ width: 130 }}><SelectField value={fRole} onChange={setFRole} options={['All roles', 'Admin', 'Member', 'Operator']} /></div>
        <div style={{ width: 130 }}><SelectField value={fStatus} onChange={setFStatus} options={['All statuses', 'Active', 'Invited', 'Disabled']} /></div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <ColHead>Audience</ColHead>
          <div style={{ display: 'inline-flex', padding: 2, borderRadius: T.rMd, background: T.sunken, border: `1px solid ${T.borderSubtle}` }}>
            {['ALL', 'ORGANIZATIONS', 'INTERNAL'].map((t) => <button key={t} onClick={() => setAudience(t)} style={{ font: `600 10.5px/1 ${T.mono}`, letterSpacing: '0.05em', padding: '6px 9px', borderRadius: 5, cursor: 'pointer', border: 'none', background: audience === t ? T.fg : 'transparent', color: audience === t ? '#fff' : T.tertiary }}>{t}</button>)}
          </div>
        </div>
        <Mono>{filtered.length} of {users.length}</Mono>
      </div>

      {/* table */}
      <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: 'visible', background: T.raised }}>
        <div style={{ display: 'grid', gridTemplateColumns: GRID, gap: 12, padding: '11px 18px', borderBottom: `1px solid ${T.borderSubtle}`, background: T.sunken, borderRadius: `${T.rLg} ${T.rLg} 0 0` }}>
          <ColHead>User</ColHead><ColHead>Organization</ColHead><ColHead>Role</ColHead><ColHead>Sign-in method</ColHead><ColHead>Status</ColHead><ColHead>Last active</ColHead><ColHead></ColHead>
        </div>
        {loading ? Array.from({ length: 7 }).map((_, i) => <TableRowSkel key={i} grid={GRID} cells={['user', '72%', 'badge', 100, 'pill', 64, 'menu']} first={i === 0} />) : filtered.map((u, i) => (
          <div key={u.id} onClick={() => setDrawer(u)} style={{ cursor: 'pointer', display: 'grid', gridTemplateColumns: GRID, gap: 12, padding: '13px 18px', alignItems: 'center', borderTop: i ? `1px solid ${T.borderSubtle}` : 'none' }}
            onMouseEnter={(e) => e.currentTarget.style.background = T.sunken} onMouseLeave={(e) => e.currentTarget.style.background = T.raised}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 11, minWidth: 0 }}>
              <Avatar name={u.name} size={30} tone={u.internal ? 'brand' : undefined} />
              <span style={{ minWidth: 0 }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                  <span style={{ font: `600 13.5px/1.2 ${T.sans}`, color: T.fg, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{u.name}</span>
                  {u.internal && <span style={{ font: `600 8px/1 ${T.mono}`, letterSpacing: '0.06em', color: '#7a3ea8', background: '#f3e9fb', padding: '2px 4px', borderRadius: 3 }}>STAFF</span>}
                </span>
                <Mono style={{ fontSize: 10.5, color: T.tertiary, display: 'block', marginTop: 2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{u.email}</Mono>
              </span>
            </span>
            <span style={{ font: `400 12.5px/1.3 ${T.sans}`, color: T.secondary, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{u.org}</span>
            <RoleBadge role={u.role} internal={u.internal} />
            <MethodBadge method={u.method} />
            <span><StatusCell status={u.status} /></span>
            <Mono style={{ fontSize: 10.5, whiteSpace: 'nowrap' }}>{u.last}</Mono>
            <RowMenu user={u} onAct={act} />
          </div>
        ))}
        {!loading && filtered.length === 0 && (
          <div style={{ padding: '44px 18px', textAlign: 'center' }}><Mono style={{ fontSize: 12, color: T.tertiary }}>No users match these filters.</Mono></div>
        )}
      </div>

      {add && <AddUserModal onClose={() => setAdd(false)} onCreate={(u) => setUsers((list) => [u, ...list])} />}
      {drawer && <UserDrawer user={drawer} onClose={() => setDrawer(null)} onAct={act} />}
    </React.Fragment>
  );
}

Object.assign(window, { UsersManagement, USERS_SEED });
