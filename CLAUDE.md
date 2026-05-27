# CustomerServe Analytics Agent — Project Guide

## What this project is

A natural-language analytics agent for retail order data, built as a portfolio piece for a job interview. Users type questions in plain English; the agent writes SQL, queries DuckDB, and renders interactive Plotly charts in a Gradio UI.

**Deployment target:** HuggingFace Spaces (Docker, free tier)

---

## What is already built and working

Do not re-implement or re-scaffold any of the following — they are complete:

### Core architecture
- **`app.py`** — Gradio UI with built-in login, role badge, chat panel, chart panel. Single-process entry point.
- **`agent/gemini_agent.py`** — Gemini 2.0 Flash agent with MCP-style function-calling loop (max 8 rounds). Singleton pattern via `get_agent()`.
- **`agent/system_prompt.py`** — Role-scoped system prompt builder.
- **`mcp/tools.py`** — Four MCP-compatible tools: `get_schema`, `query_database`, `get_sample_data`, `build_chart`. Dispatcher maps tool names to implementations.
- **`database/connection.py`** — Thread-safe DuckDB connection (singleton + lock).
- **`database/setup.py`** — DB bootstrap: downloads CSVs from HuggingFace Dataset if not local, loads into DuckDB, creates `query_logs` table.
- **`database/logger.py`** — Query audit logger writing to `query_logs` table.
- **`auth/manager.py`** — User authentication, role lookup, Gradio auth pairs from env vars.
- **`auth/roles.py`** — `Role` enum (ADMIN, ANALYST, VIEWER), `PERMISSIONS` dict, `VIEWER_TEMPLATES` list.
- **`guardrails/input_guardrail.py`** — Layer 1: blocks off-topic queries and injection patterns before the LLM.
- **`guardrails/sql_guardrail.py`** — Layer 3: blocks non-SELECT SQL and enforces row limits per role.

### Infrastructure
- **`Dockerfile`** — Python 3.11-slim, installs requirements, exposes port 7860, runs `python app.py`. `DB_PATH` and `DATA_DIR` set to `/app/Data/`.
- **`requirements.txt`** — All dependencies pinned and tested.
- **`.env.example`** — Template for local credentials.
- **`Data/`** — `orders.csv`, `order_items.csv`, `products.csv` present locally.
- **`README.md`** — HuggingFace Spaces metadata header (Docker SDK, port 7860).

### Three-layer guardrail system
| Layer | Location | Blocks |
|-------|----------|--------|
| 1 — Input | `guardrails/input_guardrail.py` | Off-topic, injection, prompt hacks |
| 2 — Prompt | System prompt | LLM instructed to refuse non-domain / non-SELECT |
| 3 — SQL | `guardrails/sql_guardrail.py` | Non-SELECT, unauthorised tables, row-limit |

### Role-Based Access Control
| Role | Free-form queries | Raw rows | Row limit | Logs |
|------|-------------------|----------|-----------|------|
| ADMIN | Yes | Yes | 10,000 | Yes |
| ANALYST | Yes | No (aggregated only) | 1,000 | No |
| VIEWER | No (templates only) | No | 100 | No |

Users: `admin` / `alice` (analyst) / `bob` (viewer). Passwords from env vars.

---

## Key design decisions (do not reverse)

- **Model:** `llama-3.3-70b-versatile` via **Groq** (groq.com) — free tier, excellent function calling. Do not switch to paid models.
- **No FastAPI server separate from Gradio** — everything runs in one process via `app.py`. The `api/` directory exists but the app launches via Gradio only.
- **DuckDB is in-process** — no separate database server. DB file lives at `DB_PATH` env var (`/app/Data/customerserve.duckdb` in Docker).
- **CSV data is bundled in `Data/`** — the `setup.py` also supports downloading from a HuggingFace Dataset repo (`HF_DATASET_REPO` env var, defaults to `aparajita/customerserve-data`) if files are missing.
- **Gradio `type="messages"` format** — history is a list of `{"role": ..., "content": ...}` dicts, converted to `(user, assistant)` tuples before passing to the agent.
- **Groq tool schema** — tools are declared in OpenAI format (`{"type": "function", "function": {...}}`). Tool results returned as `role="tool"` messages with `tool_call_id`.

---

## How to run locally

```powershell
# From E:\My_Software_Projects\CustomerServe
pip install -r requirements.txt
# Copy .env.example to .env and fill in GROQ_API_KEY + passwords
python app.py
# Open http://localhost:7860
```

## How to deploy to HuggingFace Spaces

1. Push repo to GitHub (branch: `main`)
2. Create a new Space → **Docker** runtime
3. Connect the GitHub repo in Space Settings
4. Add **Secrets** in Space Settings → Variables and Secrets:
   - `GROQ_API_KEY`
   - `ADMIN_PASSWORD`, `ANALYST_PASSWORD`, `VIEWER_PASSWORD`
5. Push to GitHub — Space auto-builds and deploys
6. App is live at `https://huggingface.co/spaces/YOUR_USERNAME/SPACE_NAME`

---

## Known issues / things to watch

- The `api/main.py` FastAPI file exists but is **not wired in** — the app runs purely through Gradio. Do not try to start it separately.
- No persistent storage is configured in the Space (Dockerfile stores DB in `/app/Data/` which is part of the image). If persistent storage is needed later, mount `/data/` and update `DB_PATH`.
- `groq>=0.9.0` — uses the OpenAI-compatible chat completions API. Do not switch to the legacy `google-generativeai` package.
