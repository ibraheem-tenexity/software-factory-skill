// DesignReview.tsx — the stage-triggered customer design-review ACTION (SOF-252), rendered ONLY
// inside Factory Activity (design: buildprogress.jsx DesignReviewBar). This is the in-Activity
// process action, NOT the Wave-2 permanent design-review panel.
//
// Every value is REAL: the screens are the project's stored `mockup` artifacts (count varies per
// project — never hardcoded), the header model is the recorded producing model, and the theme
// clause only appears when the backend has a real org-theme record (brand & theme is Wave-2 /
// not-shipping, so today `theme` is null and the clause is honestly omitted). The action self-gates
// on `available` (design node complete + ≥1 mockup) and renders null otherwise, so nothing shows
// before the design node completes.
//
// Three customer actions, each hitting the same functions the backend/Concierge use:
//   · Approve & continue → api.approveDesign → records approval + lets the pipeline proceed via the
//     existing lifecycle boundary; the REAL continuation outcome (or refusal) is shown, and the
//     action flips to the factual "Design locked" result with Re-open review.
//   · Iterate           → api.reviseDesign(selected screens, instructions) → the SAME function the
//     Concierge `request_design_revision` tool calls; records a new version + re-runs the design
//     workflow, surfacing the real regeneration outcome (a refusal stays visible, honestly).
//   · Re-open review    → api.reopenDesign → returns the latest version to actionable review.
//
// A clicked screen opens the EXACT stored artifact through the board's shared open path
// (onOpenArtifact — the same callback the Activity rows use), never a forked viewer.
import { useEffect, useState } from "react";
import { T, Icon, Sparkle, Btn } from "../onboarding/design";
import { api, DesignReview as DesignReviewData, DesignScreen } from "../../api";
import { ArtifactRef } from "./Artifacts";

// A small live preview of the stored mockup HTML — rendered from the real artifact bytes in a
// sandboxed, script-disabled iframe (same sandbox posture the design specifies for mockups). If the
// artifact can't be fetched the tile still shows its identity; it never fakes a frame.
function ScreenThumb({ projectId, screen }: { projectId: string; screen: DesignScreen }) {
  const isHtml = /\.html?$/i.test(screen.path || "");
  if (isHtml && screen.path) {
    const src = `/api/projects/${projectId}/artifact?path=${encodeURIComponent(screen.path)}&raw=1`;
    return (
      <div style={{ height: 96, overflow: "hidden", background: T.bg, position: "relative", pointerEvents: "none" }}>
        <iframe title={screen.title} src={src} sandbox="" scrolling="no"
          style={{ width: 320, height: 320, border: 0, transform: "scale(0.5)", transformOrigin: "top left" }} />
      </div>
    );
  }
  return (
    <div style={{ height: 96, background: `repeating-linear-gradient(135deg, ${T.sunken}, ${T.sunken} 8px, ${T.bg} 8px, ${T.bg} 16px)`,
      display: "grid", placeItems: "center" }}>
      <span style={{ font: `400 10px/1 ${T.mono}`, color: T.tertiary }}>frame · v{screen.version ?? 1}</span>
    </div>
  );
}

export function DesignReview({ projectId, onOpenArtifact, onContinued }: {
  projectId: string;
  onOpenArtifact: (a: ArtifactRef) => void;
  onContinued?: () => void;
}) {
  const [data, setData] = useState<DesignReviewData | null>(null);
  const [busy, setBusy] = useState<null | "approve" | "reopen" | "revise">(null);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [instructions, setInstructions] = useState("");
  const [notice, setNotice] = useState<string | null>(null); // honest continuation/revision result

  useEffect(() => {
    let live = true;
    const tick = () => api.designReview(projectId)
      .then((d) => { if (live) setData(d); })
      .catch(() => { /* degrade to hidden; a transient poll error must not surface a fake action */ });
    tick();
    const h = setInterval(tick, 5000);
    return () => { live = false; clearInterval(h); };
  }, [projectId]);

  // Self-gating: nothing renders before the design node completes with real screen artifacts.
  if (!data || !data.available) return null;

  const openScreen = (s: DesignScreen) => onOpenArtifact({
    label: s.title, path: s.path, url: null,
    id: s.artifact_id ?? undefined, kind: "fig", agent: s.agent ?? undefined,
  });

  const affectedIds = data.screens.filter((s) => selected[s.id]).map((s) => s.id);

  const approve = async () => {
    setBusy("approve"); setNotice(null);
    try {
      const r = await api.approveDesign(projectId);
      setData(r);
      if (r.continuation) {
        setNotice(r.continuation.continued
          ? `Continuing: ${r.continuation.detail}`
          : `Approval recorded, but the pipeline did not continue: ${r.continuation.detail}`);
      }
      if (r.continuation?.continued && onContinued) onContinued();
    } catch (e: any) {
      setNotice(`Approve failed: ${e?.detail || e?.message || "unknown error"}`);
    } finally { setBusy(null); }
  };

  const reopen = async () => {
    setBusy("reopen"); setNotice(null);
    try { setData(await api.reopenDesign(projectId)); }
    catch (e: any) { setNotice(`Re-open failed: ${e?.detail || e?.message || "unknown error"}`); }
    finally { setBusy(null); }
  };

  const revise = async () => {
    if (!instructions.trim()) return;
    setBusy("revise"); setNotice(null);
    try {
      const r = await api.reviseDesign(projectId, affectedIds, instructions.trim());
      setData(r);
      if (r.revision) {
        setNotice(r.revision.regenerating
          ? `Revision v${r.revision.version} requested for ${r.revision.affected.length} screen(s): ${r.revision.detail}`
          : `Revision recorded, but regeneration did not start: ${r.revision.detail}`);
      }
      setInstructions(""); setSelected({});
    } catch (e: any) {
      setNotice(`Revision failed: ${e?.detail || e?.message || "unknown error"}`);
    } finally { setBusy(null); }
  };

  const n = data.screen_count;
  const header = `design · ${data.model || "unknown model"}${data.theme ? ` · on ${data.theme}` : ""}`;

  // ── Locked result: the factual "Design locked" state with Re-open review ──────────────────────
  if (data.status === "locked") {
    return (
      <div style={{ border: `1px solid ${T.success}`, background: T.successSoft + "66", borderRadius: T.rXl,
        padding: "13px 15px", display: "flex", flexDirection: "column", gap: 8, animation: "sfRise .3s ease both" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <Icon name="check" size={15} color={T.success} />
          <span style={{ flex: 1, font: `500 12.5px/1.4 ${T.sans}`, color: T.fg, minWidth: 200 }}>
            Design locked — tickets and the build proceed from these <b>{n}</b> screen{n === 1 ? "" : "s"} (v{data.approved_version ?? data.version}).
          </span>
          <button onClick={reopen} disabled={busy !== null}
            style={{ font: `500 11.5px/1 ${T.sans}`, color: T.tertiary, background: "none", border: "none",
              cursor: busy ? "default" : "pointer" }}>
            {busy === "reopen" ? "Re-opening…" : "Re-open review"}
          </button>
        </div>
        {notice && <p style={{ margin: 0, font: `400 11.5px/1.5 ${T.sans}`, color: T.secondary }}>{notice}</p>}
      </div>
    );
  }

  // ── Actionable review ─────────────────────────────────────────────────────────────────────────
  return (
    <div style={{ border: `1px solid ${T.brand}`, background: T.brandSoft + "55", borderRadius: T.rXl,
      padding: "13px 15px", display: "flex", flexDirection: "column", gap: 12, animation: "sfRise .3s ease both" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 9, flexWrap: "wrap" }}>
          <span style={{ width: 12, height: 12, background: T.brand, transform: "rotate(45deg)", borderRadius: 2, flexShrink: 0 }} />
          <span style={{ font: `600 13px/1.3 ${T.sans}`, color: T.fg }}>
            Design review — {n} screen{n === 1 ? "" : "s"} generated{data.version > 1 ? ` · v${data.version}` : ""}
          </span>
          <span style={{ font: `500 9.5px/1 ${T.mono}`, letterSpacing: "0.06em", color: T.brandDeep, background: T.brandSoft,
            border: `1px solid ${T.brand}44`, padding: "4px 6px", borderRadius: 4 }}>STAGE-TRIGGERED</span>
        </div>
        <span style={{ font: `500 11px/1 ${T.mono}`, color: T.brandDeep }}>{header}</span>
      </div>

      <p style={{ margin: 0, font: `400 11.5px/1.5 ${T.sans}`, color: T.secondary }}>
        Surfaced now because the build completed the <b style={{ color: T.fg }}>design</b> node. These
        screens are the real stored mockups the design workflow produced. <b style={{ color: T.fg }}>Approve</b> to
        lock the look and let the build proceed — or select screens below and describe what to change; only the
        affected screens re-generate.
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 10 }}>
        {data.screens.map((s) => (
          <div key={s.id} style={{ border: `1px solid ${selected[s.id] ? T.brand : T.borderSubtle}`, borderRadius: T.rMd,
            overflow: "hidden", background: T.raised, display: "flex", flexDirection: "column" }}>
            <button onClick={() => openScreen(s)} title="Open the exact stored mockup"
              style={{ textAlign: "left", cursor: "pointer", border: 0, background: "none", padding: 0, display: "block" }}>
              <ScreenThumb projectId={projectId} screen={s} />
              <div style={{ padding: "8px 10px" }}>
                <div style={{ font: `600 12px/1.2 ${T.sans}`, color: T.fg, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{s.title}</div>
                <div style={{ font: `400 10px/1.3 ${T.mono}`, color: T.tertiary, marginTop: 2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{s.id} · v{s.version ?? 1}</div>
              </div>
            </button>
            <label style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 10px", borderTop: `1px solid ${T.borderSubtle}`,
              cursor: "pointer", font: `500 10.5px/1 ${T.sans}`, color: selected[s.id] ? T.brandDeep : T.tertiary }}>
              <input type="checkbox" checked={!!selected[s.id]}
                onChange={(e) => setSelected({ ...selected, [s.id]: e.target.checked })} />
              revise this
            </label>
          </div>
        ))}
      </div>

      {/* Iterate composer — grounds the request in the selected screen identities (empty ⇒ all). */}
      <div style={{ display: "flex", flexDirection: "column", gap: 8, background: T.raised,
        border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, padding: "10px 12px" }}>
        <div style={{ font: `500 11.5px/1.4 ${T.sans}`, color: T.tertiary, display: "inline-flex", alignItems: "center", gap: 6 }}>
          <Sparkle size={11} color={T.brandDeep} />
          Iterate — {affectedIds.length ? `${affectedIds.length} screen(s) selected` : "all screens"} · e.g. “denser quote table”, “approvals first”.
          You can also ask the Concierge; it uses the same tool.
        </div>
        <textarea value={instructions} onChange={(e) => setInstructions(e.target.value)} rows={2}
          placeholder="Describe what to change on the selected screen(s)…"
          style={{ width: "100%", boxSizing: "border-box", resize: "vertical", padding: "8px 10px", borderRadius: T.rMd,
            border: `1px solid ${instructions ? T.brand : T.borderDefault}`, background: T.bg, color: T.fg,
            font: `400 12px/1.5 ${T.sans}`, outline: "none" }} />
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 9 }}>
          <Btn variant="secondary" size="sm" disabled={!instructions.trim() || busy !== null} onClick={revise}>
            {busy === "revise" ? "Requesting…" : "Iterate via Concierge"}
          </Btn>
          <Btn variant="primary" size="sm" disabled={busy !== null} onClick={approve} style={{ background: T.success }}>
            <Icon name="check" size={13} color="#fff" /> {busy === "approve" ? "Approving…" : "Approve & continue"}
          </Btn>
        </div>
      </div>

      {notice && <p style={{ margin: 0, font: `400 11.5px/1.5 ${T.sans}`, color: T.secondary }}>{notice}</p>}
    </div>
  );
}
