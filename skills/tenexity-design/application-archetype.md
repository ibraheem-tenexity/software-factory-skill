---
name: Application archetype
description: Functional anatomy of every Tenexity workflow app — the seven canonical zones (Dashboard / Worklist / Detail / Collaboration / Agent Console / Insights / Admin), what each contains, where the agent lives in each, and how they fit together. Source for every app build going forward.
type: design
---

# Tenexity Application Archetype

Every Tenexity workflow app solves a function (collect cash, ingest invoices,
quote orders, etc.). Every one of them is built from the same seven canonical
zones. This is the operator-product equivalent of "every page has a header,
hero, body, footer." Memorize these — when we build a new app, we build these
seven zones in this order.

The neighborhood: Linear (worklist + detail + activity), Attio (record-centric
detail + activity), Ramp (worklist + bulk approve + side panel), Pylon
(triage queue + thread), Temporal (run history + decision trace), Microsoft
Copilot Studio (multistage approval + agent flow), Smashing's real-time
dashboard UX work (decision-oriented dashboards).

## The seven canonical zones

| # | Zone | Verb | Who uses it | Where the agent lives |
|---|---|---|---|---|
| 1 | **Dashboard** | *Sense* | Manager / lead, 30 sec | Daily brief + anomaly callouts |
| 2 | **Worklist** | *Triage* | Operator, primary surface | Pre-sort + auto-disposition + bulk apply |
| 3 | **Detail** | *Resolve* | Operator, deep work | Co-pilot side panel: summarize + draft + act |
| 4 | **Collaboration** | *Discuss* | Cross-functional | Mention `@agent` to ask/draft/act |
| 5 | **Agent console** | *Govern* | Owner / admin | Mission, playbooks, autonomy, live feed (already built) |
| 6 | **Insights** | *Learn* | Manager + exec | Trend charts, calibration, cost vs saved |
| 7 | **Admin / Settings** | *Configure* | Admin | Roles, integrations, data sources, SLAs |

A working app has all seven. A *great* app makes zones 1→2→3→4 feel like one
continuous motion (sense → triage → resolve → discuss) and keeps 5→6→7 as
governance surfaces operators visit weekly, not daily.

---

## Zone 1 — Dashboard (Sense)

**Mandate:** In 30 seconds, tell the operator what changed, what's at risk,
and what the agent did overnight.

**Required parts (top to bottom):**

1. **Pulse strip** — 4-7 KPIs in a horizontal row, each showing today's value,
   delta vs yesterday/last week, sparkline. Tabular nums. Click → filtered
   worklist.
2. **Daily brief card** — agent-written 3-bullet summary of the last 24h
   (Georgia title, body in Hanken). "Touchless rate held at 78%. Three vendors
   flagged for invoice anomalies. $42k of payments queued for your approval."
   Each bullet links to the specific worklist filter that proves it.
3. **Anomaly / next-best-action panel** — the 3-5 things that need a human
   today, ranked. Each has a one-click "Take action" button that drops the
   user into the right Detail view.
4. **At-risk strip** — items breaching SLA in the next N hours. Red bar that
   pulses on breach.
5. **Trend tiles** (optional, 2-4) — small charts for the leading indicators
   the operator cares about (DSO, touchless %, exception backlog).

**Where the agent lives:**
- Writes the daily brief.
- Detects anomalies and proposes the next-best-action list.
- Each item has a confidence chip and a "Why?" reveal.

**What this zone is NOT:**
- Not a 47-tile data warehouse. Operators don't want every metric — they want
  the 5 that drive their day.
- Not interactive analytics. That's the Insights zone.

---

## Zone 2 — Worklist (Triage)

**Mandate:** The primary screen. Show every open item, sortable, filterable,
keyboard-navigable, with bulk actions and saved views.

**Required parts:**

1. **Tab strip** — system-defined buckets (e.g. AP: New / Matched /
   Exceptions / Approvals / Paid). Each tab has a count chip with severity
   color.
2. **Saved views rail** — left side or top dropdown. User-created filters
   ("Past 60d, my customers, > $5k"). Sharable.
3. **Filter + sort bar** — column-aware filters; sort by any column. State
   stored in URL.
4. **Density toggle** — comfortable (44px row) default; compact (32px) for
   power users.
5. **The table itself** — `DataTable` with checkbox column, status pills,
   confidence chips on agent-touched values, sparkles on agent-resolved rows,
   tabular nums for $ and dates.
6. **Bulk action bar** — appears when rows selected. Approve / Reject /
   Reassign / Snooze / Run playbook / Export. Keyboard shortcuts shown.
7. **Quick-peek side panel** — preview row without leaving the worklist.
   Press `Space` or click a row to peek; `Enter` to open full Detail.

**Where the agent lives:**
- Pre-sorts the worklist by priority (confidence × $ × SLA risk).
- Shades agent-resolved rows with a subtle blue tint until confirmed.
- Confidence chip on every value the agent touched.
- Bulk action: "Approve all similar to selection" with a safe-rollout %.
- Empty state when the worklist is clean: "Ledger handled 47 items overnight.
  Nothing for you here." — celebrates the agent's work.

**Patterns to enforce:**
- URL-driven state (every filter, sort, selection lives in the URL).
- Keyboard-first: J/K up/down, X to select, Y/N approve/reject, E to edit.
- Stable row identity across re-sorts (no jumpy UI when status changes).

---

## Zone 3 — Detail (Resolve)

**Mandate:** Everything you need to resolve one item, on one screen, no
modals. Three columns: context · primary work area · co-pilot.

**Required parts (3-column layout):**

**Left rail — Context strip (240-280px):**
- Record ID + status pill + assignee
- Key facts (parties, amounts, dates) — tabular, scannable
- Linked records (PO, invoice, vendor, customer) as `CrossAppLink`s
- Document thumbnails (invoice PDF, PO PDF) with one-click open
- SLA bar + escalation timer
- Audit summary: "Agent touched 12 fields. Last edit by Maya 4m ago."

**Center column — Primary work area:**
- The artifact itself (invoice line items, customer 360, quote builder).
- Inline-editable fields with `ConfidencePill` on agent-populated values,
  `UncertaintyRange` on numerical estimates.
- Per-line action buttons (override, approve line, flag).
- Sticky action bar at the bottom: primary action (Approve · Send · Post),
  secondary (Reject · Modify · Snooze), tertiary (Reassign · Comment).

**Right rail — Co-pilot panel (320-360px, collapsible):**
- `AgentHeader` (the app's named agent, e.g. Ledger)
- **Summarize tab** — 2-3 bullet plain-English summary of the record
- **Suggest tab** — agent's recommendation with reasoning trace
- **Act tab** — buttons to run a playbook on this record ("Run 3-way match",
  "Draft dunning email", "Generate JE")
- **Ask tab** — chat-style: "Why did the agent reject line 3?", "Show me all
  invoices from this vendor with similar variance"

**Where the agent lives:** the right rail *is* the agent. It is always
present in the Detail zone; it is the operator's pair.

**Patterns to enforce:**
- No modals for resolution actions. Modals are reserved for destructive
  confirmations only.
- Optimistic UI for every action; rollback on failure with a toast + undo.
- "Why?" reveal on every agent-touched field shows the prompt + tools used.

---

## Zone 4 — Collaboration (Discuss)

**Mandate:** Comments, mentions, threads, activity log — humans (and the
agent) discussing one item or one queue. Lives inside Detail (per record)
and at the queue level (per saved view).

**Required parts:**

1. **Activity timeline** — chronological log of every event (status change,
   field edit, agent action, comment). Each event has an actor (avatar) and
   a relative timestamp. Agent actions get a sparkle.
2. **Comment composer** — markdown, mentions (`@maya`, `@agent`, `@finance-team`),
   file attachments, emoji reactions. Threaded replies.
3. **Mention-to-action** — `@agent draft a dunning email for this customer`
   triggers the agent inline; reply appears as a draft message with Approve /
   Modify / Reject.
4. **Watchers** — who's subscribed; subscribe/unsubscribe with one click.
5. **External shares** — generate a redacted share-link to send to a vendor
   or customer for a specific question.

**Where the agent lives:**
- The agent is a first-class participant. `@agent` mentions invoke it.
- Agent-authored comments are styled with a subtle blue-tinted bubble + sparkle.
- Drafts the agent generates on behalf of a human appear as "drafted by
  Ledger for Maya — Send · Modify · Discard".

**Patterns to enforce:**
- Mentions across people, agents, and roles use the same `@` syntax.
- Activity events that the agent caused are attributable: "Ledger auto-coded
  this invoice using the PO-48190 template" — never anonymous.
- Read receipts on @mentions for SLA tracking on cross-functional asks.

---

## Zone 5 — Agent console (Govern)

**Already built (commit 1).** Mission · Playbooks · Autonomy. Commit 2 will
add Live · Approval · Escalation · History · Calibration.

**Where it sits in the app:** top entry in every app's sidebar, sparkle icon.
Operators visit it when they want to govern, not when they want to work.

---

## Zone 6 — Insights (Learn)

**Mandate:** "How is this function performing over time, and why?" Trend
analysis, calibration, cost economics. Manager + exec audience.

**Required parts:**

1. **Time-range selector** — 7d / 30d / 90d / QTD / YTD / custom.
2. **Goal vs actual cards** — per-KPI, with progress bar to target and
   trend sparkline.
3. **Cohort tables** — performance by vendor, customer, product, region.
4. **Agent calibration card** — claimed confidence vs actual accuracy, drift
   alert if > 8%.
5. **Cost economics card** — agent cost (tokens × $) vs human-hours saved
   ($ saved). Net ROI.
6. **Failure-mode breakdown** — top 5 reasons items escalated this period,
   with click-through to the underlying cases (closes the loop into Worklist).

**Where the agent lives:**
- Writes the period summary (Georgia headline + Hanken bullets).
- Surfaces "What changed and why" — anomaly explanations.
- Suggests playbook tuning ("Confidence floor of 0.85 caused 23 unnecessary
  escalations this week — consider lowering to 0.78 for vendors in the
  approved list").

**What this zone is NOT:**
- Not a self-service BI tool. Push the operator into a worklist filter, not
  into a chart drill-down rabbit hole.

---

## Zone 7 — Admin / Settings (Configure)

**Mandate:** Per-app configuration. Roles, integrations, SLAs, notification
preferences, data-source mappings.

**Required parts:**

1. **Roles & permissions** — who can view, approve, override caps.
2. **Integrations** — links into the Integration Workbench, scoped to this app.
3. **SLAs & escalation paths** — time-to-respond, time-to-resolve, on-call rota.
4. **Notification rules** — what triggers email/Slack/Teams to whom.
5. **Templates** — email templates, JE templates, comment macros.
6. **Data dictionary** — fields, types, validation rules, agent-writable flag.

**Where the agent lives:** read-only here. Settings configure the agent;
the agent doesn't configure itself.

---

## How the seven zones flow together

```
       Sense                Triage             Resolve               Discuss
    [Dashboard]  ── click → [Worklist] ── enter → [Detail] ── @ment → [Collab thread]
        ▲                       │                    │                     │
        │                       │                    │                     │
        │                       └─── bulk approve ───┘                     │
        │                                                                  │
        └──────────────── Insights (weekly) ──── Agent console (govern) ───┘
                                                       │
                                                  Admin (configure)
```

**The hot loop is 1→2→3→4.** Operators live there. Zones 5/6/7 are weekly
or as-needed.

---

## What every app must ship (the checklist)

When a new app is built, it must contain:

- [ ] Dashboard with pulse strip + daily brief + anomaly panel
- [ ] Worklist with tabs, filters, saved views, bulk actions, keyboard nav
- [ ] Detail with 3-column layout (context · work · co-pilot)
- [ ] Activity timeline with comments, mentions, agent participation
- [ ] Agent console with all 6 tabs (Mission/Playbooks/Autonomy already built)
- [ ] Insights with calibration + cost economics
- [ ] Admin with roles, integrations, SLAs, templates

If any are missing, the app is incomplete.

---

## Where the agent shows up — at-a-glance map

| Zone | Agent surface |
|---|---|
| Dashboard | Daily brief author + anomaly proposer |
| Worklist | Pre-sort, confidence chips, "approve all similar" |
| Detail | Right-rail co-pilot (Summarize/Suggest/Act/Ask) |
| Collaboration | First-class `@agent` participant |
| Agent console | The agent itself |
| Insights | Period-summary author + tuning suggestions |
| Admin | Read-only target of configuration |

The agent is not in a separate app. It is woven into every zone, with the
console as the governance backstop.

---

## Why this archetype works

- **Predictable for operators** — once you learn one app, you've learned them all.
- **Cheap to build** — a new app is a new dataset + new playbooks slotted into
  the same seven shells.
- **Forces the agent into the work** — by reserving a co-pilot slot in Detail
  and a brief slot in Dashboard, every app ships with the agent visible.
- **Separates work from governance** — the hot loop (1→4) is uncluttered;
  governance (5→7) is one click away but doesn't pollute daily work.
- **Best-in-class neighborhood** — Linear, Attio, Ramp, Pylon, Temporal, and
  Copilot Studio all converge on this shape. We are the agent-native version.
