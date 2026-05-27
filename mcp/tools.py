"""
MCP-compatible tool definitions and implementations.

Each tool is described with a JSON schema matching the MCP tool-call spec so
the same definitions can be handed to Gemini's function-calling API.
"""

import json
import time
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
            "Create a Plotly visualisation from query results. Call after "
            "query_database once you have the data."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "data": {
                    "type": "array",
                    "description": "Array of row objects returned by query_database.",
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

    try:
        if chart_type == "bar":
            fig = px.bar(df, x=x_col, y=y_col, title=title)
        elif chart_type == "line":
            fig = px.line(df, x=x_col, y=y_col, title=title, markers=True)
        elif chart_type == "pie":
            fig = px.pie(df, names=x_col, values=y_col, title=title)
        elif chart_type == "scatter":
            fig = px.scatter(df, x=x_col, y=y_col, title=title)
        elif chart_type == "histogram":
            fig = px.histogram(df, x=x_col, title=title)
        else:
            fig = px.bar(df, x=x_col, y=y_col, title=title)

        fig.update_layout(template="plotly_white")
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
