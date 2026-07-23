// eventTimeline.ts — the canonical normalization of a project's PERSISTED conversation + PERSISTED
// system events into ONE time-ordered timeline (SOF-247). This is a REUSABLE projection, not a
// Concierge-only helper: the Concierge dock (SOF-247) and the Factory Console Activity mode
// (SOF-249) both build from these SAME types and functions.
//
// HARD CONTRACT: only persisted data goes in. The ephemeral per-turn `display_context` (SOF-246) is
// NEVER a timeline item — it is send-time prompt grounding, never persisted, never shown here.
import { ProjectEvent } from "../../api";

export type ChatMsg = { role: string; content: string; ts: number; msg_type?: string };

// routine = compact neutral lifecycle row · attention = needs the customer/operator · failure = a
// real failure. Consumers render tone from this; they do not re-derive severity.
export type Severity = "routine" | "attention" | "failure";

export type TimelineItem =
  | { kind: "message"; ts: number; role: "user" | "agent"; text: string }
  | {
      kind: "event";
      ts: number;              // display ts (for a collapsed group, the LATEST occurrence)
      type: string;            // the raw ProjectEvent.type
      severity: Severity;
      label: string;           // one-line human label
      detail?: string;         // expandable truthful detail (blocker reason, verified URL, raw payload)
      artifact?: { title?: string; path?: string; url?: string }; // artifact events → "Open output"
      count?: number;          // >1 when consecutive identical routine events were summarized
      tss?: number[];          // every individual timestamp in a summarized group (kept available)
    };

// Classify ONE persisted system event → severity + label (+ optional truthful detail / artifact).
// Central so the Concierge and the Activity mode label events identically.
export function normalizeEvent(e: ProjectEvent): {
  severity: Severity; label: string; detail?: string; artifact?: { title?: string; path?: string; url?: string };
} {
  const p = e.payload || {};
  switch (e.type) {
    case "phase": return { severity: "routine", label: `${p.name ?? "phase"} → ${p.status ?? ""}`.trim() };
    case "artifact": return { severity: "routine", label: `Produced ${p.title || p.path || "an output"}`,
      artifact: { title: p.title, path: p.path, url: p.url } };
    case "blocker": return { severity: "attention", label: "Blocked", detail: p.what };
    case "done": return { severity: "routine", label: "Verified live", detail: p.url };
    case "lifecycle": {
      // SOF-188: operator/host run-control actions (stop/pause/resume/auto-resume/archive/restore),
      // recorded on the ProjectState lifecycle trail. Routine severity — a normal lifecycle action,
      // not a failure — with the same verb-tensed label the Concierge feed uses.
      const verb: Record<string, string> = { stop: "stopped", pause: "paused", resume: "resumed",
        "auto-resume": "auto-resumed", archive: "archived", restore: "restored" };
      const action = verb[p.action] || p.action || "updated";
      const who = p.actor && p.actor !== "operator" ? ` by ${p.actor}` : "";
      return { severity: "routine", label: `Run ${action}${who}`, detail: p.reason || undefined };
    }
    default:
      // Unknown types default to routine; anything that reads as a failure is surfaced as one with
      // the raw payload as truthful expandable detail (never a plausible guess).
      if (/fail|crash|error|refus/i.test(e.type)) {
        return { severity: "failure", label: e.type, detail: Object.keys(p).length ? JSON.stringify(p) : undefined };
      }
      return { severity: "routine", label: e.type };
  }
}

// The canonical timeline: persisted messages + persisted events, chronological, ONE item each.
// Internal tool-call/tool_result rows are hidden (customer-facing), matching the existing chat rule.
export function buildTimeline(messages: ChatMsg[], events: ProjectEvent[]): TimelineItem[] {
  const items: TimelineItem[] = [];
  for (const m of messages) {
    if (m.msg_type === "tool_call" || m.msg_type === "tool_result") continue;
    items.push({ kind: "message", ts: m.ts, role: m.role === "assistant" ? "agent" : "user", text: m.content });
  }
  for (const e of events) {
    const n = normalizeEvent(e);
    items.push({ kind: "event", ts: e.ts, type: e.type, ...n });
  }
  // stable chronological order; ties keep insertion order (messages before events at the same ts).
  return items
    .map((it, i) => ({ it, i }))
    .sort((a, b) => a.it.ts - b.it.ts || a.i - b.i)
    .map(({ it }) => it);
}

// Presentation helper (Concierge's compact feed): summarize CONSECUTIVE identical routine events
// (e.g. retries) into one row carrying `count` and every original `tss` — so the design's "may
// summarize but keep individual timestamps" holds. The Activity mode can skip this and show all.
export function collapseConsecutive(items: TimelineItem[]): TimelineItem[] {
  const out: TimelineItem[] = [];
  for (const it of items) {
    const prev = out[out.length - 1];
    if (it.kind === "event" && prev && prev.kind === "event"
        && it.severity === "routine" && prev.severity === "routine"
        && it.type === prev.type && it.label === prev.label) {
      prev.count = (prev.count ?? 1) + 1;
      prev.tss = [...(prev.tss ?? [prev.ts]), it.ts];
      prev.ts = it.ts;   // show the latest; every ts stays in `tss`
      continue;
    }
    out.push({ ...it });
  }
  return out;
}
