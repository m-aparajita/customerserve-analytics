"""
QueryAgent — Groq LLaMA agent with OpenAI-compatible function calling.

Flow per user turn:
  1. Input guardrail (Layer 1)
  2. Build role-scoped system prompt
  3. Send to Groq with tool declarations (get_schema, query_database, get_sample_data)
  4. Loop: dispatch function calls → feed results back → repeat until text answer
  5. Return (text_answer, query_result | None)
     query_result is passed to ChartAgent for visualisation + insights.
"""

import json
import os

from groq import Groq
from dotenv import load_dotenv

from agent.system_prompt import build as build_prompt
from auth.roles import Role, VIEWER_TEMPLATES
from database.logger import log_query
from guardrails.input_guardrail import check as input_check
from mcp.tools import TOOL_DECLARATIONS, dispatch

load_dotenv()

_MODEL_NAME = "meta-llama/llama-4-scout-17b-16e-instruct"
_MAX_TOOL_ROUNDS = 8
_HISTORY_TURNS = 6

# QueryAgent only handles schema + data retrieval; build_chart is owned by ChartAgent
_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": t["name"],
            "description": t["description"],
            "parameters": t["parameters"],
        },
    }
    for t in TOOL_DECLARATIONS
    if t["name"] != "build_chart"
]


class QueryAgent:
    def __init__(self) -> None:
        self._client = Groq(api_key=os.environ["GROQ_API_KEY"])

    # ── public ────────────────────────────────────────────────────────────────

    def chat(
        self,
        user_query: str,
        history: list[tuple[str, str]],
        role: Role,
        username: str,
    ) -> tuple[str, dict | None]:
        """Return (text_response, query_result_or_None).

        query_result is the parsed JSON from the last query_database call,
        containing 'rows', 'columns', and 'row_count'. Passed to ChartAgent.
        """

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

        system_prompt = build_prompt(role, username)

        # Build message list with system prompt and conversation history
        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        for user_msg, assistant_msg in history[-_HISTORY_TURNS:]:
            messages.append({"role": "user", "content": user_msg})
            messages.append({"role": "assistant", "content": assistant_msg})
        messages.append({"role": "user", "content": user_query})

        log_query(username=username, role=role, user_query=user_query, status="processing")

        last_query_result: dict | None = None
        final_text = "I was unable to generate a response."
        last_msg = None

        # ── agentic tool loop ──────────────────────────────────────────────
        for _ in range(_MAX_TOOL_ROUNDS):
            response = self._client.chat.completions.create(
                model=_MODEL_NAME,
                messages=messages,
                tools=_TOOLS,
                tool_choice="auto",
                max_tokens=4096,
            )
            last_msg = response.choices[0].message

            asst_entry: dict = {
                "role": "assistant",
                "content": last_msg.content or "",
            }
            if last_msg.tool_calls:
                asst_entry["tool_calls"] = [
                    {
                        "id": c.id,
                        "type": "function",
                        "function": {
                            "name": c.function.name,
                            "arguments": c.function.arguments,
                        },
                    }
                    for c in last_msg.tool_calls
                ]
            messages.append(asst_entry)

            if not last_msg.tool_calls:
                final_text = last_msg.content or final_text
                break

            for call in last_msg.tool_calls:
                fn_name = call.function.name
                fn_args = json.loads(call.function.arguments)

                result_str = dispatch(fn_name, fn_args, role, username)

                if fn_name == "query_database":
                    parsed = json.loads(result_str)
                    if "rows" in parsed:
                        last_query_result = parsed

                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": result_str,
                })

        log_query(username=username, role=role, user_query=user_query, status="success")

        return final_text, last_query_result

# Singleton — one agent instance shared across all requests.
_agent: QueryAgent | None = None


def get_agent() -> QueryAgent:
    global _agent
    if _agent is None:
        _agent = QueryAgent()
    return _agent
