// FactoryActivity.tsx — the exhaustive Factory Console "Activity" mode (SOF-249). This is the
// event-only projection of the SAME canonical timeline the Concierge dock renders (SOF-247): it
// IMPORTS buildTimeline from the shared ./eventTimeline contract and renders every event
// TimelineItem in occurrence order, skipping message items. It does NOT re-implement normalizeEvent
// or any severity classifier — severity/label/detail/artifact all come pre-normalized on each item.
//
// Unlike the Concierge feed it does NOT collapse consecutive routine events (the design's Activity
// mode "shows all"), it carries a stable per-event anchor so a URL/reload/alert can select+scroll to
// one event, and it opens artifact events through the SAME shared DocViewer the board already owns
// (via the onOpenArtifact callback), never a forked viewer.
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { T, Icon, CategoryLabel } from "../onboarding/design";
import { api, ProjectEvent } from "../../api";
import { linkify } from "../../linkify";
import { ArtifactRef } from "./Artifacts";
import { TimelineItem, buildTimeline } from "./eventTimeline";

const PAGE = 80; // progressive reveal window — long histories load older records without reordering.

type EventItem = Extract<TimelineItem, { kind: "event" }>;

// Stable anchor for one event row: rounded-ms timestamp + type, deduped by occurrence. This is the
// id the URL (?fevent=…) and an alert deep-link reference to select and scroll to one event.
export function eventAnchor(it: EventItem, occurrence: number): string {
  const base = `${Math.round(it.ts * 1000)}-${it.type}`;
  return occurrence > 0 ? `${base}-${occurrence}` : base;
}

function fmtTs(ts: number): string {
  const d = new Date(ts * 1000);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

// One event row — consumes the pre-normalized fields (severity/label/detail/artifact). Attention and
// failure rows carry an expandable truthful detail; artifact rows expose "Open output".
function ActivityRow({ it, anchor, selected, artifacts, onOpenArtifact, rowRef }: {
  it: EventItem; anchor: string; selected: boolean;
  artifacts: ArtifactRef[]; onOpenArtifact: (a: ArtifactRef) => void;
  rowRef?: (el: HTMLDivElement | null) => void;
}) {
  const tone = it.severity === "failure" ? T.danger : it.severity === "attention" ? T.warning : T.tertiary;
  const icon = it.type === "done" ? "check" : it.severity !== "routine" ? "x" : "layers";
  const openOutput = it.artifact
    ? () => {
        const a = it.artifact!;
        const match = artifacts.find((x) => (a.path && x.path === a.path) || (a.title && x.label === a.title));
        onOpenArtifact(match || ({ label: a.title || it.label, path: a.path, url: a.url ?? null } as ArtifactRef));
      }
    : undefined;
  const inline = it.severity === "routine" && it.detail ? `${it.label}: ${it.detail}` : it.label;
  const expandable = !!it.detail && it.severity !== "routine";

  const head = (
    <div style={{ display: "flex", alignItems: "flex-start", gap: 10, padding: "10px 12px", borderRadius: T.rLg,
      background: selected ? T.brandSoft : T.raised,
      border: `1px solid ${selected ? T.brand : T.borderSubtle}`,
      borderLeft: it.severity !== "routine" ? `3px solid ${tone}` : `1px solid ${selected ? T.brand : T.borderSubtle}`,
      transition: "background .3s, border-color .3s" }}>
      <span style={{ marginTop: 1, flexShrink: 0 }}><Icon name={icon} size={14} color={tone} /></span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ font: `${it.severity === "routine" ? 400 : 500} 12.5px/1.4 ${T.sans}`, color: it.severity === "routine" ? T.secondary : T.fg, wordBreak: "break-word" }}>
          {linkify(inline)}{it.count && it.count > 1 ? ` ·×${it.count}` : ""}
        </div>
        <div style={{ marginTop: 3, display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ font: `500 10px/1 ${T.mono}`, color: T.tertiary }}>{fmtTs(it.ts)}</span>
          <span style={{ font: `500 9px/1 ${T.mono}`, letterSpacing: "0.04em", color: T.tertiary, textTransform: "uppercase" }}>{it.type}</span>
        </div>
      </div>
      {openOutput && (
        <button onClick={openOutput} style={{ border: 0, background: "none", color: T.brandDeep, cursor: "pointer",
          font: `600 11px/1 ${T.sans}`, flexShrink: 0, marginTop: 2 }}>Open output</button>
      )}
    </div>
  );

  return (
    <div ref={rowRef} id={anchor} data-event-anchor={anchor} style={{ scrollMarginTop: 16 }}>
      {expandable ? (
        <details>
          <summary style={{ listStyle: "none", cursor: "pointer" }}>{head}</summary>
          <div style={{ padding: "8px 14px 4px 34px", font: `400 11.5px/1.5 ${T.sans}`, color: T.tertiary, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
            {linkify(it.detail!)}
          </div>
        </details>
      ) : head}
    </div>
  );
}

// The Activity mode body. Self-polls persisted events (matching the Concierge's own poll cadence),
// builds the shared event-only timeline, and renders it exhaustively. `depsPanel` is the live
// stage-triggered action (Wait-for-deps) the board hands down; it renders at the chronological tail
// (it is the current gate) and — because it lives INSIDE this mode — leaving Activity removes it from
// layout, so it can never push another selected view below the viewport.
export function FactoryActivity({ projectId, artifacts, onOpenArtifact, selectedEventId, designPanel, depsPanel, focusDeps, onFocusHandled }: {
  projectId: string; artifacts: ArtifactRef[]; onOpenArtifact: (a: ArtifactRef) => void;
  selectedEventId?: string | null; designPanel?: ReactNode; depsPanel?: ReactNode;
  focusDeps?: boolean; onFocusHandled?: () => void;
}) {
  const [events, setEvents] = useState<ProjectEvent[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [revealed, setRevealed] = useState(0); // 0 ⇒ not yet initialized
  const prevTotal = useRef(0);
  const rowEls = useRef<Record<string, HTMLDivElement | null>>({});
  const depsRef = useRef<HTMLDivElement | null>(null);

  // SOF-250: the StageRail's "wait for deps" pill lives outside this mode; clicking it switches to
  // Activity and raises `focusDeps`. Wait for the events to load (they render ABOVE this tail panel and
  // would push it below the fold if we scrolled first), then defer past the reveal commit's paint via
  // double-rAF before scrolling — and clear the one-shot only AFTER scrolling, so the reset can't cancel it.
  useEffect(() => {
    if (!focusDeps || !loaded) return;
    const id = requestAnimationFrame(() => requestAnimationFrame(() => {
      depsRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
      onFocusHandled?.();
    }));
    return () => cancelAnimationFrame(id);
  }, [focusDeps, loaded, onFocusHandled]);

  useEffect(() => {
    let live = true;
    // Exhaustive record: render every persisted event the API returns (SOF-247/SOF-249 AC — never
    // truncate to the latest N). buildTimeline orders them; this view never collapses them.
    const tick = () => api.events(projectId)
      .then((d) => { if (live) { setEvents(d.events || []); setLoaded(true); } })
      .catch(() => { if (live) setLoaded(true); });
    tick();
    const h = setInterval(tick, 4000);
    return () => { live = false; clearInterval(h); };
  }, [projectId]);

  // Event-only projection of the shared canonical timeline. Passing no messages yields the exhaustive
  // ordered event record; the filter is defensive (buildTimeline emits only events for [] messages).
  const items = useMemo(
    () => buildTimeline([], events).filter((it): it is EventItem => it.kind === "event"),
    [events],
  );

  // Stable anchors, deduped for identical ts+type.
  const anchors = useMemo(() => {
    const seen: Record<string, number> = {};
    return items.map((it) => {
      const base = `${Math.round(it.ts * 1000)}-${it.type}`;
      const n = seen[base] ?? 0; seen[base] = n + 1;
      return eventAnchor(it, n);
    });
  }, [items]);

  const total = items.length;

  // Progressive reveal that never drops or reorders already-shown records: first load shows the last
  // PAGE; polled-in newer events extend the window at the tail (top boundary stays fixed); "Show
  // earlier" grows it toward the head.
  useEffect(() => {
    if (total === 0) return;
    setRevealed((r) => {
      if (r === 0) return Math.min(PAGE, total);          // first load → last PAGE
      if (total > prevTotal.current) return r + (total - prevTotal.current); // append new at tail
      return r;
    });
    prevTotal.current = total;
  }, [total]);

  const start = Math.max(0, total - revealed);

  // URL/alert selection: expand the window to include the target if it's above the fold, then scroll.
  useEffect(() => {
    if (!selectedEventId) return;
    const idx = anchors.indexOf(selectedEventId);
    if (idx < 0) return;
    if (idx < start) setRevealed(total - idx); // reveal enough to include the target
    const el = rowEls.current[selectedEventId];
    if (el) el.scrollIntoView({ block: "center", behavior: "auto" });
  }, [selectedEventId, anchors, start, total]);

  const visible = items.slice(start);
  const visibleAnchors = anchors.slice(start);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
        <CategoryLabel>Activity record</CategoryLabel>
        {total > 0 && <span style={{ font: `500 10px/1 ${T.mono}`, color: T.tertiary }}>{total} event{total === 1 ? "" : "s"}</span>}
      </div>

      {start > 0 && (
        <button onClick={() => setRevealed((r) => Math.min(total, r + PAGE))}
          style={{ alignSelf: "center", padding: "6px 14px", borderRadius: 9999, cursor: "pointer",
            border: `1px solid ${T.borderDefault}`, background: T.raised, color: T.secondary, font: `600 11px/1 ${T.sans}` }}>
          Show earlier activity ({start})
        </button>
      )}

      {loaded && total === 0 ? (
        <div style={{ padding: "40px 20px", textAlign: "center", border: `1px dashed ${T.borderSubtle}`, borderRadius: T.rLg }}>
          <Icon name="activity" size={20} color={T.tertiary} />
          <p style={{ margin: "10px 0 0", font: `400 13px/1.5 ${T.sans}`, color: T.tertiary }}>
            No activity yet — stage transitions, agent actions, and outputs will appear here as the factory works.
          </p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {visible.map((it, i) => {
            const anchor = visibleAnchors[i];
            return (
              <ActivityRow key={anchor} it={it} anchor={anchor} selected={anchor === selectedEventId}
                artifacts={artifacts} onOpenArtifact={onOpenArtifact}
                rowRef={(el) => { rowEls.current[anchor] = el; }} />
            );
          })}
        </div>
      )}

      {/* Stage-triggered action panels render at the chronological tail (the current live gates),
          INSIDE Activity only — selecting Kanban/Tree/Map removes them from layout entirely. Design
          review (the design gate, Stage 2) precedes wait-for-deps (the Stage 2→3 boundary); each
          self-gates and shows only when it is the live gate. The depsRef wrapper is the scroll target
          for the StageRail's wait-for-deps pill (SOF-250 cross-mode click-through). */}
      {designPanel}
      {depsPanel && <div ref={depsRef}>{depsPanel}</div>}
    </div>
  );
}
