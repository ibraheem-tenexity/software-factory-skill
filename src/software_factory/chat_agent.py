"""OpenAI Agents SDK concierge — gathers user requirements and drives the pipeline."""
from __future__ import annotations

import json
import os
import time

from agents import Agent, FunctionTool, ItemHelpers
from agents.items import MessageOutputItem, ToolCallItem
from openai.types.responses import ResponseFunctionToolCall

from software_factory.chat_store import ChatMessage
from software_factory.console import Console


def select_chat_model():
    """Concierge model: gpt-4o (OpenAI) or Kimi K2.7 Code via OpenRouter's OpenAI-compatible API.

    SF_CHAT_MODEL=kimi forces Kimi; SF_CHAT_MODEL=gpt-4o forces OpenAI; unset picks gpt-4o when
    OPENAI_API_KEY exists, else Kimi when only OPENROUTER_API_KEY does. The env flag IS the
    rollback path if Kimi's function-calling misbehaves through the compat proxy."""
    choice = os.environ.get("SF_CHAT_MODEL", "").strip().lower()
    use_kimi = choice == "kimi" or (
        not choice and not os.environ.get("OPENAI_API_KEY") and os.environ.get("OPENROUTER_API_KEY")
    )
    if use_kimi:
        from agents import OpenAIChatCompletionsModel, set_tracing_disabled
        from openai import AsyncOpenAI

        set_tracing_disabled(True)  # tracing would try (and fail) to reach OpenAI
        client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ.get("OPENROUTER_API_KEY", ""),
        )
        return OpenAIChatCompletionsModel(model="moonshotai/kimi-k2.7-code", openai_client=client)
    return "gpt-4o"


CONCIERGE_INSTRUCTIONS = """\
You are the Factory Concierge for the Software Factory onboarding. You guide the user through a short \
intake — their company (first-time users only) and THIS project — PERSISTING each answer as you go \
with your tools, then hand off to the build factory. Ask EXACTLY ONE question per turn and WAIT for \
the answer before moving on (never stack two questions in one message).

## First, who am I talking to
Call **get_company_profile** at the start. If it returns an org, this is a RETURNING user — their \
company context is on file and REUSED; do NOT re-ask it, go straight to the project. If it returns \
null, this is a FIRST-TIME user — set up the company first, then the project.

## Company setup (first-time only)
Gather and persist with **set_company_profile** (industry + what the company does, company name, \
headcount, annual revenue, the user's role). Optionally call **set_connected_systems** with the ids \
of systems they use (epicor | sap | netsuite | qb | sf | site) — optional, it lets the factory pull \
real SKUs/customers/pricing. One question per turn; persist as each answer comes in.

## The project (always)
- Project name + what they're building (the outcome/goal) → **set_project_basics**.
- Which parts of the business it touches (the scope of work) → **set_project_scope**.
- Materials: a walkthrough video or documents are the highest-signal input. Files the user attaches \
  arrive with their message and are saved automatically — acknowledge them with \
  **attach_project_materials**. If a specific high-value material is missing, ask for it with \
  **request_materials**.

## Persisting + proceeding
Persist every answer immediately via the matching set_* tool — never just hold it in the chat. Use \
**get_intake_state** to see what's captured and **validate_intake_complete** to gauge readiness. The \
USER decides when to proceed and the on-screen checklist owns completion, so don't badger — when they \
are ready (or say "just build it"), confirm in one short line and call **hand_off_to_factory**, which \
promotes the draft into a real run and launches the build.

## After handoff
Stay on. Use **check_status** to report progress naturally; **request_dep_input** when the build needs \
credentials (NEVER ask the user to paste tokens as chat text); **get_result** to share the deployment \
URL(s) when it's done — a project may ship more than one deliverable.

## Style
Concise — 1-3 sentences per turn, ONE question, specific not generic. A short "got it — <next>" is ideal.
"""


def make_tools(console: Console, users=None, attachments=lambda: [],
               runtime=lambda: "", models=lambda: ("", ""),
               project_name=lambda: "", gated=lambda: False,
               owner=lambda: "", viewer=lambda: ("", "admin"),
               draft_id=lambda: "", interview=lambda: "") -> list[FunctionTool]:
    """The locked 13-tool concierge set (Option C onboarding). Tools delegate to Console (draft/run)
    and the UserStore (company org). `users` is the UserStore; `owner`/`viewer` give the signed-in
    email + role; `draft_id` is the canonical run-<8hex> of the in-progress onboarding draft (the form
    eagerly creates it and shares the id); `interview` is the rendered transcript threaded into Stage 1
    on hand-off; `attachments` is the files on the current message (auto-persisted by the server).
    """
    from .brief import enough

    def _email() -> str:
        return (owner() or "").strip().lower()

    def _allowed(project_id: str) -> bool:
        """Ownership check for run-scoped tools. Admins bypass; members must own the run."""
        email, role = viewer()
        if role == "admin":
            return True
        return bool(project_id) and (console.project_owner(project_id) or "").lower() == (email or "").lower()

    # ── Company / org (first-time setup; editable when returning) ──────────────────────────────
    async def _get_company_profile() -> str:
        if not users:
            return json.dumps({"org": None})
        return json.dumps({"org": users.org_for_user(_email())})

    async def _set_company_profile(name: str = "", industry: str = None, sub_focus: list = None,
                                   headcount: str = None, revenue: str = None, website: str = None,
                                   role: str = None, role_description: str = None) -> str:
        if not users:
            return json.dumps({"error": "no user store"})
        email = _email()
        if not email:
            return json.dumps({"error": "no signed-in user"})
        org = users.org_for_user(email)
        if org:
            fields = {k: v for k, v in {"name": (name or None), "industry": industry,
                      "sub_focus": sub_focus, "headcount": headcount, "revenue": revenue,
                      "website": website}.items() if v is not None}
            if fields:
                users.update_org(org["id"], **fields)
            oid = org["id"]
        else:
            if not (name or "").strip():
                return json.dumps({"error": "company name required to create the profile"})
            oid = users.create_org(name, industry=industry, sub_focus=sub_focus, headcount=headcount,
                                   revenue=revenue, website=website, by=email)
        if role is not None or role_description is not None:
            users.set_profile(email, org_id=oid, designation=role, role_description=role_description)
        return json.dumps({"org": users.get_org(oid)})

    async def _set_connected_systems(ids: list) -> str:
        if not users:
            return json.dumps({"error": "no user store"})
        org = users.org_for_user(_email())
        if not org:
            return json.dumps({"error": "set the company profile first"})
        users.update_org(org["id"], connected_systems=ids or [])
        return json.dumps({"org": users.get_org(org["id"])})

    # ── Project (writes to the draft; description composed server-side) ────────────────────────
    async def _set_project_basics(name: str = "", goal: str = "") -> str:
        pid = draft_id()
        if not pid:
            return json.dumps({"error": "no active draft"})
        return json.dumps(console.set_draft_project(pid, name=(name or None), goal=(goal or None)))

    async def _set_project_scope(scope: list) -> str:
        pid = draft_id()
        if not pid:
            return json.dumps({"error": "no active draft"})
        return json.dumps(console.set_draft_project(pid, scope=(scope or [])))

    async def _attach_project_materials() -> str:
        # Files arrive with the chat message and the server auto-persists them to the draft's input/.
        # This tool just lets the agent acknowledge what came in this turn.
        names = [f.get("name", "file") for f in (attachments() or [])]
        return json.dumps({"attached_this_turn": names})

    async def _request_materials(what: str = "", why: str = "") -> str:
        return json.dumps({"type": "materials_request", "what": what, "why": why})

    async def _get_intake_state() -> str:
        # READ-ONLY. The frontend OWNS the checklist + ready gate; this is for the agent's own
        # reasoning, it must NOT compute or push completion to the UI.
        pid = draft_id()
        org = users.org_for_user(_email()) if users else None
        project = console.draft_project(pid) if pid else {}
        return json.dumps({"company": org, "project": project})

    async def _validate_intake_complete() -> str:
        pid = draft_id()
        brief = console.draft_brief(pid) if pid else {}
        ready, missing = enough(brief)
        return json.dumps({"ready": ready, "missing": missing})

    async def _hand_off_to_factory(target: str = "railway") -> str:
        pid = draft_id()
        if not pid:
            return json.dumps({"error": "no active draft to promote"})
        try:
            project_id = console.promote_draft(pid, interview_md=interview(), target=target)
        except ValueError as e:               # duplicate project name — tell the user
            return json.dumps({"error": str(e)})
        return json.dumps({"project_id": project_id, "status": "started"})

    async def _check_status(project_id: str) -> str:
        if not _allowed(project_id):
            return json.dumps({"error": "forbidden"})
        return json.dumps(console.status(project_id))

    async def _request_dep_input(project_id: str, dep_names: list) -> str:
        if not _allowed(project_id):
            return json.dumps({"error": "forbidden"})
        return json.dumps({"type": "dep_request", "project_id": project_id, "dep_names": dep_names})

    async def _get_result(project_id: str) -> str:
        if not _allowed(project_id):
            return json.dumps({"error": "forbidden"})
        return json.dumps(console.evidence(project_id))

    def _tool(name, desc, props, required, fn):
        return FunctionTool(name=name, description=desc,
                            params_json_schema={"type": "object", "properties": props,
                                                "required": required, "additionalProperties": False},
                            on_invoke_tool=lambda ctx, inp, _fn=fn: _fn(**json.loads(inp or "{}")))

    _str = {"type": "string"}
    _strs = {"type": "array", "items": {"type": "string"}}
    return [
        _tool("get_company_profile",
              "Read the company/org already on file for the signed-in user (null if first-time). "
              "Call this first to tell returning users from first-time users.",
              {}, [], lambda: _get_company_profile()),
        _tool("set_company_profile",
              "Create or update the user's company profile (first-time setup, or edits). Persists to "
              "the org. industry/headcount/revenue are stored as LABELS (e.g. '51–200', '$10M–$50M').",
              {"name": _str, "industry": _str, "sub_focus": _strs, "headcount": _str,
               "revenue": _str, "website": _str, "role": _str, "role_description": _str},
              [], _set_company_profile),
        _tool("set_connected_systems",
              "Record which systems the company uses (ids: epicor|sap|netsuite|qb|sf|site). Optional; "
              "lets the factory pull real SKUs/customers/pricing. Requires a company profile first.",
              {"ids": _strs}, ["ids"], _set_connected_systems),
        _tool("set_project_basics",
              "Set the project NAME and the GOAL (what they're building / the outcome). Persists to the "
              "draft; the server composes the canonical description from goal + scope.",
              {"name": _str, "goal": _str}, [], _set_project_basics),
        _tool("set_project_scope",
              "Set the scope-of-work areas this project touches (e.g. 'Quoting / RFQ', 'Order entry'). "
              "Persists to the draft and is appended to the project description server-side.",
              {"scope": _strs}, ["scope"], _set_project_scope),
        _tool("attach_project_materials",
              "Acknowledge materials the user attached this turn (walkthrough video / documents). Files "
              "auto-persist to the draft; this confirms what arrived.",
              {}, [], lambda: _attach_project_materials()),
        _tool("request_materials",
              "Ask the user to provide a specific high-signal material you don't have yet (e.g. a "
              "walkthrough video). Use for missing inputs, not for tokens (use request_dep_input).",
              {"what": _str, "why": _str}, ["what"], _request_materials),
        _tool("get_intake_state",
              "READ-ONLY snapshot of what's captured: company org + project {name, goal, scope, "
              "description, brief}. For your reasoning only — the on-screen checklist owns completion.",
              {}, [], lambda: _get_intake_state()),
        _tool("validate_intake_complete",
              "Check whether enough is captured to proceed. Returns {ready, missing}. Advisory — the "
              "user decides when to hand off.",
              {}, [], lambda: _validate_intake_complete()),
        _tool("hand_off_to_factory",
              "Promote the draft into a real run and launch the build. Call when the user is ready (or "
              "says 'just build it').",
              {"target": {"type": "string", "enum": ["railway", "vercel"], "default": "railway"}},
              [], _hand_off_to_factory),
        _tool("check_status",
              "Check current pipeline status — phase, stage, cost — after handoff.",
              {"project_id": _str}, ["project_id"], _check_status),
        _tool("request_dep_input",
              "Signal the frontend to show secure input fields for dependency tokens. Use this instead "
              "of asking the user to paste tokens in chat.",
              {"project_id": _str, "dep_names": _strs}, ["project_id", "dep_names"], _request_dep_input),
        _tool("get_result",
              "Get final artifacts and deployment URL(s) after the pipeline completes.",
              {"project_id": _str}, ["project_id"], _get_result),
    ]


def _render_interview(history: list[dict]) -> str:
    """Render the conversation so far as a plain-text transcript for the Stage-1 input."""
    lines = []
    for turn in history:
        role = (turn.get("role") or "").upper()
        content = turn.get("content")
        if isinstance(content, str) and content.strip():
            lines.append(f"{role}: {content.strip()}")
    return "\n\n".join(lines)


class ChatAgentRunner:
    """Manages the concierge agent and translates between chat and Console."""

    def __init__(self, console: Console, users=None):
        self._console = console
        self._users = users
        self._pending_files: list = []
        self._pending_runtime: str = ""
        self._pending_models: tuple = ("", "")
        self._pending_name: str = ""
        self._pending_gated: bool = False
        self._pending_owner: str = ""
        self._pending_viewer: tuple[str, str] = ("", "admin")
        self._pending_draft_id: str = ""
        self._pending_interview_md: str = ""
        tools = make_tools(console, users=users, attachments=lambda: self._pending_files,
                           runtime=lambda: self._pending_runtime,
                           models=lambda: self._pending_models,
                           project_name=lambda: self._pending_name,
                           gated=lambda: self._pending_gated,
                           owner=lambda: self._pending_owner,
                           viewer=lambda: self._pending_viewer,
                           draft_id=lambda: self._pending_draft_id,
                           interview=lambda: self._pending_interview_md)
        self._agent = Agent(
            name="Factory Concierge",
            instructions=CONCIERGE_INSTRUCTIONS,
            tools=tools,
            model=select_chat_model(),
        )
        self._conversations: dict[str, list] = {}

    async def handle_message(self, project_id: str | None, user_msg: str,
                              files: list, images: list,
                              runtime: str = "", planning_model: str = "",
                              impl_model: str = "",
                              project_name: str = "",
                              gated: bool = False,
                              owner: str = "", role: str = "admin") -> tuple[str | None, list[ChatMessage]]:
        """Process a user message through the agent. Returns (project_id, response_messages)."""
        from agents import Runner

        conv_key = project_id or "__new__"
        history = self._conversations.get(conv_key, [])

        content_parts = []
        if user_msg:
            content_parts.append({"type": "input_text", "text": user_msg})
        for f in (files or []):
            content_parts.append({"type": "input_text",
                                  "text": f"[Attached file: {f.get('name', 'file')}]"})
        for img in (images or []):
            content_parts.append({"type": "input_text",
                                  "text": f"[Attached image: {img.get('name', 'image')}]"})

        if len(content_parts) == 1 and content_parts[0]["type"] == "input_text":
            user_input = content_parts[0]["text"]
        else:
            user_input = "\n".join(p.get("text", "") for p in content_parts)

        history.append({"role": "user", "content": user_input})

        # Make attachments + the picked runtime available to start_pipeline, which fires
        # inside Runner.run. The draft id (canonical run-<8hex>, minted by the server before the
        # interview) is what record_brief_section / propose_proceed / start_pipeline act on; the
        # transcript so far is threaded into Stage 1 on promote.
        self._pending_files = files or []
        self._pending_runtime = runtime or ""
        self._pending_models = (planning_model or "", impl_model or "")
        self._pending_name = project_name or ""
        self._pending_gated = bool(gated)
        self._pending_owner = owner or ""
        self._pending_viewer = (owner or "", role or "admin")
        self._pending_draft_id = project_id or ""
        self._pending_interview_md = _render_interview(history)
        try:
            result = await Runner.run(self._agent, input=history)
        finally:
            self._pending_files = []
            self._pending_runtime = ""
            self._pending_models = ("", "")
            self._pending_name = ""
            self._pending_gated = False
            self._pending_owner = ""
            self._pending_viewer = ("", "admin")
            self._pending_draft_id = ""
            self._pending_interview_md = ""

        response_msgs = []
        text_parts: list[str] = []
        now = time.time()

        for item in result.new_items:
            if isinstance(item, MessageOutputItem):
                # raw_item is a ResponseOutputMessage; ItemHelpers walks its
                # ResponseOutputText parts and concatenates the text. The SDK can emit MORE THAN
                # ONE MessageOutputItem in a single turn (the model pausing around tool calls, or
                # just being chatty) — surfacing each as its own bubble showed the user two
                # questions in a row. Collapse all of a turn's assistant text into ONE message.
                text = ItemHelpers.text_message_output(item)
                if text:
                    text_parts.append(text)
            elif isinstance(item, ToolCallItem) and isinstance(item.raw_item, ResponseFunctionToolCall):
                call = item.raw_item  # typed: .name and .arguments (JSON str) always present
                # Required params are schema-validated by the SDK against OpenAI, but a
                # ChatCompletions-compat proxy (Kimi via OpenRouter) can emit malformed
                # arguments — degrade to a plain reply rather than 500ing the chat endpoint.
                if call.name == "hand_off_to_factory":
                    # The draft was promoted in-place; project_id is already the canonical draft id
                    # (set by the server before the interview). No slug minting.
                    if not project_id:
                        continue
                    response_msgs.append(ChatMessage(
                        role="system", content="Pipeline started.",
                        msg_type="pipeline_started", ts=now,
                        metadata={"project_id": project_id},
                    ))
                elif call.name == "request_dep_input":
                    try:
                        dep_names = json.loads(call.arguments)["dep_names"]
                    except (ValueError, TypeError, KeyError):
                        continue
                    response_msgs.append(ChatMessage(
                        role="assistant",
                        content="The architecture requires these credentials. Please provide them below.",
                        msg_type="dep_request", ts=now,
                        metadata={"project_id": project_id, "dep_names": dep_names},
                    ))

        # One assistant bubble per turn: the reply (joined text) goes first, then any
        # tool-driven system messages (pipeline_started / dep_request).
        if text_parts:
            response_msgs.insert(0, ChatMessage(
                role="assistant", content="\n\n".join(text_parts), msg_type="text", ts=now,
            ))

        if result.final_output and not response_msgs:
            response_msgs.append(ChatMessage(
                role="assistant", content=str(result.final_output),
                msg_type="text", ts=now,
            ))

        history.extend([{"role": "assistant", "content": m.content} for m in response_msgs
                        if m.role == "assistant"])
        self._conversations[project_id or conv_key] = history

        return project_id, response_msgs

    def check_and_notify(self, project_id: str, prev_stage: int = 0) -> list[ChatMessage]:
        """Check pipeline status and generate notification messages for transitions."""
        status = self._console.status(project_id)
        msgs: list[ChatMessage] = []
        now = time.time()

        if status.get("stage1_done") and prev_stage < 2:
            msgs.append(ChatMessage(
                role="system",
                content="Research complete — Design & Architecture stage starting.",
                msg_type="status_update", ts=now,
                metadata={"project_id": project_id, "stage": 2},
            ))

        if status.get("stage2_done") and prev_stage < 3:
            deps = status.get("deps_required", [])
            if deps and not status.get("deps_satisfied"):
                msgs.append(ChatMessage(
                    role="assistant",
                    content="The architecture requires these credentials to proceed. "
                            "Please provide them in the secure fields below.",
                    msg_type="dep_request", ts=now,
                    metadata={"project_id": project_id, "dep_names": deps},
                ))
            else:
                msgs.append(ChatMessage(
                    role="system",
                    content="Design complete — Build stage starting.",
                    msg_type="status_update", ts=now,
                    metadata={"project_id": project_id, "stage": 3},
                ))

        if status.get("done"):
            url = status.get("deploy_url", "")
            spent = status.get("spent_usd", 0)
            msgs.append(ChatMessage(
                role="assistant",
                content=f"Build complete! Deployed to {url} — total cost ${spent:.2f}.",
                msg_type="complete", ts=now,
                metadata={"project_id": project_id, "url": url, "spent_usd": spent},
            ))

        return msgs
