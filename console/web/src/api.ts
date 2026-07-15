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
  summary?: string;       // customer-facing summary; preferred over description in the dashboard snippet
  deploy_url?: string;    // present ⇒ deployed/live
  budget_stopped?: boolean;
  credential_stopped?: boolean;  // SOF-148: uncleared credential blocker — needs operator provisioning
  held?: boolean;
  agents?: string[];      // distinct agent roles on the run (avatar stack)
  updated?: number;       // last-activity epoch (seconds)
  created_by?: string;    // immutable creator email (set-once; backfilled from owner for legacy projects)
  created_at?: number;    // epoch seconds of project creation
  archived?: boolean;     // soft-deleted — rendered in the dashboard's Archived section
  maintenance_enabled?: boolean;  // SOF-94: no-op maintenance-agent placeholder preference (completed projects)
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
  // Optional confidence band (exact|high|med|low|none). The backend may not send this yet —
  // the board renders a ConfidencePill only when it is actually present (no fabrication).
  confidence?: string;
  // SOF-100: ticket depth fields. acceptance/dod always travel with the ticket (older rows have
  // them non-empty per the hollow gate); the rest are null/[] on a not-yet-upgraded ticket.
  acceptance?: string;
  dod?: string;
  goal?: string;
  design_refs?: string[] | null;
  dependencies?: string[] | null;
  scope_genre?: string | null;
  implementation_notes?: string;
  // SOF-118: the build agent's own disclosure — null until the ticket is closed (mark_done sets
  // it), [] for an honest "nothing to declare".
  decision_log?: DecisionLogEntry[] | null;
};

export type DecisionLogEntry = {
  type: "assumption" | "shortcut" | "known-gap";
  statement: string;
  reason: string;
  affected_surface: string;
};

export type TicketsResponse = { tickets: Ticket[]; waves: number[] };

export type GraphNode = { data: Record<string, any> };
export type GraphEdge = { data: Record<string, any> };
export type Graph = { nodes: GraphNode[]; edges: GraphEdge[] };

// SOF-37/SOF-60: assumptions are reference-backed (every entry links to a real source document
// + section, never a confidence score).
export type Assumption = { fact: string; document_blob_id: number; section_path: string | null; document_name: string };
// brief_markdown/brief_url are the concierge-finalized product brief (SOF-137: written to durable
// storage; both null until finalized).
export type BriefResponse = { brief_markdown: string | null; brief_url: string | null; assumptions: Assumption[] };

export type Me = { email: string; role: string; auth: boolean; name?: string; is_internal?: boolean };

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
// POST /api/projects/{id}/deps/provide — #107 post-deploy "provide your own key": pushes a real
// value onto the ALREADY-LIVE app's Railway service (triggers a redeploy). Always 200; `ok`
// carries success/failure so the UI can show a specific error, never a silent no-op.
// vault_saved false (on an ok:true response) means the live app got the real key (it works) but
// the value wasn't recorded in the vault — a later replace would need it re-entered.
export type ProvideDepResponse = { ok: boolean; detail?: string; name?: string; disposition?: string; vault_saved?: boolean };

export type ProjectEvent = { ts: number; type: string; payload: Record<string, any> };
export type Artifact = { path: string; content?: string; error?: string };

// Project view (§2.5) — Overview rollup + Documents, per tjyb5gmy's LOCKED shapes (PR #13).
// Callers degrade to empty until live.
export type ProjectMaterial = { id?: string; name: string; kind?: string; size_bytes?: number; content_type?: string; storage_key?: string; created_at?: number; scope?: "project" | "org"; tag?: string; used_count?: number; summary?: string; summary_status?: "pending" | "ready" | "failed" };
export type ProjectArtifact = { id?: number; title: string; path?: string; kind?: string; agent?: string; ts?: number };
export type ProjectOverview = {
  brief?: { name?: string; description?: string; goal?: string; scope?: string[]; owner?: string; phase?: string; stage?: number; created?: number | string; runtime?: string; created_by?: string };
  build?: { pct?: number; tickets_done?: number; tickets_total?: number; agents_working?: number; spent_usd?: number; budget_ceiling?: number; done?: boolean; deploy_url?: string };
  // `metric` / `price_book` are OPTIONAL forward-compat fields (SOF-69): today's backend doesn't
  // send them, so the Overview renders them presence-gated only — never fabricated.
  services?: { label: string; kind?: string; status?: string; detail?: string; url?: string; metric?: string }[];
  agents?: { role: string; model?: string; status?: string; task?: string; cost_usd?: number }[];
  org?: { name?: string; industry?: string; connected_systems?: string[]; price_book?: string } | null;
  materials?: ProjectMaterial[];
  produced?: ProjectArtifact[];
  materials_count?: number;
  produced_count?: number;
};
export type ProjectDocuments = { uploaded: ProjectMaterial[]; produced: ProjectArtifact[]; org?: ProjectMaterial[] };

// Org-admin (§2.3) — org-scoped, per the locked contract in docs/plans/org-admin-api.md.
export type Member = { email: string; role: string; designation?: string; you?: boolean };
export type OrgDoc = { id: string; name: string; kind?: string; tag?: string; size_bytes?: number; content_type?: string; used_count?: number; updated?: number };
export type OrgUsage = {
  plan?: string; monthly_budget_cap?: number; spent?: number;
  active_projects?: number; total_projects?: number;
  by_project: { project_id: string; name: string; spent_usd: number }[];
};

export type OrgSecret = { name: string; kind: string; last4: string; used_by: number; updated_at: string };

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
  tools?: AdminTool[];
  activity?: { text: string; ts?: string }[];
};

export type AdminTool = {
  name: string;
  config: Record<string, unknown>;
  attached_to: string[];
  has_key: boolean;
  key_last4: string | null;
  updated_by: string | null;
  updated_at: string | null;
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
  id: string;
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

// SOF-34/T1.5 — cross-tenant conversation history (Tenexity OS).
export type AdminConversationSession = {
  session_id: string;
  org_id: string | null;
  org_name: string | null;
  project_id: string | null;
  project_name: string | null;
  user_id: string | null;
  user_email: string | null;
  turn_count: number;
  last_activity: string;
  total_cost: number;
};

export type AdminConversationsResponse = {
  sessions: AdminConversationSession[];
  next_cursor: string | null;
};

export type AdminConversationMessage = {
  id: string;
  session_id: string;
  seq: number;
  user_id: string | null;
  project_id: string | null;
  org_id: string | null;
  role: string;
  input: string | null;
  json_blob: unknown[];
  tool_name: string | null;
  tool_call_id: string | null;
  tool_result: unknown | null;
  referenced_artifact: number | null;
  model: string | null;
  provider: string | null;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  created_at: string;
};

export type AdminConversationTranscript = {
  session_id: string;
  messages: AdminConversationMessage[];
};

export type AdminConversationsFilter = {
  org_id?: string;
  project_id?: string;
  user_id?: string;
  session_id?: string;
  role?: string;
  date_from?: string;
  date_to?: string;
  cursor?: string;
  limit?: number;
};

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

// An Error that also carries the HTTP status and the server's parsed `detail` payload, so callers
// can report the REAL reason (e.g. the promote 409's open-questions list) instead of a generic
// guess (SOF-97). The message keeps the `${path} → ${status}` shape so existing `.includes("409")`
// checks still work; new callers should read `.status` / `.detail`.
export type ApiError = Error & { status: number; detail?: unknown };

async function httpError(path: string, r: Response): Promise<ApiError> {
  let detail: unknown;
  try { detail = (await r.json() as { detail?: unknown }).detail; } catch { /* non-JSON body */ }
  const e = new Error(`${path} → ${r.status}`) as ApiError;
  e.status = r.status;
  e.detail = detail;
  return e;
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path, { credentials: "include" });
  if (!r.ok) { checkAuth(r); throw await httpError(path, r); }
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
  if (!r.ok) { checkAuth(r); throw await httpError(path, r); }
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
  // Thin goal/scope editor (post-promote "Edit brief"); returns the draft-projection shape.
  putBrief: (id: string, brief: { goals?: string; scope?: string[] }) =>
    send<{ name: string; goal: string; scope: string[]; description: string }>(`/api/projects/${id}/brief`, "PUT", brief),
  chat: (body: Record<string, unknown>, signal?: AbortSignal) =>
    send<{ project_id: string; messages: any[] }>("/api/chat", "POST", body, signal),
  // Onboarding Concierge conversation turn: one user message -> the agent's ConciergeTurn reply
  // (T2.2) — plain text when suggested_responses is empty, else selectable options whose `type`
  // drives single/multi-select render. No `choices`/`done`.
  converse: (projectId: string, message: string) =>
    send<{ response: string; suggested_responses: { response: string; type: "single select" | "multi select" }[];
          message_id?: string; session_id?: string }>(`/api/projects/${projectId}/converse`, "POST", { message }),
  // SOF-154: streaming sibling of `converse` — NDJSON over the raw Response body, same shape as
  // `chatStream` below. Caller reads `.body.getReader()` and parses `working`/`token`/`option`/
  // `done`/`error` events itself.
  converseStream: async (projectId: string, message: string, signal?: AbortSignal): Promise<Response> => {
    const path = `/api/projects/${projectId}/converse/stream`;
    const r = await fetch(path, {
      method: "POST",
      credentials: "include",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ message }),
      signal,
    });
    if (!r.ok) { checkAuth(r); throw new Error(`${path} → ${r.status}`); }
    return r;
  },
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
  transcribe: (audio_base64: string, format: string, language?: string) =>
    send<{ text: string }>("/api/transcribe", "POST", { audio_base64, format, language }),
  deps: (id: string) => get<DepsResponse>(`/api/projects/${id}/deps`),
  submitDeps: (id: string, deps: DepSubmit) =>
    send<DepsSubmitResponse>(`/api/projects/${id}/deps`, "POST", { deps }),
  provideDep: (id: string, name: string, value: string) =>
    send<ProvideDepResponse>(`/api/projects/${id}/deps/provide`, "POST", { name, value }),
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
  inviteMember: (body: { email: string; role: string; designation?: string }) => send<{ members?: Member[]; invite_email_sent?: boolean }>("/api/org/members", "POST", body),
  updateMember: (email: string, body: { role?: string; designation?: string }) => send<{ members?: Member[] }>(`/api/org/members/${encodeURIComponent(email)}`, "PATCH", body),
  removeMember: (email: string) => send<{ ok?: boolean }>(`/api/org/members/${encodeURIComponent(email)}`, "DELETE"),
  orgDocs: () => get<{ docs: OrgDoc[] }>("/api/org/docs"),
  orgUsage: () => get<OrgUsage>("/api/org/usage"),
  patchBilling: (body: { plan?: string; monthly_budget_cap?: number }) => send<OrgUsage>("/api/org/billing", "PATCH", body),
  listSecrets: () => get<{ secrets: OrgSecret[] }>("/api/org/secrets"),
  createSecret: (body: { name: string; value: string; kind: string }) => send<{ secret: OrgSecret }>("/api/org/secrets", "POST", body),
  rotateSecret: (name: string, body: { value: string }) => send<{ secret: OrgSecret }>(`/api/org/secrets/${encodeURIComponent(name)}`, "PATCH", body),
  deleteSecret: (name: string) => send<void>(`/api/org/secrets/${encodeURIComponent(name)}`, "DELETE"),
  // ── Tenexity OS admin portal (§3). Staff-gated, cross-tenant. Degrade to empty until live.
  adminOverview: () => get<AdminOverview>("/api/admin/overview"),
  adminClients: () => get<{ clients: AdminClient[] }>("/api/admin/clients"),
  adminCreateClient: (body: Partial<Omit<AdminClient, "org_id">> & { name: string }) => send<{ client: AdminClient }>("/api/admin/clients", "POST", body),
  adminUpdateClient: (org_id: string, body: Partial<AdminClient>) => send<{ client: AdminClient }>(`/api/admin/clients/${encodeURIComponent(org_id)}`, "PATCH", body),
  adminDeleteClient: (org_id: string) => send<{ ok?: boolean }>(`/api/admin/clients/${encodeURIComponent(org_id)}`, "DELETE"),
  adminProjects: (mode?: AdminProjectMode) => get<{ projects: AdminProjectRow[] }>(`/api/admin/projects${mode ? `?mode=${mode}` : ""}`),
  adminAgents: () => get<{ agents: AdminAgent[] }>("/api/admin/agents"),
  adminSyncAgents: () => send<{ synced: number; agents: AdminAgent[] }>("/api/admin/agents/sync", "POST"),
  adminCreateAgent: (body: Partial<Omit<AdminAgent, "callsign">> & { callsign: string }) => send<{ agent: AdminAgent }>("/api/admin/agents", "POST", body),
  adminUpdateAgent: (callsign: string, body: Partial<AdminAgent>) => send<{ agent: AdminAgent }>(`/api/admin/agents/${encodeURIComponent(callsign)}`, "PATCH", body),
  adminDeleteAgent: (callsign: string) => send<{ ok?: boolean }>(`/api/admin/agents/${encodeURIComponent(callsign)}`, "DELETE"),
  adminAgent: (callsign: string, runtime?: string) => get<AdminAgent>(`/api/admin/agents/${encodeURIComponent(callsign)}${runtime ? `?runtime=${encodeURIComponent(runtime)}` : ""}`),
  adminPatchAgentPrompt: (callsign: string, prompt: string, runtime?: string) => send<{ version?: number; applied: boolean; is_default?: boolean }>(`/api/admin/agents/${encodeURIComponent(callsign)}/prompt`, "PATCH", runtime ? { prompt, runtime } : { prompt }),
  adminRevertAgentPrompt: (callsign: string, runtime?: string) => send<{ version?: number; is_default?: boolean }>(`/api/admin/agents/${encodeURIComponent(callsign)}/prompt${runtime ? `?runtime=${encodeURIComponent(runtime)}` : ""}`, "DELETE"),
  adminTools: () => get<{ tools: AdminTool[] }>("/api/admin/tools"),
  adminCreateTool: (body: { name: string; config: Record<string, unknown>; attached_to?: string[] }) => send<{ tool: AdminTool }>("/api/admin/tools", "POST", body),
  adminUpdateTool: (name: string, body: { config?: Record<string, unknown>; attached_to?: string[] }) => send<{ tool: AdminTool }>(`/api/admin/tools/${encodeURIComponent(name)}`, "PATCH", body),
  adminDeleteTool: (name: string) => send<{ ok?: boolean }>(`/api/admin/tools/${encodeURIComponent(name)}`, "DELETE"),
  adminSetToolKey: (name: string, value: string) => send<{ tool: AdminTool }>(`/api/admin/tools/${encodeURIComponent(name)}/key`, "PUT", { value }),
  adminDeleteToolKey: (name: string) => send<{ tool: AdminTool }>(`/api/admin/tools/${encodeURIComponent(name)}/key`, "DELETE"),
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
  // SOF-34/T1.5 — cross-tenant conversation history.
  adminConversations: (filter: AdminConversationsFilter = {}) => {
    const params = new URLSearchParams();
    Object.entries(filter).forEach(([k, v]) => { if (v !== undefined && v !== "") params.set(k, String(v)); });
    const qs = params.toString();
    return get<AdminConversationsResponse>(`/api/admin/conversations${qs ? `?${qs}` : ""}`);
  },
  adminConversationTranscript: (sessionId: string) => get<AdminConversationTranscript>(`/api/admin/conversations/${encodeURIComponent(sessionId)}`),
  // ── Onboarding draft model (docs/plans/concierge-onboarding-api.md) ──
  // runtime ("claude"|"opencode") + model ("kimi"|"glm") are persisted by the backend (DraftCreateIn
  // → projectstate). BYOK keys: when keySource="byok", the FE POSTs the runtime-specific runner key
  // (ANTHROPIC_API_KEY for claude, OPENROUTER_API_KEY for opencode) to /creds, which Vault-stores it
  // and records creds_vault_ids on the draft; promote threads those into the runner env (BYOK wins
  // over the platform key). keySource/key on createDraft/patchDraft are passthrough (ignored by
  // Pydantic); the real BYOK path is submitCreds.
  createDraft: (body?: { project_name?: string; runtime?: string; model?: string; keySource?: string; key?: string; budget?: number }) =>
    send<{ project_id: string }>("/api/drafts", "POST", body || {}),
  // SOF-108: DB-backed scope chips — genre recipes authored on the SOW screen (status='Template').
  scopeGenres: () => get<{ genres: { name: string; description: string }[] }>("/api/scope-genres"),
  patchDraft: (id: string, body: { name?: string; goal?: string; scope?: string[]; runtime?: string; model?: string; keySource?: string; key?: string; budget?: number }) =>
    send<{ name: string; goal: string; scope: string[]; description: string }>(`/api/projects/${id}/draft`, "PATCH", body),
  // Read counterpart to PATCH /draft (qsvigmth's run-control PR #48) — rehydrates the intake form
  // when RESUMING an existing draft instead of minting a new one. budget (SOF-137) is included
  // since it's now one of the three required intake fields (name+goal+budget, scope optional).
  getDraft: (id: string) =>
    get<{ name: string; goal: string; scope: string[]; description: string; budget: number | null }>(`/api/projects/${id}/draft`),
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
  // SOF-94: no-op maintenance-agent placeholder toggle (persists a preference on completed projects).
  setMaintenance: (id: string, enabled: boolean) => send<{ project_id: string; maintenance_enabled: boolean }>(`/api/projects/${id}/maintenance`, "POST", { enabled }),
  // ── Recovery endpoints (bkkc52v5 PR #89) ──
  pauseProject: (id: string) => send<Record<string, any>>(`/api/projects/${id}/pause`, "POST"),
  resumeProject: (id: string) => send<Record<string, any>>(`/api/projects/${id}/resume`, "POST"),
  relaunchProject: (id: string) => send<{ project_id: string; relaunched_from: string }>(`/api/projects/${id}/relaunch`, "POST"),
  retryNode: (id: string, node: string) => send<Record<string, any>>(`/api/projects/${id}/retry-node`, "POST", { node }),
  rewindTo: (id: string, node: string) => send<Record<string, any>>(`/api/projects/${id}/rewind`, "POST", { node }),
  uploadMaterial: (id: string, file: { name: string; tag?: string; content_type?: string; data_b64: string }) =>
    send<{ ok?: boolean }>(`/api/projects/${id}/materials`, "POST", file),
  // Auto-summarize / Regenerate (SOF-36/T3.3) — synchronous, blocks until the fresh summary is
  // persisted; 404s if project memory (SF_MEMORY) isn't enabled.
  summarizeDocument: (id: string, blobId: string) =>
    send<ProjectDocuments>(`/api/projects/${id}/documents/${blobId}/summarize`, "POST"),
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

