// WaitForDeps.tsx — the stage-triggered "wait for deps" bar. Renders ONLY while the run is
// actually parked at the deps gate (FactoryConsole decides via atWaitForDeps). The dep set is
// architecture-derived, so the count varies run-to-run — the grid auto-wraps to any number, and
// the header tracks resolved/total.
//
// Per dep the operator picks a disposition (matches the server's deps model in console.submit_deps):
//   Get-from-MCP (mcp) · Mock-it (mock) · Input-key (provide, with a value field).
// Submitting POSTs to /api/runs/{id}/deps via api.submitDeps; provided values ride into the
// Stage-3 env only and are never persisted to disk (see console.submit_deps docstring).
import { useEffect, useState } from "react";
import { T, Icon, Btn } from "../onboarding/design";
import { api, DepsResponse, DepSubmit } from "../../api";

type Disp = "mcp" | "mock" | "provide";
const OPTIONS: { id: Disp; label: string; icon: string }[] = [
  { id: "mcp", label: "Get from MCP", icon: "zap" },
  { id: "mock", label: "Mock it", icon: "flask" },
  { id: "provide", label: "Input key", icon: "lock" },
];

function isSatisfied(name: string, disp: Disp, value: string): boolean {
  // mcp/mock are self-satisfying; provide needs a value (mirrors deps.resolve_satisfied).
  return disp !== "provide" || value.trim().length > 0;
}

export function WaitForDeps({ runId, onResolved }: { runId: string; onResolved?: () => void }) {
  const [deps, setDeps] = useState<DepsResponse | null>(null);
  const [disp, setDisp] = useState<Record<string, Disp>>({});
  const [vals, setVals] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let live = true;
    api.deps(runId).then((d) => {
      if (!live) return;
      setDeps(d);
      // seed from the server-classified disposition (smart default per token).
      const seed: Record<string, Disp> = {};
      for (const name of d.deps_required) {
        const v = d.disposition[name];
        seed[name] = (v === "mcp" || v === "mock" || v === "provide") ? v : "mock";
      }
      setDisp(seed);
    }).catch(() => {});
    return () => { live = false; };
  }, [runId]);

  if (!deps) return null;
  const names = deps.deps_required;
  const resolved = names.filter((n) => isSatisfied(n, disp[n] || "mock", vals[n] || "")).length;
  const allResolved = resolved === names.length && names.length > 0;

  const submit = async () => {
    setSubmitting(true);
    const body: DepSubmit = {};
    for (const name of names) {
      const d = disp[name] || "mock";
      body[name] = d === "provide" ? { disposition: "provide", value: vals[name] || "" } : { disposition: d };
    }
    try {
      const r = await api.submitDeps(runId, body);
      if (r.satisfied && onResolved) onResolved();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ background: T.warningSoft, border: `1px solid ${T.warning}55`, borderRadius: T.rXl, padding: 16,
      display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
          <Icon name="lock" size={16} color={T.warning} />
          <span style={{ font: `600 14px/1.2 ${T.sans}`, color: T.fg }}>Waiting on dependencies</span>
          <span style={{ font: `500 12px/1 ${T.mono}`, color: T.warning }}>{resolved}/{names.length} resolved</span>
        </div>
        <Btn variant="primary" size="sm" disabled={!allResolved || submitting} onClick={submit}>
          {submitting ? "Submitting…" : "Resolve & continue"}
        </Btn>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 10 }}>
        {names.map((name) => {
          const d = disp[name] || "mock";
          return (
            <div key={name} style={{ background: T.raised, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg,
              padding: "11px 12px", display: "flex", flexDirection: "column", gap: 8 }}>
              <span style={{ font: `500 12px/1.2 ${T.mono}`, color: T.fg, wordBreak: "break-all" }}>{name}</span>
              <div style={{ display: "flex", gap: 4 }}>
                {OPTIONS.map((o) => (
                  <button key={o.id} onClick={() => setDisp({ ...disp, [name]: o.id })}
                    style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", gap: 4,
                      padding: "6px 4px", borderRadius: T.rMd, cursor: "pointer",
                      border: `1px solid ${d === o.id ? T.brand : T.borderDefault}`,
                      background: d === o.id ? T.brandSoft : T.raised,
                      color: d === o.id ? T.brandDeep : T.secondary, font: `500 11px/1 ${T.sans}` }}>
                    <Icon name={o.icon} size={12} color={d === o.id ? T.brandDeep : T.tertiary} />{o.label}
                  </button>
                ))}
              </div>
              {d === "provide" && (
                <input type="password" value={vals[name] || ""} placeholder="paste value"
                  onChange={(e) => setVals({ ...vals, [name]: e.target.value })}
                  style={{ width: "100%", boxSizing: "border-box", height: 30, padding: "0 9px", borderRadius: T.rMd,
                    border: `1px solid ${T.borderDefault}`, background: T.bg, color: T.fg, font: `400 12px/1 ${T.mono}`, outline: "none" }} />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
