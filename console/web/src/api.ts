// Thin typed client over the existing console JSON API. Cookie auth → credentials: "include".

export type RunSummary = {
  run_id: string;
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

// GET /api/runs/{id}/deployments → console.deployments(). Per-deliverable: a run ships 1..N apps.
export type Deployment = { app?: string; url?: string; repo?: string; [k: string]: any };
export type DeploymentsResponse = { deployments: Deployment[]; apps: string[] };

// GET /api/runs/{id}/deps → console.stage2_artifacts(). `tokens` are the architecture-derived
// required tokens; `disposition[name]` is the per-token plan (mcp | mock | provide).
export type DepToken = { name: string; [k: string]: any };
export type DepsResponse = {
  deps_required: string[];
  deps_provided: string[];
  deps_satisfied: boolean;
  disposition: Record<string, string>;
  tokens: DepToken[];
};
// POST /api/runs/{id}/deps body — {deps: {name: {disposition, value?}}}. value rides into the
// Stage-3 env only; it is never persisted to disk (see console.submit_deps).
export type DepSubmit = Record<string, { disposition: string; value?: string }>;
export type DepsSubmitResponse = {
  deps_provided: string[]; deps_required: string[]; disposition: Record<string, string>;
  missing: string[]; satisfied: boolean;
};

export type RunEvent = { ts: number; type: string; payload: Record<string, any> };
export type Artifact = { path: string; content?: string; error?: string };

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
  runs: () => get<{ runs: RunSummary[] }>("/api/runs"),
  status: (id: string) => get<RunSummary & Record<string, any>>(`/api/runs/${id}`),
  graph: (id: string) => get<Graph>(`/api/runs/${id}/graph`),
  tickets: (id: string) => get<TicketsResponse>(`/api/runs/${id}/tickets`),
  brief: (id: string) => get<BriefResponse>(`/api/runs/${id}/brief`),
  putBrief: (id: string, brief: Brief) => send<BriefResponse>(`/api/runs/${id}/brief`, "PUT", brief),
  chat: (body: Record<string, unknown>) =>
    send<{ run_id: string; messages: any[] }>("/api/chat", "POST", body),
  chatHistory: (id: string) => get<{ messages: any[] }>(`/api/chat/${id}/history`),
  deployments: (id: string) => get<DeploymentsResponse>(`/api/runs/${id}/deployments`),
  deps: (id: string) => get<DepsResponse>(`/api/runs/${id}/deps`),
  submitDeps: (id: string, deps: DepSubmit) =>
    send<DepsSubmitResponse>(`/api/runs/${id}/deps`, "POST", { deps }),
  events: (id: string) => get<{ events: RunEvent[] }>(`/api/runs/${id}/events`),
  artifact: (id: string, path: string) =>
    get<Artifact>(`/api/runs/${id}/artifact?path=${encodeURIComponent(path)}`),
  getOrg: () => get<{ org: Org | null }>("/api/org"),
  createOrg: (body: OrgInput) => send<{ org: Org }>("/api/org", "POST", body),
  patchOrg: (body: Partial<Org>) => send<{ org: Org }>("/api/org", "PATCH", body),
  createRun: (body: { description: string; project_name: string }) =>
    send<{ run_id: string }>("/api/runs", "POST", body),
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
