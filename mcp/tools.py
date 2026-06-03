"""
MCP-compatible tool definitions and implementations.

Each tool is described with a JSON schema matching the MCP tool-call spec so
the same definitions can be handed to Gemini's function-calling API.
"""

import json
import time
import numpy as np
import pandas as pd
import plotly.express as px

from database.connection import get_connection
from database.logger import log_query
from guardrails.sql_guardrail import validate
from auth.roles import Role, PERMISSIONS

# ── Tool schema declarations (MCP-compatible) ────────────────────────────────

TOOL_DECLARATIONS: list[dict] = [
    {
        "name": "get_schema",
        "description": (
            "Return the full database schema: table names, column names, data types, "
            "and row counts. Call this first to understand the available data before "
            "writing any SQL query."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "query_database",
        "description": (
            "Execute a SQL SELECT query against the database and return the results as "
            "a list of row objects. Only SELECT statements are allowed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "A valid SQL SELECT statement."}
            },
            "required": ["sql"],
        },
    },
    {
        "name": "get_sample_data",
        "description": (
            "Return a few sample rows from a table to help understand its data format "
            "before writing queries."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "table": {
                    "type": "string",
                    "description": "Table name: orders, order_items, or products.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of rows to return (1–10). Default 5.",
                },
            },
            "required": ["table"],
        },
    },
    {
        "name": "build_chart",
        "description": (
            "Create a Plotly visualisation from query results. "
            "You MUST call query_database first and receive its response. "
            "Then pass the 'rows' array from that response as the 'data' parameter. "
            "Never pass a function reference — only pass the actual row objects."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "data": {
                    "type": "array",
                    "description": (
                        "The literal 'rows' array from query_database's JSON response. "
                        "Each element is a dict with column names as keys. "
                        "Example: [{'month': 'Jan', 'revenue': 5000}, ...]"
                    ),
                    "items": {"type": "object"},
                },
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
                    "description": "Chart title.",
                },
            },
            "required": ["data", "chart_type", "x_col", "y_col"],
        },
    },
]

# ── Tool implementations ──────────────────────────────────────────────────────

def get_schema() -> str:
    conn, lock = get_connection()
    with lock:
        tables = [r[0] for r in conn.execute("SHOW TABLES").fetchall()]
        schema: dict = {}
        for tbl in tables:
            if tbl == "query_logs":
                continue
            cols = conn.execute(f"DESCRIBE {tbl}").fetchall()
            count = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            schema[tbl] = {
                "row_count": count,
                "columns": [{"name": c[0], "type": c[1]} for c in cols],
            }
    return json.dumps(schema, indent=2)


def query_database(sql: str, role: Role, username: str) -> str:
    start = time.monotonic()

    allowed, reason, safe_sql = validate(sql, role)
    if not allowed:
        log_query(username=username, role=role, generated_sql=sql,
                  status="blocked", guardrail_layer="3_sql", guardrail_reason=reason)
        return json.dumps({"error": reason})

    conn, lock = get_connection()
    try:
        with lock:
            df: pd.DataFrame = conn.execute(safe_sql).fetchdf()
        exec_ms = int((time.monotonic() - start) * 1000)
        rows = df.to_dict(orient="records")
        log_query(username=username, role=role, generated_sql=safe_sql,
                  exec_ms=exec_ms, rows_returned=len(rows), status="success")
        return json.dumps({
            "columns": list(df.columns),
            "rows": rows,
            "row_count": len(rows),
            "exec_ms": exec_ms,
        }, default=str)
    except Exception as exc:
        exec_ms = int((time.monotonic() - start) * 1000)
        log_query(username=username, role=role, generated_sql=safe_sql,
                  exec_ms=exec_ms, status="error", error_message=str(exc))
        return json.dumps({"error": str(exc)})


def get_sample_data(table: str, limit: int = 5) -> str:
    if table.lower() not in {"orders", "order_items", "products"}:
        return json.dumps({"error": f"Table '{table}' is not accessible."})
    safe_limit = min(max(int(limit), 1), 10)
    conn, lock = get_connection()
    with lock:
        df = conn.execute(f"SELECT * FROM {table} LIMIT {safe_limit}").fetchdf()
    return json.dumps({"columns": list(df.columns), "rows": df.to_dict(orient="records")}, default=str)


def _format_abbrev(v: float) -> str:
    """Return a K / Mn / Bn abbreviated label for a number."""
    abs_v = abs(v)
    if abs_v >= 1_000_000_000:
        return f"{v / 1_000_000_000:.2f}Bn"
    if abs_v >= 1_000_000:
        return f"{v / 1_000_000:.2f}Mn"
    if abs_v >= 1_000:
        return f"{v / 1_000:.2f}K"
    return f"{v:.2f}"


def _apply_abbrev_y_axis(fig, series: pd.Series) -> None:
    """Replace y-axis tick labels with K / Mn / Bn abbreviations."""
    try:
        mn, mx = float(series.min()), float(series.max())
        if mn == mx:
            return
        tickvals = np.linspace(mn, mx, 5).tolist()
        ticktext = [_format_abbrev(v) for v in tickvals]
        fig.update_yaxes(tickvals=tickvals, ticktext=ticktext, automargin=True)
    except Exception:
        pass


def build_chart(data: list, chart_type: str, x_col: str, y_col: str,
                title: str = "", role: Role = Role.ANALYST) -> str:
    allowed = PERMISSIONS[role].allowed_charts
    if chart_type not in allowed:
        chart_type = allowed[0]

    if not data:
        return json.dumps({"error": "No data to chart."})

    df = pd.DataFrame(data)
    if x_col not in df.columns or (chart_type != "histogram" and y_col not in df.columns):
        return json.dumps({"error": f"Column '{x_col}' or '{y_col}' not found in data."})

    # Colours that read clearly on a light/white background
    _PRIMARY   = "#7c3aed"   # deep violet
    _SECONDARY = "#0891b2"   # dark cyan
    _PIE_SEQ   = ["#7c3aed", "#0891b2", "#059669", "#d97706", "#dc2626", "#4f46e5"]

    try:
        if chart_type == "bar":
            fig = px.bar(df, x=x_col, y=y_col, title=title,
                         color_discrete_sequence=[_PRIMARY])
            _apply_abbrev_y_axis(fig, df[y_col])
            fig.update_traces(
                hovertemplate=f"%{{x}}<br>{y_col}: %{{y:,.2f}}<extra></extra>"
            )
        elif chart_type == "line":
            fig = px.line(df, x=x_col, y=y_col, title=title, markers=True,
                          color_discrete_sequence=[_PRIMARY])
            _apply_abbrev_y_axis(fig, df[y_col])
            fig.update_traces(
                hovertemplate=f"%{{x}}<br>{y_col}: %{{y:,.2f}}<extra></extra>",
                line=dict(width=2.5),
                marker=dict(size=6),
            )
        elif chart_type == "pie":
            fig = px.pie(df, names=x_col, values=y_col, title=title,
                         color_discrete_sequence=_PIE_SEQ)
            fig.update_traces(
                hovertemplate="%{label}<br>Value: %{value:,.2f}<br>%{percent}<extra></extra>",
                textfont=dict(color="#f0f0f8"),
            )
        elif chart_type == "scatter":
            fig = px.scatter(df, x=x_col, y=y_col, title=title,
                             color_discrete_sequence=[_PRIMARY])
            _apply_abbrev_y_axis(fig, df[y_col])
            fig.update_traces(
                hovertemplate=f"%{{x}}<br>{y_col}: %{{y:,.2f}}<extra></extra>",
                marker=dict(size=8, opacity=0.85),
            )
        elif chart_type == "histogram":
            fig = px.histogram(df, x=x_col, title=title,
                               color_discrete_sequence=[_PRIMARY])
            fig.update_traces(
                hovertemplate=f"{x_col}: %{{x}}<br>Count: %{{y:,}}<extra></extra>"
            )
        else:
            fig = px.bar(df, x=x_col, y=y_col, title=title,
                         color_discrete_sequence=[_PRIMARY])
            _apply_abbrev_y_axis(fig, df[y_col])
            fig.update_traces(
                hovertemplate=f"%{{x}}<br>{y_col}: %{{y:,.2f}}<extra></extra>"
            )

        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(245,243,255,0.55)",
            font=dict(family="Inter, system-ui, sans-serif", color="#1e1b4b", size=12),
            title=dict(font=dict(family="Space Grotesk, sans-serif", size=15, color="#3b0764")),
            xaxis=dict(
                gridcolor="rgba(0,0,0,0.07)",
                linecolor="rgba(0,0,0,0.15)",
                tickfont=dict(color="#374151", size=11),
                automargin=True,
            ),
            yaxis=dict(
                gridcolor="rgba(0,0,0,0.07)",
                linecolor="rgba(0,0,0,0.15)",
                tickfont=dict(color="#374151", size=11),
                automargin=True,
            ),
            hoverlabel=dict(
                bgcolor="#1e1b4b",
                bordercolor="rgba(124,58,237,0.40)",
                font=dict(color="#ffffff", size=12),
            ),
            legend=dict(
                bgcolor="rgba(255,255,255,0.85)",
                bordercolor="rgba(0,0,0,0.10)",
                font=dict(color="#1e1b4b"),
            ),
            margin=dict(t=50, l=70, r=20, b=55),
        )
        return json.dumps({"chart_json": fig.to_json(), "chart_type": chart_type})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ── Dispatcher: maps tool name → implementation ───────────────────────────────

def dispatch(name: str, args: dict, role: Role, username: str) -> str:
    if name == "get_schema":
        return get_schema()
    if name == "query_database":
        return query_database(args["sql"], role, username)
    if name == "get_sample_data":
        return get_sample_data(args["table"], args.get("limit", 5))
    if name == "build_chart":
        return build_chart(
            data=args["data"],
            chart_type=args["chart_type"],
            x_col=args["x_col"],
            y_col=args["y_col"],
            title=args.get("title", ""),
            role=role,
        )
    return json.dumps({"error": f"Unknown tool: {name}"})
