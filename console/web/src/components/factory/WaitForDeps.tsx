// WaitForDeps.tsx — the stage-triggered "wait for deps" bar (design: buildprogress.jsx DepsBar).
// Renders ONLY while the run is actually parked at the deps gate (FactoryConsole decides via
// atWaitForDeps). The dep set is architecture-derived, so the count varies run-to-run — the grid
// auto-wraps to any number, and the header tracks resolved/total.
//
// Chrome per the design: rotated-square glyph + "STAGE-TRIGGERED" mono badge + an explanatory
// paragraph; each dep card shows a human label (the token's provider) with the raw token name as
// the hint line, and a per-mode explanation for mcp/mock. When the submit lands satisfied, the
// bar flips to the GREEN "Dependencies resolved — build unblocked" state for a beat before
// onResolved refreshes the status (instead of instantly vanishing).
//
// Per dep the operator picks a disposition (matches the server's deps model in console.submit_deps):
//   Get-from-MCP (mcp) · Mock-it (mock) · Input-key (provide, with a value field).
// Submitting POSTs to /api/projects/{id}/deps via api.submitDeps; provided values ride into the
// Stage-3 env only and are never persisted to disk (see console.submit_deps docstring).
import { useEffect, useRef, useState } from "react";
import { T, Icon, Sparkle, Btn } from "../onboarding/design";
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

// Human label for a token: the provider parsed from architecture.md (tokens[].provider), falling
// back to the token's first word — e.g. OPENAI_API_KEY → "Openai".
function labelFor(name: string, tokens: DepsResponse["tokens"]): string {
  const t = tokens.find((x) => x.name === name);
  if (t?.provider) return String(t.provider);
  const head = name.split("_")[0] || name;
  return head.charAt(0).toUpperCase() + head.slice(1).toLowerCase();
}

export function WaitForDeps({ projectId, onResolved }: { projectId: string; onResolved?: () => void }) {
  const [deps, setDeps] = useState<DepsResponse | null>(null);
  const [disp, setDisp] = useState<Record<string, Disp>>({});
  const [vals, setVals] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  // true once the server confirmed satisfied — the green "build unblocked" beat before refresh
  const [unblocked, setUnblocked] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let live = true;
    api.deps(projectId).then((d) => {
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
    return () => { live = false; if (timerRef.current) clearTimeout(timerRef.current); };
  }, [projectId]);

  if (!deps) return null;
  const names = deps.deps_required;
  const resolved = unblocked ? names.length : names.filter((n) => isSatisfied(n, disp[n] || "mock", vals[n] || "")).length;
  const allResolved = resolved === names.length && names.length > 0;

  const submit = async () => {
    setSubmitting(true);
    const body: DepSubmit = {};
    for (const name of names) {
      const d = disp[name] || "mock";
      body[name] = d === "provide" ? { disposition: "provide", value: vals[name] || "" } : { disposition: d };
    }
    try {
      const r = await api.submitDeps(projectId, body);
      if (r.satisfied) {
        // hold the green unblocked state briefly instead of instantly vanishing
        setUnblocked(true);
        if (onResolved) timerRef.current = setTimeout(onResolved, 2500);
      }
    } finally {
      setSubmitting(false);
    }
  };

  const tone = unblocked ? T.success : T.warning;
  const toneSoft = unblocked ? T.successSoft : T.warningSoft;

  return (
    <div style={{ background: toneSoft, border: `1px solid ${tone}55`, borderRadius: T.rXl, padding: 16,
      display: "flex", flexDirection: "column", gap: 12, animation: "sfRise .3s ease both" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 9, flexWrap: "wrap" }}>
          {/* rotated-square gate glyph (design: buildprogress.jsx:67) */}
          <span style={{ width: 12, height: 12, background: tone, transform: "rotate(45deg)", borderRadius: 2, flexShrink: 0 }} />
          <span style={{ font: `600 14px/1.2 ${T.sans}`, color: T.fg }}>
            {unblocked ? "Dependencies resolved — build unblocked" : "Wait for dependencies"}
          </span>
          <span style={{ font: `500 9.5px/1 ${T.mono}`, letterSpacing: "0.06em", color: tone, background: toneSoft,
            border: `1px solid ${tone}55`, padding: "4px 6px", borderRadius: 4 }}>STAGE-TRIGGERED</span>
          <span style={{ font: `500 12px/1 ${T.mono}`, color: tone }}>{resolved}/{names.length} resolved</span>
        </div>
        {!unblocked && (
          <Btn variant="primary" size="sm" disabled={!allResolved || submitting} onClick={submit}>
            {submitting ? "Submitting…" : "Resolve & continue"}
          </Btn>
        )}
      </div>
      <p style={{ margin: 0, font: `400 11.5px/1.5 ${T.sans}`, color: T.secondary }}>
        {unblocked
          ? <>All <b style={{ color: T.fg }}>{names.length}</b> external service{names.length === 1 ? "" : "s"} resolved — the build is continuing into Stage 3.</>
          : <>Surfaced now because the build reached the <b style={{ color: T.fg }}>wait-for-deps</b> stage.
              This architecture needs <b style={{ color: T.fg }}>{names.length}</b> external
              service{names.length === 1 ? "" : "s"} — the set is derived from the design, so it grows or
              shrinks per project. For each: pull from MCP, mock it, or paste a key.</>}
      </p>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 10 }}>
        {names.map((name) => {
          const d = disp[name] || "mock";
          const ok = unblocked || isSatisfied(name, d, vals[name] || "");
          return (
            <div key={name} style={{ background: T.raised, border: `1px solid ${ok ? T.borderSubtle : T.warning}`, borderRadius: T.rLg,
              padding: "12px 13px", display: "flex", flexDirection: "column", gap: 9 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 6, minWidth: 0 }}>
                  <span style={{ font: `600 12.5px/1 ${T.sans}`, color: T.fg }}>{labelFor(name, deps.tokens)}</span>
                  <span style={{ font: `400 10.5px/1 ${T.mono}`, color: T.tertiary, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{name}</span>
                </div>
                {ok
                  ? <Icon name="check" size={14} color={T.success} />
                  : <span style={{ width: 6, height: 6, borderRadius: "50%", background: T.warning, flexShrink: 0 }} />}
              </div>
              <div style={{ display: "flex", gap: 4 }}>
                {OPTIONS.map((o) => (
                  <button key={o.id} disabled={unblocked} onClick={() => setDisp({ ...disp, [name]: o.id })}
                    style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", gap: 4,
                      padding: "6px 4px", borderRadius: T.rMd, cursor: unblocked ? "default" : "pointer",
                      border: `1px solid ${d === o.id ? T.brand : T.borderDefault}`,
                      background: d === o.id ? T.brandSoft : T.raised,
                      color: d === o.id ? T.brandDeep : T.secondary, font: `500 11px/1 ${T.sans}` }}>
                    <Icon name={o.icon} size={12} color={d === o.id ? T.brandDeep : T.tertiary} />{o.label}
                  </button>
                ))}
              </div>
              {d === "mcp" && (
                <div style={{ font: `400 11.5px/1.4 ${T.sans}`, color: T.success, display: "flex", alignItems: "center", gap: 5 }}>
                  <Icon name="link" size={12} color={T.success} /> Pulled from the {labelFor(name, deps.tokens)} MCP server — no key to manage.
                </div>
              )}
              {d === "mock" && (
                <div style={{ font: `400 11.5px/1.4 ${T.sans}`, color: T.secondary, display: "flex", alignItems: "center", gap: 5 }}>
                  <Sparkle size={11} color={T.brand} /> Mocked responses — build &amp; test now, wire the real service later.
                </div>
              )}
              {d === "provide" && (
                <input type="password" value={vals[name] || ""} placeholder="paste value" disabled={unblocked}
                  onChange={(e) => setVals({ ...vals, [name]: e.target.value })}
                  style={{ width: "100%", boxSizing: "border-box", height: 30, padding: "0 9px", borderRadius: T.rMd,
                    border: `1px solid ${vals[name] ? T.brand : T.borderDefault}`,
                    background: vals[name] ? T.brandSoft : T.bg, color: T.fg, font: `400 12px/1 ${T.mono}`, outline: "none" }} />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
