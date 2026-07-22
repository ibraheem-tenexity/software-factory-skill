// login.jsx — Software Factory sign-in. Google, Microsoft, email/password,
// and org SSO. AppRoot gates the product: login → dashboard/factory.

function GoogleLogo({ size = 17 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
      <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
    </svg>
  );
}
function MicrosoftLogo({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 21 21" aria-hidden="true">
      <rect x="1" y="1" width="9" height="9" fill="#F25022" />
      <rect x="11" y="1" width="9" height="9" fill="#7FBA00" />
      <rect x="1" y="11" width="9" height="9" fill="#00A4EF" />
      <rect x="11" y="11" width="9" height="9" fill="#FFB900" />
    </svg>
  );
}

function ProviderButton({ logo, children, onClick }) {
  return (
    <button onClick={onClick} style={{ width: '100%', height: 46, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 11, cursor: 'pointer',
      border: `1px solid ${T.borderDefault}`, borderRadius: T.rMd, background: T.raised, color: T.fg, font: `500 14px/1 ${T.sans}`, transition: 'background .12s, border-color .12s' }}
      onMouseEnter={(e) => { e.currentTarget.style.background = T.sunken; e.currentTarget.style.borderColor = T.borderDefault; }}
      onMouseLeave={(e) => { e.currentTarget.style.background = T.raised; }}>
      {logo}{children}
    </button>
  );
}

function Login({ onAuthed }) {
  const [mode, setMode] = React.useState('default'); // 'default' | 'sso'
  const [email, setEmail] = React.useState('');
  const [pw, setPw] = React.useState('');
  const [domain, setDomain] = React.useState('');
  const [showPw, setShowPw] = React.useState(false);

  const Divider = ({ children }) => (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, margin: '4px 0' }}>
      <span style={{ flex: 1, height: 1, background: T.borderSubtle }} />
      <span style={{ font: `500 11px/1 ${T.sans}`, letterSpacing: '0.08em', textTransform: 'uppercase', color: T.tertiary }}>{children}</span>
      <span style={{ flex: 1, height: 1, background: T.borderSubtle }} />
    </div>
  );

  return (
    <div style={{ height: '100%', display: 'flex', background: T.bg, fontFamily: T.sans }}>
      {/* brand panel */}
      <div style={{ flex: '0 0 46%', position: 'relative', overflow: 'hidden', background: '#0f1320', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', padding: '42px 44px' }}>
        {/* decorative process graph */}
        <svg viewBox="0 0 520 820" preserveAspectRatio="xMidYMid slice" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', opacity: 0.5 }} aria-hidden="true">
          <defs><radialGradient id="lgGlow" cx="30%" cy="40%" r="80%"><stop offset="0%" stopColor="#1A7BFF" stopOpacity="0.32" /><stop offset="100%" stopColor="#1A7BFF" stopOpacity="0" /></radialGradient></defs>
          <rect width="520" height="820" fill="url(#lgGlow)" />
          {[[90,140,'#2f6bd6'],[210,210,'#1A7BFF'],[150,330,'#2f6bd6'],[300,300,'#1A7BFF'],[260,440,'#2f6bd6'],[400,420,'#1A7BFF'],[210,560,'#2f6bd6'],[360,600,'#1A7BFF'],[170,700,'#2f6bd6']].map((n,i,a)=>{
            const next=a[i+1]; return (<g key={i}>{next&&<line x1={n[0]} y1={n[1]} x2={next[0]} y2={next[1]} stroke="#2a3550" strokeWidth="1.5" />}<circle cx={n[0]} cy={n[1]} r={i%3===0?6:4} fill={n[2]} opacity="0.9" /></g>);
          })}
        </svg>
        <div style={{ position: 'relative', display: 'flex', alignItems: 'center', gap: 9 }}>
          <span style={{ width: 26, height: 26, borderRadius: 7, background: T.brand, display: 'grid', placeItems: 'center' }}><Icon name="layers" size={15} color="#fff" strokeWidth={2.2} /></span>
          <span style={{ font: `700 19px/1 ${T.display}`, letterSpacing: '-0.015em', color: '#fff' }}>Software Factory</span>
        </div>
        <div style={{ position: 'relative' }}>
          <h2 style={{ font: `400 30px/1.25 ${T.display}`, letterSpacing: '-0.01em', color: '#fff', margin: 0, maxWidth: 420 }}>
            Describe your business. Watch agents research, design, build, and ship the software.
          </h2>
          <p style={{ font: `400 14px/1.6 ${T.sans}`, color: '#9aa6c0', margin: '18px 0 0', maxWidth: 380 }}>
            Purpose-built for industrial &amp; IT distribution — quoting, ordering, AP/AR, inventory, and the workflows in between.
          </p>
        </div>
        <div style={{ position: 'relative', display: 'flex', alignItems: 'center', gap: 8, font: `400 12px/1 ${T.sans}`, color: '#6b7693' }}>
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: T.success }} />SOC 2 Type II · data stays in your tenant
        </div>
      </div>

      {/* auth form */}
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '32px' }}>
        <div style={{ width: '100%', maxWidth: 380 }}>
          <CategoryLabel style={{ marginBottom: 12 }}>{mode === 'sso' ? 'Single sign-on' : 'Welcome back'}</CategoryLabel>
          <h1 style={{ font: `700 30px/1.12 ${T.display}`, letterSpacing: '-0.02em', color: T.fg, margin: 0 }}>
            {mode === 'sso' ? 'Sign in with your organization' : 'Sign in to Software Factory'}
          </h1>
          <p style={{ font: `400 14px/1.5 ${T.sans}`, color: T.secondary, margin: '8px 0 26px' }}>
            {mode === 'sso' ? 'Enter your work domain and we’ll route you to your identity provider.' : 'Continue with your work account to reach your projects.'}
          </p>

          {mode === 'default' ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <ProviderButton logo={<GoogleLogo />} onClick={onAuthed}>Continue with Google</ProviderButton>
                <ProviderButton logo={<MicrosoftLogo />} onClick={onAuthed}>Continue with Microsoft</ProviderButton>
              </div>

              <Divider>or</Divider>

              <Field label="Work email"><TextInput type="email" value={email} onChange={setEmail} placeholder="you@company.com" style={{ height: 44 }} /></Field>
              <Field label={<span style={{ display: 'flex', justifyContent: 'space-between', width: '100%' }}><span>Password</span></span>}>
                <div style={{ position: 'relative' }}>
                  <TextInput type={showPw ? 'text' : 'password'} value={pw} onChange={setPw} placeholder="••••••••" style={{ height: 44, paddingRight: 56 }} />
                  <button onClick={() => setShowPw((v) => !v)} style={{ position: 'absolute', right: 10, top: 0, bottom: 0, font: `500 12px/1 ${T.sans}`, color: T.brandDeep, background: 'none', border: 'none', cursor: 'pointer' }}>{showPw ? 'Hide' : 'Show'}</button>
                </div>
              </Field>
              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: -4 }}>
                <button style={{ font: `500 12.5px/1 ${T.sans}`, color: T.brandDeep, background: 'none', border: 'none', cursor: 'pointer' }}>Forgot password?</button>
              </div>
              <Btn variant="primary" size="lg" full onClick={onAuthed} style={{ height: 46, marginTop: 2 }}>Sign in <Icon name="arrowRight" size={15} color="#fff" /></Btn>

              <button onClick={() => setMode('sso')} style={{ width: '100%', height: 44, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 9, cursor: 'pointer',
                border: `1px solid ${T.borderDefault}`, borderRadius: T.rMd, background: 'transparent', color: T.fg, font: `500 13.5px/1 ${T.sans}` }}>
                <Icon name="building" size={15} color={T.secondary} /> Use organization SSO
              </button>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <Field label="Organization domain" hint="e.g. acme-industrial.com — we support SAML & OIDC.">
                <TextInput value={domain} onChange={setDomain} placeholder="yourcompany.com" mono style={{ height: 44 }} />
              </Field>
              <Btn variant="primary" size="lg" full onClick={onAuthed} style={{ height: 46 }}>Continue with SSO <Icon name="arrowRight" size={15} color="#fff" /></Btn>
              <button onClick={() => setMode('default')} style={{ width: '100%', height: 44, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, cursor: 'pointer', border: 'none', background: 'transparent', color: T.secondary, font: `500 13.5px/1 ${T.sans}` }}>
                <Icon name="arrowLeft" size={15} color={T.secondary} /> Back to all sign-in options
              </button>
            </div>
          )}

          <p style={{ font: `400 12.5px/1.5 ${T.sans}`, color: T.tertiary, margin: '26px 0 0', textAlign: 'center' }}>
            New to Software Factory? <button style={{ font: `600 12.5px/1 ${T.sans}`, color: T.brandDeep, background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>Request access</button>
          </p>
        </div>
      </div>
    </div>
  );
}

// Top-level product gate: login → dashboard/factory.
function AppRoot() {
  const [authed, setAuthed] = React.useState(false);
  if (!authed) return <Login onAuthed={() => setAuthed(true)} />;
  return <FactoryApp />;
}

Object.assign(window, { Login, AppRoot, GoogleLogo, MicrosoftLogo });
