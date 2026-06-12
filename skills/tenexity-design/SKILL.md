# tenexity-design — the Tenexity design canon

Vendored from `github.com/tenexity/tenexity-design-master` @ `624b8e4` (2026-06-12).
Apps built by this factory are Tenexity products: they must LOOK like one. This skill is
the source of truth for visual identity — it overrides any palette/typography suggestions
from other design skills when they conflict.

## Files

- `tokens.css` — THE design tokens (CSS custom properties, HSL, light-first). Brand:
  `--brand: 214 100% 55%` (Tenexity Blue #1A7BFF). Copy this file into the app
  (e.g. as the base of `index.css` / `globals.css`) — do not retype values.
- `tailwind.config.ts` — the Tailwind theme mapping over those tokens. Adapt the
  content globs to the app; keep the theme block intact.
- `PATTERN_MATRIX.md` — which UI pattern to use for which job (worklist, detail,
  dashboard, configurator…). Pick the matching archetype before inventing layout.
- `application-archetype.md` — the canonical application shell: sidebar nav, page
  headers, card grammar, table conventions.

## Rules (Stage 2 design + Stage 3 build)

1. The design doc (Stage 2) must name the archetype(s) chosen from PATTERN_MATRIX.md
   and use the token names (not raw hex) when specifying color/spacing/type.
2. The built app (Stage 3) must ship `tokens.css` verbatim (additions allowed,
   deletions/edits of existing tokens are not) and reference colors via the tokens
   (`hsl(var(--brand))` / Tailwind theme keys), never hard-coded hex.
3. Buttons, inputs, cards, tables follow the shadcn-over-tokens grammar in
   `tailwind.config.ts` — radius `--radius`, borders `--border-*`, text `--text-*`.
4. Status colors: use `--success/--warning/--destructive` — never ad-hoc greens/reds.
5. VERIFICATION (gate): the deployed app's served CSS must contain the literal token
   `--brand: 214 100% 55%`. The happy-flow gate includes this check; an app that
   restyles the brand fails the gate.
