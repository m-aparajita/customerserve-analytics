from dataclasses import dataclass, field
from enum import Enum


class Role(str, Enum):
    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


@dataclass
class RolePermissions:
    free_form_queries: bool
    see_raw_rows: bool
    max_rows: int
    allowed_charts: list[str]
    can_export: bool
    can_see_schema: bool
    can_see_logs: bool


PERMISSIONS: dict[Role, RolePermissions] = {
    Role.ADMIN: RolePermissions(
        free_form_queries=True,
        see_raw_rows=True,
        max_rows=10_000,
        allowed_charts=["bar", "line", "pie", "scatter", "histogram"],
        can_export=True,
        can_see_schema=True,
        can_see_logs=True,
    ),
    Role.ANALYST: RolePermissions(
        free_form_queries=True,
        see_raw_rows=False,
        max_rows=1_000,
        allowed_charts=["bar", "line", "pie", "scatter", "histogram"],
        can_export=True,
        can_see_schema=True,
        can_see_logs=False,
    ),
    Role.VIEWER: RolePermissions(
        free_form_queries=False,
        see_raw_rows=False,
        max_rows=100,
        allowed_charts=["bar", "line"],
        can_export=False,
        can_see_schema=False,
        can_see_logs=False,
    ),
}

VIEWER_TEMPLATES: list[str] = [
    "Show total revenue by month",
    "Show top 10 products by net sales",
    "Show order count by status",
    "Show revenue by product category",
    "Show top 5 brands by revenue",
    "Show orders by payment method",
    "Show revenue by state",
]
