# Software Factory — Product Specification

Turns a described business problem into shipped, working software — guided end-to-end by one AI Concierge a non-technical operator can talk to like a competent colleague, not a form.

*Scope: customer product & Tenexity operator platform. Feature-level — what must be true for the user, not how it's built.*

## 1. Problem & opportunity

Mid-market industrial and IT-distribution companies run on a patchwork of spreadsheets, email, and legacy systems — Epicor, SAP, NetSuite, QuickBooks, Salesforce. They know exactly where the pain is: quoting takes too long, orders get re-keyed by hand, approvals live in someone's inbox. What they don't have is an engineering org, and traditional software vendors are too slow and too expensive for problems of this size. The company understands its own business better than any outside vendor ever will — it has simply never had a reliable way to turn that understanding into working software.

Software Factory closes that gap. A customer describes the problem, hands over the materials that show how the business actually works, and a supervised AI pipeline researches, designs, architects, tickets, builds, tests, and deploys the result — with a live guide (the **Concierge**) walking them through every step and letting them redirect it in plain language. The product is two things bound together: a **customer-facing product** that creates the value, and an internal operator platform, **Tenexity OS**, that keeps the whole factory healthy across every customer at once.

## 2. Who this is for

| Persona | Who they are | What they need from us |
|---|---|---|
| Operator / Owner | Runs or manages a piece of the business (ops, sales, IT). Not a developer. | To describe a problem in their own words and trust that it was understood — without learning "how to write a spec." |
| Org Admin | Sets up the company once — profile, systems, team, billing. Often the same person as the Operator at a small company. | A one-time setup that is never repeated, and confidence it's being reused correctly. |
| Returning user | Has already shipped one or more projects. | Zero repetition of anything the system should already know, and a faster path to the next project. |
| Internal Operator (Tenexity staff) | Supports every tenant and every project across the whole platform. | Visibility across the entire fleet, the ability to unblock or support any customer directly, and control over the agents and tools doing the work. |

## 3. Product principles

Six commitments that hold across every screen — the tests any new feature should be checked against before it ships.

1. **Never a blank, silent screen.** Anything loading from the network shows a placeholder shaped like the real content. Anything long-running shows visible, specific progress — never a spinner standing in for an unknown wait.
2. **One assistant, one identity, everywhere.** The guiding agent is the same character with the same voice on every project screen — onboarding, project home, the build board, documents. Only what it's talking about changes.
3. **Nothing is created by accident.** State-changing actions — creating a project, starting a build — are explicit, named actions with visible confirmation, never an implicit side effect of moving through a flow.
4. **Show sources, don't invent a score.** Every fact the system infers rather than the customer stated is traceable back to exactly where it came from — the specific file, upload, or answer — so the customer can judge it themselves. The system never asserts a confidence level it has no real way to compute.
5. **Progress is resumable, never fragile.** Everything the system produces during a build is saved permanently as it's produced. A failure or a pause must never mean starting over.
6. **Momentum beats completeness.** The product's job is to reach a *good* brief fast, not to interrogate for a *perfect* one. The customer can always say "that's enough, build it" — a longer intake is not automatically a better one.

## 4. Customer product

The surface that creates the value — from first sign-in through a shipped, living application.

### 4.1 Getting in: sign-in & access control
**Need:** Employees need a fast, familiar way to sign in, and the company needs assurance only people it has approved can get in.

**Capabilities:** Sign in with Google, Microsoft, company email/password, or the company's own SSO if it has one. Password recovery on the email/password path. A visible way to request access if not yet approved. Access is allow-list gated — an email must be explicitly approved before *any* sign-in method admits it.

**Feels like:** a modern SaaS login, fast for the 90% who use Google or Microsoft — while quietly enforcing that only approved people ever get past the door.

**Out of scope:** self-service signup with no approval step; MFA policy configuration (inherited from the identity provider).

### 4.2 Home base: the projects dashboard
**Need:** A returning user needs to instantly see the state of everything they're running, and start something new.

**Capabilities:** Projects listed and grouped as in-progress vs. deployed, with at-a-glance counts and spend for the month. Each row: owner, status (Draft / Needs input / Researching / Building / Deployed), progress, active agents, last activity, spend so far. Filter to one teammate's projects; start a new one from here. Archive a project (reversible); permanently delete an archived one (irreversible, requires confirming the project's name). Admins see a compact org-context preview with a path to manage it in full; non-admins simply don't see it — no disabled placeholder.

**Feels like:** knowing in five seconds whether anything needs you — nothing stale, nothing that looks broken while it's only loading.

**Out of scope:** cross-organization project views (that's Tenexity OS, §5); bulk operations on the list.

### 4.3 Set once, reused forever: organization context
**Need:** A company should never re-explain who it is on every project.

**Capabilities:** A canonical company profile (industry, sub-focus, HQ, founded, headcount, revenue band, website, footprint) — editable at any time. A shared knowledge base of company documents (price books, line cards, policies, SOPs), each showing how many projects have reused it. Connected business systems (ERP etc.), linked once at the org level and available to every future project. Team management — roles, invites — and visibility into plan, spend, and per-project breakdown.

**Feels like:** answering a question about your company exactly once, ever — and every future project already knowing it.

**Out of scope:** per-document granular permissions beyond project-only vs. org-wide; self-serve billing plan changes.

### 4.4 Starting a project: intake
**Need:** The factory needs enough context to build the right thing, and the customer needs giving that context to feel quick — especially the second time.

**Capabilities:**
- A guided form with a visible Concierge that adapts to first-time (walks through company setup too) vs. returning (skips straight to the project, showing what's already on file).
- A labeled split between "already known about your company" and "specific to this project," so nothing company-level is ever re-asked.
- Project name; a description of what's being built (renders simple formatting cleanly, not raw symbols); scope-of-work tags with the ability to add one not on the preset list; a choice of build engine, and whether the platform's own AI access or the customer's own credentials power it.
- Materials — a walkthrough video, documents — each with an auto-draftable description and a choice of Project-only vs. Org-wide (org-wide saves it to the shared knowledge base); existing knowledge-base documents can be pulled in instead of re-uploaded.
- A spend ceiling for the whole project, set from presets or a custom amount. **This is a promise, not a suggestion:** the build pauses for explicit approval before ever crossing it.
- **The project must be explicitly created before any of the above is usable.** Naming it and clicking Create is a real, immediate save — a draft project exists from that moment, not just in a browser tab. Everything downstream stays visibly locked until then; success is confirmed clearly, not implied.
- A way to leave at any point and resume later without losing progress, and a way to exit to the dashboard entirely.

**Feels like:** the first project takes real thought and a few minutes; every one after takes ninety seconds because the system already knows who you are.

**Out of scope:** collecting payment details during intake; grading the quality of uploaded materials (the system reads and describes them — it doesn't judge them).

### 4.5 Proving it understood: processing & interview
**Need:** After handing over documents and a video, the customer needs proof the system absorbed them correctly before real work — and real spend — begins, and should never sit staring at a frozen screen while a large file is read.

**Capabilities:**
- Visible ingestion progress — what's being read right now, how much is left, an estimate of time remaining — never a generic spinner.
- An option to keep working elsewhere while ingestion finishes in the background, with a clear indicator and an easy way back the moment it's done.
- A review step showing exactly what the system learned — each fact traced back to the specific file or answer it came from, so the customer can see where it came from and judge it for themselves. **Correcting a wrong assumption here must be cheap and obvious** — this is the single biggest trust risk in the product: an uncaught wrong assumption means the whole build starts from a bad premise, and there is no confidence score doing the customer's judgment for them.
- A short, focused follow-up conversation — one question at a time, offered as a quick multiple-choice when there's a clean set of likely answers, open-ended when the real answer needs nuance.
- Building only begins once the customer has confirmed what was learned and answered every outstanding question — there is no path to a build starting on unconfirmed assumptions. But per Principle 6, "enough" is decided by the customer's own "let's build it," not by exhausting every possible question.

**Feels like:** watching your own materials get "read" in real time — reassuring, not anxious — followed by a short, relevant conversation and a clear, satisfying "we're ready" moment.

**Out of scope:** editing extracted facts by directly rewriting them — correction happens by confirming and answering, not free-text overrides.

### 4.6 The always-on guide: Concierge
**Need:** From the first question through a build lasting hours or days, the customer needs one place to ask "what's happening" and one place to say "change this" — without learning a new interface per phase.

**Capabilities:** A persistent assistant panel on every project screen — intake, project home, build board, documents. The same tone and identity throughout; only its focus changes — checklist during intake, live narration during the build ("a test caught a bug, it's being fixed"), reminders during background processing, document-specific prompts on the documents view. A way to message it at any time, to ask a question or redirect the work in plain language. A running, clickable list of everything the pipeline has produced so far. A visible cue, during a build, that it's actively relaying live information rather than idle.

**Feels like:** one competent project manager who never leaves, always knows the current state, and will happily interrupt the build to explain what just happened.

**Out of scope:** answering questions about specific passages inside a document with inline citations to the exact source location — a stated future capability, not part of this version.

### 4.7 Checking in: project overview
**Need:** A single-page health summary, without opening the full build board, and a jumping-off point into deeper detail.

**Capabilities:** If not yet handed off: a clear "finish setup" banner and a checklist of what's outstanding (brief, scope, engine, materials) with one action to resume. Once building: goal, scope, owner, created date, build progress, tickets done, active agents, and spend against the cap — editable right on the page, reflected everywhere the cap appears. Which connected systems this project uses and their live status; who's working on it right now and on what; uploaded materials; produced documents (each opens in the Artifact Viewer); a summary of what was inherited from the org's shared context. One click through to the full build board.

**Feels like:** a mission-control snapshot — nothing is a mystery, nothing requires drilling in unless you want the detail.

**Out of scope:** editing scope or materials directly from this page — those edits route back through intake, keeping one source of truth.

### 4.8 The core experience: the build board
**Need:** The single most important screen in the product. The customer needs to see real progress, understand what's blocking it, and unblock or redirect it — without needing to understand the engineering underneath.

**Capabilities:**
- A top-level view of every stage the build passes through, in order — complete, active, or waiting.
- **Visible, actionable resilience:** if a build stalls or is paused, the customer sees exactly where and is offered clear choices — resume where it stopped, retry just the stuck part, or roll back and redo from an earlier point. Never a demand to start over; never silent loss of finished work.
- **A visible way to resolve external blockers:** when the build needs something from outside itself — access, a credential, a decision about a dependency — the customer sees exactly what's needed, why, and how many items remain, and resolves each without engineering help.
- The same progress shown three ways depending on how the customer thinks: a task-board view, a hierarchical view of what spawned what, and a visual map — same underlying truth, different lenses.
- Live spend against the cap, visible throughout.
- At 100%, one-click access to the finished application and its codebase.
- Every substantial document the pipeline produces along the way is inspectable the moment it exists — not withheld until the end.

**Feels like:** watching a competent team work through a glass wall — you always know what's happening, and when something needs you, it asks clearly and gets out of your way the moment you answer.

**Out of scope:** directly editing code, tickets, or architecture — control is conversational, via the Concierge and the specific unblock actions above.

### 4.9 Reading the work: the Artifact Viewer
**Need:** Every document or file the build produces needs one good place to actually read it — not a generic file download.

**Capabilities:** Opens full-page from anywhere a produced file is clickable; browsable and searchable across everything produced for a project. Each file displayed appropriately to its type — formatted text with a table of contents, diagrams as diagrams, code with line numbers, tables for tabular data, a browsable tree for a codebase, a frame grid for designs, images as images. Basic metadata on every file — type and last updated; copy and download actions.

**Feels like:** opening any artifact and having it look like it was made to be read — never a wall of raw markdown symbols.

**Out of scope:** in-place editing of produced artifacts by the customer (the SOW editor, §5.3, is the one place editing happens, and that's an operator tool).

## 5. Tenexity OS — the operator platform

A distinct surface for Tenexity's own staff, not customers — because someone has to keep the whole factory healthy across every tenant at once.

### 5.1 Platform pulse & cross-tenant visibility
**Need:** See the health of the entire platform at a glance, and drop into any single customer's project exactly as that customer sees it.

**Capabilities:** A platform-wide summary: customers, projects, agents currently active, today's spend. Every customer organization with project count, in-flight work, total spend, last activity — plus adding a new organization. Every project across every customer, filterable by organization, engine, owner, status, and real-vs-demo — opening straight into the exact overview/build-board/documents experience the customer sees, with a way back.

**Feels like:** one pane of glass for the whole business — zero friction from "something looks off in aggregate" to the exact screen the affected customer is looking at.

### 5.2 Managing who can sign in
**Need:** Access to the whole platform — every customer, plus internal staff — must be centrally controlled, not scattered per organization.

**Capabilities:** One master table of every person allowed to sign in anywhere: organization (or internal), role, sign-in method, status, last seen — filterable and searchable. Add a person: which organization or internal staff, their role, their sign-in method; for email/password, set a password directly or send a set-your-own invite link. "Invited" is a visible, distinct state that resolves to active on first sign-in. Edit anyone's role or method after the fact; resend/copy their invite; disable, re-enable, or remove entirely. A quick, standalone "provide access" action: invite someone as the admin of a brand-new organization, or as internal staff with full cross-tenant access.

**Feels like:** total confidence that access is centrally auditable — one place to answer "who can get in here, and as what."

### 5.3 Statements of work
**Need:** Every proposal the platform generates needs to be tracked, refined, and reused — not scattered across individual projects.

**Capabilities:** A master list of every SOW, each showing status, customer, and version; a reusable template so a new one never starts blank. An editor showing key details (customer, project, value, file) beside the written content, with live preview and a path to the full document viewer. A clear status progression: template → draft → in review → sent → signed.

**Feels like:** a lightweight, purpose-built proposal tool that never requires leaving the platform to track where a deal stands.

### 5.4 Every produced file, indexed
**Need:** One comprehensive index of literally everything the platform has ever produced, across every customer, findable without knowing which project it came from.

**Capabilities:** Every file produced by a build or authored by an operator, grouped by project, opening in the same viewer customers use. The SOW library (5.3) lives inside this same index, not as a separate silo.

**Feels like:** finding any file in seconds, whether or not you remember which project it came from.

### 5.5 Managing the agent workforce
**Need:** See every AI agent the platform runs, understand how well each performs, and adjust how each behaves.

**Capabilities:** A roster of every agent — role, status, underlying model, relative cost, autonomy/success track record. A visible warning when an agent's behavior appears to be drifting. Open any agent to edit its governing instructions, see which tools it can use, review its recent activity, and get AI-assisted suggestions for improving it.

**Feels like:** direct, confident control over the "employees" doing the actual work, with enough transparency to catch a misbehaving one early.

### 5.6 Tools & integrations registry
**Need:** Know every external tool, connector, or system the platform can call on behalf of any customer, and manage its availability centrally.

**Capabilities:** Summary counts — registered, connected, available. Every tool/connector: kind, provider, scope, auth, used-by count, live-or-needs-connecting status. Register a new tool; re-sync existing ones.

**Feels like:** knowing exactly what any agent, anywhere, is capable of reaching for — never surprised by a tool nobody registered.

## 6. Cross-cutting requirements

Not features of any one screen — properties every screen must have.

- **Loading states.** Nothing reading from a live source may render empty or pop in unstyled. Every list, card, table, or field shows a placeholder matching its eventual shape and size while loading.
- **Source transparency.** Anywhere the system presents a derived fact rather than one the customer explicitly stated, it's visibly traced back to exactly where it came from, so the customer always knows what came from them versus what was inferred — without the system asserting a confidence score it has no real way to compute.
- **Accessible control.** Every interactive element is clearly focusable and operable without a mouse.
- **No silent state changes.** Creating a project, starting a build, and other consequential actions are explicit and confirmed — never an implicit side effect of navigation.

## 7. Explicitly out of scope, this version

- Inline, pinpoint citations when the Concierge answers questions about a specific document (it can direct the customer to the right one; exact-passage citation is stated future work).
- Customer self-service billing or plan changes beyond viewing spend and the org's plan.
- Direct customer editing of code, architecture, or individual tickets — control stays conversational and via the build board's specific unblock/recovery actions.
- Bulk operations on the projects list.
- Granular per-document permissions beyond the project-only / org-wide toggle.
- MFA policy configuration (inherited from the identity provider in use).
- Editing extracted facts by directly rewriting them during the interview review.
- Real-time, multi-person co-authoring of a single project's brief — intake is designed for one primary voice at a time.
- Self-hosted / on-premise deployment for customers.
- A mandatory human code-review gate before every deploy — the trust model rests on visibility and control, not a required sign-off on every change.

## 8. Success metrics

**Adoption & activation**
- % of new organizations completing first-project intake (create → confirm interview → hand off) without abandoning.
- Time from account creation to first successful hand-off.
- Second-project intake time vs. first — the direct proof that org-level context reuse is actually saving time.

**Trust & comprehension**
- Rate at which customers accept system-inferred facts as-is vs. correct them — healthy when this trends toward "accept" because extraction improved, not because customers stopped checking.
- Concierge-escalation rate during builds — how often a customer needs to step in vs. the build proceeding unattended.

**Delivery reliability**
- % of builds reaching 100% without a customer-visible crash requiring manual recovery.
- Of builds that do stall, % successfully resumed vs. abandoned or restarted from scratch — the direct measure of whether checkpoint recovery works for customers, not just in theory.
- % of projects staying within their spend cap without a pause, and separately, how often approval pauses are actually granted — a very low grant rate signals the cap-setting UX itself is miscalibrated.

**Business outcomes**
- Deployed-project rate — % of created projects reaching "Deployed," not just "Building."
- Spend predictability — variance between a project's cap and its actual final spend.
- Operator leverage — how many customer organizations one Tenexity operator can support at acceptable quality, tracked alongside how often staff must manually rescue a stuck project (see Risk 5) so this efficiency metric can't be gamed by quietly doing the customer's job for them.

## 9. Prioritization

**P0 — nothing works without these.** Sign-in & access control (4.1); project creation and the explicit create-gate (4.4); processing & interview before any build (4.5); the build board with stage progress, crash recovery, and dependency resolution (4.8); the persistent Concierge shell (4.6); basic cross-tenant visibility (5.1) and sign-in management (5.2). Without this set, customers can't safely start or trust a build, and operators can't run the platform.

**P1 — required to feel complete, not just functional.** Org-level shared context & knowledge base (4.3); the projects dashboard with archive/delete (4.2); project overview (4.7); the Artifact Viewer (4.9); multiple build-board views beyond the minimum single view; agent roster management (5.5); the tools/integration registry (5.6).

**P2 — high value, can trail the initial release.** Statements of Work library (5.3); the full produced-files index (5.4); markdown polish in the project-goal field; "continue in background" during processing (a first release can ship with the customer simply waiting through ingestion, though this materially improves the experience for large uploads).

**Deferred by design, not merely deprioritized:** inline document citations in Concierge answers. It's called out explicitly as future work and should not be quietly smuggled into an earlier milestone at the cost of shipping speed.

**Sequencing logic:** the intake → processing → interview → handoff spine and the build board are the product's core promise. Everything else either makes that promise trustworthy at a glance (dashboard, overview, artifact viewer) or makes running the business behind it possible (all of §5). Ship the spine and the operator's ability to see and unblock any customer before investing in secondary views.

## 10. Risks & open questions

1. **The reflection-step trust risk.** If "what I learned" is wrong and goes uncaught, the whole build starts from a bad premise. What's the fastest, lowest-friction way to correct a wrong assumption mid-conversation — and how do we make correcting *cheap*, so people actually do it instead of shrugging and hoping it's fine?
2. **Question fatigue vs. brief quality.** Every additional question improves the brief but risks losing patience. Who — or what signal — decides "we have enough," and is that threshold the same for a five-minute project and a five-week one?
3. **Budget-cap trust runs in both directions.** Too aggressive a pause-for-approval interrupts flow and feels naggy; too permissive erodes the promise entirely. What's the right default, and should it adapt to project size rather than being one constant?
4. **The single-voice intake assumption.** Today's model assumes one person drives the conversation. Is there real demand for a second stakeholder to weigh in on the same brief before hand-off — and if so, does that live inside the Concierge conversation or outside it?
5. **When does internal rescue become a crutch?** If Tenexity OS makes it too easy for staff to manually save a stuck project, the platform may never learn whether the self-serve experience actually works unassisted. What's the guardrail that keeps "unassisted build rate" and "operator leverage" honest rather than quietly propped up by staff doing the customer's job?

---

*A note on how this was written: this specification reconciles two independently authored passes over the same design reference (the PRD), kept deliberately separate until synthesis, so a gap in one pass would not be quietly masked by the other. Where the two disagreed on structure or depth, the more complete treatment was kept; where one surfaced a risk or framing the other didn't, it was folded in rather than dropped for the sake of brevity.*
