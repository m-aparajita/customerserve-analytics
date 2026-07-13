"""
ChartAgent — selects the best visualisation for query results and surfaces key insights.

Receives rows + columns + user question from QueryAgent.
Responsibilities:
  1. Choose the most appropriate chart type for the data
  2. Call build_chart with correct parameters
  3. Return 1-2 bullet-point insights (trends, anomalies, highlights)
"""

import json
import logging
import os

from groq import Groq
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

from agent.call_log import record as record_call
from auth.roles import Role
from mcp.tools import TOOL_DECLARATIONS, cap_rows_for_llm, dispatch

load_dotenv()

_MODEL_NAME = "openai/gpt-oss-120b"
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
  x_col and y_col must be two DIFFERENT columns (unless chart_type is histogram) — x_col is
  the category/label column, y_col is the numeric value column. Never repeat the same column.
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

_SYSTEM_PROMPT_DEEP = """You are a data visualisation and insight specialist.
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
  x_col and y_col must be two DIFFERENT columns (unless chart_type is histogram) — x_col is
  the category/label column, y_col is the numeric value column. Never repeat the same column.
  Do NOT include a data parameter — the rows are injected automatically.

Step 2.5 — ENRICHMENT (mandatory — do this before writing any bullets).
  a) Call get_schema FIRST to confirm exact table and column names.
  b) Then call query_database ONCE to fetch the time or comparison dimension missing from the original data.
  Examples:
    • Original data: order count by payment method → query the same breakdown by month
    • Original data: revenue by product/brand/category → query those items' revenue month by month
    • Original data: order count by status → query each status grouped by month or quarter
  Only skip step (b) if the original data already contains a date/time column with multiple periods.
  If the enrichment query returns an error or empty rows, silently ignore it and proceed to Step 3
  using the original data only — never write "No data available" or mention the failed query.

Step 3 — write exactly 3 bullet points using the • character.
  Use the enrichment query results if available, otherwise use the original data.
  First, identify the best narrative frame:
  - Time        : lead with the trend arc (growth, peak, decline) using specific months and numbers
  - Contrast    : find the biggest divergence between categories over time, name both sides
  - Outlier     : one category moved very differently from the rest — quantify the gap
  - Near-parity : if top values are within 5% of each other, that IS the story — tight competition,
                  who is gaining ground, who is losing it

  Structure your 3 bullets so they build on each other:
  • bullet 1 — headline: the most important trend or shift, with specific numbers and time period
  • bullet 2 — story beat: what explains or contrasts with bullet 1 (a turning point, a rival gaining ground)
  • bullet 3 — hook: one concrete question or angle the user should explore next

  Rules:
  - Interpret the data, don't list it ("Himalaya led but Mamaearth closed the gap by 8Mn in Q4" not "Himalaya had highest revenue")
  - Use specific numbers and time references wherever available
  - Maximum 25 words per bullet
  - No preamble — output only the 3 bullets
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
            "description": "Return exact table names, column names, and data types. Always call this before query_database to confirm the correct column names to use in your SQL.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_database",
            "description": "Run a follow-up SQL SELECT to fetch the time trend or category breakdown that enriches the original data. Use column names confirmed by get_schema.",
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
        username: str = "chart_agent",
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

        system_prompt = _SYSTEM_PROMPT_DEEP if deep_insights else _SYSTEM_PROMPT
        tools = _TOOLS + (_DEEP_EXTRA_TOOLS if deep_insights else [])
        max_rounds = _MAX_TOOL_ROUNDS_DEEP if deep_insights else _MAX_TOOL_ROUNDS

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_content},
        ]

        chart_json: str | None = None
        insights:   str | None = None
        _enrichment_done = False

        for round_num in range(max_rounds):
            # In deep mode: if chart is built and schema was fetched but query_database
            # still hasn't run, force it by injecting a reminder before the next LLM call.
            if deep_insights and chart_json is not None and not _enrichment_done:
                _called_so_far = {
                    tc["function"]["name"]
                    for m in messages if m.get("role") == "assistant"
                    for tc in (m.get("tool_calls") or [])
                }
                if "get_schema" in _called_so_far and "query_database" not in _called_so_far:
                    messages.append({
                        "role": "user",
                        "content": (
                            "You have the schema. Now call query_database to fetch the "
                            "time trend or monthly breakdown for these results. "
                            "Do NOT write bullet points yet."
                        ),
                    })

            response = self._client.chat.completions.create(
                model=_MODEL_NAME,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                max_tokens=2048 if deep_insights else 1024,
                reasoning_effort="low",
            )
            usage = response.usage
            logger.info(
                "[ChartAgent] round=%d deep=%s model=%s messages=%d prompt_tokens=%s completion_tokens=%s total_tokens=%s",
                round_num, deep_insights, _MODEL_NAME, len(messages),
                usage.prompt_tokens if usage else None,
                usage.completion_tokens if usage else None,
                usage.total_tokens if usage else None,
            )
            record_call(
                username, agent="ChartAgent", model=_MODEL_NAME, round_num=round_num,
                deep=deep_insights, messages=len(messages),
                prompt_tokens=usage.prompt_tokens if usage else None,
                completion_tokens=usage.completion_tokens if usage else None,
                total_tokens=usage.total_tokens if usage else None,
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
                logger.info("[ChartAgent] round=%d deep=%s → no tool calls, writing insights", round_num, deep_insights)
                insights = msg.content or None
                break

            tool_names = [c.function.name for c in msg.tool_calls]
            logger.info("[ChartAgent] round=%d deep=%s → tools called: %s", round_num, deep_insights, tool_names)

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
                        # The model never needs the figure spec back — just confirmation.
                        # Keeping full fig.to_json() in context gets resent every later round.
                        result_str = json.dumps({"status": "chart created", "chart_type": parsed.get("chart_type")})
                elif fn_name == "query_database":
                    _enrichment_done = True
                    parsed = json.loads(result_str)
                    if "error" in parsed:
                        logger.warning("[ChartAgent] query_database error: %s", parsed["error"])
                    else:
                        logger.info("[ChartAgent] query_database returned %d rows", parsed.get("row_count", 0))

                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": cap_rows_for_llm(result_str),
                })

        return chart_json, insights


_chart_agent: ChartAgent | None = None


def get_chart_agent() -> ChartAgent:
    global _chart_agent
    if _chart_agent is None:
        _chart_agent = ChartAgent()
    return _chart_agent
