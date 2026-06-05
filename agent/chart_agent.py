"""
ChartAgent — selects the best visualisation for query results and surfaces key insights.

Receives rows + columns + user question from QueryAgent.
Responsibilities:
  1. Choose the most appropriate chart type for the data
  2. Call build_chart with correct parameters
  3. Return 1-2 bullet-point insights (trends, anomalies, highlights)
"""

import json
import os

from groq import Groq
from dotenv import load_dotenv

from auth.roles import Role
from mcp.tools import TOOL_DECLARATIONS, dispatch

load_dotenv()

_MODEL_NAME = "meta-llama/llama-4-scout-17b-16e-instruct"
_MAX_TOOL_ROUNDS = 3
_MAX_ROWS_TO_CHART = 200

_SYSTEM_PROMPT = """You are a data visualisation and insight specialist.
You receive query results and the user's original question.

Step 1 — choose the best chart type:
  - line    : time-series or sequential data (dates, months, ordered categories)
  - bar     : categorical comparisons (products, cities, brands)
  - pie     : part-of-whole with 6 or fewer categories
  - scatter : correlation between two numeric columns
  - histogram : distribution of a single numeric column
  If the data is a single scalar value or clearly unsuitable for a chart, skip build_chart.

Step 2 — call build_chart with chart_type, x_col, y_col, and a concise descriptive title.

Step 3 — after the chart is built (or if you skipped it), respond with exactly 1–2 bullet points using the • character.
Each bullet must highlight one notable trend, anomaly, or standout figure from the data.
Maximum 15 words per bullet. No preamble — output only the bullets.
"""

# ChartAgent only has access to build_chart
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
    if t["name"] == "build_chart"
]


class ChartAgent:
    def __init__(self) -> None:
        self._client = Groq(api_key=os.environ["GROQ_API_KEY"])

    def analyze(
        self,
        rows: list,
        columns: list,
        user_question: str,
        role: Role,
    ) -> tuple[str | None, str | None]:
        """Return (chart_json, insights_text)."""

        sample = rows[:_MAX_ROWS_TO_CHART]
        user_content = (
            f"User question: {user_question}\n\n"
            f"Columns: {columns}\n"
            f"Total rows: {len(rows)} (showing first {len(sample)})\n\n"
            f"Data:\n{json.dumps(sample, default=str)}"
        )

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_content},
        ]

        chart_json: str | None = None
        insights:   str | None = None

        for _ in range(_MAX_TOOL_ROUNDS):
            response = self._client.chat.completions.create(
                model=_MODEL_NAME,
                messages=messages,
                tools=_TOOLS,
                tool_choice="auto",
                max_tokens=1024,
            )
            msg = response.choices[0].message

            asst_entry: dict = {"role": "assistant", "content": msg.content or ""}
            if msg.tool_calls:
                asst_entry["tool_calls"] = [
                    {
                        "id": c.id,
                        "type": "function",
                        "function": {
                            "name": c.function.name,
                            "arguments": c.function.arguments,
                        },
                    }
                    for c in msg.tool_calls
                ]
            messages.append(asst_entry)

            if not msg.tool_calls:
                insights = msg.content or None
                break

            for call in msg.tool_calls:
                fn_name = call.function.name
                fn_args = json.loads(call.function.arguments)
                result_str = dispatch(fn_name, fn_args, role, "chart_agent")

                if fn_name == "build_chart":
                    parsed = json.loads(result_str)
                    if "chart_json" in parsed:
                        chart_json = parsed["chart_json"]

                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": result_str,
                })

        return chart_json, insights


_chart_agent: ChartAgent | None = None


def get_chart_agent() -> ChartAgent:
    global _chart_agent
    if _chart_agent is None:
        _chart_agent = ChartAgent()
    return _chart_agent
