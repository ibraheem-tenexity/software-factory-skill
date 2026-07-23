"""Pydantic request bodies for the console API. Pure data shapes — no logic, no app imports."""
from typing import Annotated

from pydantic import BaseModel, Field


BudgetAmount = Annotated[float, Field(gt=5)]


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


class OrgDiscoveryIn(BaseModel):
    repo_url: str = ""
    pat_secret: str | None = None


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


class CompanyEnrichIn(BaseModel):
    name: str | None = None
    website: str | None = None
    email_domain: str | None = None


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


class ConverseIn(BaseModel):
    message: str = ""


class SuggestedResponseOut(BaseModel):
    response: str
    type: str   # "single select" | "multi select"


class ConverseOut(BaseModel):
    # T2.2: no `choices`/readiness `done`. Empty suggested_responses means a plain-text turn; the
    # FE derives single/multi-select from each item's `type`. handed_off reports actual project state.
    response: str
    suggested_responses: list[SuggestedResponseOut] = []
    message_id: str = ""
    session_id: str = ""
    handed_off: bool = False  # factual result of this turn, so the UI follows agent-triggered promotion


class TranscribeIn(BaseModel):
    audio_base64: str = ""
    format: str = "webm"
    language: str | None = None


class DepsIn(BaseModel):
    deps: dict = {}


class ProvideDepIn(BaseModel):
    name: str = ""
    value: str = ""


class ProjectPatchIn(BaseModel):
    name: str | None = None
    description: str | None = None
    scope: list | None = None
    summary: str | None = None


class MaterialScopeIn(BaseModel):
    scope: str = "project"     # "project" | "org"


# ── Files browser (SOF-253): directory-aware source-tree mutations ────────────────────────────
class DirectoryCreateIn(BaseModel):
    parent_id: str = ""            # a real scoped directory (root or folder); the virtual root is rejected
    name: str = ""


class FileUploadIn(BaseModel):
    name: str = ""
    tag: str | None = None
    content_type: str | None = None
    data_b64: str = ""
    directory_id: str | None = None    # a project-scoped folder; omit => the project root


class FileMoveIn(BaseModel):
    # Omit `scope` for a within-scope move (just re-home under `directory_id`); set it to
    # "project"/"org" for a cross-scope move (existing scope-change policy + re-home under the
    # destination directory, or the destination scope root when `directory_id` is omitted).
    directory_id: str | None = None
    scope: str | None = None


class MaintenanceToggleIn(BaseModel):
    enabled: bool = False      # SOF-94: no-op maintenance-agent placeholder preference


class BudgetIn(BaseModel):
    ceiling: BudgetAmount


class RetryNodeIn(BaseModel):
    node: str


class RewindIn(BaseModel):
    node: str


# Option C onboarding (draft model): the form defers draft creation until the user types a name,
# then write-throughs project fields, attaches materials, and promotes at handoff. See docs/plans/fastapi-db-replacement.md.
class DraftCreateIn(BaseModel):
    project_name: str = ""
    runtime: str = ""
    planning_model: str = ""
    impl_model: str = ""
    model: str = ""   # opencode model alias: "kimi"|"glm"
    budget: BudgetAmount | None = None  # incomplete drafts may omit it; supplied caps must exceed $5
    github_username: str = ""


class DraftPatchIn(BaseModel):
    name: str | None = None
    goal: str | None = None
    scope: list | None = None
    runtime: str | None = None   # "claude"|"opencode"|"codex" — lets the Build-engine card update the draft after eager create
    model: str | None = None     # opencode model alias: "kimi"|"glm"
    budget: BudgetAmount | None = None  # update the spend ceiling; supplied caps must exceed $5
    recipe_id: str | None = None  # CBT-9: the picked recipe id (must name a published recipe), or "" to clear
    github_username: str | None = None


class RepoAccessIn(BaseModel):
    github_username: str = ""


class CredsIn(BaseModel):
    credentials: dict = {}   # {key_name: secret_value}; value never stored in DB — vault-only


class AttachIn(BaseModel):
    files: list = []


class PromoteIn(BaseModel):
    description: str = ""
    target: str = "railway"


class BriefVersionIn(BaseModel):
    # SOF-244: a complete Product Brief markdown body + the artifact id the editor loaded
    # (base_version_id). base_version_id is null only for the very first version; a stale base
    # (someone else saved meanwhile) returns 409 with the current latest.
    markdown: str
    base_version_id: int | None = None


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
    config: dict = {}
    attached_to: list | None = None


class ToolPatchIn(BaseModel):
    config: dict | None = None
    attached_to: list | None = None


class ToolKeyIn(BaseModel):
    value: str = ""


class RecipeIn(BaseModel):
    name: str
    tagline: str | None = None
    category: str | None = None
    capabilities: list | None = None
    body_md: str | None = None
    repo_url: str | None = None
    images: list | None = None
    status: str = "draft"


class RecipePatchIn(BaseModel):
    name: str | None = None
    tagline: str | None = None
    category: str | None = None
    capabilities: list | None = None
    body_md: str | None = None
    repo_url: str | None = None
    images: list | None = None
    status: str | None = None


# ── Org Secrets vault (§2.3) ────────────────────────────────────────────────────────────────────
from pydantic import Field  # noqa: E402


class SecretCreateIn(BaseModel):
    name: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    value: str
    kind: str = "api_key"


class SecretRotateIn(BaseModel):
    value: str
