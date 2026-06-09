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
    """Concierge model: gpt-4o (OpenAI) or Kimi K2.6 via OpenRouter's OpenAI-compatible API.

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
        return OpenAIChatCompletionsModel(model="moonshotai/kimi-k2.6", openai_client=client)
    return "gpt-4o"


CONCIERGE_INSTRUCTIONS = """\
You are the Factory Concierge — a friendly, focused assistant that helps users define \
what software to build. Your job is to gather enough information to launch the \
software factory pipeline.

## What you need before launching:
1. **Description** — what the user wants built (required)
2. **Context** — domain details, constraints, tech preferences (optional but helpful)
3. **Budget** — dollar amount for the build (default $100 if not specified)
4. **Target** — deployment target: "railway" (default) or "vercel"

## Conversation flow:
- Greet the user and ask what they'd like to build
- If the request is clear and complete, launch immediately — don't over-interrogate
- If the request is vague, ask ONE clarifying question at a time
- Accept files and images as additional context — acknowledge them
- Once you have enough, call start_pipeline to launch

## After pipeline launches:
- Use check_status to monitor progress and report updates naturally
- When the pipeline needs dependency tokens (API keys, etc.), call request_dep_input \
  — this shows secure input fields in the chat. NEVER ask users to paste tokens as text.
- When the pipeline completes, call get_result and share the deployment URL

## Style:
- Be concise — 1-3 sentences per response
- Be specific — name what you're building, not generic platitudes
- Don't repeat back the entire request — summarize in your own words
- Don't ask about budget/target unless the user brings it up (use defaults)
"""


def make_tools(console: Console, attachments=lambda: []) -> list[FunctionTool]:
    """Create agent tools that delegate to Console methods.

    `attachments` returns the files attached to the message currently being
    handled, so start_pipeline can thread them into the run.
    """

    async def _start_pipeline(description: str, context: str = "",
                              budget: float = 25.0, target: str = "railway") -> str:
        req = RunRequest(description=description, context=context,
                         budget=budget, target=target, context_files=attachments())
        run_id = console.start_run(req)
        return json.dumps({"run_id": run_id, "status": "started"})

    async def _check_status(run_id: str) -> str:
        return json.dumps(console.status(run_id))

    async def _get_required_deps(run_id: str) -> str:
        return json.dumps(console.stage2_artifacts(run_id))

    async def _request_dep_input(run_id: str, dep_names: list[str]) -> str:
        return json.dumps({"type": "dep_request", "run_id": run_id,
                           "dep_names": dep_names})

    async def _get_result(run_id: str) -> str:
        return json.dumps(console.evidence(run_id))

    return [
        FunctionTool(
            name="start_pipeline",
            description="Launch the software factory pipeline. Call when you have enough info from the user.",
            params_json_schema={
                "type": "object",
                "properties": {
                    "description": {"type": "string", "description": "What to build"},
                    "context": {"type": "string", "description": "Additional context", "default": ""},
                    "budget": {"type": "number", "description": "Budget in USD", "default": 25},
                    "target": {"type": "string", "enum": ["railway", "vercel"], "default": "railway"},
                },
                "required": ["description"],
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


class ChatAgentRunner:
    """Manages the concierge agent and translates between chat and Console."""

    def __init__(self, console: Console):
        self._console = console
        self._pending_files: list = []
        tools = make_tools(console, attachments=lambda: self._pending_files)
        self._agent = Agent(
            name="Factory Concierge",
            instructions=CONCIERGE_INSTRUCTIONS,
            tools=tools,
            model=select_chat_model(),
        )
        self._conversations: dict[str, list] = {}

    async def handle_message(self, run_id: str | None, user_msg: str,
                              files: list, images: list) -> tuple[str | None, list[ChatMessage]]:
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

        # Make attachments available to start_pipeline, which fires inside Runner.run.
        self._pending_files = files or []
        try:
            result = await Runner.run(self._agent, input=history)
        finally:
            self._pending_files = []

        response_msgs = []
        now = time.time()

        for item in result.new_items:
            if isinstance(item, MessageOutputItem):
                # raw_item is a ResponseOutputMessage; ItemHelpers walks its
                # ResponseOutputText parts and concatenates the text.
                text = ItemHelpers.text_message_output(item)
                if text:
                    response_msgs.append(ChatMessage(
                        role="assistant", content=text, msg_type="text", ts=now,
                    ))
            elif isinstance(item, ToolCallItem) and isinstance(item.raw_item, ResponseFunctionToolCall):
                call = item.raw_item  # typed: .name and .arguments (JSON str) always present
                # Required params are schema-validated by the SDK against OpenAI, but a
                # ChatCompletions-compat proxy (Kimi via OpenRouter) can emit malformed
                # arguments — degrade to a plain reply rather than 500ing the chat endpoint.
                if call.name == "start_pipeline":
                    try:
                        args = json.loads(call.arguments)
                        if not run_id:
                            run_id = f"run-{args['description'][:8].lower().replace(' ', '-')}"
                    except (ValueError, TypeError, KeyError):
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
