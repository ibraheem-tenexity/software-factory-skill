"""OpenAI Agents SDK concierge — gathers user requirements and drives the pipeline."""
from __future__ import annotations

import json
import os
import time
from typing import Any

from agents import Agent, FunctionTool, ItemHelpers
from agents.items import MessageOutputItem, ToolCallItem
from openai.types.responses import ResponseFunctionToolCall

from software_factory.chat_store import ChatMessage
from software_factory.console import Console, RunRequest


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
You are the Factory Concierge. Your job is to INTERVIEW the user to build a complete project \
brief BEFORE launching the build — a richer brief produces a far more mature result than a \
single lazy prompt. Do not launch on the first vague request; interview first.

## The interview (one topic at a time)
Work through these topics conversationally, ONE question per turn, in roughly this order. Use \
the rubric in your head to know when a topic is sufficiently answered:
1. **Goals / context** — what the business does, the problem this solves, the primary objective.
2. **Success metrics** — concrete outcomes/numbers; how success is measured.
3. **Constraints** — timeline, budget, required/avoided tech, hosting, compliance.
4. **Stakeholders** — decision-makers, end users, sign-off.
5. **Existing assets** — code, designs, brand assets, wireframes, integrations, docs (accept files/images).
6. **Risks** — technical/business/dependency unknowns.
7. **Definition of done** — what the first version must do to be accepted.

After the user answers a topic, call **record_brief_section** with the section key \
(goals | success_metrics | constraints | stakeholders | existing_assets | risks | definition_of_done) \
and a crisp summary of their answer in your own words. Acknowledge attached files/images as \
existing_assets. Keep moving — don't re-ask what's already covered.

## Proceeding to the build
Call **propose_proceed** to check whether enough of the brief is covered. Once it reports ready \
(or the user explicitly says "just build it"), summarize the brief in 2-3 sentences, confirm, then \
call **start_pipeline** — this PROMOTES the in-progress draft into a real run and launches Stage 1, \
where a council of agents turns the brief into a full PRD. Never trap the user in endless \
questions: if they want to proceed early, do.

## After the pipeline launches
- Use check_status to monitor progress and report updates naturally.
- When the pipeline needs dependency tokens, call request_dep_input — this shows secure input \
  fields. NEVER ask users to paste tokens as text.
- When the pipeline completes, call get_result and share the deployment URL(s) — a project may \
  ship MORE THAN ONE deliverable (e.g. a mobile-web app + a web app + an API).

## Style
- Concise — 1-3 sentences per turn. Specific, not generic. One question at a time.
- Don't dump the whole brief back each turn; a short "got it — <next question>" is ideal.
"""


def make_tools(console: Console, attachments=lambda: [],
               runtime=lambda: "", models=lambda: ("", ""),
               project_name=lambda: "", gated=lambda: False,
               owner=lambda: "", viewer=lambda: ("", "admin"),
               draft_id=lambda: "", interview=lambda: "") -> list[FunctionTool]:
    """Create agent tools that delegate to Console methods.

    `attachments` returns files attached to the current message. `draft_id` returns the canonical
    run-<8hex> of the in-progress onboarding draft (minted by the server before the interview);
    record_brief_section/propose_proceed/start_pipeline all act on it. `interview` returns the
    rendered transcript so far (threaded into Stage 1 on promote). `viewer` returns (email, role)
    for run-scoped tool access control: admins/service see all, members see only their own.
    """
    from .brief import BRIEF_SECTIONS, enough

    def _allowed(run_id: str) -> bool:
        """Ownership check inside chat tools. Admins bypass; members must own the run."""
        email, role = viewer()
        if role == "admin":
            return True
        return bool(run_id) and (console.run_owner(run_id) or "").lower() == (email or "").lower()

    async def _record_brief_section(section: str, summary: str) -> str:
        rid = draft_id()
        if not rid:
            return json.dumps({"error": "no active draft"})
        if section not in BRIEF_SECTIONS:
            return json.dumps({"error": f"unknown section {section!r}", "valid": BRIEF_SECTIONS})
        cov = console.update_draft_brief(rid, {section: summary})
        ready, missing = enough(console.draft_brief(rid))
        return json.dumps({"recorded": section, "coverage": cov, "ready": ready, "missing": missing})

    async def _propose_proceed() -> str:
        rid = draft_id()
        if not rid:
            return json.dumps({"error": "no active draft"})
        brief = console.draft_brief(rid)
        ready, missing = enough(brief)
        return json.dumps({"ready": ready, "missing": missing,
                           "sections_filled": sorted(k for k, v in brief.items() if v)})

    async def _start_pipeline(description: str = "", context: str = "",
                              budget: float = 25.0, target: str = "railway") -> str:
        """Promote the in-progress draft into a real run and launch Stage 1 (the council writes the
        PRD from the accumulated brief + interview transcript)."""
        rid = draft_id()
        if not rid:
            return json.dumps({"error": "no active draft to promote"})
        try:
            run_id = console.promote_draft(rid, description=description,
                                           interview_md=interview(), target=target)
        except ValueError as e:               # duplicate project name — tell the user
            return json.dumps({"error": str(e)})
        return json.dumps({"run_id": run_id, "status": "started"})

    async def _check_status(run_id: str) -> str:
        if not _allowed(run_id):
            return json.dumps({"error": "forbidden"})
        return json.dumps(console.status(run_id))

    async def _get_required_deps(run_id: str) -> str:
        if not _allowed(run_id):
            return json.dumps({"error": "forbidden"})
        return json.dumps(console.stage2_artifacts(run_id))

    async def _request_dep_input(run_id: str, dep_names: list[str]) -> str:
        if not _allowed(run_id):
            return json.dumps({"error": "forbidden"})
        return json.dumps({"type": "dep_request", "run_id": run_id,
                           "dep_names": dep_names})

    async def _get_result(run_id: str) -> str:
        if not _allowed(run_id):
            return json.dumps({"error": "forbidden"})
        return json.dumps(console.evidence(run_id))

    return [
        FunctionTool(
            name="record_brief_section",
            description="Record one section of the project brief after the user answers that topic. "
                        "Call this as the interview progresses.",
            params_json_schema={
                "type": "object",
                "properties": {
                    "section": {"type": "string",
                                "enum": ["goals", "success_metrics", "constraints", "stakeholders",
                                         "existing_assets", "risks", "definition_of_done"]},
                    "summary": {"type": "string", "description": "A crisp summary of the user's answer"},
                },
                "required": ["section", "summary"],
            },
            on_invoke_tool=lambda ctx, inp: _record_brief_section(**json.loads(inp)),
        ),
        FunctionTool(
            name="propose_proceed",
            description="Check whether enough of the brief is covered to start the build. Returns "
                        "ready + which required sections are still missing.",
            params_json_schema={"type": "object", "properties": {}},
            on_invoke_tool=lambda ctx, inp: _propose_proceed(),
        ),
        FunctionTool(
            name="start_pipeline",
            description="Promote the interviewed draft into a real run and launch the build. Call only "
                        "after propose_proceed reports ready (or the user asks to proceed now).",
            params_json_schema={
                "type": "object",
                "properties": {
                    "description": {"type": "string", "description": "One-line app description (optional; "
                                    "the brief is the real payload)", "default": ""},
                    "target": {"type": "string", "enum": ["railway", "vercel"], "default": "railway"},
                },
                "required": [],
            },
            on_invoke_tool=lambda ctx, inp: _start_pipeline(**json.loads(inp)),
        ),
        FunctionTool(
            name="check_status",
            description="Check current pipeline status — phase, stage, cost.",
            params_json_schema={
                "type": "object",
                "properties": {"run_id": {"type": "string"}},
                "required": ["run_id"],
            },
            on_invoke_tool=lambda ctx, inp: _check_status(**json.loads(inp)),
        ),
        FunctionTool(
            name="get_required_deps",
            description="Get list of required dependency tokens after Stage 2 completes.",
            params_json_schema={
                "type": "object",
                "properties": {"run_id": {"type": "string"}},
                "required": ["run_id"],
            },
            on_invoke_tool=lambda ctx, inp: _get_required_deps(**json.loads(inp)),
        ),
        FunctionTool(
            name="request_dep_input",
            description="Signal the frontend to show secure input fields for dependency tokens. Use this instead of asking the user to paste tokens in chat.",
            params_json_schema={
                "type": "object",
                "properties": {
                    "run_id": {"type": "string"},
                    "dep_names": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["run_id", "dep_names"],
            },
            on_invoke_tool=lambda ctx, inp: _request_dep_input(**json.loads(inp)),
        ),
        FunctionTool(
            name="get_result",
            description="Get final artifacts and deployment URL after pipeline completes.",
            params_json_schema={
                "type": "object",
                "properties": {"run_id": {"type": "string"}},
                "required": ["run_id"],
            },
            on_invoke_tool=lambda ctx, inp: _get_result(**json.loads(inp)),
        ),
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

    def __init__(self, console: Console):
        self._console = console
        self._pending_files: list = []
        self._pending_runtime: str = ""
        self._pending_models: tuple = ("", "")
        self._pending_name: str = ""
        self._pending_gated: bool = False
        self._pending_owner: str = ""
        self._pending_viewer: tuple[str, str] = ("", "admin")
        self._pending_draft_id: str = ""
        self._pending_interview_md: str = ""
        tools = make_tools(console, attachments=lambda: self._pending_files,
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

    async def handle_message(self, run_id: str | None, user_msg: str,
                              files: list, images: list,
                              runtime: str = "", planning_model: str = "",
                              impl_model: str = "",
                              project_name: str = "",
                              gated: bool = False,
                              owner: str = "", role: str = "admin") -> tuple[str | None, list[ChatMessage]]:
        """Process a user message through the agent. Returns (run_id, response_messages)."""
        from agents import Runner

        conv_key = run_id or "__new__"
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
        self._pending_draft_id = run_id or ""
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
                if call.name == "start_pipeline":
                    # The draft was promoted in-place; run_id is already the canonical draft id
                    # (set by the server before the interview). No slug minting.
                    if not run_id:
                        continue
                    response_msgs.append(ChatMessage(
                        role="system", content="Pipeline started.",
                        msg_type="pipeline_started", ts=now,
                        metadata={"run_id": run_id},
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
                        metadata={"run_id": run_id, "dep_names": dep_names},
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
        self._conversations[run_id or conv_key] = history

        return run_id, response_msgs

    def check_and_notify(self, run_id: str, prev_stage: int = 0) -> list[ChatMessage]:
        """Check pipeline status and generate notification messages for transitions."""
        status = self._console.status(run_id)
        msgs: list[ChatMessage] = []
        now = time.time()

        if status.get("stage1_done") and prev_stage < 2:
            msgs.append(ChatMessage(
                role="system",
                content="Research complete — Design & Architecture stage starting.",
                msg_type="status_update", ts=now,
                metadata={"run_id": run_id, "stage": 2},
            ))

        if status.get("stage2_done") and prev_stage < 3:
            deps = status.get("deps_required", [])
            if deps and not status.get("deps_satisfied"):
                msgs.append(ChatMessage(
                    role="assistant",
                    content="The architecture requires these credentials to proceed. "
                            "Please provide them in the secure fields below.",
                    msg_type="dep_request", ts=now,
                    metadata={"run_id": run_id, "dep_names": deps},
                ))
            else:
                msgs.append(ChatMessage(
                    role="system",
                    content="Design complete — Build stage starting.",
                    msg_type="status_update", ts=now,
                    metadata={"run_id": run_id, "stage": 3},
                ))

        if status.get("done"):
            url = status.get("deploy_url", "")
            spent = status.get("spent_usd", 0)
            msgs.append(ChatMessage(
                role="assistant",
                content=f"Build complete! Deployed to {url} — total cost ${spent:.2f}.",
                msg_type="complete", ts=now,
                metadata={"run_id": run_id, "url": url, "spent_usd": spent},
            ))

        return msgs
