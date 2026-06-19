// OrgAdminScreen.tsx — PLACEHOLDER for the Organization admin page (PRD §2.3, orgproject.jsx →
// OrgAdmin). The dashboard's org switcher + "Manage organization →" route here. This honors the
// routing intent now; the real screen (company profile, knowledge base, connected systems, team,
// usage & billing) is a separate task.
//
// TODO(§2.3 / Task 6 — Org admin owner): replace this body with the real OrgAdmin. The seam is
// stable: App.tsx routes here via showOrg; keep the `onBack` prop to return to the dashboard.
import { T, Wordmark, Icon, CategoryLabel, Btn } from "./onboarding/design";

export function OrgAdminScreen({ onBack }: { onBack: () => void }) {
  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column", background: T.bg, fontFamily: T.sans }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "13px 26px", background: T.raised, borderBottom: `1px solid ${T.borderSubtle}`, flexShrink: 0 }}>
        <button onClick={onBack} style={{ display: "inline-flex", alignItems: "center", gap: 6, background: "none", border: "none", cursor: "pointer", font: `500 13px/1 ${T.sans}`, color: T.secondary, padding: 0 }}>
          <Icon name="arrowLeft" size={15} color={T.secondary} /> Projects
        </button>
        <span style={{ font: `400 13px/1 ${T.mono}`, color: T.tertiary }}>/</span>
        <Wordmark />
      </div>
      <div style={{ flex: 1, display: "grid", placeItems: "center", padding: 32 }}>
        <div style={{ maxWidth: 420, textAlign: "center" }}>
          <CategoryLabel style={{ marginBottom: 10 }}>Organization</CategoryLabel>
          <h1 style={{ font: `700 26px/1.15 ${T.display}`, letterSpacing: "-0.02em", color: T.fg, margin: 0 }}>Organization admin</h1>
          <p style={{ font: `400 14px/1.6 ${T.sans}`, color: T.secondary, margin: "10px 0 22px" }}>
            Company profile, knowledge base, connected systems, team &amp; access, and billing live here. This screen is coming soon (PRD §2.3).
          </p>
          <Btn variant="secondary" size="md" onClick={onBack}>Back to projects</Btn>
        </div>
      </div>
    </div>
  );
}
