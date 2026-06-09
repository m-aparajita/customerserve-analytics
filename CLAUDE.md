# Order Insights

Natural-language analytics agent for retail order data. Users ask questions in plain English; a QueryAgent writes SQL and queries DuckDB, then a ChartAgent selects the best visualisation and surfaces key insights. Users can email the resulting chart and insights to themselves on demand or on a recurring schedule.

**Two live environments:** `hf` = interview Space (stable), `hf-dev` = dev Space (experimental). Active branch: `dev`. Promote to `main` only when ready.

---

## Stack

| Layer | File(s) | Notes |
|-------|---------|-------|
| UI | `app.py` | Gradio, single process, built-in auth, chart PNG download (kaleido), schedule panel |
| QueryAgent | `agent/gemini_agent.py` | Groq + llama-4-scout; tools: `get_schema`, `query_database`, `get_sample_data`; returns rows to ChartAgent |
| ChartAgent | `agent/chart_agent.py` | Groq + llama-4-scout; tool: `build_chart` only (no `data` param — injected by agent); picks chart type + returns 1–2 insight bullets |
| Prompt | `agent/system_prompt.py` | Role-scoped (QueryAgent only); ChartAgent has its own inline prompt |
| Tools | `mcp/tools.py` | `get_schema`, `query_database`, `get_sample_data`, `build_chart`; axis labels auto-formatted via `_label()` |
| Mailer | `mailer/sender.py` | Resend API; sends chart PNG + insights as HTML email; env var: `RESEND_API_KEY` |
| Scheduler | `database/scheduler.py` | CRUD for `scheduled_reports` table; calculates `next_send_date`; triggered on page load via background thread |
| DB | `database/` | In-process DuckDB; CSVs downloaded from HF Dataset on first run; tables: orders, order_items, products, query_logs, scheduled_reports |
| Auth | `auth/` | ADMIN / ANALYST / VIEWER roles from env vars |
| Guardrails | `guardrails/` | Layer 1 input, Layer 2 prompt, Layer 3 SQL |

---

## Key decisions (do not reverse)

- **LLM:** `meta-llama/llama-4-scout-17b-16e-instruct` via Groq (free tier). Env var: `GROQ_API_KEY`.
- **Tool schema:** OpenAI format. Do not add `"required": []` to tools with no required params — omit the key entirely.
- **ChartAgent tool schema:** `build_chart` does NOT include a `data` parameter in the ChartAgent's schema — the agent injects `fn_args["data"] = rows` before dispatch. This prevents the LLM from stringifying the array, which Groq rejects.
- **System prompt:** Keep short. Do not embed schema JSON — the model calls `get_schema` tool instead.
- **Single process:** Everything runs through Gradio. `api/main.py` exists but is not wired in.
- **DB path:** `DB_PATH` env var → `/app/Data/customerserve.duckdb` in Docker.
- **Email:** Resend v1.x API (`resend.api_key` + `resend.Emails.send()`). Do not upgrade to v2 — the client API changed and breaks the current sender.

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
# Copy .env.example → .env, fill in GROQ_API_KEY + passwords
python app.py
```

## Deploy

| Target | Command | When |
|--------|---------|------|
| Dev Space (test) | `git push origin dev && git push hf-dev dev:main` | After any `dev` commit |
| Interview Space (stable) | `git checkout main && git merge dev && git push origin main && git push hf main` | Only when fully satisfied |

HF Spaces secrets (both Spaces): `GROQ_API_KEY`, `ADMIN_PASSWORD`, `ANALYST_PASSWORD`, `VIEWER_PASSWORD`, `RESEND_API_KEY`.

Optional: `RESEND_FROM_EMAIL` (defaults to `Order Insights <onboarding@resend.dev>`). Set this if you verify a custom domain in Resend.

Rollback: `git checkout v1.0` restores the last known-good interview version.
