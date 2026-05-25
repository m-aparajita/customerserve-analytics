import re

# Patterns that must never appear in a user query.
_BLOCKED = [
    r"\bdrop\b", r"\bdelete\b", r"\btruncate\b", r"\bupdate\b",
    r"\binsert\b", r"\balter\b", r"\bcreate\b", r"\bgrant\b", r"\brevoke\b",
    r"ignore\s+(previous|above|prior|all)\s+instructions?",
    r"forget\s+(previous|above|prior)",
    r"you\s+are\s+now\s+a", r"\bact\s+as\b", r"\bpretend\b",
    r"\bjailbreak\b", r"system\s+prompt", r"your\s+instructions",
    r"ignore\s+all", r"do\s+anything\s+now",
]
_BLOCKED_RE = [re.compile(p, re.IGNORECASE) for p in _BLOCKED]

# At least one of these must be present for a query to be domain-relevant.
_DOMAIN_KEYWORDS = [
    "order", "product", "revenue", "sale", "brand", "price", "quantity",
    "item", "total", "count", "average", "top", "best", "worst", "trend",
    "month", "week", "day", "year", "status", "category", "sub_category",
    "profit", "discount", "mrp", "payment", "city", "state", "cancelled",
    "delivered", "shipped", "compare", "show", "list", "how many",
    "highest", "lowest", "most", "least", "summary", "report", "net",
    "which", "what", "when", "nykaa",
]


def check(query: str) -> tuple[bool, str]:
    """Returns (allowed, rejection_reason). Empty reason means allowed."""
    q = query.strip()

    if len(q) < 3:
        return False, "Please ask a more specific question."

    if len(q) > 1000:
        return False, "Query too long — please keep it under 1000 characters."

    ql = q.lower()
    for pattern in _BLOCKED_RE:
        if pattern.search(ql):
            return False, (
                "Your query contains restricted content and cannot be processed. "
                "Please ask questions about orders, products, or sales."
            )

    if not any(kw in ql for kw in _DOMAIN_KEYWORDS):
        return False, (
            "I can only answer questions about orders, products, and sales data. "
            "Try asking something like 'Show top 5 brands by revenue'."
        )

    return True, ""
