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
_MAX_TOOL_ROUNDS_DEEP = 6
_MAX_ROWS_TO_CHART = 200

_SYSTEM_PROMPT = """You are a data visualisation and insight specialist.
You receive query results and the user's original question.

Step 1 — choose the best chart type:
  - line      : time-series or sequential data (dates, months, ordered categories)
  - bar       : categorical comparisons (products, cities, brands, counts)
  - pie       : part-of-whole with 6 or fewer categories
  - scatter   : correlation between two numeric columns
  - histogram : distribution of a single numeric column
  Skip build_chart ONLY if the result is a single scalar number.

Step 2 — call build_chart immediately. Use EXACT column names from the data.
  Required parameters:
    chart_type : one of bar / line / pie / scatter / histogram
    x_col      : exact column name for the X axis (or pie labels)
    y_col      : exact column name for the Y axis (or pie values)
    title      : short descriptive title (e.g. "Monthly Revenue 2024")
  Do NOT include a data parameter — the rows are injected automatically.

Step 3 — after the tool returns, write exactly 3 bullet points using the • character.
First, identify the best narrative frame for the data:
  - Time        : a date or period column exists — lead with the trend arc (growth, peak, decline, acceleration)
  - Contrast    : multiple categories — find the biggest gap, name both sides with specific numbers
  - Outlier     : one value sits significantly above or below the rest — call it out and quantify how far
  - Distribution: a ranking or spread — highlight concentration (e.g. top 2 items account for 60% of total)

Then structure your 3 bullets so they build on each other:
  • bullet 1 — headline: the single most important thing the data is saying, with a specific number
  • bullet 2 — story beat: supporting detail that explains, contrasts, or adds context to bullet 1
  • bullet 3 — hook: one concrete question or angle the user should explore next

Rules:
  - Interpret the data, don't just describe it ("Revenue peaked in March before dropping 30%" not "March had the highest revenue")
  - Use specific numbers from the data wherever possible
  - Maximum 25 words per bullet
  - No preamble — output only the 3 bullets
"""

_DEEP_INSIGHT_ADDENDUM = """
Step 2.5 — DEEP INSIGHTS MODE (active). After calling build_chart, run ONE follow-up query_database call to fetch the time or comparison dimension that is missing from the original data.
  - Call get_schema first if you need to confirm table/column names.
  - If the original data is grouped by a category (e.g. status, product) with no date column →
    query that same category broken down by month or quarter.
  - If the original data is already time-based or already contains enough comparison context →
    skip this step entirely.
  - Keep the follow-up query simple and targeted.
Use results from the follow-up query in your 3 bullets to tell a time or contrast story.
"""

# ChartAgent-specific build_chart schema: data is injected by the agent, not the LLM.
_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "build_chart",
            "description": (
                "Create a Plotly visualisation from the query results. "
                "The data is supplied automatically — you only need to specify "
                "chart_type, x_col, y_col, and title."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "chart_type": {
                        "type": "string",
                        "description": "One of: bar, line, pie, scatter, histogram.",
                    },
                    "x_col": {
                        "type": "string",
                        "description": "Column name for the X axis (or pie labels).",
                    },
                    "y_col": {
                        "type": "string",
                        "description": "Column name for the Y axis (or pie values).",
                    },
                    "title": {
                        "type": "string",
                        "description": "A concise descriptive chart title.",
                    },
                },
                "required": ["chart_type", "x_col", "y_col"],
            },
        },
    }
]


_DEEP_EXTRA_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_schema",
            "description": "Return table names, column names, and data types. Call this before query_database if you are unsure of exact column names.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_database",
            "description": "Run a follow-up SQL SELECT to fetch the time trend or comparison dimension missing from the original data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "A valid SQL SELECT statement."}
                },
                "required": ["sql"],
            },
        },
    },
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
        deep_insights: bool = False,
    ) -> tuple[str | None, str | None]:
        """Return (chart_json, insights_text)."""

        sample = rows[:_MAX_ROWS_TO_CHART]
        user_content = (
            f"User question: {user_question}\n\n"
            f"Columns: {columns}\n"
            f"Total rows: {len(rows)} (showing first {len(sample)})\n\n"
            f"Data:\n{json.dumps(sample, default=str)}"
        )

        system_prompt = _SYSTEM_PROMPT + (_DEEP_INSIGHT_ADDENDUM if deep_insights else "")
        tools = _TOOLS + (_DEEP_EXTRA_TOOLS if deep_insights else [])
        max_rounds = _MAX_TOOL_ROUNDS_DEEP if deep_insights else _MAX_TOOL_ROUNDS

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_content},
        ]

        chart_json: str | None = None
        insights:   str | None = None

        for _ in range(max_rounds):
            response = self._client.chat.completions.create(
                model=_MODEL_NAME,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                max_tokens=1024,
            )
            msg = response.choices[0].message

            asst_entry: dict = {"role": "assistant", "content": msg.content or None}
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
                if fn_name == "build_chart":
                    # Always use the original rows — never the LLM's possibly-filtered version
                    fn_args["data"] = rows
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
