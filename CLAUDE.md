# Order Insights

Natural-language analytics over retail order data. QueryAgent writes SQL → DuckDB, ChartAgent visualises + surfaces insights. Users can email charts on demand or on a schedule.

**Environments:** `hf` = prod (stable), `hf-dev` = dev (experimental). Active branch: `dev`.

---

## Stack

| Layer | File(s) |
|-------|---------|
| UI | `app.py` — Gradio, auth, schedule panel, PNG download |
| QueryAgent | `agent/gemini_agent.py` — Groq llama-4-scout; tools: `get_schema`, `query_database`, `get_sample_data` |
| ChartAgent | `agent/chart_agent.py` — Groq llama-4-scout; standard mode: `build_chart` only; deep mode: `build_chart` + `get_schema` + `query_database`; returns 3 narrative insight bullets |
| Tools | `mcp/tools.py` — all tool implementations; `get_schema()` excludes `query_logs` + `scheduled_reports` (LLM must never see internal tables) |
| Mailer | `mailer/sender.py` — generic `send_email(to, subject, html, attachment)`; Resend v1.x; normalises to lowercase. HTML assembled in `app.py::_build_report_email_html` |
| Scheduler | `database/scheduler.py` — CRUD for `scheduled_reports`; triggered on page load |
| DB | `database/` — DuckDB in-process; tables: `orders`, `order_items`, `products`, `query_logs`, `scheduled_reports` |
| Auth/Guardrails | `auth/`, `guardrails/` — RBAC roles; Layers 1 (input), 2 (prompt), 3 (SQL) |
| Voice ("Ask Aloud") | `agent/voice.py` — STT only, `transcribe_audio()` via Groq `whisper-large-v3-turbo`; feeds transcribed text into the same `respond()` pipeline as typed input |

---

## Key decisions (do not reverse)

- **LLM:** `meta-llama/llama-4-scout-17b-16e-instruct` via Groq. Env: `GROQ_API_KEY`.
- **Tool schema:** OpenAI format. Omit `"required"` key entirely when no params are required.
- **ChartAgent `build_chart`:** no `data` param in schema — agent injects `fn_args["data"] = rows` before dispatch. Prevents Groq rejecting a stringified array.
- **ChartAgent deep mode:** activated by "Want me to include related insights?" checkbox in UI. Uses `_SYSTEM_PROMPT_DEEP` (separate prompt, not an addendum) with steps: build_chart → get_schema → query_database → bullets. Max 6 tool rounds, 2048 tokens. Code-level enforcement: if model calls `get_schema` but skips `query_database`, an injected user message forces it before bullets are written. Enrichment errors are silently ignored; model falls back to original data.
- **ChartAgent insights:** always 3 bullets structured as headline → story beat → exploration hook. Narrative frames: Time / Contrast / Outlier / Distribution / Near-parity (values within 5%).
- **Y-axis formatting:** `_nice_ticks()` always starts from 0, uses round intervals (1/2/2.5/5/10 × magnitude). `_format_abbrev()` strips trailing zeros (e.g. "1.2Mn" not "1.20Mn").
- **Assistant messages:** set `content: None` (not `""`) when `tool_calls` is present — empty string causes intermittent 400s.
- **System prompt:** keep short; model calls `get_schema` tool rather than embedding schema JSON.
- **Email:** Resend v1.x (`resend.api_key` + `resend.Emails.send()`). Do not upgrade to v2.
- **DB path:** `DB_PATH` env var → `/app/Data/customerserve.duckdb` in Docker.
- **Voice input (STT):** Groq `whisper-large-v3-turbo`, reuses `GROQ_API_KEY`. Free tier confirmed (no card): 2,000 req/day, 7,200 audio-sec/hour. Transcribed text is not a separate trust boundary — it passes through the same guardrails/RBAC as typed input, no bypass path.
- **Voice output (TTS):** browser `speechSynthesis` (client-side JS in `app.py`), not a Groq API. Groq's TTS (PlayAI/Orpheus) is priced per character with no confirmed free tier — deliberately avoided. Zero new dependencies or Docker changes.

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
