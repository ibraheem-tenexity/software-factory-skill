// EnrichFromWeb.tsx — CBT-1/3 wow prefill: "We already know you" company lookup, shared by
// first-time intake (OnboardingScreen fresh mode) and Org admin → Company profile ("Enrich from
// web"). Visual source: design/discovery.jsx EnrichFromWeb/FoundCompanyCard/MiniLog as amended by
// aac5660/913d9c0 (sources only — no confidence pill/tier, ever). Real contract, not the design's
// canned demo data: hits POST /api/research/company (depth=quick, ~1-3s) via api.enrichCompany;
// "Use these details" is the ONLY write (the caller's onAccept does the PATCH /api/org + form
// fill) — nothing here persists anything before that click.
import React, { useState } from "react";
import { api, CompanyProfile } from "../../api";
import { T, Icon, Sparkle, CategoryLabel, Btn, Field, TextInput } from "./design";

// Compact streaming log — same visual contract as the design's MiniLog, standing in for a
// progress indicator during the real lookup. Lines are deliberately GENERIC ("searching…",
// "reading…") rather than the design mockup's specific invented findings ("Epicor referenced in
// 2 job posts") — we have no real incremental signal from a single Exa call, so the log may only
// claim what's actually happening, never a specific finding we haven't received yet.
function MiniLog({ lines, label = "Agent log", speed = 550 }: { lines: string[]; label?: string; speed?: number }) {
  const [n, setN] = useState(0);
  const ref = React.useRef<HTMLDivElement | null>(null);
  React.useEffect(() => {
    const t = setInterval(() => setN((x) => (x >= lines.length ? x : x + 1)), speed);
    return () => clearInterval(t);
  }, [lines.length, speed]);
  React.useEffect(() => { if (ref.current) ref.current.scrollTop = ref.current.scrollHeight; }, [n]);
  const done = n >= lines.length;
  return (
    <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, background: "#1c1c20", overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 7, padding: "8px 12px", borderBottom: "1px solid #2a2a30" }}>
        <span style={{ width: 7, height: 7, borderRadius: "50%", background: done ? T.success : T.brand }} />
        <CategoryLabel style={{ color: "#a8a8b0" }}>{label}</CategoryLabel>
      </div>
      <div ref={ref} style={{ maxHeight: 148, overflow: "auto", padding: "10px 13px", display: "flex", flexDirection: "column", gap: 6 }}>
        {lines.slice(0, n).map((l, i) => (
          <div key={i} style={{ display: "flex", gap: 9, font: `400 12px/1.5 ${T.mono}`, color: i === n - 1 && !done ? "#fff" : "#9a9aa2" }}>
            <span style={{ color: T.success, flexShrink: 0 }}>{i === n - 1 && !done ? "›" : "✓"}</span>
            <span>{l}</span>
          </div>
        ))}
        <div style={{ display: "flex", gap: 9, font: `400 12px/1.5 ${T.mono}`, color: "#6a6a72" }}>
          <span style={{ display: "inline-flex", animation: "sf-spin 0.9s linear infinite" }}><Icon name="refresh" size={12} color="#6a6a72" /></span>
          <span>working…</span>
        </div>
      </div>
    </div>
  );
}

const LOOKUP_LINES = (site: string) => [`Searching the web for ${site}…`, "Reading what we find…", "Compiling the profile…"];

// Rows shown when present in the profile — never a placeholder for an absent field (no fabrication).
const ROWS: { key: keyof CompanyProfile; label: string; format?: (v: any) => string }[] = [
  { key: "name", label: "Company" },
  { key: "industry", label: "Industry" },
  { key: "sub_focus", label: "Sub-focus" },
  { key: "size_hint", label: "Company size" },
  { key: "connected_systems", label: "Systems mentioned", format: (v: string[]) => v.join(", ") },
  { key: "website", label: "Website" },
  { key: "description", label: "About" },
];

function FoundCompanyCard({ profile, onAccept, onRetry }: { profile: CompanyProfile; onAccept: () => void; onRetry: () => void }) {
  const rows = ROWS.map((r) => {
    const raw = profile[r.key];
    const value = Array.isArray(raw) ? (raw.length ? r.format!(raw) : "") : (raw ? String(raw) : "");
    return value ? { ...r, value, src: profile.field_sources?.[r.key as string] } : null;
  }).filter(Boolean) as { key: string; label: string; value: string; src?: string }[];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
        <Sparkle size={12} color={T.brand} /><CategoryLabel tone="brand">What we found on the web</CategoryLabel>
        <span style={{ font: `400 11.5px/1.3 ${T.sans}`, color: T.tertiary }}>· confirm what's right — nothing saves until you do</span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {rows.map((r) => (
          <div key={r.key} className="ai-tint" style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 12px", borderRadius: T.rMd }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <CategoryLabel style={{ display: "block", marginBottom: 3, fontSize: 9.5 }}>{r.label}</CategoryLabel>
              <span style={{ font: `500 13px/1.35 ${T.sans}`, color: T.fg }}>{r.value}</span>
            </div>
            {/* Per-field source (deep mode only, currently never reached by this quick-mode UI) —
                the fields above without one are covered by the overall "Consulted" line below. */}
            {r.src && <span style={{ display: "inline-flex", alignItems: "center", gap: 4, flexShrink: 0, font: `400 10.5px/1 ${T.mono}`, color: T.tertiary }}><Icon name="link" size={10} color={T.tertiary} />{r.src}</span>}
          </div>
        ))}
      </div>
      {profile.sources.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6, font: `400 11px/1.4 ${T.sans}`, color: T.tertiary }}>
          <span>Consulted:</span>
          {profile.sources.map((s) => (
            <span key={s} style={{ display: "inline-flex", alignItems: "center", gap: 4, font: `400 10.5px/1 ${T.mono}` }}><Icon name="link" size={10} color={T.tertiary} />{s}</span>
          ))}
        </div>
      )}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <button onClick={onRetry} style={{ font: `500 12px/1 ${T.sans}`, color: T.tertiary, background: "none", border: "none", cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 5 }}>
          <Icon name="refresh" size={12} color={T.tertiary} /> Not right — look again
        </button>
        <Btn variant="primary" onClick={onAccept}><Icon name="check" size={14} color="#fff" /> Use these details</Btn>
      </div>
    </div>
  );
}

export function EnrichFromWeb({ initialWebsite = "", onAccept, onSkip }:
  { initialWebsite?: string; onAccept: (profile: CompanyProfile) => void; onSkip?: () => void }) {
  const [stage, setStage] = useState<"idle" | "running" | "found" | "error">("idle");
  const [site, setSite] = useState(initialWebsite);
  const [profile, setProfile] = useState<CompanyProfile | null>(null);
  const [errMsg, setErrMsg] = useState("");
  const canLook = site.trim().length > 3;

  const find = async () => {
    setStage("running");
    try {
      const p = await api.enrichCompany({ website: site.trim() });
      setProfile(p);
      setStage("found");
    } catch (e: any) {
      // Honest error, verbatim (CLAUDE.md Principle 4) — e.g. "EXA_API_KEY is not set — required
      // for mode='quick'". Never a guess, never a silent fallback to a fabricated card.
      setErrMsg(String(e?.detail || e?.message || "lookup failed"));
      setStage("error");
    }
  };

  if (stage === "idle") {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ display: "flex", gap: 9, alignItems: "flex-end", flexWrap: "wrap" }}>
          <div style={{ flex: 1, minWidth: 220 }}>
            <Field label="Company website" hint="We'll pull the public profile — you confirm before anything saves.">
              <TextInput value={site} onChange={setSite} placeholder="yourcompany.com" />
            </Field>
          </div>
          <Btn variant="primary" onClick={find} disabled={!canLook} title={canLook ? "Look up this company on the web" : "Enter a website first"}>
            <Icon name="search" size={14} color="#fff" /> Find my company
          </Btn>
        </div>
        {onSkip && <button onClick={onSkip} style={{ alignSelf: "flex-start", font: `500 12px/1 ${T.sans}`, color: T.tertiary, background: "none", border: "none", cursor: "pointer" }}>Skip — I'll type everything myself</button>}
      </div>
    );
  }

  if (stage === "running") return <MiniLog lines={LOOKUP_LINES(site.trim())} label="Looking your company up" />;

  if (stage === "error") {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <div style={{ font: `400 12.5px/1.5 ${T.sans}`, color: T.danger }}>Couldn't look that up: {errMsg}</div>
        <button onClick={() => setStage("idle")} style={{ alignSelf: "flex-start", font: `500 12px/1 ${T.sans}`, color: T.tertiary, background: "none", border: "none", cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 5 }}>
          <Icon name="refresh" size={12} color={T.tertiary} /> Try again
        </button>
      </div>
    );
  }

  return <FoundCompanyCard profile={profile!} onAccept={() => onAccept(profile!)} onRetry={() => setStage("idle")} />;
}
