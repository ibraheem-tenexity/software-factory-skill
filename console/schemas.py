"""Pydantic request bodies for the console API. Pure data shapes — no logic, no app imports."""
from pydantic import BaseModel


class GoogleLoginIn(BaseModel):
    credential: str = ""


class UserMgmtIn(BaseModel):
    email: str = ""
    role: str | None = None


class OrgIn(BaseModel):
    name: str = ""
    industry: str | None = None
    sub_focus: list = []
    headcount: str | None = None
    revenue: str | None = None
    location: str | None = None
    website: str | None = None
    connected_systems: list = []
    designation: str | None = None
    role_description: str | None = None


class OrgPatchIn(BaseModel):
    name: str | None = None
    industry: str | None = None
    sub_focus: list | None = None
    headcount: str | None = None
    revenue: str | None = None
    location: str | None = None
    website: str | None = None
    connected_systems: list | None = None
    plan: str | None = None
    monthly_budget_cap: float | None = None


class OrgDocIn(BaseModel):
    name: str = ""
    tag: str | None = None
    content_type: str | None = None
    data_b64: str = ""


class OrgDocPatchIn(BaseModel):
    name: str | None = None
    tag: str | None = None


class OrgDocUseIn(BaseModel):
    project_id: str = ""


class OrgMemberIn(BaseModel):
    email: str = ""
    role: str = "member"
    designation: str | None = None


class OrgMemberPatchIn(BaseModel):
    role: str | None = None
    designation: str | None = None


class OrgBillingIn(BaseModel):
    plan: str | None = None
    monthly_budget_cap: float | None = None


class ChatIn(BaseModel):
    project_id: str | None = None
    message: str = ""
    files: list = []
    images: list = []
    runtime: str = ""
    planning_model: str = ""
    impl_model: str = ""
    model: str = ""   # opencode model alias: "kimi"|"glm"
    project_name: str = ""
    gated: bool = False


class DepsIn(BaseModel):
    deps: dict = {}


class ContinueIn(BaseModel):
    gate: str = ""


class ProjectPatchIn(BaseModel):
    name: str | None = None
    description: str | None = None
    scope: list | None = None


class MaterialScopeIn(BaseModel):
    scope: str = "project"     # "project" | "org"


class Stage3In(BaseModel):
    creds: dict | None = None


class BudgetIn(BaseModel):
    ceiling: float | None = None


class RetryIn(BaseModel):
    stage: int = 0
    creds: dict | None = None


class RetryNodeIn(BaseModel):
    node: str


class RewindIn(BaseModel):
    node: str


class ProjectCreateIn(BaseModel):
    description: str = ""
    context: str = ""
    budget: float = 100
    target: str = "railway"
    files: list = []
    runtime: str = ""
    planning_model: str = ""
    impl_model: str = ""
    model: str = ""   # opencode model alias: "kimi"|"glm"
    project_name: str = ""
    gated: bool = False
    railway_token: str = ""
    railway_project_id: str = ""


# Option C onboarding (draft model): the form defers draft creation until the user types a name,
# then write-throughs project fields, attaches materials, and promotes at handoff. See docs/plans/fastapi-db-replacement.md.
class DraftCreateIn(BaseModel):
    project_name: str = ""
    runtime: str = ""
    planning_model: str = ""
    impl_model: str = ""
    model: str = ""   # opencode model alias: "kimi"|"glm"


class DraftPatchIn(BaseModel):
    name: str | None = None
    goal: str | None = None
    scope: list | None = None
    runtime: str | None = None   # "claude"|"opencode" — lets the Build-engine card update the draft's runtime after the eager create
    model: str | None = None     # opencode model alias: "kimi"|"glm"


class CredsIn(BaseModel):
    credentials: dict = {}   # {key_name: secret_value}; value never stored in DB — vault-only


class AttachIn(BaseModel):
    files: list = []


class PromoteIn(BaseModel):
    description: str = ""
    target: str = "railway"


# ── Tenexity OS (§3) admin bodies ───────────────────────────────────────────────────────────────
class DemoIn(BaseModel):
    is_demo: bool = False


class PromptIn(BaseModel):
    prompt: str = ""
    runtime: str | None = None   # "claude"|"opencode" for stage-skill prompts; omitted for others


class PasswordLoginIn(BaseModel):
    email: str = ""
    password: str = ""


class InviteIn(BaseModel):
    email: str = ""
    access_type: str = "org"     # "org" | "tenexity"
    org_name: str | None = None
    name: str | None = None
    designation: str | None = None
    method: str = "google"       # google|microsoft|password|sso
    password: str | None = None  # required when method == "password"
    role: str | None = None      # admin|member — honored for org users (was derived)


class AccessPatchIn(BaseModel):
    role: str | None = None
    status: str | None = None
    is_internal: bool | None = None   # Tenexity-staff flag; {role:"admin", is_internal:true} = "Make Tenexity admin"


class AgentIn(BaseModel):
    callsign: str = ""
    name: str = ""
    role: str | None = None
    model: str | None = None
    cost_tier: int = 1
    descr: str | None = None


class AgentPatchIn(BaseModel):
    name: str | None = None
    role: str | None = None
    model: str | None = None
    cost_tier: int | None = None
    descr: str | None = None


class ToolIn(BaseModel):
    name: str = ""
    type: str | None = None
    provider: str | None = None
    scope: str | None = None
    auth: str | None = None
    status: str = "available"


class ToolPatchIn(BaseModel):
    name: str | None = None
    type: str | None = None
    provider: str | None = None
    scope: str | None = None
    auth: str | None = None
    status: str | None = None


class SowIn(BaseModel):
    title: str
    org: str | None = None
    project: str | None = None
    value: str | None = None
    file: str | None = None
    version: int = 1
    status: str = "Draft"
    body: str | None = None


class SowPatchIn(BaseModel):
    title: str | None = None
    org: str | None = None
    project: str | None = None
    value: str | None = None
    file: str | None = None
    version: int | None = None
    status: str | None = None
    body: str | None = None

