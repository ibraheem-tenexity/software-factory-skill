// LoginScreen.tsx — Software Factory sign-in. Faithful TSX port of the design's login.jsx
// (two-pane: dark brand panel + auth form; Tenexity system via design.tsx primitives).
//
// FUNCTIONAL sign-in paths: GOOGLE (GIS ID token → POST /api/auth/google) and EMAIL+PASSWORD
// (POST /api/auth/password — both set the same sf_session cookie → the App.tsx Gate re-resolves
// /api/me → dashboard). Org-SSO remains rendered-but-mocked ("coming soon"). The SSO
// mode toggle + show/hide password are pure UI.
import React, { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { T, Icon, CategoryLabel, Field, TextInput, Btn } from "./onboarding/design";

const GIS_SRC = "https://accounts.google.com/gsi/client";
const MOCK_NOTICE = "Email and SSO sign-in are coming soon — continue with Google.";

// Load Google Identity Services once; resolve when the global is ready.
function loadGis(): Promise<void> {
  return new Promise((resolve, reject) => {
    if ((window as any).google?.accounts?.id) return resolve();
    const existing = document.getElementById("gis-script") as HTMLScriptElement | null;
    if (existing) {
      existing.addEventListener("load", () => resolve());
      existing.addEventListener("error", () => reject(new Error("gis load failed")));
      return;
    }
    const s = document.createElement("script");
    s.id = "gis-script";
    s.src = GIS_SRC;
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("gis load failed"));
    document.head.appendChild(s);
  });
}

function GoogleLogo({ size = 17 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
      <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
    </svg>
  );
}
function ProviderButton({ logo, children, onClick }:
  { logo: React.ReactNode; children: React.ReactNode; onClick?: () => void }) {
  return (
    <button onClick={onClick} style={{ width: "100%", height: 46, display: "flex", alignItems: "center", justifyContent: "center", gap: 11, cursor: "pointer",
      border: `1px solid ${T.borderDefault}`, borderRadius: T.rMd, background: T.raised, color: T.fg, font: `500 14px/1 ${T.sans}`, transition: "background .12s, border-color .12s" }}
      onMouseEnter={(e) => { e.currentTarget.style.background = T.sunken; e.currentTarget.style.borderColor = T.borderDefault; }}
      onMouseLeave={(e) => { e.currentTarget.style.background = T.raised; }}>
      {logo}{children}
    </button>
  );
}

const Divider = ({ children }: { children: React.ReactNode }) => (
  <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "4px 0" }}>
    <span style={{ flex: 1, height: 1, background: T.borderSubtle }} />
    <span style={{ font: `500 11px/1 ${T.sans}`, letterSpacing: "0.08em", textTransform: "uppercase", color: T.tertiary }}>{children}</span>
    <span style={{ flex: 1, height: 1, background: T.borderSubtle }} />
  </div>
);

export function LoginScreen({ clientId, onAuthed }: { clientId: string; onAuthed: () => void }) {
  const [mode, setMode] = useState<"default" | "sso">("default");
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [domain, setDomain] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [notice, setNotice] = useState("");   // mocked-path "coming soon" affordance
  const [error, setError] = useState("");     // Google rejected (not authorized / failed)
  const gisRef = useRef<HTMLDivElement | null>(null);

  // The real Google login: validate the GIS credential against the existing exchange.
  const handleCredential = async (resp: { credential?: string }) => {
    setError("");
    try {
      const r = await fetch("/api/auth/google", {
        method: "POST", credentials: "include",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ credential: resp.credential }),
      });
      if (r.ok) onAuthed();
      else setError("This account is not authorized.");
    } catch {
      setError("Sign-in failed. Please try again.");
    }
  };

  // Render the real (invisible) GIS button as an overlay over the faithful design button, so the
  // custom UI is what's seen but the click triggers Google's credential flow.
  useEffect(() => {
    if (mode !== "default" || !clientId) return;
    let cancelled = false;
    loadGis().then(() => {
      if (cancelled) return;
      const g = (window as any).google;
      if (!g?.accounts?.id || !gisRef.current) return;
      g.accounts.id.initialize({ client_id: clientId, callback: handleCredential });
      const w = Math.max(200, Math.min(400, gisRef.current.offsetWidth || 360));
      gisRef.current.innerHTML = "";
      g.accounts.id.renderButton(gisRef.current, { type: "standard", theme: "outline", size: "large", text: "continue_with", width: w });
    }).catch(() => { /* GIS unreachable — custom button shows the loading notice on click */ });
    return () => { cancelled = true; };
  }, [clientId, mode]);

  const [signingIn, setSigningIn] = useState(false);
  // Real email+password sign-in. 200 sets the session cookie ⇒ onAuthed (gate → dashboard);
  // bad creds ⇒ inline error in the interface's voice (no apology).
  const handlePassword = async () => {
    const e = email.trim();
    if (!e || !pw || signingIn) return;
    setError(""); setNotice(""); setSigningIn(true);
    try {
      // 401 {detail:"invalid credentials"} is generic for all failure cases (per contract) →
      // one message, no branching on 403/429.
      const { ok } = await api.passwordLogin({ email: e, password: pw });
      if (ok) onAuthed();
      else setError("Wrong email or password.");
    } catch {
      setError("Sign-in failed. Please try again.");
    }
    setSigningIn(false);
  };

  const mock = () => { setError(""); setNotice(MOCK_NOTICE); };

  return (
    <div style={{ height: "100vh", display: "flex", background: T.bg, fontFamily: T.sans }}>
      {/* brand panel */}
      <div style={{ flex: "0 0 46%", position: "relative", overflow: "hidden", background: "#0f1320", display: "flex", flexDirection: "column", justifyContent: "space-between", padding: "42px 44px" }}>
        {/* decorative process graph */}
        <svg viewBox="0 0 520 820" preserveAspectRatio="xMidYMid slice" style={{ position: "absolute", inset: 0, width: "100%", height: "100%", opacity: 0.5 }} aria-hidden="true">
          <defs><radialGradient id="lgGlow" cx="30%" cy="40%" r="80%"><stop offset="0%" stopColor="#1A7BFF" stopOpacity="0.32" /><stop offset="100%" stopColor="#1A7BFF" stopOpacity="0" /></radialGradient></defs>
          <rect width="520" height="820" fill="url(#lgGlow)" />
          {([[90, 140, "#2f6bd6"], [210, 210, "#1A7BFF"], [150, 330, "#2f6bd6"], [300, 300, "#1A7BFF"], [260, 440, "#2f6bd6"], [400, 420, "#1A7BFF"], [210, 560, "#2f6bd6"], [360, 600, "#1A7BFF"], [170, 700, "#2f6bd6"]] as [number, number, string][]).map((n, i, a) => {
            const next = a[i + 1];
            return (<g key={i}>{next && <line x1={n[0]} y1={n[1]} x2={next[0]} y2={next[1]} stroke="#2a3550" strokeWidth="1.5" />}<circle cx={n[0]} cy={n[1]} r={i % 3 === 0 ? 6 : 4} fill={n[2]} opacity="0.9" /></g>);
          })}
        </svg>
        <div style={{ position: "relative", display: "flex", alignItems: "center", gap: 9 }}>
          <span style={{ width: 26, height: 26, borderRadius: 7, background: T.brand, display: "grid", placeItems: "center" }}><Icon name="layers" size={15} color="#fff" strokeWidth={2.2} /></span>
          <span style={{ font: `700 19px/1 ${T.display}`, letterSpacing: "-0.015em", color: "#fff" }}>Software Factory</span>
        </div>
        <div style={{ position: "relative" }}>
          <h2 style={{ font: `400 30px/1.25 ${T.display}`, letterSpacing: "-0.01em", color: "#fff", margin: 0, maxWidth: 420 }}>
            Describe your business. Watch agents research, design, build, and ship the software.
          </h2>
          <p style={{ font: `400 14px/1.6 ${T.sans}`, color: "#9aa6c0", margin: "18px 0 0", maxWidth: 380 }}>
            Purpose-built for industrial &amp; IT distribution — quoting, ordering, AP/AR, inventory, and the workflows in between.
          </p>
        </div>
        <div style={{ position: "relative", display: "flex", alignItems: "center", gap: 8, font: `400 12px/1 ${T.sans}`, color: "#6b7693" }}>
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: T.success }} />SOC 2 Type II · data stays in your tenant
        </div>
      </div>

      {/* auth form */}
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: "32px" }}>
        <div style={{ width: "100%", maxWidth: 380 }}>
          <CategoryLabel style={{ marginBottom: 12 }}>{mode === "sso" ? "Single sign-on" : "Welcome back"}</CategoryLabel>
          <h1 style={{ font: `700 30px/1.12 ${T.display}`, letterSpacing: "-0.02em", color: T.fg, margin: 0 }}>
            {mode === "sso" ? "Sign in with your organization" : "Sign in to Software Factory"}
          </h1>
          <p style={{ font: `400 14px/1.5 ${T.sans}`, color: T.secondary, margin: "8px 0 26px" }}>
            {mode === "sso" ? "Enter your work domain and we’ll route you to your identity provider." : "Continue with your work account to reach your projects."}
          </p>

          {mode === "default" ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {/* Google = real. Custom button is the visible design; the GIS button is an
                    invisible overlay that captures the click and runs the credential flow. */}
                <div style={{ position: "relative" }}>
                  <ProviderButton logo={<GoogleLogo />} onClick={() => setNotice("Loading Google sign-in…")}>Continue with Google</ProviderButton>
                  <div ref={gisRef} aria-label="Google sign-in" style={{ position: "absolute", inset: 0, opacity: 0, overflow: "hidden", colorScheme: "light" }} />
                </div>
              </div>

              <Divider>or</Divider>

              <Field label="Work email"><TextInput type="email" value={email} onChange={setEmail} placeholder="you@company.com" style={{ height: 44 }} onKeyDown={(e) => { if (e.key === "Enter") handlePassword(); }} /></Field>
              <Field label="Password">
                <div style={{ position: "relative" }}>
                  <TextInput type={showPw ? "text" : "password"} value={pw} onChange={setPw} placeholder="••••••••" style={{ height: 44, paddingRight: 56 }} onKeyDown={(e) => { if (e.key === "Enter") handlePassword(); }} />
                  <button onClick={() => setShowPw((v) => !v)} style={{ position: "absolute", right: 10, top: 0, bottom: 0, font: `500 12px/1 ${T.sans}`, color: T.brandDeep, background: "none", border: "none", cursor: "pointer" }}>{showPw ? "Hide" : "Show"}</button>
                </div>
              </Field>
              <div style={{ display: "flex", justifyContent: "flex-end", marginTop: -4 }}>
                <button onClick={mock} style={{ font: `500 12.5px/1 ${T.sans}`, color: T.brandDeep, background: "none", border: "none", cursor: "pointer" }}>Forgot password?</button>
              </div>
              <Btn variant="primary" size="lg" full onClick={handlePassword} disabled={signingIn || !email.trim() || !pw} style={{ height: 46, marginTop: 2 }}>{signingIn ? "Signing in…" : "Sign in"} <Icon name="arrowRight" size={15} color="#fff" /></Btn>

              <button onClick={() => { setNotice(""); setError(""); setMode("sso"); }} style={{ width: "100%", height: 44, display: "flex", alignItems: "center", justifyContent: "center", gap: 9, cursor: "pointer",
                border: `1px solid ${T.borderDefault}`, borderRadius: T.rMd, background: "transparent", color: T.fg, font: `500 13.5px/1 ${T.sans}` }}>
                <Icon name="building" size={15} color={T.secondary} /> Use organization SSO
              </button>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <Field label="Organization domain" hint="e.g. acme-industrial.com — we support SAML & OIDC.">
                <TextInput value={domain} onChange={setDomain} placeholder="yourcompany.com" mono style={{ height: 44 }} />
              </Field>
              <Btn variant="primary" size="lg" full onClick={mock} style={{ height: 46 }}>Continue with SSO <Icon name="arrowRight" size={15} color="#fff" /></Btn>
              <button onClick={() => { setNotice(""); setError(""); setMode("default"); }} style={{ width: "100%", height: 44, display: "flex", alignItems: "center", justifyContent: "center", gap: 8, cursor: "pointer", border: "none", background: "transparent", color: T.secondary, font: `500 13.5px/1 ${T.sans}` }}>
                <Icon name="arrowLeft" size={15} color={T.secondary} /> Back to all sign-in options
              </button>
            </div>
          )}

          {error && (
            <p style={{ font: `500 12.5px/1.5 ${T.sans}`, color: T.danger, margin: "14px 0 0", textAlign: "center" }}>{error}</p>
          )}
          {notice && !error && (
            <p style={{ font: `500 12.5px/1.5 ${T.sans}`, color: T.secondary, margin: "14px 0 0", textAlign: "center" }}>{notice}</p>
          )}

          <p style={{ font: `400 12.5px/1.5 ${T.sans}`, color: T.tertiary, margin: "26px 0 0", textAlign: "center" }}>
            New to Software Factory? <button onClick={mock} style={{ font: `600 12.5px/1 ${T.sans}`, color: T.brandDeep, background: "none", border: "none", cursor: "pointer", padding: 0 }}>Request access</button>
          </p>
        </div>
      </div>
    </div>
  );
}
