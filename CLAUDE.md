# Order Insights

Natural-language analytics over retail order data. QueryAgent writes SQL → DuckDB, ChartAgent visualises + surfaces insights. Users can email charts on demand or on a schedule.

**Environments:** `hf` = prod (stable), `hf-dev` = dev (experimental). Active branch: `dev`.

---

## Stack

| Layer | File(s) |
|-------|---------|
| UI | `app.py` — Gradio, auth, schedule panel, PNG download |
| QueryAgent | `agent/gemini_agent.py` — Groq llama-4-scout; tools: `get_schema`, `query_database`, `get_sample_data` |
| ChartAgent | `agent/chart_agent.py` — Groq llama-4-scout; tool: `build_chart` only; returns 1–2 insight bullets |
| Tools | `mcp/tools.py` — all tool implementations; schema panel excludes internal tables |
| Mailer | `mailer/sender.py` — Resend v1.x; normalises recipient email to lowercase |
| Scheduler | `database/scheduler.py` — CRUD for `scheduled_reports`; triggered on page load |
| DB | `database/` — DuckDB in-process; tables: `orders`, `order_items`, `products`, `query_logs`, `scheduled_reports` |
| Auth/Guardrails | `auth/`, `guardrails/` — RBAC roles; Layers 1 (input), 2 (prompt), 3 (SQL) |

---

## Key decisions (do not reverse)

- **LLM:** `meta-llama/llama-4-scout-17b-16e-instruct` via Groq. Env: `GROQ_API_KEY`.
- **Tool schema:** OpenAI format. Omit `"required"` key entirely when no params are required.
- **ChartAgent `build_chart`:** no `data` param in schema — agent injects `fn_args["data"] = rows` before dispatch. Prevents Groq rejecting a stringified array.
- **Assistant messages:** set `content: None` (not `""`) when `tool_calls` is present — empty string causes intermittent 400s.
- **System prompt:** keep short; model calls `get_schema` tool rather than embedding schema JSON.
- **Email:** Resend v1.x (`resend.api_key` + `resend.Emails.send()`). Do not upgrade to v2.
- **DB path:** `DB_PATH` env var → `/app/Data/customerserve.duckdb` in Docker.

## RBAC

| Role | Free-form | Raw rows | Row limit |
|------|-----------|----------|-----------|
| ADMIN | Yes | Yes | 10,000 |
| ANALYST | Yes | No | 1,000 |
| VIEWER | Templates only | No | 100 |

Users: `admin` / `alice` (analyst) / `bob` (viewer). Passwords from env vars.

---

## Run locally

```powershell
pip install -r requirements.txt
# Copy .env.example → .env, fill in keys and passwords
python app.py
```

## Deploy

| Target | Command |
|--------|---------|
| Dev | `git push origin dev && git push hf-dev dev:main` |
| Prod | `git checkout main && git merge dev && git push origin main && git push hf main` |

HF secrets (both Spaces): `GROQ_API_KEY`, `ADMIN_PASSWORD`, `ANALYST_PASSWORD`, `VIEWER_PASSWORD`, `RESEND_API_KEY`, `RESEND_FROM_EMAIL` (optional).

Rollback: `git checkout v1.0`
