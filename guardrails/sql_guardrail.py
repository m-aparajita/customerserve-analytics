import re
from auth.roles import Role, PERMISSIONS

_ALLOWED_TABLES = {"orders", "order_items", "products", "query_logs"}
_SELECT_RE = re.compile(r"^\s*SELECT\b", re.IGNORECASE)
_TABLE_RE = re.compile(r"\bFROM\s+(\w+)|\bJOIN\s+(\w+)", re.IGNORECASE)


def _extract_tables(sql: str) -> set[str]:
    return {m.group(1) or m.group(2) for m in _TABLE_RE.finditer(sql)}


def validate(sql: str, role: Role) -> tuple[bool, str, str]:
    """Returns (allowed, rejection_reason, safe_sql_with_limit_applied)."""
    if not _SELECT_RE.match(sql):
        return False, "Only SELECT queries are permitted.", sql

    tables = {t.lower() for t in _extract_tables(sql)}

    # Only admin may query logs
    if "query_logs" in tables and role != Role.ADMIN:
        return False, "You do not have permission to access query logs.", sql

    disallowed = tables - _ALLOWED_TABLES
    if disallowed:
        return False, f"Access to table(s) {disallowed} is not allowed.", sql

    safe_sql = _apply_limit(sql, PERMISSIONS[role].max_rows)
    return True, "", safe_sql


def _apply_limit(sql: str, max_rows: int) -> str:
    """Inject or lower an existing LIMIT clause."""
    limit_match = re.search(r"\bLIMIT\s+(\d+)", sql, re.IGNORECASE)
    if limit_match:
        existing = int(limit_match.group(1))
        if existing > max_rows:
            sql = re.sub(
                r"\bLIMIT\s+\d+", f"LIMIT {max_rows}", sql, flags=re.IGNORECASE
            )
    else:
        sql = sql.rstrip(";").rstrip() + f" LIMIT {max_rows}"
    return sql
