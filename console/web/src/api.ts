// Thin typed client over the existing console JSON API. Cookie auth → credentials: "include".

export type ProjectSummary = {
  project_id: string;
  name?: string;
  phase?: string;
  stage?: number;
  spent_usd?: number;
  owner?: string;
  done?: boolean;
  description?: string;   // the project goal (one-liner shown on the dashboard row)
  deploy_url?: string;    // present ⇒ deployed/live
  budget_stopped?: boolean;
  held?: boolean;
  agents?: string[];      // distinct agent roles on the run (avatar stack)
  updated?: number;       // last-activity epoch (seconds)
  created_by?: string;    // immutable creator email (set-once; backfilled from owner for legacy projects)
  created_at?: number;    // epoch seconds of project creation
  archived?: boolean;     // soft-deleted — rendered in the dashboard's Archived section
};

export type TicketStatus =
  | "open" | "in_progress" | "done" | "deployed" | "qa_testing" | "approved";

export type Ticket = {
  id: number;
  title: string;
  wave: number;
  status: TicketStatus;
  agent: string | null;
  provenance: string | null;
  provenance_type: string | null;
  diff_lines: number;
  app: string | null;
  description?: string;
};

export type TicketsResponse = { tickets: Ticket[]; waves: number[] };

export type GraphNode = { data: Record<string, any> };
export type GraphEdge = { data: Record<string, any> };
export type Graph = { nodes: GraphNode[]; edges: GraphEdge[] };

export type Brief = Record<string, string>;
export type BriefResponse = { brief: Brief; coverage: Record<string, boolean> };

export type Me = { email: string; role: string; auth: boolean; name?: string; is_internal?: boolean };

// GET /api/projects/{id}/deployments → console.deployments(). Per-deliverable: a run ships 1..N apps.
export type Deployment = { app?: string; url?: string; repo?: string; [k: string]: any };
export type DeploymentsResponse = { deployments: Deployment[]; apps: string[] };

// GET /api/projects/{id}/deps → console.stage2_artifacts(). `tokens` are the architecture-derived
// required tokens; `disposition[name]` is the per-token plan (mcp | mock | provide).
export type DepToken = { name: string; [k: string]: any };
export type DepsResponse = {
  deps_required: string[];
  deps_provided: string[];
  deps_satisfied: boolean;
  disposition: Record<string, string>;
  tokens: DepToken[];
};
// POST /api/projects/{id}/deps body — {deps: {name: {disposition, value?}}}. value rides into the
// Stage-3 env only; it is never persisted to disk (see console.submit_deps).
export type DepSubmit = Record<string, { disposition: string; value?: string }>;
export type DepsSubmitResponse = {
  deps_provided: string[]; deps_required: string[]; disposition: Record<string, string>;
  missing: string[]; satisfied: boolean;
};

export type ProjectEvent = { ts: number; type: string; payload: Record<string, any> };
export type Artifact = { path: string; content?: string; error?: string };

// Project view (§2.5) — Overview rollup + Documents, per tjyb5gmy's LOCKED shapes (PR #13).
// Callers degrade to empty until live.
export type ProjectMaterial = { id?: string; name: string; kind?: string; size_bytes?: number; content_type?: string; storage_key?: string; created_at?: number; scope?: "project" | "org" };
export type ProjectArtifact = { id?: number; title: string; path?: string; kind?: string; agent?: string; ts?: number };
export type ProjectOverview = {
  brief?: { name?: string; description?: string; goal?: string; scope?: string[]; owner?: string; phase?: string; stage?: number; created?: number | string; runtime?: string; created_by?: string };
  build?: { pct?: number; tickets_done?: number; tickets_total?: number; agents_working?: number; spent_usd?: number; budget_ceiling?: number; done?: boolean; deploy_url?: string };
  services?: { label: string; kind?: string; status?: string; detail?: string; url?: string }[];
  agents?: { role: string; model?: string; status?: string; task?: string; cost_usd?: number }[];
  org?: { name?: string; industry?: string; connected_systems?: string[] } | null;
  materials?: ProjectMaterial[];
  produced?: ProjectArtifact[];
  materials_count?: number;
  produced_count?: number;
};
export type ProjectDocuments = { uploaded: ProjectMaterial[]; produced: ProjectArtifact[] };

// Org-admin (§2.3) — org-scoped, per the locked contract in docs/plans/org-admin-api.md.
export type Member = { email: string; role: string; designation?: string; you?: boolean };
export type OrgDoc = { id: string; name: string; kind?: string; tag?: string; size_bytes?: number; content_type?: string; used_count?: number; updated?: number };
export type OrgUsage = {
  plan?: string; monthly_budget_cap?: number; spent?: number;
  active_projects?: number; total_projects?: number;
  by_project: { project_id: string; name: string; spent_usd: number }[];
};

// Public boot config the SPA reads to decide whether to gate on login (auth on) or open
// straight to the console (auth off, dev/test). client_id feeds the Google sign-in button.
export type AuthConfig = { enabled: boolean; client_id: string };

export type Org = {
  id: string;
  name: string;
  industry?: string | null;
  sub_focus: string[];
  headcount?: string | null;
  revenue?: string | null;
  location?: string | null;
  website?: string | null;
  connected_systems: string[];
  plan?: string | null;               // billing plan + monthly cap (set via /api/org/billing)
  monthly_budget_cap?: number | null;
  created_at?: number;
  created_by?: string;
};

// POST body: org fields plus the current user's self-described role (designation/role_description).
export type OrgInput = Partial<Omit<Org, "id" | "created_at" | "created_by">> & {
  name: string;
  designation?: string;
  role_description?: string;
};

// ── Tenexity OS admin portal (§3) — staff-gated, cross-tenant. Degrade to empty until live.
export type AdminPulse = {
  tenants?: number;
  projects?: number;
  projects_active?: number | null;
  agents_active?: number;
  agents_total?: number;
  today_burn?: number | string;
  avg_friction?: number | null;
};

export type AdminProjectRow = {
  project_id: string;
  name: string;
  client: string;
  factory: string;
  phase: string;
  stage?: number;
  tasks_done: number;
  tasks_total: number;
  spent_usd?: number;
  updated?: number | string;
  is_demo: boolean;
  owner?: string;
  created_by?: string;
  created_at?: number | string;
};

export type AdminAgent = {
  callsign: string;
  sign: string;
  name?: string;
  role: string;
  desc: string;
  model: string;
  cost_tier: number;
  success?: number | null;
  runs?: number | null;
  on?: boolean;
  kind?: "stage_skill" | "concierge";
  stage?: number;
  prompt_version?: number;
  prompt_applied?: boolean;
  prompt?: string;
  prompt_source?: "skill_file" | "code" | "store" | string;
  is_default?: boolean;
  overridden?: boolean;
  version?: number;
  editable?: boolean;
  skill?: string;
  skill_path?: string;
  source_ref?: string;
  runtime?: string;
  variants?: Record<string, string>;
  tools?: { name: string; type?: string; scope?: string }[];
  activity?: { text: string; ts?: string }[];
};

export type AdminTool = {
  name: string;
  type: "MCP" | "API" | "native" | "HTTP";
  provider: string;
  scope: string;
  status: "connected" | "available";
  used: number;
  auth: string;
};

export type AdminClient = {
  org_id: string;
  name: string;
  initials: string;
  projects: number;
  tickets: number;
  spend: string;
  last_activity: string;
};

export type AdminAccessUser = {
  email: string;
  type: "New org" | "Tenexity";
  org: string;
  role: string;
  status: "active" | "invited" | "disabled";
  is_internal?: boolean;
  name?: string;
  designation?: string;
  method?: string;
  sign_in_method?: string;
  last_active?: number | string | null;
  invited_by?: string | null;
  created_at?: string | number;
};

export type AdminOverview = {
  pulse: AdminPulse;
  active_projects: AdminProjectRow[];
  agents: AdminAgent[];
};

export type AdminProjectMode = "all" | "real" | "demo";

export type AdminSow = {
  id: number;
  title: string;
  org?: string | null;
  project?: string | null;
  value?: string | null;
  file?: string | null;
  version: number;
  status: string;
  body?: string | null;
  created_at?: string | number | null;
  updated_at?: string | number | null;
};

function checkAuth(r: Response): void {
  if (r.status === 401) window.dispatchEvent(new CustomEvent("sf:auth-expired"));
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path, { credentials: "include" });
  if (!r.ok) { checkAuth(r); throw new Error(`${path} → ${r.status}`); }
  return r.json() as Promise<T>;
}

async function send<T>(path: string, method: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const r = await fetch(path, {
    method,
    credentials: "include",
    headers: { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
  if (!r.ok) { checkAuth(r); throw new Error(`${path} → ${r.status}`); }
  return r.json() as Promise<T>;
}

export const api = {
  authConfig: () => get<AuthConfig>("/api/auth/config"),
  me: () => get<Me>("/api/me"),
  // Sign out (backend POST /api/auth/logout clears the sf_session cookie). Resolves regardless so
  // the caller can always redirect to "/" (SPA re-checks /api/me → login).
  logout: async (): Promise<void> => { try { await fetch("/api/auth/logout", { method: "POST", credentials: "include" }); } catch { /* redirect anyway */ } },
  // Email+password sign-in (backend POST /api/auth/password). On 200 the server sets the sf_session
  // cookie (same as Google). Returns {ok,status} (not get/send) so the caller can branch on 401.
  passwordLogin: async (body: { email: string; password: string }): Promise<{ ok: boolean; status: number }> => {
    const r = await fetch("/api/auth/password", {
      method: "POST", credentials: "include",
      headers: { "content-type": "application/json" }, body: JSON.stringify(body),
    });
    return { ok: r.ok, status: r.status };
  },
  projects: (includeArchived = false) =>
    get<{ projects: ProjectSummary[] }>(`/api/projects${includeArchived ? "?include_archived=true" : ""}`),
  status: (id: string) => get<ProjectSummary & Record<string, any>>(`/api/projects/${id}`),
  graph: (id: string) => get<Graph>(`/api/projects/${id}/graph`),
  tickets: (id: string) => get<TicketsResponse>(`/api/projects/${id}/tickets`),
  brief: (id: string) => get<BriefResponse>(`/api/projects/${id}/brief`),
  putBrief: (id: string, brief: Brief) => send<BriefResponse>(`/api/projects/${id}/brief`, "PUT", brief),
  chat: (body: Record<string, unknown>, signal?: AbortSignal) =>
    send<{ project_id: string; messages: any[] }>("/api/chat", "POST", body, signal),
  chatStream: async (body: Record<string, unknown>, signal?: AbortSignal): Promise<Response> => {
    const r = await fetch("/api/chat", {
      method: "POST",
      credentials: "include",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
    if (!r.ok) { checkAuth(r); throw new Error(`/api/chat → ${r.status}`); }
    return r;
  },
  chatHistory: (id: string) => get<{ messages: any[] }>(`/api/chat/${id}/history`),
  deployments: (id: string) => get<DeploymentsResponse>(`/api/projects/${id}/deployments`),
  deps: (id: string) => get<DepsResponse>(`/api/projects/${id}/deps`),
  submitDeps: (id: string, deps: DepSubmit) =>
    send<DepsSubmitResponse>(`/api/projects/${id}/deps`, "POST", { deps }),
  events: (id: string) => get<{ events: ProjectEvent[] }>(`/api/projects/${id}/events`),
  artifact: (id: string, path: string) =>
    get<Artifact>(`/api/projects/${id}/artifact?path=${encodeURIComponent(path)}`),
  getArtifact: (id: string | number) => get<Record<string, any>>(`/api/artifacts/${id}`),
  // Project view (§2.5) — Overview rollup + Documents. Backend landing via #13; degrade to empty.
  overview: (id: string) => get<ProjectOverview>(`/api/projects/${id}/overview`),
  documents: (id: string) => get<ProjectDocuments>(`/api/projects/${id}/documents`),
  getOrg: () => get<{ org: Org | null }>("/api/org"),
  createOrg: (body: OrgInput) => send<{ org: Org }>("/api/org", "POST", body),
  patchOrg: (body: Partial<Org>) => send<{ org: Org }>("/api/org", "PATCH", body),
  // Org-admin §2.3 — org-scoped (resolve org from session). Backend in progress (tjyb5gmy);
  // callers degrade to empty/null until live. NOT /api/users (that's the global cross-org dir).
  orgMembers: () => get<{ members: Member[] }>("/api/org/members"),
  inviteMember: (body: { email: string; role: string; designation?: string }) => send<{ members?: Member[] }>("/api/org/members", "POST", body),
  updateMember: (email: string, body: { role?: string; designation?: string }) => send<{ members?: Member[] }>(`/api/org/members/${encodeURIComponent(email)}`, "PATCH", body),
  removeMember: (email: string) => send<{ ok?: boolean }>(`/api/org/members/${encodeURIComponent(email)}`, "DELETE"),
  orgDocs: () => get<{ docs: OrgDoc[] }>("/api/org/docs"),
  orgUsage: () => get<OrgUsage>("/api/org/usage"),
  patchBilling: (body: { plan?: string; monthly_budget_cap?: number }) => send<OrgUsage>("/api/org/billing", "PATCH", body),
  createProject: (body: { description: string; project_name: string }) =>
    send<{ project_id: string }>("/api/projects", "POST", body),
  // ── Tenexity OS admin portal (§3). Staff-gated, cross-tenant. Degrade to empty until live.
  adminOverview: () => get<AdminOverview>("/api/admin/overview"),
  adminClients: () => get<{ clients: AdminClient[] }>("/api/admin/clients"),
  adminCreateClient: (body: Partial<Omit<AdminClient, "org_id">> & { name: string }) => send<{ client: AdminClient }>("/api/admin/clients", "POST", body),
  adminUpdateClient: (org_id: string, body: Partial<AdminClient>) => send<{ client: AdminClient }>(`/api/admin/clients/${encodeURIComponent(org_id)}`, "PATCH", body),
  adminDeleteClient: (org_id: string) => send<{ ok?: boolean }>(`/api/admin/clients/${encodeURIComponent(org_id)}`, "DELETE"),
  adminProjects: (mode?: AdminProjectMode) => get<{ projects: AdminProjectRow[] }>(`/api/admin/projects${mode ? `?mode=${mode}` : ""}`),
  adminSetProjectMode: (rid: string, is_demo: boolean) => send<{ project: AdminProjectRow }>(`/api/admin/projects/${encodeURIComponent(rid)}`, "PATCH", { is_demo }),
  adminAgents: () => get<{ agents: AdminAgent[] }>("/api/admin/agents"),
  adminSyncAgents: () => send<{ synced: number; agents: AdminAgent[] }>("/api/admin/agents/sync", "POST"),
  adminCreateAgent: (body: Partial<Omit<AdminAgent, "callsign">> & { callsign: string }) => send<{ agent: AdminAgent }>("/api/admin/agents", "POST", body),
  adminUpdateAgent: (callsign: string, body: Partial<AdminAgent>) => send<{ agent: AdminAgent }>(`/api/admin/agents/${encodeURIComponent(callsign)}`, "PATCH", body),
  adminDeleteAgent: (callsign: string) => send<{ ok?: boolean }>(`/api/admin/agents/${encodeURIComponent(callsign)}`, "DELETE"),
  adminAgent: (callsign: string, runtime?: string) => get<AdminAgent>(`/api/admin/agents/${encodeURIComponent(callsign)}${runtime ? `?runtime=${encodeURIComponent(runtime)}` : ""}`),
  adminPatchAgentPrompt: (callsign: string, prompt: string, runtime?: string) => send<{ version?: number; applied: boolean; is_default?: boolean }>(`/api/admin/agents/${encodeURIComponent(callsign)}/prompt`, "PATCH", runtime ? { prompt, runtime } : { prompt }),
  adminRevertAgentPrompt: (callsign: string, runtime?: string) => send<{ version?: number; is_default?: boolean }>(`/api/admin/agents/${encodeURIComponent(callsign)}/prompt${runtime ? `?runtime=${encodeURIComponent(runtime)}` : ""}`, "DELETE"),
  adminTools: () => get<{ tools: AdminTool[] }>("/api/admin/tools"),
  adminCreateTool: (body: Partial<AdminTool> & { name: string; type: AdminTool["type"]; provider: string }) => send<{ tool: AdminTool }>("/api/admin/tools", "POST", body),
  adminUpdateTool: (id: string, body: Partial<AdminTool>) => send<{ tool: AdminTool }>(`/api/admin/tools/${encodeURIComponent(id)}`, "PATCH", body),
  adminDeleteTool: (id: string) => send<{ ok?: boolean }>(`/api/admin/tools/${encodeURIComponent(id)}`, "DELETE"),
  adminAccess: () => get<{ users: AdminAccessUser[] }>("/api/admin/access"),
  adminInvite: (body: {
    email: string;
    access_type: "org" | "tenexity";
    org_name?: string;
    name?: string;
    designation?: string;
    method?: "google" | "microsoft" | "password" | "sso";
    password?: string;
    role?: "admin" | "member";
  }) => send<{ users: AdminAccessUser[] }>("/api/admin/access", "POST", body),
  adminUpdateAccess: (email: string, body: { role?: string; status?: "active" | "invited" | "disabled"; is_internal?: boolean }) =>
    send<{ users: AdminAccessUser[] }>(`/api/admin/access/${encodeURIComponent(email)}`, "PATCH", body),
  adminDeleteAccess: (email: string) => send<{ users: AdminAccessUser[] }>(`/api/admin/access/${encodeURIComponent(email)}`, "DELETE"),
  adminResendInvite: (email: string) => send<{ email: string; status: string; link: string }>(`/api/admin/access/${encodeURIComponent(email)}/resend`, "POST"),
  adminSowList: () => get<{ sows: AdminSow[] }>("/api/admin/sow"),
  adminSowGet: (id: number) => get<AdminSow>(`/api/admin/sow/${id}`),
  adminSowCreate: (body: { title: string; org?: string; project?: string; value?: string; file?: string; version?: number; status?: string; body?: string }) => send<AdminSow>("/api/admin/sow", "POST", body),
  adminSowUpdate: (id: number, body: { title?: string; org?: string; project?: string; value?: string; file?: string; version?: number; status?: string; body?: string }) => send<AdminSow>(`/api/admin/sow/${id}`, "PATCH", body),
  // ── Onboarding draft model (docs/plans/concierge-onboarding-api.md) ──
  // runtime ("claude"|"opencode") + model ("kimi"|"glm") are persisted by the backend (DraftCreateIn
  // → projectstate). BYOK keys: when keySource="byok", the FE POSTs the runtime-specific runner key
  // (ANTHROPIC_API_KEY for claude, OPENROUTER_API_KEY for opencode) to /creds, which Vault-stores it
  // and records creds_vault_ids on the draft; promote threads those into the runner env (BYOK wins
  // over the platform key). keySource/key on createDraft/patchDraft are passthrough (ignored by
  // Pydantic); the real BYOK path is submitCreds.
  createDraft: (body?: { project_name?: string; runtime?: string; model?: string; keySource?: string; key?: string; budget?: number }) =>
    send<{ project_id: string }>("/api/drafts", "POST", body || {}),
  patchDraft: (id: string, body: { name?: string; goal?: string; scope?: string[]; runtime?: string; model?: string; keySource?: string; key?: string; budget?: number }) =>
    send<{ name: string; goal: string; scope: string[]; description: string; brief: Record<string, string>; coverage: Record<string, boolean> }>(`/api/projects/${id}/draft`, "PATCH", body),
  // Read counterpart to PATCH /draft (qsvigmth's run-control PR #48) — rehydrates the intake form
  // when RESUMING an existing draft instead of minting a new one.
  getDraft: (id: string) =>
    get<{ name: string; goal: string; scope: string[]; description: string; brief: Record<string, string>; coverage: Record<string, boolean> }>(`/api/projects/${id}/draft`),
  // BYOK key submission (qsvigmth's draft-BYOK PR). Vault-stores each credential; records UUIDs in
  // state.creds_vault_ids; promote threads them into the runner env. Returns names only, never values.
  submitCreds: (id: string, credentials: Record<string, string>) =>
    send<{ creds_provided: string[] }>(`/api/projects/${id}/creds`, "POST", { credentials }),
  attach: (id: string, files: { name: string; content_b64: string }[]) =>
    send<{ attached: string[] }>(`/api/projects/${id}/attach`, "POST", { files }),
  promote: (id: string, body?: { description?: string; target?: string }) =>
    send<{ project_id: string; status: string }>(`/api/projects/${id}/promote`, "POST", body || {}),
  // ── CRUD (no-dummy/full-CRUD pass, docs/plans/crud-contract.md). NEW endpoints (patchProject/
  // deleteProject/uploadMaterial) graceful-degrade until tjyb5gmy ships them; KB doc ops are LIVE. ──
  patchProject: (id: string, body: { name?: string; description?: string; scope?: string[] }) =>
    send<ProjectSummary & Record<string, any>>(`/api/projects/${id}`, "PATCH", body),
  setMaterialScope: (id: string, materialId: string, scope: "project" | "org") =>
    send<ProjectDocuments>(`/api/projects/${id}/materials/${materialId}`, "PATCH", { scope }),
  deleteProject: (id: string) => send<{ project_id: string; archived: boolean }>(`/api/projects/${id}`, "DELETE"),
  // Restore an archived project (un-archives it); permanent delete removes the run for good.
  restoreProject: (id: string) => send<{ project_id: string; archived: boolean }>(`/api/projects/${id}/restore`, "POST"),
  deleteProjectPermanently: (id: string) => send<{ project_id: string; deleted: boolean }>(`/api/projects/${id}/permanent`, "DELETE"),
  // Manual kill-switch — halts the live stage process, sets phase=stopped, stops the poller
  // re-advancing. Endpoint shipping in qsvigmth's run-control PR; graceful until then.
  stopProject: (id: string) => send<ProjectSummary & Record<string, any>>(`/api/projects/${id}/stop`, "POST"),
  // ── Recovery endpoints (bkkc52v5 PR #89) ──
  pauseProject: (id: string) => send<Record<string, any>>(`/api/projects/${id}/pause`, "POST"),
  resumeProject: (id: string) => send<Record<string, any>>(`/api/projects/${id}/resume`, "POST"),
  relaunchProject: (id: string) => send<{ project_id: string; relaunched_from: string }>(`/api/projects/${id}/relaunch`, "POST"),
  retryNode: (id: string, node: string) => send<Record<string, any>>(`/api/projects/${id}/retry-node`, "POST", { node }),
  rewindTo: (id: string, node: string) => send<Record<string, any>>(`/api/projects/${id}/rewind`, "POST", { node }),
  uploadMaterial: (id: string, file: { name: string; tag?: string; content_type?: string; data_b64: string }) =>
    send<{ ok?: boolean }>(`/api/projects/${id}/materials`, "POST", file),
  orgDocUpload: (body: { name: string; tag?: string; content_type?: string; data_b64: string }) =>
    send<{ doc?: OrgDoc }>("/api/org/docs", "POST", body),
  orgDocDelete: (docId: string) => send<{ ok?: boolean }>(`/api/org/docs/${docId}`, "DELETE"),
  orgDocPatch: (docId: string, body: { name?: string; tag?: string }) =>
    send<{ doc?: OrgDoc }>(`/api/org/docs/${docId}`, "PATCH", body),
  putBudget: (id: string, ceiling: number) =>
    send<Record<string, any>>(`/api/projects/${id}/budget`, "POST", { ceiling }),
};

// Phase-lag detection: stage is stamped the moment a new stage launches, before the agent
// has emitted its first set-phase. If the recorded phase belongs to a DIFFERENT stage,
// it's stale — show "stage N · starting" instead of the misleading prior-stage phase name.
const _STAGE_PHASES: Record<number, string[]> = {
  1: ["extract", "provision", "research"],
  2: ["architect", "tickets"],
  3: ["build", "deploy", "test", "teardown"],
};
const _ALL_STAGE_PHASES = new Set(Object.values(_STAGE_PHASES).flat());

export function phaseIsStale(phase: string | undefined, stage: number | undefined): boolean {
  if (!phase || !stage || stage < 1 || stage > 3) return false;
  if (!_ALL_STAGE_PHASES.has(phase)) return false; // non-pipeline (draft/paused/crashed): never stale
  return !(_STAGE_PHASES[stage] || []).includes(phase);
}

export const BRIEF_SECTIONS: { key: string; label: string }[] = [
  { key: "goals", label: "Context & Goals" },
  { key: "scale", label: "Scale & Usage" },
  { key: "success_metrics", label: "Success Metrics" },
  { key: "constraints", label: "Constraints" },
  { key: "stakeholders", label: "Stakeholders" },
  { key: "existing_assets", label: "Existing Assets" },
  { key: "risks", label: "Risks & Unknowns" },
  { key: "definition_of_done", label: "Definition of Done" },
];
