# Component Library — format definition (SOF-109 · milestone E)

**Status:** AC-1 proposal (format definition). The relationship to recipes is a proposal pending
gyogcl1y (recipes-program owner) + operator/design sign-off — see **Open decisions**.

## Why

Nearly every business app the factory builds needs the same governance capabilities — user
management, access/roles, auth, settings, an audit log. Today the design + build stages regenerate
these from scratch every run: slower, more tokens, and inconsistent screen-to-screen. This library
ships them **once**, pre-designed on the token system and pre-built as adaptable templates, so the
design stage composes them in and the build stage **swaps + customizes** instead of generating.

## Where it sits (relationship to what already exists)

Three existing systems this extends — it introduces **no competing mechanism**:

| System | Grain | Owns |
|---|---|---|
| **Application archetype** (`skills/tenexity-design/application-archetype.md`) | the 7 canonical zones every app is built from | the compositional framework |
| **Design tokens (B2)** (`tenexity-design`, `tokens.css` → `--brand: 214 100% 55%`) | visual primitives vended into every app | look/brand consistency |
| **Recipes** (`recipes` table: `body_md` + `repo_url`) | fork-and-extend a **whole seed app** | coarse, whole-app starting point |

A **library component** is the missing middle grain: a **reusable implementation of one archetype
capability-zone** (primarily Zone 5 *Agent console / Govern* and Zone 7 *Admin / Settings*), built
on the tokens, composable into **any** app — whether that app started from a recipe seed or from
scratch. Components are **complementary to recipes**, not an alternative to them: a recipe seeds a
whole app; components fill in the common capability-zones of any app.

## What a component is (the three parts — AC-1)

Each component is a versioned directory under `skills/component-library/<component-id>/` (bundled
skill asset, isolated from application packages, same as the other `skills/` — see CLAUDE.md
"vendored resources … isolated from application packages"):

```
skills/component-library/<component-id>/
  manifest.json          # the integration contract (below)
  design/                # 1. DESIGN MOCKUP — tokens-based static HTML per screen
    <screen-id>.html     #    same shape the build stage already consumes at context/mockups/<id>.html
  template/              # 2. CODE TEMPLATE — the pre-built implementation
    ...                  #    framework-neutral reference impl on the design tokens; wired to a
                         #    documented data/permission interface, NOT to a specific app's schema
  README.md              # what it is, the screens it covers, the archetype zone(s) it fills
```

1. **Design mockup** (`design/*.html`) — static, token-styled HTML per screen, byte-identical in
   shape to what the design stage already emits at `context/mockups/<SCREEN_ID>.html` (SOF-99/100),
   so the build stage's existing WYSIWYG check (`design_refs` → open `context/mockups/<id>.html`)
   works unchanged.
2. **Code template** (`template/`) — the pre-built implementation on the token system, wired to a
   **documented interface** (the data shape + permission checks it expects), not to any one app's
   schema. The build stage adapts this interface to the real app rather than generating the screen.
3. **Integration contract** (`manifest.json`) — the machine-readable glue:

```jsonc
{
  "id": "user-management",
  "version": "1.0.0",
  "name": "User management",
  "archetype_zones": ["admin-settings"],          // which archetype zone(s) this fills
  "capabilities": ["invite user", "deactivate user", "reset password"],
  "screens": [                                     // each maps a design mockup ⇄ template entry
    { "screen_id": "users-list", "mockup": "design/users-list.html", "template": "template/UsersList" },
    { "screen_id": "user-detail", "mockup": "design/user-detail.html", "template": "template/UserDetail" }
  ],
  "data_interface": {                              // what the template needs the app to provide
    "entities": ["User { id, email, name, role, status, last_active }"],
    "operations": ["listUsers", "inviteUser(email,role)", "setUserStatus(id,status)"]
  },
  "permissions": ["admin"],                        // roles that may reach these screens
  "tokens": "required",                            // asserts the app vends tokens.css (B2)
  "customization_points": ["extra profile fields", "SSO providers", "invite copy"]
}
```

## How the stages use it

- **Stage 2 (design)** — when the PRD calls for a capability a component covers, the design stage
  **references the component** in its `design-spec.md` + copies the component's `design/*.html` into
  the run's `context/mockups/` (tagged with the component id + version) instead of designing those
  screens from scratch. The archetype zone the component fills is marked "provided by
  `<component-id>@<version>`".
- **Stage 3 (build)** — for a ticket whose `design_refs` point at a component-provided screen, the
  build sub-agent **starts from the component's `template/`** and adapts its `data_interface` to the
  real app's schema + wires the declared `permissions` — customization, not from-scratch generation.
  The existing happy-flow + review gates are unchanged (a component screen is verified like any other).

Both are **prompt-level seams** (the stage SKILLs reference the catalog), consistent with
minimum-machinery — no new gating engine. This mirrors CBT-9's fork-and-extend framing for recipes,
applied at the component grain.

## First components to ship (AC-2: ≥3)

Chosen because they recur in nearly every app and map cleanly onto governance zones:

1. **user-management** — users list + detail, invite, deactivate, reset (Zone 7 Admin/Settings).
2. **access-roles** — roles list, role→permission matrix, assign role to user (Zone 7).
3. **settings** — app settings groups (profile, integrations, data sources, SLAs) (Zone 7).

(`auth` and `audit-log` follow once the format is confirmed.)

## Acceptance-criteria mapping

- **AC-1 (format defined):** this document — the three parts + the `manifest.json` integration
  contract + the stage seams.
- **AC-2 (≥3 components):** the three above, authored to this format.
- **AC-3 (benchmark app uses ≥2 with token consistency):** a benchmark run whose design stage
  composes ≥2 components; verified by the existing brand-token gate + Playwright happy-flow.
- **AC-4 (measurably cheaper/faster):** compare stage-2+3 tokens/cost for the component-covered
  screens vs a from-scratch control run of the same screens.

## Open decisions (need sign-off before AC-2 build)

1. **Component ↔ recipes relationship** — this doc proposes *complementary* (component = capability
   grain; recipe = whole-app seed). @gyogcl1y (recipes owner) to confirm, or direct that components
   ride the recipes storage/mechanism instead. **Blocks the storage decision (#2).**
2. **Storage** — bundled skill assets under `skills/component-library/` (this proposal, matches how
   skills/tokens ship) vs a DB `components` table analogous to `recipes` (operator-editable via an OS
   admin screen). Recommend skill-assets first (versioned in git, no migration); add a DB registry
   only if operator-editing is wanted.
3. **Framework of the code template** — the factory builds apps in a stack the build stage picks per
   run. Recommend the template be a **framework-neutral reference impl on the tokens** + a clear
   data/permission interface, so the build stage ports it into the run's actual stack (vs pinning one
   framework). Design-agent input wanted.
4. **"Absorbs Nick's Templates"** — reconcile this format against whatever "Templates" spec Nick has
   so we ship one concept, not two (operator to point at that source if it exists).

---
*SOF-109 · this is the AC-1 deliverable, delivered as a doc for review before any component is built.
No pipeline code is wired by this change.*
