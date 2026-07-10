"""In-memory, per-user record of LLM calls made during the current app session.

Not persisted to disk — resets on app restart. Backs the "click your role
badge" LLM call log panel in the UI (Admin only, see auth.roles.can_see_logs).
"""

import collections
import datetime

_MAX_CALLS_PER_USER = 50

_logs: dict[str, collections.deque] = {}


def record(username: str, *, agent: str, model: str, round_num: int,
           deep: bool | None, messages: int,
           prompt_tokens: int | None, completion_tokens: int | None,
           total_tokens: int | None) -> None:
    dq = _logs.setdefault(username, collections.deque(maxlen=_MAX_CALLS_PER_USER))
    dq.append({
        "time": datetime.datetime.now().strftime("%H:%M:%S"),
        "agent": agent,
        "model": model,
        "round": round_num,
        "deep": deep,
        "messages": messages,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    })


def get_calls(username: str) -> list[dict]:
    return list(_logs.get(username, ()))
