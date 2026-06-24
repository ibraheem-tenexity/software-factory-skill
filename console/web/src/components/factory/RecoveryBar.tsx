// RecoveryBar.tsx — operator recovery controls shown when a run is paused or crashed.
//
// Surfaces three actions:
//   Resume    — POST /resume → clears pause/crash marker, relaunches from haltedNode
//   Retry     — POST /retry-node {node} → invalidates checkpoint at haltedNode+downstream, relaunches
//   Rewind to — dropdown of all upstream done nodes → POST /rewind {node} → sets phase=paused there
//
// The bar is stateless — all side-effects call the API then propagate the updated status via onUpdate.
import { useState } from "react";
import { T, Icon, Btn } from "../onboarding/design";
import { api } from "../../api";
import { PIPELINE_ORDER, STAGES } from "./pipeline";

const PHASE_LABEL: Record<string, string> = Object.fromEntries(
  STAGES.flatMap((s) => s.phases.map((p) => [p.id, p.label])));

type Props = {
  projectId: string;
  phase: "paused" | "crashed";
  haltedNode: string;
  doneNodes: string[];                    // pipeline nodes whose phaseState === "done"
  onUpdate: (status: Record<string, any>) => void;
};

export function RecoveryBar({ projectId, phase, haltedNode, doneNodes, onUpdate }: Props) {
  const [busy, setBusy] = useState<"resume" | "retry" | "rewind" | null>(null);
  const [rewindOpen, setRewindOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const nodeLabel = PHASE_LABEL[haltedNode] || haltedNode;
  const isPaused = phase === "paused";

  async function doResume() {
    setBusy("resume"); setError(null);
    try { onUpdate(await api.resumeProject(projectId)); }
    catch (e) { setError(String(e)); }
    finally { setBusy(null); }
  }

  async function doRetry() {
    setBusy("retry"); setError(null);
    try { onUpdate(await api.retryNode(projectId, haltedNode)); }
    catch (e) { setError(String(e)); }
    finally { setBusy(null); }
  }

  async function doRewind(node: string) {
    setRewindOpen(false); setBusy("rewind"); setError(null);
    try { onUpdate(await api.rewindTo(projectId, node)); }
    catch (e) { setError(String(e)); }
    finally { setBusy(null); }
  }

  // Nodes eligible for rewind: upstream done nodes (strictly before haltedNode in pipeline order)
  const haltedIdx = PIPELINE_ORDER.indexOf(haltedNode);
  const rewindTargets = doneNodes.filter((n) => {
    const i = PIPELINE_ORDER.indexOf(n);
    return i !== -1 && i < haltedIdx;
  }).reverse(); // most recent first

  return (
    <div style={{ position: "relative", display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap",
      padding: "11px 15px", borderRadius: T.rLg, background: isPaused ? T.warningSoft : "#FFF1F1",
      border: `1px solid ${isPaused ? T.warning : T.danger}` }}>
      {/* status label */}
      <span style={{ display: "inline-flex", alignItems: "center", gap: 7,
        font: `600 13px/1 ${T.sans}`, color: isPaused ? T.warning : T.danger }}>
        <span style={{ width: 8, height: 8, borderRadius: "50%", background: isPaused ? T.warning : T.danger, flexShrink: 0 }} />
        Run {isPaused ? "paused" : "crashed"} at <b style={{ font: `700 13px/1 ${T.mono}` }}>{nodeLabel}</b>
      </span>

      <span style={{ flex: 1 }} />

      {/* Resume */}
      <Btn variant="primary" size="sm" disabled={!!busy} onClick={doResume}>
        {busy === "resume" ? "Resuming…" : <>Resume from {nodeLabel} <Icon name="arrowRight" size={12} color="#fff" /></>}
      </Btn>

      {/* Retry */}
      <Btn variant="secondary" size="sm" disabled={!!busy} onClick={doRetry}>
        {busy === "retry" ? "Retrying…" : <>↺ Retry {nodeLabel}</>}
      </Btn>

      {/* Rewind to… */}
      {rewindTargets.length > 0 && (
        <div style={{ position: "relative" }}>
          <Btn variant="secondary" size="sm" disabled={!!busy} onClick={() => setRewindOpen((o) => !o)}>
            {busy === "rewind" ? "Rewinding…" : <>Rewind to… <Icon name="chevronDown" size={11} /></>}
          </Btn>
          {rewindOpen && (
            <div style={{ position: "absolute", top: "calc(100% + 6px)", right: 0, zIndex: 20,
              background: T.raised, border: `1px solid ${T.borderDefault}`, borderRadius: T.rLg,
              boxShadow: T.shadowMd, minWidth: 160, overflow: "hidden" }}>
              {rewindTargets.map((n) => (
                <button key={n} onClick={() => doRewind(n)}
                  style={{ display: "flex", alignItems: "center", gap: 8, width: "100%", padding: "9px 13px",
                    border: "none", background: "transparent", cursor: "pointer", textAlign: "left",
                    font: `500 12.5px/1.2 ${T.sans}`, color: T.fg }}>
                  <Icon name="arrowLeft" size={12} color={T.tertiary} />
                  {PHASE_LABEL[n] || n}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {error && (
        <span style={{ width: "100%", font: `400 11.5px/1.4 ${T.sans}`, color: T.danger }}>{error}</span>
      )}
    </div>
  );
}
