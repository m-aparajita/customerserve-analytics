from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from agent.gemini_agent import get_agent
from auth.manager import get_role, authenticate
from mcp.tools import get_schema as _get_schema

app = FastAPI(title="CustomerServe Query API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ── Request / Response models ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    query: str
    username: str
    history: list[tuple[str, str]] = []


class ChatResponse(BaseModel):
    text: str
    chart_json: Optional[str] = None
    role: str


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/schema")
def schema(username: str):
    role = get_role(username)
    if not role:
        raise HTTPException(status_code=401, detail="Unknown user.")
    return {"schema": _get_schema(), "role": role.value}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    role = get_role(req.username)
    if not role:
        raise HTTPException(status_code=401, detail="Unknown user.")

    agent = get_agent()
    text, chart_json = agent.chat(
        user_query=req.query,
        history=req.history,
        role=role,
        username=req.username,
    )
    return ChatResponse(text=text, chart_json=chart_json, role=role.value)
