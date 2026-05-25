import hashlib
import os
from auth.roles import Role

# Users are defined entirely through environment variables — no secrets in code.
def _hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _build_user_map() -> dict[str, dict]:
    return {
        os.getenv("ADMIN_USERNAME", "admin"): {
            "hash": _hash(os.getenv("ADMIN_PASSWORD", "admin123")),
            "role": Role.ADMIN,
        },
        os.getenv("ANALYST_USERNAME", "alice"): {
            "hash": _hash(os.getenv("ANALYST_PASSWORD", "alice123")),
            "role": Role.ANALYST,
        },
        os.getenv("VIEWER_USERNAME", "bob"): {
            "hash": _hash(os.getenv("VIEWER_PASSWORD", "bob123")),
            "role": Role.VIEWER,
        },
    }


# Build once at import time so env vars are read after .env is loaded.
_USERS: dict[str, dict] = {}


def _ensure_loaded() -> None:
    global _USERS
    if not _USERS:
        _USERS = _build_user_map()


def authenticate(username: str, password: str) -> bool:
    _ensure_loaded()
    user = _USERS.get(username)
    return bool(user and user["hash"] == _hash(password))


def get_role(username: str) -> Role:
    _ensure_loaded()
    user = _USERS.get(username)
    return user["role"] if user else Role.VIEWER


def gradio_auth_pairs() -> list[tuple[str, str]]:
    """Return (username, password) pairs for Gradio's auth parameter."""
    return [
        (os.getenv("ADMIN_USERNAME", "admin"),   os.getenv("ADMIN_PASSWORD",   "admin123")),
        (os.getenv("ANALYST_USERNAME", "alice"), os.getenv("ANALYST_PASSWORD", "alice123")),
        (os.getenv("VIEWER_USERNAME", "bob"),    os.getenv("VIEWER_PASSWORD",  "bob123")),
    ]
