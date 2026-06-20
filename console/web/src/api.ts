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

export type Me = { email: string; role: string; auth: boolean };

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
export type ProjectMaterial = { name: string; kind?: string; size_bytes?: number; content_type?: string; storage_key?: string; created_at?: number };
export type ProjectArtifact = { title: string; path?: string; kind?: string; agent?: string; ts?: number };
export type ProjectOverview = {
  brief?: { name?: string; description?: string; goal?: string; scope?: string[]; owner?: string; phase?: string; stage?: number; created?: number | string };
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
  created_at?: number;
  created_by?: string;
};

// POST body: org fields plus the current user's self-described role (designation/role_description).
export type OrgInput = Partial<Omit<Org, "id" | "created_at" | "created_by">> & {
  name: string;
  designation?: string;
  role_description?: string;
};

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path, { credentials: "include" });
  if (!r.ok) throw new Error(`${path} → ${r.status}`);
  return r.json() as Promise<T>;
}

async function send<T>(path: string, method: string, body?: unknown): Promise<T> {
  const r = await fetch(path, {
    method,
    credentials: "include",
    headers: { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${path} → ${r.status}`);
  return r.json() as Promise<T>;
}

export const api = {
  authConfig: () => get<AuthConfig>("/api/auth/config"),
  me: () => get<Me>("/api/me"),
  projects: () => get<{ projects: ProjectSummary[] }>("/api/projects"),
  status: (id: string) => get<ProjectSummary & Record<string, any>>(`/api/projects/${id}`),
  graph: (id: string) => get<Graph>(`/api/projects/${id}/graph`),
  tickets: (id: string) => get<TicketsResponse>(`/api/projects/${id}/tickets`),
  brief: (id: string) => get<BriefResponse>(`/api/projects/${id}/brief`),
  putBrief: (id: string, brief: Brief) => send<BriefResponse>(`/api/projects/${id}/brief`, "PUT", brief),
  chat: (body: Record<string, unknown>) =>
    send<{ project_id: string; messages: any[] }>("/api/chat", "POST", body),
  chatHistory: (id: string) => get<{ messages: any[] }>(`/api/chat/${id}/history`),
  deployments: (id: string) => get<DeploymentsResponse>(`/api/projects/${id}/deployments`),
  deps: (id: string) => get<DepsResponse>(`/api/projects/${id}/deps`),
  submitDeps: (id: string, deps: DepSubmit) =>
    send<DepsSubmitResponse>(`/api/projects/${id}/deps`, "POST", { deps }),
  events: (id: string) => get<{ events: ProjectEvent[] }>(`/api/projects/${id}/events`),
  artifact: (id: string, path: string) =>
    get<Artifact>(`/api/projects/${id}/artifact?path=${encodeURIComponent(path)}`),
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
  // ── Onboarding draft model (docs/plans/concierge-onboarding-api.md) ──
  createDraft: (body?: { project_name?: string }) =>
    send<{ project_id: string }>("/api/drafts", "POST", body || {}),
  patchDraft: (id: string, body: { name?: string; goal?: string; scope?: string[] }) =>
    send<{ name: string; goal: string; scope: string[]; description: string; brief: Record<string, string>; coverage: Record<string, boolean> }>(`/api/projects/${id}/draft`, "PATCH", body),
  attach: (id: string, files: { name: string; content_b64: string }[]) =>
    send<{ attached: string[] }>(`/api/projects/${id}/attach`, "POST", { files }),
  promote: (id: string, body?: { description?: string; target?: string }) =>
    send<{ project_id: string; status: string }>(`/api/projects/${id}/promote`, "POST", body || {}),
};

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
