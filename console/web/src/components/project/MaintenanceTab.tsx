// MaintenanceTab.tsx — Project view §2.5 Maintenance (SOF-94): a placeholder surface shown on
// COMPLETED projects. It explains what the maintenance agent will do once it ships (log review,
// user feedback/ticket ingestion, security patches), states "coming soon", and offers a persisted
// no-op opt-in toggle. Nothing here drives real behavior yet — the agent doesn't exist. Matches the
// Overview board aesthetic (dotted canvas + T-token cards).
import { useState } from "react";
import { api } from "../../api";
import { T, Icon, StatusPill } from "../onboarding/design";

const DUTIES: { icon: string; title: string; detail: string }[] = [
  {
    icon: "search",
    title: "Log review",
    detail: "Watches the live app's logs and error streams, surfacing crashes, regressions, and anomalies before they reach your users.",
  },
  {
    icon: "send",
    title: "Feedback & ticket ingestion",
    detail: "Pulls in user feedback and support tickets, triages them, and turns actionable reports into work the factory can pick up.",
  },
  {
    icon: "lock",
    title: "Security patches",
    detail: "Tracks dependency and platform advisories, then prepares and verifies patches so the deployed app stays secure over time.",
  },
];

// A no-op opt-in switch. Persists the preference on project state (SOF-94); it does not activate
// anything — there is no maintenance agent to activate yet.
function Toggle({ on, busy, onChange }: { on: boolean; busy: boolean; onChange: (next: boolean) => void }) {
  return (
    <button
      role="switch"
      aria-checked={on}
      disabled={busy}
      onClick={() => onChange(!on)}
      title={on ? "Turn off maintenance monitoring" : "Turn on maintenance monitoring"}
      style={{
        position: "relative", width: 40, height: 23, flexShrink: 0, borderRadius: 999,
        border: `1px solid ${on ? T.brand : T.borderDefault}`, background: on ? T.brand : T.sunken,
        cursor: busy ? "default" : "pointer", opacity: busy ? 0.6 : 1, padding: 0, transition: "background .15s, border-color .15s",
      }}
    >
      <span style={{
        position: "absolute", top: 2, left: on ? 19 : 2, width: 17, height: 17, borderRadius: "50%",
        background: T.raised, boxShadow: T.shadowXs, transition: "left .15s",
      }} />
    </button>
  );
}

export function MaintenanceTab({ projectId, enabled, onToggle }:
  { projectId: string; enabled: boolean; onToggle: (next: boolean) => void }) {
  const [busy, setBusy] = useState(false);

  const change = async (next: boolean) => {
    setBusy(true);
    onToggle(next);           // optimistic — parent owns the status object
    try {
      await api.setMaintenance(projectId, next);
    } catch {
      onToggle(!next);        // revert on failure
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ flex: 1, overflow: "auto", backgroundImage: `radial-gradient(circle, ${T.borderSubtle} 1px, transparent 1px)`, backgroundSize: "22px 22px" }}>
      <div style={{ padding: "22px 24px 36px" }}>
        <div style={{ maxWidth: 1080, margin: "0 auto", display: "flex", flexDirection: "column", gap: 16 }}>

          {/* hero — what maintenance is + coming-soon status + the opt-in toggle */}
          <section style={{ display: "flex", alignItems: "flex-start", gap: 16, padding: "20px 22px", borderRadius: T.rXl, border: `1px solid ${T.brand}44`, background: T.raised, boxShadow: T.shadowXs }}>
            <span style={{ width: 38, height: 38, flexShrink: 0, borderRadius: 10, display: "grid", placeItems: "center", background: T.brandSoft, border: `1px solid ${T.brand}44` }}>
              <Icon name="bot" size={19} color={T.brand} />
            </span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ font: `700 16px/1.2 ${T.display}`, letterSpacing: "-0.01em", color: T.fg }}>Maintenance agent</span>
                <StatusPill tone="neutral">Coming soon</StatusPill>
              </div>
              <p style={{ margin: "6px 0 0", font: `400 13px/1.55 ${T.sans}`, color: T.secondary, maxWidth: 640 }}>
                Once your project ships, the maintenance agent keeps it healthy — reviewing logs, taking in
                user feedback, and applying security patches without a full rebuild. It isn't available yet;
                turn on monitoring below to opt in, and it'll begin when the agent goes live.
              </p>
            </div>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 6, flexShrink: 0 }}>
              <Toggle on={enabled} busy={busy} onChange={change} />
              <span style={{ font: `500 11px/1 ${T.mono}`, color: enabled ? T.brand : T.tertiary }}>
                {enabled ? "Monitoring on" : "Monitoring off"}
              </span>
            </div>
          </section>

          {/* the three duties, as cards */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 14, alignItems: "start" }}>
            {DUTIES.map((d) => (
              <section key={d.title} style={{ display: "flex", flexDirection: "column", gap: 10, padding: "16px 18px", borderRadius: T.rXl, border: `1px solid ${T.borderSubtle}`, background: T.raised, boxShadow: T.shadowXs }}>
                <span style={{ width: 30, height: 30, borderRadius: 8, display: "grid", placeItems: "center", background: T.sunken, border: `1px solid ${T.borderSubtle}` }}>
                  <Icon name={d.icon} size={15} color={T.secondary} />
                </span>
                <span style={{ font: `600 13.5px/1.3 ${T.sans}`, color: T.fg }}>{d.title}</span>
                <span style={{ font: `400 12.5px/1.5 ${T.sans}`, color: T.tertiary }}>{d.detail}</span>
              </section>
            ))}
          </div>

          <p style={{ margin: "2px 0 0", font: `400 11.5px/1.5 ${T.sans}`, color: T.tertiary, textAlign: "center" }}>
            These capabilities are on the roadmap. Your monitoring preference is saved now so it's ready the moment the agent ships.
          </p>
        </div>
      </div>
    </div>
  );
}
