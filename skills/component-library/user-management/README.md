# user-management (component-library · SOF-109)

A pre-designed, token-styled **user management** screen set — the archetype's Zone 7
(Admin / Settings) capability nearly every business app needs. The design stage composes it in;
the build stage swaps in the implementation and adapts it to the app's schema instead of generating
these screens from scratch. Format spec: [`docs/design/component-library.md`](../../../docs/design/component-library.md).

## Screens
- **users-list** (`design/users-list.html`) — users table (name/email, role, status, last active),
  search + role/status filters, invite action, per-row actions. **Shipped in v0.1.**
- **user-detail** — profile, role change, reset password, deactivate/reactivate. *Pending.*

## Contract
`manifest.json` declares the `data_interface` (the `User` entity + `listUsers`/`inviteUser`/
`setUserStatus`/`setUserRole`/`resetPassword` operations) the build stage wires to the real app, the
`permissions` (admin-only), and the `customization_points`. The build stage adapts this interface;
it does not re-derive the screens.

## v0.1 scope (this change)
Ships the **format-validating** pieces only — the `manifest.json` integration contract + the
token-authentic `users-list` design mockup — to prove SOF-109's AC-1 format end-to-end with a real
example. The **code template** (`template/`) and the `user-detail` screen follow once SOF-109's two
open decisions land (see the spec's *Open decisions*): the **storage** model (skill assets vs a DB
`components` registry) and the **template framework** (framework-neutral reference vs pinned stack).
Building the template before those would be rework. No pipeline code is wired by this change.
