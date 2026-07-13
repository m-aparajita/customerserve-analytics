# Order Insights

Natural-language analytics over retail order data. QueryAgent writes SQL → DuckDB, ChartAgent visualises + surfaces insights. Users can email charts on demand or on a schedule.

**Environments:** `hf` = prod (stable), `hf-dev` = dev (experimental). Active branch: `dev`.

---

## Stack

| Layer | File(s) |
|-------|---------|
| UI | `app.py` — Gradio, auth, schedule panel, PNG download |
| QueryAgent | `agent/gemini_agent.py` — Groq `openai/gpt-oss-120b`; tools: `get_schema`, `query_database`, `get_sample_data` |
| ChartAgent | `agent/chart_agent.py` — Groq `openai/gpt-oss-120b`; standard mode: `build_chart` only; deep mode: `build_chart` + `get_schema` + `query_database`; returns 3 narrative insight bullets |
| Tools | `mcp/tools.py` — all tool implementations; `get_schema()` excludes `query_logs` + `scheduled_reports` (LLM must never see internal tables) |
| Mailer | `mailer/sender.py` — generic `send_email(to, subject, html, attachment)`; Resend v1.x; normalises to lowercase. HTML assembled in `app.py::_build_report_email_html` |
| Scheduler | `database/scheduler.py` — CRUD for `scheduled_reports`; triggered on page load |
| DB | `database/` — DuckDB in-process; tables: `orders`, `order_items`, `products`, `query_logs`, `scheduled_reports` |
| Auth/Guardrails | `auth/`, `guardrails/` — RBAC roles; Layers 1 (input), 2 (prompt), 3 (SQL) |
| Voice ("Ask Aloud") | `agent/voice.py` — STT via Groq `whisper-large-v3-turbo`; `app.py::voice_respond()` — TTS via browser `speechSynthesis`; mic feeds transcribed text into the same `respond()` pipeline as typed input |
| LLM Call Log | `agent/call_log.py` — in-memory per-user ring buffer (max 50) of every Groq call: agent, model, round, message count, prompt/completion/total tokens. Recorded from `QueryAgent.chat()` and `ChartAgent.analyze()`. Surfaced via a popup opened by clicking the role badge (Admin only, gated by `can_see_logs`) |

---

## Key decisions (do not reverse)

- **LLM:** `openai/gpt-oss-120b` via Groq (migrated 2026-07 off `meta-llama/llama-4-scout-17b-16e-instruct`, which Groq deprecated 2026-06-17 with shutdown 2026-07-17). `reasoning_effort="low"` set on both agents' completions calls to cut hidden chain-of-thought token usage — this is a fast interactive tool, not a deep-reasoning one. Env: `GROQ_API_KEY`.
- **Tool schema:** OpenAI format. Omit `"required"` key entirely when no params are required.
- **ChartAgent `build_chart`:** no `data` param in schema — agent injects `fn_args["data"] = rows` before dispatch. Prevents Groq rejecting a stringified array.
- **ChartAgent deep mode:** activated by "Want me to include related insights?" checkbox in UI. Uses `_SYSTEM_PROMPT_DEEP` (separate prompt, not an addendum) with steps: build_chart → get_schema → query_database → bullets. Max 6 tool rounds, 2048 tokens. Code-level enforcement: if model calls `get_schema` but skips `query_database`, an injected user message forces it before bullets are written. Enrichment errors are silently ignored; model falls back to original data.
- **ChartAgent insights:** always 3 bullets structured as headline → story beat → exploration hook. Narrative frames: Time / Contrast / Outlier / Distribution / Near-parity (values within 5%).
- **Y-axis formatting:** `_nice_ticks()` always starts from 0, uses round intervals (1/2/2.5/5/10 × magnitude). `_format_abbrev()` strips trailing zeros (e.g. "1.2Mn" not "1.20Mn").
- **Assistant messages:** set `content: None` (not `""`) when `tool_calls` is present — empty string causes intermittent 400s.
- **System prompt embeds schema:** `agent/system_prompt.py::build()` inlines a compact listing from `mcp/tools.py::get_schema_compact()` (`table(col type, ...)`, no indentation/row counts). **Reversed 2026-07** from "always call `get_schema` first" — free-tier TPM dropped 30K→8K on the post-scout models, so the mandatory per-turn tool round was cut. `get_schema` remains a fallback tool, just not mandatory.
- **TPM budget (2026-07, free tier 30K→8K):** `cap_rows_for_llm()` caps any tool result's `rows` to 40 before re-entering LLM context in both agents — full uncapped data still flows separately to `last_query_result`/charting. `build_chart`'s tool result is replaced with a minimal confirmation instead of the full `fig.to_json()`. QueryAgent history trimmed 6→3 turns, each stored answer capped at 600 chars.
- **Email:** Resend v1.x (`resend.api_key` + `resend.Emails.send()`). Do not upgrade to v2.
- **DB path:** `DB_PATH` env var → `/app/Data/customerserve.duckdb` in Docker.
- **Voice:** STT via Groq `whisper-large-v3-turbo` (reuses `GROQ_API_KEY`; free tier 2,000 req/day, 7,200 audio-sec/hr) — transcribed text is not a separate trust boundary, same guardrails/RBAC as typed input. TTS via browser `speechSynthesis`, client-side JS, zero new deps — Groq's paid per-character TTS deliberately avoided. Mic widget: `editable=False`, download/share hidden — record/stop, play, clear (x) only.
- **`ffmpeg` in Dockerfile:** required — Gradio's `Audio` component needs it to convert the browser's recorded webm/ogg into a file Whisper can read. Missing it caused every voice query to silently fail (empty transcript, no exception) in prod; do not remove.
- **`voice_respond()` in `app.py`:** wraps `respond()` for the Ask Aloud path only. If the transcript is `< 3` chars (mirrors the input guardrail's own threshold — Whisper returns near-empty text on mostly-silent recordings), shows "I didn't catch that — try recording again" instead of routing through to the generic guardrail message, which is confusing for a bad-recording cause.
- **LLM Call Log popup:** the role badge is deliberately plain HTML (`_heading_html()`), not a `gr.Button` — CSS resets on an actual Button component (`all:unset`, then `size="sm"`) never took visible effect across two attempts, so don't retry that. Badge `onclick` triggers a hidden, permanently `display:none` Gradio Button (`#llm-log-trigger`) via JS. The popup itself (`llm_log_modal`) stays `visible=True` at the Gradio level always — its open/closed state is driven purely by toggling the `llm-modal-open` CSS class via `elem_classes`, never Gradio's own `visible` prop. **Do not put a `display` rule on `.llm-modal-overlay` guarded by Gradio's `visible=`** — it fought Gradio's internal show/hide and left the modal stuck open, blocking the whole app.
- **`products` has no name column:** only `product_id`, `brand`, `category`, `sub_category`, `mrp`. System prompt tells QueryAgent to group/label generic "products" questions by `brand`, not raw `product_id`.
- **`build_chart` axis guard:** if the model passes the same column for `x_col`/`y_col` (occasional Groq mistake), code auto-swaps `y_col` to another numeric column rather than rendering a broken chart.

## RBAC

| Role | Free-form | Raw rows | Row limit |
|------|-----------|----------|-----------|
| ADMIN | Yes | Yes | 10,000 |
| ANALYST | Yes | No | 1,000 |
| VIEWER | Templates only | No | 100 |

Users: `admin` / `alice` (analyst) / `bob` (viewer). Passwords from env vars.

`can_see_logs` (ADMIN only, `auth/roles.py`) gates the LLM Call Log popup — other roles see the same role badge but clicking it does nothing.

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
