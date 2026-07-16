// BuildBoard.tsx — the Kanban board (design: buildboard.jsx Kanban), bound to REAL tickets from
// /api/projects/{id}/tickets (console.tickets → TicketStore.all_tickets).
//
// The backend's 6 raw ticket statuses (open · in_progress · done · deployed · qa_testing ·
// approved) project onto the design's 5 columns:
//   open                         -> Backlog
//   in_progress  & no agent      -> Claimed
//   in_progress  & has agent     -> Building
//   done | deployed | qa_testing -> Testing
//   approved                     -> Done
// A QA bounce is qa_reject -> back to `open` with a markdown bug report written into the ticket's
// `description`; those re-opened tickets land in Backlog and we surface the BUG tag (the design's
// red "bug" badge + Testing→Building loop note in the footer).
import { T, Avatar, Icon, ConfidencePill } from "../onboarding/design";
import { Ticket } from "../../api";

type Col = "backlog" | "claimed" | "building" | "testing" | "done";
const COLS: { id: Col; label: string; tone: keyof typeof TONE_DOT; wipMax?: number }[] = [
  { id: "backlog", label: "Backlog", tone: "neutral" },
  { id: "claimed", label: "Claimed", tone: "info" },
  { id: "building", label: "Building", tone: "warning", wipMax: 4 },
  { id: "testing", label: "Testing", tone: "brand" },
  { id: "done", label: "Done", tone: "success" },
];
const TONE_DOT = { neutral: T.tertiary, info: T.brand, warning: T.warning, brand: T.brand, success: T.success, danger: T.danger };

function columnOf(t: Ticket): Col {
  switch (t.status) {
    case "open": return "backlog";
    case "in_progress": return t.agent ? "building" : "claimed";
    case "done":
    case "deployed":
    case "qa_testing": return "testing";
    case "approved": return "done";
    default: return "backlog";
  }
}

// A re-opened ticket carrying a markdown bug report in its description is a QA bounce.
function hasBug(t: Ticket): boolean {
  return t.status === "open" && !!t.description && /bug|fail|reject|❌|## /i.test(t.description);
}

// Derive the small tag badge from REAL fields only (design: bug / needs key / e2e).
type TagKind = "bug" | "deps" | "pr";
// "needs key" is real when the ticket's own title says it is blocked on a key/dependency.
function needsKey(t: Ticket): boolean {
  return /\bneeds?[ -]key\b|\bblocked on (a )?(key|creds?|deps?)\b|\bmissing (api[ -]?)?key\b/i.test(t.title);
}
function tagOf(t: Ticket): TagKind | null {
  if (hasBug(t)) return "bug";
  if (needsKey(t)) return "deps";
  if (t.provenance_type === "pr" && t.provenance) return "pr";
  return null;
}

// Confidence band, rendered only when the backend actually sent a valid one.
const BANDS = ["exact", "high", "med", "low", "none"] as const;
function confBand(t: Ticket): (typeof BANDS)[number] | null {
  const c = t.confidence;
  return c && (BANDS as readonly string[]).includes(c) ? (c as (typeof BANDS)[number]) : null;
}
function TagBadge({ tag, prov }: { tag: TagKind; prov?: string | null }) {
  const map: Record<TagKind, [string, string, string]> = {
    bug: ["bug", T.dangerSoft, T.danger],
    deps: ["needs key", T.warningSoft, T.warning],
    pr: [`PR #${prov}`, T.brandSoft, T.brandDeep],
  };
  const m = map[tag];
  return <span style={{ font: `600 9.5px/1 ${T.mono}`, letterSpacing: "0.04em", textTransform: "uppercase",
    color: m[2], background: m[1], padding: "3px 6px", borderRadius: 4 }}>{m[0]}</span>;
}

function TicketCard({ t, onOpen }: { t: Ticket; onOpen: (t: Ticket) => void }) {
  const col = columnOf(t);
  const tag = tagOf(t);
  const conf = confBand(t);
  return (
    <article onClick={() => onOpen(t)} style={{ background: T.bg, border: `1px solid ${tag === "bug" ? T.danger + "66" : T.borderSubtle}`,
      borderRadius: T.rMd, padding: 9, boxShadow: T.shadowXs, cursor: "pointer", display: "flex", flexDirection: "column", gap: 7 }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 6 }}>
        <span style={{ font: `500 12.5px/1.35 ${T.sans}`, color: T.fg }}>{t.title}</span>
        {tag ? <TagBadge tag={tag} prov={t.provenance} /> : (t.app ? <span style={{ font: `500 9.5px/1 ${T.mono}`, color: T.tertiary, whiteSpace: "nowrap" }}>{t.app}</span> : null)}
      </div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", borderTop: `1px solid ${T.borderSubtle}`, paddingTop: 7 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ font: `500 10px/1 ${T.mono}`, color: T.tertiary }}>#{t.id}</span>
          {t.agent && <Avatar name={t.agent} size={18} />}
          {t.diff_lines > 0 && <span style={{ font: `500 10px/1 ${T.mono}`, color: T.success }}>+{t.diff_lines}</span>}
        </div>
        {col === "building" && (conf
          ? <ConfidencePill band={conf} />
          : <span style={{ font: `500 10px/1 ${T.mono}`, color: T.warning }}>● working</span>)}
        {col === "testing" && <span style={{ font: `500 10px/1 ${T.mono}`, color: T.brandDeep }}>● testing</span>}
        {col === "done" && <Icon name="check" size={14} color={T.success} />}
      </div>
    </article>
  );
}

export function BuildBoard({ tickets, onOpenTicket }: { tickets: Ticket[]; onOpenTicket: (t: Ticket) => void }) {
  if (!tickets.length) {
    return (
      <div style={{ padding: 40, textAlign: "center", font: `400 13px/1.5 ${T.sans}`, color: T.tertiary,
        background: T.raised, border: `1px dashed ${T.borderDefault}`, borderRadius: T.rLg }}>
        No build tickets yet — these appear once the Design stage (Stage 2) plans the work.
      </div>
    );
  }
  return (
    <div style={{ display: "grid", gridTemplateColumns: `repeat(${COLS.length}, minmax(220px, 1fr))`, gap: 12,
      height: "min(560px, 56vh)", minHeight: 240, alignItems: "stretch", overflowX: "auto" }}>
      {COLS.map((c) => {
        const list = tickets.filter((t) => columnOf(t) === c.id);
        const over = c.wipMax != null && list.length > c.wipMax;
        return (
          <div key={c.id} style={{ display: "flex", flexDirection: "column", minHeight: 0, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, background: T.raised }}>
            <div style={{ flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "space-between", padding: "9px 11px", borderBottom: `1px solid ${T.borderSubtle}` }}>
              <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                <span style={{ width: 6, height: 6, borderRadius: "50%", background: TONE_DOT[c.tone] }} />
                <span style={{ font: `600 13px/1 ${T.display}`, letterSpacing: "-0.01em", color: T.fg }}>{c.label}</span>
                <span style={{ font: `500 10px/1 ${T.mono}`, color: T.tertiary }}>{list.length}</span>
              </div>
              {c.wipMax != null && (
                <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
                  <span style={{ width: 34, height: 4, borderRadius: 2, background: T.sunken, overflow: "hidden", display: "inline-block" }}>
                    <span style={{ display: "block", height: "100%", width: Math.min(100, (list.length / c.wipMax) * 100) + "%", background: over ? T.danger : T.brand }} />
                  </span>
                  <span style={{ font: `500 9.5px/1 ${T.mono}`, color: over ? T.danger : T.tertiary }}>{list.length}/{c.wipMax}</span>
                </span>
              )}
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8, padding: 9, flex: 1, minHeight: 0,
              overflowY: "auto", overscrollBehavior: "contain" }}>
              {list.map((t) => <TicketCard key={t.id} t={t} onOpen={onOpenTicket} />)}
            </div>
          </div>
        );
      })}
    </div>
  );
}
