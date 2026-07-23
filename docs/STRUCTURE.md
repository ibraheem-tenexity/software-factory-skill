# Backend Structure Direction

## Purpose

Software Factory is moving to a **bounded-context modular monolith**. This is the canonical
reference for backend organization during the refactor and for new backend work afterward.

The objective is not to maximize the number of packages or to apply Clean Architecture ceremony.
The objective is code that an operator can read by following one capability: fewer pass-through
layers, fewer mixed-responsibility files, and fewer duplicate workflows. HTTP, CLI, database,
queue, artifact, and agent behavior remain unchanged while internal code moves.

## Program constraints and assessment basis

This direction was chosen after an audit of all **153 tracked non-test Python files** on the
`staging` baseline. The scope is backend Python: application package, FastAPI console, scripts,
migrations, resources, and bundled Python tooling. Tests were intentionally outside the audit.

- This is a large coordinated restructuring, not a feature rewrite. Preserve existing behavior;
  internal import paths and internal module locations may change.
- Code reduction is an explicit outcome. Removing duplication and pass-through indirection is as
  important as moving files into a prettier tree.
- The structural direction applies to parallel development immediately. New work follows the
  target ownership rules even while legacy modules still exist; do not create a second competing
  structure beside the target one.
- A behavior-preserving refactor plan is the next artifact after this decision record. It will
  name moves, consolidations, compatibility shims, verification points, and deletion candidates.

The audit found a sound general dependency direction (transport imports application code) but a
flat 60-module package root, oversized mixed-responsibility workflow modules, and several generic
layers that merely forward calls. It also distinguished deliberate isolation from clutter:
Alembic history, vendored Langfuse code, bundled skills, focused algorithms, provider adapters,
and stable data contracts are not consolidation targets.

## Target shape

```text
src/software_factory/
  api/             FastAPI app factory, dependencies, capability routers, wire schemas
  projects/        state, lifecycle, drafts, materials/artifacts, read projections
  execution/       stage orchestration, runtime agents, tickets, swarm adapter
  conversation/    chat agent, prompts, tool assembly, persistence, provider rendering
  memory/          ingestion/search algorithms and one memory persistence boundary
  identity/        users, organizations, roles, membership, authorization
  admin/           staff-facing projections and operations
  ingestion/       upload pipeline, extractor routing, DOCX/PDF specializations
  research/        public research facade, providers, parsing
  evaluation/      judge, autopsy, score persistence orchestration
  cleanup/         GitHub/Railway reaping policy and reporting
  integrations/    Railway, GitHub, Linear, OpenAI, notifications, storage clients
  infrastructure/  database connection/models/migrate, environment, filesystem, process runner
  workers/         run supervisor started by API lifespan, not owned by the API package
  cli/             thin command adapters
```

The target is not one file per directory entry. Each context should use as few modules as its
real responsibilities allow. A substantive module with several closely related functions is
better than a collection of single-function files.

## Ownership rules

1. **Organize by capability, not generic layer.** A feature package owns the application policy
   for one business capability. Put a function beside the workflow that calls it, not in a
   catch-all utility module because it is technically reusable.
2. **Keep functions together by change reason.** Split a module only when callers, external
   dependencies, or policy diverge. File length alone is not a reason to split.
3. **Every boundary earns its cost.** A repository, service, helper, or interface must own SQL,
   policy, mapping, lifecycle, or an external provider boundary. A layer that only forwards a
   method call is removed or folded into its owner.
4. **Transport stays thin.** Routers serialize/validate HTTP and translate errors; CLI modules
   parse arguments and render results. Neither owns project workflows, persistence choreography,
   or provider policy.
5. **Workers own lifecycle policy.** ASGI startup starts/stops a worker. Stage advancement,
   recovery, reaping, health policy, and boot coordination belong to the worker/application
   boundary rather than to the FastAPI package.
6. **Integrations own provider mechanics.** Railway, GitHub, Linear, OpenAI, storage, and
   notification clients own request/response transport and provider parsing. They do not own
   project, stage, or tenant policy.
7. **Queries are named.** Cross-context reads for project views and admin dashboards live in
   explicit query/projection modules. Do not accumulate them in a generic service facade.
8. **Shared means genuinely shared.** Promote code into `infrastructure/` or `integrations/` only
   after it has a stable shared owner. Do not add an abstraction for a single current caller.

## Required dependency direction

```text
api / cli / workers
        ↓
feature contexts: projects, execution, conversation, identity, memory, ...
        ↓
integrations and infrastructure
```

- Feature contexts may use one another through a narrow, explicit operation or projection.
- Infrastructure and integrations never import API, CLI, or feature policy.
- API and CLI packages must not become alternate homes for application behavior.
- Avoid a new generic `utils.py`, `common.py`, or global service locator. Extract a shared module
  only when it has a specific owner and stable responsibility.

## Current consolidation direction

The following are refactor targets, not permission to change behavior:

| Current area | Direction |
| --- | --- |
| `software_factory.console` | Compatibility exports only. Production composition imports `ExecutionService` from `execution/service.py`; preserve this path for active operator scripts and external callers until they migrate. |
| `execution/{prompts,process,service}.py` | Stage request/prompt construction and OS launch mechanics are separate from the current execution owner: lifecycle, recovery, budget enforcement, provision, promotion, gates, dependency handoff, and run status. `service.py` is a deliberate intermediate consolidation, not a new catch-all: project queries/mutations move to `projects`, and teardown/reapers move to `cleanup` in subsequent coherent slices. |
| `workers/supervisor.py` | The autonomy loop: boot sweep, run supervision, auto-advance, recovery/reaper ticks, log flush, health, and ASGI lifespan. It reads the application singleton at call time, but no longer belongs to the HTTP console package. |
| `conversation/dock.py`, `conversation/persistence.py` | The project chat dock and its durable conversation history/tool-trace persistence. `console/chat_dock.py` and `console/chat_persistence.py` are compatibility exports only. |
| `projects/intake.py` | Own draft creation, intake updates, material attachment, product-brief reads, BYOK credential references, repository-access projection, and project path composition. Production callers use the explicit `ExecutionService.intake` owner until application composition moves out of the execution service. |
| `projects/materials.py` | Own project-material persistence, document projection, ingestion kickoff/regeneration, and deletion across storage, blobs, memory, input files, and artifact records. The router retains wire validation and HTTP error translation only. |
| `projects/records.py` | Own coherent read-only projections over project state, tickets, agents, artifacts, deployments, and activity. Production callers use the explicit `ExecutionService.records` owner while execution compatibility methods remain. |
| `projects/product_brief.py` | Own the versioned canonical Product Brief (SOF-244): read latest / list versions / read one historical version / create a new version, over the append-only immutable `kind='product_brief'` artifact stream. Direct human edits (`origin='user'`) and Concierge finalization (`origin='agent'`) converge on one newest-wins history; optimistic concurrency on the base version id. Exposed as `ExecutionService.briefs`. |
| `conversation/concierge_prompt.py` | Own editable concierge prompt retrieval, short-lived cache, and context-specific framing. The prompt text itself remains in `system_agents.CONCIERGE`; there is no code default. |
| `console/routers/projects.py` | Extract project/material workflows before dividing the router into capability routes. |
| `execution/service.py` project query, archive, graph, artifact, and reaper methods | Continue moving read/mutation workflows to `projects/` and teardown policy to `cleanup/`; do not add unrelated behavior to the execution service. |
| `services/conversation.py` | Consolidate onboarding and dock turn preparation around the shared `conversation/` persistence boundary. Keep wire encoding at the API edge. |
| `repositories/_exec.py` | Replace `PathExec` and `GlobalExec` with one executor and an explicit connection/transaction strategy. |
| Store/repository pairs for system agents, eval scores, and autopsy | Collapse pairs that only delegate. Keep rich repository-plus-policy boundaries such as recipes, tickets, and runtime agents. |
| `artifacts.py`, PDF/DOCX extraction, material upload paths | Group artifact policy and extraction by capability; remove duplicate conversion and storage choreography. |
| `scripts/` | Keep executables as thin operator adapters. Move reusable application behavior into the package; preserve existing script entry points while operators migrate. |

## Deliberate exceptions

- `migrations/versions/` is immutable Alembic replay history. Do not consolidate, modernize, or
  move old revisions to improve aesthetics.
- `resources/langfuse_hook.py` is vendored/generated-workspace integration code. Keep it isolated
  and track its upstream compatibility separately.
- `skills/` is a bundled tooling boundary, not application code. Maintain it internally only when
  the repository owns the fork; do not mix it into `software_factory`.
- Small modules remain appropriate for focused algorithms, provider adapters, error taxonomies,
  stable data contracts, and independently reusable policies.

## Refactor safety

1. Preserve wire and operational contracts: route paths/payloads, CLI commands, environment
   variables, database schema, persisted JSON keys, artifacts, background lifecycle, and agent
   invocation behavior.
2. Change internal import paths freely in the coordinated refactor. Use compatibility modules only
   for active external or operational callers; remove them once those callers have moved.
3. Characterize the real behavior before moving a workflow, then compile/build and exercise the
   live route, CLI, worker, or provider flow required by the changed boundary.
4. Keep structural commits coherent by capability. Do not combine unrelated cleanup with a
   behavior change.
5. When a structural move lands, update this file and `ARCHITECTURE.md` with the new ownership.

## Parallel development protocol

1. Read this document before adding a backend module or moving an existing one.
2. State the owning context in the PR description and keep a change inside that context unless a
   real cross-context contract is required.
3. If concurrent work means a target package does not yet exist, create it only with the smallest
   coherent owner module. Do not add placeholder layers or empty packages for the full target tree.
4. When moving a public operational entry point, retain the old module/command as a documented
   forwarding shim until its active callers are migrated. Record the shim and removal condition in
   the PR.
5. Surface a conflict with this structure rather than silently creating a new generic layer. The
   operator resolves ambiguous ownership; agents do not invent a parallel convention.

## Decision record

Selected direction: **bounded-context modular monolith**.

Rejected alternatives:

- Technical layers (`api` → `services` → `repositories`) would formalize the current generic
  indirection and preserve the service/store clutter.
- Full vertical slices are a useful local technique, but applying them universally would multiply
  small files and duplicate shared agent/runtime infrastructure.
- Strict hexagonal/clean architecture would add ports and adapters that this product does not need.
