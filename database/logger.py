import uuid
from concurrent.futures import ThreadPoolExecutor
from database.connection import get_connection

_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="log-writer")


def _write(log_id, username, role, user_query, generated_sql,
           exec_ms, rows_returned, chart_type, status,
           guardrail_layer, guardrail_reason, error_message):
    try:
        conn, lock = get_connection()
        role_val = role.value if hasattr(role, "value") else role
        with lock:
            conn.execute("""
                INSERT INTO query_logs VALUES (?,CURRENT_TIMESTAMP,?,?,?,?,?,?,?,?,?,?,?)
            """, [log_id, username, role_val, user_query, generated_sql,
                  exec_ms, rows_returned, chart_type, status,
                  guardrail_layer, guardrail_reason, error_message])
    except Exception as exc:
        print(f"[logger] non-fatal write error: {exc}")


def log_query(*,
              username: str,
              role,
              user_query: str = None,
              generated_sql: str = None,
              exec_ms: int = None,
              rows_returned: int = None,
              chart_type: str = None,
              status: str = "success",
              guardrail_layer: str = None,
              guardrail_reason: str = None,
              error_message: str = None) -> None:
    """Fire-and-forget async log write — never blocks the request."""
    _pool.submit(
        _write,
        str(uuid.uuid4()), username, role, user_query, generated_sql,
        exec_ms, rows_returned, chart_type, status,
        guardrail_layer, guardrail_reason, error_message,
    )
