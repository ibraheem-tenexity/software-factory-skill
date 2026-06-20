# Concierge onboarding — backend API contract (Option C, draft model)

For the OnboardingScreen frontend (owner: mwbcupd9). Backend (this branch): the 4 draft endpoints +
the concierge agent. All endpoints are cookie-authed; run-scoped routes enforce ownership.

## Lifecycle

1. **On mount** — `GET /api/org` → `{org|null}`. `null` = first-time (show company setup); an org =
   returning (reuse, show Manage editor only).
2. **Eager draft (form is sole creator)** — `POST /api/drafts` → `{project_id}`. Create ONCE on mount and
   keep the id. Pass it into every write below AND into `POST /api/chat` as `project_id`, so the form and
   the Concierge rail share ONE draft (no create-race; chat never mints a second draft).
3. **Write-through (debounced / on-blur — NOT per keystroke)**:
   - Company: `POST /api/org` (first-time, creates+links user) / `PATCH /api/org` (returning edits).
   - Project: `PATCH /api/projects/{project_id}/draft`  body `{name?, goal?, scope?}` (any subset).
   - Materials: `POST /api/projects/{project_id}/attach` body `{files:[{name, content_b64|content, ...}]}`.
4. **Handoff** — `POST /api/projects/{project_id}/promote` body `{target?}` → `{project_id, status:"started"}`
   (409 if already promoted; 409 with detail on duplicate project name). Then switch to the build view.

## Endpoints (new in this branch)

| Method & path | Body | Returns |
|---|---|---|
| `POST /api/drafts` | `{project_name?, runtime?, planning_model?, impl_model?}` | `{project_id}` |
| `PATCH /api/projects/{id}/draft` | `{name?, goal?, scope?}` | `{name, goal, scope, description, brief, coverage}` |
| `POST /api/projects/{id}/attach` | `{files:[…]}` | `{attached:[paths]}` |
| `POST /api/projects/{id}/promote` | `{description?, target?}` | `{project_id, status:"started"}` |

All four 409 if the run isn't a draft (already promoted / nonexistent).

## Key rules

- **Scope is NOT a separate stored field for you to format.** Send `scope` as a `string[]` of
  work-area labels (e.g. `["Quoting / RFQ","Pricing & approvals"]`). The server composes the
  canonical `description = goal + "\n\nScope of work: a, b, c."` — `composeDescription` is DELETED from
  the frontend (single source of truth = the setter). The PATCH response echoes the composed
  `description` if you want to display it.
- **Project name == run name** — one value (`name` on the draft).
- **Company fields persist as LABELS** via `/api/org`: `industry`, `headcount`, `revenue`,
  `sub_focus[]` are label strings (e.g. `"51–200"`, `"$10M–$50M"`); `connected_systems` is a
  `string[]` of IDs (`epicor|sap|netsuite|qb|sf|site`); `designation`+`role_description` = the role.
- **Checklist + ready gate stay 100% frontend-owned, read-only on the backend.** The concierge's
  `get_intake_state`/`validate_intake_complete` are advisory for the agent only — the agent does NOT
  compute or push completion to your UI; your form owns it.

## Concierge tool ↔ endpoint mapping (so chat and form stay in sync)

The Concierge (rail) writes through the SAME state via these tools, which call the same Console/UserStore
paths your endpoints do — so a value set by chat shows up on the next form read and vice-versa:

| Concierge tool | Backend effect (same as your endpoint) |
|---|---|
| `get_company_profile` / `set_company_profile` / `set_connected_systems` | `/api/org` GET/POST/PATCH |
| `set_project_basics(name, goal)` / `set_project_scope(scope[])` | `PATCH /api/projects/{id}/draft` |
| `attach_project_materials` (ack) / files on the message | `POST /api/projects/{id}/attach` (auto on chat) |
| `request_materials(what, why)` | (chat-only signal; no endpoint) |
| `get_intake_state` / `validate_intake_complete` | read-only |
| `hand_off_to_factory(target)` | `POST /api/projects/{id}/promote` |
| `check_status` / `request_dep_input` / `get_result` | post-handoff (existing) |

Note: mid-session two-way live sync (form re-reading values the chat just wrote without a refetch)
needs a small frontend refetch/bridge on your side — the backend persists everything to the shared
draft, but it doesn't push form-state changes. Refetch the draft (`GET /api/projects/{id}/brief` +,
if useful, a small draft read) after a concierge turn if you want the form to reflect chat writes live.
