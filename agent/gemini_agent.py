"""
Gemini 2.0 Flash agent with MCP-style function calling.

Flow per user turn:
  1. Input guardrail (Layer 1)
  2. Build role-scoped system prompt
  3. Send to Gemini with tool declarations
  4. Loop: dispatch function calls → feed results back → repeat until text answer
  5. Return (text_answer, chart_json | None)
"""

import json
import os

import google.generativeai as genai
from dotenv import load_dotenv

from agent.system_prompt import build as build_prompt
from auth.roles import Role, VIEWER_TEMPLATES
from database.logger import log_query
from guardrails.input_guardrail import check as input_check
from mcp.tools import TOOL_DECLARATIONS, dispatch, get_schema

load_dotenv()
genai.configure(api_key=os.environ["GEMINI_API_KEY"])

_MODEL_NAME = "gemini-2.0-flash"
_MAX_TOOL_ROUNDS = 8       # safety cap on the agentic loop
_HISTORY_TURNS = 6         # number of past (user, assistant) pairs to keep


class QueryAgent:
    def __init__(self) -> None:
        self._schema_cache: str | None = None
        self._model = genai.GenerativeModel(
            model_name=_MODEL_NAME,
            tools=[{"function_declarations": TOOL_DECLARATIONS}],
        )

    # ── public ────────────────────────────────────────────────────────────────

    def chat(
        self,
        user_query: str,
        history: list[tuple[str, str]],
        role: Role,
        username: str,
    ) -> tuple[str, str | None]:
        """Return (text_response, chart_json_or_None)."""

        # Layer 1 — input guardrail
        allowed, reason = input_check(user_query)
        if not allowed:
            log_query(username=username, role=role, user_query=user_query,
                      status="blocked", guardrail_layer="1_input",
                      guardrail_reason=reason)
            return reason, None

        # Viewer: only allow pre-defined templates
        if role == Role.VIEWER:
            matched = next(
                (t for t in VIEWER_TEMPLATES if t.lower() in user_query.lower()), None
            )
            if not matched:
                msg = (
                    "As a Viewer you can only use the pre-approved question templates. "
                    "Please click one of the template buttons below."
                )
                log_query(username=username, role=role, user_query=user_query,
                          status="blocked", guardrail_layer="1_input",
                          guardrail_reason="viewer_template_mismatch")
                return msg, None

        schema = self._get_schema()
        system_prompt = build_prompt(schema, role, username)

        # Build Gemini message history (last N turns)
        messages: list[dict] = []
        for user_msg, assistant_msg in history[-_HISTORY_TURNS:]:
            messages.append({"role": "user",  "parts": [{"text": user_msg}]})
            messages.append({"role": "model", "parts": [{"text": assistant_msg}]})

        full_user_message = f"{system_prompt}\n\nUser question: {user_query}"

        log_query(username=username, role=role, user_query=user_query, status="processing")

        # ── agentic tool loop ──────────────────────────────────────────────
        chat_session = self._model.start_chat(history=messages)
        response = chat_session.send_message(full_user_message)

        chart_json: str | None = None

        for _ in range(_MAX_TOOL_ROUNDS):
            fn_calls = [
                p for p in response.candidates[0].content.parts
                if p.function_call.name  # non-empty name ⇒ real function call
            ]
            if not fn_calls:
                break

            tool_responses = []
            for part in fn_calls:
                fn_name = part.function_call.name
                fn_args = dict(part.function_call.args)

                result_str = dispatch(fn_name, fn_args, role, username)

                # Capture chart JSON for the UI
                if fn_name == "build_chart":
                    parsed = json.loads(result_str)
                    if "chart_json" in parsed:
                        chart_json = parsed["chart_json"]

                tool_responses.append(
                    genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=fn_name,
                            response={"result": result_str},
                        )
                    )
                )

            response = chat_session.send_message(
                genai.protos.Content(role="user", parts=tool_responses)
            )

        # ── extract final text ─────────────────────────────────────────────
        text_parts = [
            p.text
            for p in response.candidates[0].content.parts
            if hasattr(p, "text") and p.text
        ]
        final_text = "".join(text_parts) or "I was unable to generate a response."

        log_query(username=username, role=role, user_query=user_query,
                  chart_type=json.loads(chart_json).get("chart_type") if chart_json else None,
                  status="success")

        return final_text, chart_json

    # ── private ───────────────────────────────────────────────────────────────

    def _get_schema(self) -> str:
        if self._schema_cache is None:
            self._schema_cache = get_schema()
        return self._schema_cache


# Singleton — one agent instance shared across all requests.
_agent: QueryAgent | None = None


def get_agent() -> QueryAgent:
    global _agent
    if _agent is None:
        _agent = QueryAgent()
    return _agent
