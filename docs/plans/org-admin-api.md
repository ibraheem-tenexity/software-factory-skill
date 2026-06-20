# Org Admin backend API (PRD §2.3)

Contract for the OrgAdmin frontend (`orgproject.jsx → OrgAdminScreen`, owner: mwbcupd9).
Branch `worktree-org-admin-backend` off `main`. Status: **shipped, tests green on isolated DB.**

All routes resolve the organization from the **caller's session** — there is no `org_id` in any
path. Auth model:

- **Reads** (`GET`) require an org on file for the caller → `404 {"detail":"no org on file"}` if none.
- **Writes** (`POST`/`PATCH`/`DELETE`) require the caller's role to be `admin` → `403` otherwise.

Already-existing routes the OrgAdmin screen also uses (unchanged — not in this branch):
`GET/POST/PATCH /api/org` (Company profile + Connected systems).

---

## 1. Knowledge base (org-scoped docs + reuse count)

| Method | Path | Auth | Body | Returns |
|---|---|---|---|---|
| GET | `/api/org/docs` | member | — | `{docs: [Doc]}` |
| POST | `/api/org/docs` | admin | `{name, tag?, content_type?, data_b64}` | `{doc: Doc}` |
| POST | `/api/org/docs/{doc_id}/use` | member | `{run_id}` | `{used_count}` |
| DELETE | `/api/org/docs/{doc_id}` | admin | — | `{ok: true}` |

`Doc` = `{id, name, kind, tag, size_bytes, content_type, used_count, updated}`
- `kind` ∈ `pdf | xlsx | csv | doc | video | img` (derived from filename ext; default `doc`) — maps to your `FILE_KIND` tiles.
- `size_bytes` int, `updated` epoch seconds — **format in the UI** (you already format tiles).
- `used_count` = number of distinct projects that imported the doc (`COUNT(DISTINCT run_id)`).
- Empty KB → `{docs: []}` (200). `404` only when the caller has no org → your graceful-empty path still works.

Upload: send the file bytes base64-encoded in `data_b64`. `400` on a missing `name` or invalid base64.
`/use` is what the OptionC "import from org" picker calls to bump the count (idempotent per project);
until imports wire up, counts are honestly `0`.

## 2. Team & access (members / roles / invite)

| Method | Path | Auth | Body | Returns |
|---|---|---|---|---|
| GET | `/api/org/members` | member | — | `{members: [Member]}` |
| POST | `/api/org/members` | admin | `{email, role?, designation?}` | `{members: [Member]}` |
| PATCH | `/api/org/members/{email}` | admin | `{role?, designation?}` | `{members: [Member]}` |
| DELETE | `/api/org/members/{email}` | admin | — | `{members: [Member]}` |

`Member` = `{email, role, designation, you}` — `role` ∈ `admin | member`, `you` = is the caller,
`designation` = the self-described title ("Operations", "Sales"). Every mutation returns the full
refreshed list. `400` on missing email (invite); `404` if `{email}` is not a member of this org.
**Do not use `/api/users`** for this — that's the global cross-org directory (super-admin) and would
leak other orgs' users inside a tenant's screen.

## 3. Usage & billing (plan / spend / per-project)

| Method | Path | Auth | Body | Returns |
|---|---|---|---|---|
| GET | `/api/org/usage` | member | — | Usage |
| PATCH | `/api/org/billing` | admin | `{plan?, monthly_budget_cap?}` | `{plan, monthly_budget_cap}` |

`Usage` = `{plan, monthly_budget_cap, spent, active_projects, total_projects, by_project: [Proj]}`
`Proj` = `{run_id, name, spent_usd}` (sorted by spend desc).
- The server rolls up **all** org members' runs (a member client can't — it only sees its own).
- `spent` = sum of each run's lifetime spend (no reliable per-month boundary → total-to-date, not month-windowed).
- `total_projects` = all org projects; `active_projects` = building now (not budget-stopped, not held, not yet shipped).
- Card mapping: Plan card = `plan` + `monthly_budget_cap`; "Spent this month" = `spent` (with `spent/monthly_budget_cap` for the % hint); "Active projects" = `total_projects` (hint `active_projects` building now); "Spend by project" rows = `by_project` (compute bar widths client-side).

---

### Schema (migration `0004_org_admin`)
- `blobs.name`, `blobs.tag` (display filename + category)
- `blob_uses(id, blob_id, run_id, created_at)` — reuse links
- `organizations.plan`, `organizations.monthly_budget_cap`

### Note on the run→project rename
This lands before 40zxvvrk's `run→project` sweep. Afterward `run_id`→`project_id`,
`/api/runs`→`/api/projects`, etc.; the `/api/org/*` routes here keep their shape, only the
`run_id` field in `/docs/{id}/use` and `by_project[].run_id` get renamed in the sweep.
