// LoginScreen.tsx — Software Factory sign-in. Faithful TSX port of the design's login.jsx
// (two-pane: dark brand panel + auth form; Tenexity system via design.tsx primitives).
//
// FUNCTIONAL sign-in paths: GOOGLE (GIS ID token → POST /api/auth/google) and EMAIL+PASSWORD
// (POST /api/auth/password — both set the same sf_session cookie → the App.tsx Gate re-resolves
// /api/me → dashboard). SOF-15 de-risk: ONLY real affordances render — Google's own SDK button
// (never a styled replica), no mock SSO mode, no fake trust badges. A login page on a shared
// *.up.railway.app host must never imitate a provider or offer dead credential affordances.
import React, { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { T, Icon, CategoryLabel, Field, TextInput, Btn } from "./onboarding/design";

const GIS_SRC = "https://accounts.google.com/gsi/client";

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

const Divider = ({ children }: { children: React.ReactNode }) => (
  <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "4px 0" }}>
    <span style={{ flex: 1, height: 1, background: T.borderSubtle }} />
    <span style={{ font: `500 11px/1 ${T.sans}`, letterSpacing: "0.08em", textTransform: "uppercase", color: T.tertiary }}>{children}</span>
    <span style={{ flex: 1, height: 1, background: T.borderSubtle }} />
  </div>
);

export function LoginScreen({ clientId, onAuthed }: { clientId: string; onAuthed: () => void }) {
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [notice, setNotice] = useState("");
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

  // Render Google's own GIS button, visible (SOF-15: the official SDK-rendered button is the
  // sanctioned pattern for third-party sites; a hand-styled replica is a phishing signal).
  useEffect(() => {
    if (!clientId) return;
    let cancelled = false;
    loadGis().then(() => {
      if (cancelled) return;
      const g = (window as any).google;
      if (!g?.accounts?.id || !gisRef.current) return;
      g.accounts.id.initialize({ client_id: clientId, callback: handleCredential });
      const w = Math.max(200, Math.min(400, gisRef.current.offsetWidth || 360));
      gisRef.current.innerHTML = "";
      g.accounts.id.renderButton(gisRef.current, { type: "standard", theme: "outline", size: "large", text: "continue_with", width: w });
    }).catch(() => { /* GIS unreachable — email+password remains available below */ });
    return () => { cancelled = true; };
  }, [clientId]);

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
          A Tenexity product · <a href="https://tenexity.ai" style={{ color: "#9aa6c0", textDecoration: "none" }}>tenexity.ai</a>
        </div>
      </div>

      {/* auth form */}
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: "32px" }}>
        <div style={{ width: "100%", maxWidth: 380 }}>
          <CategoryLabel style={{ marginBottom: 12 }}>Welcome back</CategoryLabel>
          <h1 style={{ font: `700 30px/1.12 ${T.display}`, letterSpacing: "-0.02em", color: T.fg, margin: 0 }}>
            Sign in to Software Factory
          </h1>
          <p style={{ font: `400 14px/1.5 ${T.sans}`, color: T.secondary, margin: "8px 0 26px" }}>
            Continue with your work account to reach your projects.
          </p>

          {(
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {/* Google sign-in renders GOOGLE'S OWN button (GIS renderButton), visible — never a
                    hand-styled replica. SOF-15: a recreated provider button + logo on a shared host
                    is a textbook Safe-Browsing phishing signal; the official SDK-rendered button is
                    the sanctioned pattern for third-party sites. */}
                <div ref={gisRef} aria-label="Google sign-in" style={{ display: "flex", justifyContent: "center", minHeight: 44, colorScheme: "light" }} />
              </div>

              <Divider>or</Divider>

              <Field label="Work email"><TextInput type="email" value={email} onChange={setEmail} placeholder="you@company.com" style={{ height: 44 }} onKeyDown={(e) => { if (e.key === "Enter") handlePassword(); }} /></Field>
              <Field label="Password">
                <div style={{ position: "relative" }}>
                  <TextInput type={showPw ? "text" : "password"} value={pw} onChange={setPw} placeholder="••••••••" style={{ height: 44, paddingRight: 56 }} onKeyDown={(e) => { if (e.key === "Enter") handlePassword(); }} />
                  <button onClick={() => setShowPw((v) => !v)} style={{ position: "absolute", right: 10, top: 0, bottom: 0, font: `500 12px/1 ${T.sans}`, color: T.brandDeep, background: "none", border: "none", cursor: "pointer" }}>{showPw ? "Hide" : "Show"}</button>
                </div>
              </Field>
              <Btn variant="primary" size="lg" full onClick={handlePassword} disabled={signingIn || !email.trim() || !pw} style={{ height: 46, marginTop: 2 }}>{signingIn ? "Signing in…" : "Sign in"} <Icon name="arrowRight" size={15} color="#fff" /></Btn>
            </div>
          )}

          {error && (
            <p style={{ font: `500 12.5px/1.5 ${T.sans}`, color: T.danger, margin: "14px 0 0", textAlign: "center" }}>{error}</p>
          )}
          {notice && !error && (
            <p style={{ font: `500 12.5px/1.5 ${T.sans}`, color: T.secondary, margin: "14px 0 0", textAlign: "center" }}>{notice}</p>
          )}

          <p style={{ font: `400 12.5px/1.5 ${T.sans}`, color: T.tertiary, margin: "26px 0 0", textAlign: "center" }}>
            New to Software Factory? <a href="mailto:hello@tenexity.ai?subject=Software%20Factory%20access" style={{ font: `600 12.5px/1 ${T.sans}`, color: T.brandDeep, textDecoration: "none" }}>Request access</a>
          </p>
        </div>
      </div>
    </div>
  );
}
