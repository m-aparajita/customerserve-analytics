# Order Insights — Architecture & Design Document

> **Purpose:** Interview preparation reference covering system design, technology choices, trade-offs, and known gaps.

---

## 1. What It Does

Order Insights is a **natural-language analytics agent** for retail order data. A user types a question in plain English; the system automatically writes SQL, queries a database, renders an interactive chart, and surfaces key insights — no coding required. Users can then email the report to themselves instantly or schedule recurring deliveries (weekly, bi-weekly, monthly).

**Core user journey:**
> *"Show me monthly revenue for 2024"* → SQL generated → DuckDB queried → Plotly bar chart rendered + text summary → optionally emailed or scheduled

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     HuggingFace Space (Docker)                  │
│                                                                 │
│   Browser                                                       │
│      │                                                          │
│      ▼                                                          │
│  ┌────────────────────────────────────────────────────────┐    │
│  │                   Gradio UI  (app.py)                  │    │
│  │   Auth Login → Role Badge → Schema Accordion           │    │
│  │   → Query Box → Templates → Chat Response              │    │
│  │   → Chart → Key Insights → Download Chart (PNG)        │    │
│   → Schedule Report (email now / recurring)            │    │
│  └───────────────────────────┬────────────────────────────┘    │
│                              │                                  │
│                    ┌─────────▼──────────┐                      │
│                    │   Auth Manager     │                      │
│                    │  ADMIN/ANALYST/    │                      │
│                    │  VIEWER + RBAC     │                      │
│                    └─────────┬──────────┘                      │
│                              │                                  │
│                    ┌─────────▼──────────┐                      │
│                    │  Input Guardrail   │  ← Layer 1           │
│                    │  (prompt injection │                      │
│                    │   & topic filter)  │                      │
│                    └─────────┬──────────┘                      │
│                              │                                  │
│                    ┌─────────▼──────────┐                      │
│                    │   QueryAgent       │                      │
│                    │  get_schema +      │◀──▶ Groq API         │
│                    │  query_database    │     gpt-oss-120b     │
│                    └─────────┬──────────┘                      │
│                         rows │                                  │
│                    ┌─────────▼──────────┐                      │
│                    │   ChartAgent       │                      │
│                    │  build_chart +     │◀──▶ Groq API         │
│                    │  key insights      │     gpt-oss-120b     │
│                    └──┬─────────────────┘                      │
│                       │                                         │
│              ┌────────▼┐  ┌──────────┐                        │
│              │get_schema│  │query_ db │                        │
│              │          │  │(+Layer 3)│                        │
│              └──────────┘  └──┬───────┘                        │
│                               │                                 │
│                    ┌──────────▼──────────┐                     │
│                    │       DuckDB        │                     │
│                    │  orders / products  │                     │
│                    │  order_items /      │                     │
│                    │  query_logs /       │                     │
│                    │  scheduled_reports  │                     │
│                    └─────────────────────┘                     │
│                                                                 │
│                    ┌─────────────────────┐                     │
│                    │   Mailer            │──▶ Resend API        │
│                    │  mailer/sender.py   │    (email + chart    │
│                    │  database/          │     PNG attachment)  │
│                    │  scheduler.py       │                     │
│                    └─────────────────────┘                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Layered Architecture

```
┌──────────────────────────────────────────┐
│  PRESENTATION       Gradio UI (app.py)   │
│                     Single-column layout  │
│                     Plotly charts        │
│                     Key Insights box     │
│                     Chart PNG export     │
│                     (kaleido, scale=2)   │
├──────────────────────────────────────────┤
│  AUTH & RBAC        auth/manager.py      │
│                     auth/roles.py        │
│                     3 roles, row limits  │
├──────────────────────────────────────────┤
│  GUARDRAILS         Layer 1 — input      │
│  (Defence-in-depth) Layer 2 — prompt     │
│                     Layer 3 — SQL        │
├──────────────────────────────────────────┤
│  QUERY AGENT        agent/gemini_agent.py│
│                     Tools: get_schema,   │
│                     query_database,      │
│                     get_sample_data      │
│                     Returns rows         │
├──────────────────────────────────────────┤
│  CHART AGENT        agent/chart_agent.py │
│                     Tool: build_chart    │
│                     (data injected by    │
│                      agent, not LLM)     │
│                     Picks chart type     │
│                     Returns insights     │
├──────────────────────────────────────────┤
│  TOOLS (MCP-style)  get_schema           │
│                     query_database       │
│                     get_sample_data      │
│                     build_chart          │
│                     (axis labels auto-   │
│                      formatted)          │
├──────────────────────────────────────────┤
│  EMAIL / SCHEDULER  mailer/sender.py     │
│                     send_email(to,subj,  │
│                     html,attachment)     │
│                     HTML built in app.py │
│                     database/scheduler   │
│                     Resend API (v1.x)    │
├──────────────────────────────────────────┤
│  DATA               DuckDB (in-process)  │
│                     CSV → HF Dataset     │
│                     query_logs table     │
│                     scheduled_reports    │
├──────────────────────────────────────────┤
│  OBSERVABILITY      agent/call_log.py    │
│  (Admin only, §9)   stdout + in-memory   │
│                     per-user ring buffer │
│                     of Groq call/token   │
│                     usage this session   │
└──────────────────────────────────────────┘
```

---

## 4. User Query Flow — Sequence Diagram

```
User    Gradio   Auth   Guardrail  QueryAgent   Groq     DuckDB  ChartAgent  Groq
 │         │       │        │           │          │         │        │         │
 │─login──▶│       │        │           │          │         │        │         │
 │         │─verify▶        │           │          │         │        │         │
 │◀─role───│       │        │           │          │         │        │         │
 │         │       │        │           │          │         │        │         │
 │─query──▶│       │        │           │          │         │        │         │
 │         │──get_role()────▶           │          │         │        │         │
 │         │       │  L1 check          │          │         │        │         │
 │         │       │  PASS              │          │         │        │         │
 │         │       │────────────────────▶          │         │        │         │
 │         │       │        │  ROUND 1  │          │         │        │         │
 │         │       │        │  messages (schema already in system prompt) ──▶  │
 │         │       │        │           │◀─tool: query_db     │        │         │
 │         │       │        │  L3 check │          │         │        │         │
 │         │       │        │  PASS     │──────────────────────▶      │         │
 │         │       │        │           │◀────────── rows ────│        │         │
 │         │       │        │  ROUND 2  │          │         │        │         │
 │         │       │        │  (rows, capped to 40) ────────▶│         │        │         │
 │         │       │        │           │◀─ text answer       │        │         │
 │         │       │        │           │          │         │        │         │
 │         │  ── rows passed to ChartAgent ──────────────────────────▶│         │
 │         │       │        │           │          │         │  ROUND 1          │
 │         │       │        │           │          │         │  (rows+question)──▶
 │         │       │        │           │          │         │        │◀─tool: build_chart
 │         │       │        │           │          │         │        │ render Plotly fig
 │         │       │        │           │          │         │  ROUND 2          │
 │         │       │        │           │          │         │  (chart confirmed)─▶
 │         │       │        │           │          │         │        │◀─insights text
 │         │       │        │           │          │         │        │         │
 │◀─ text + chart + insights ─────────────────────────────────────────│         │
```

`get_schema` is still a declared tool for QueryAgent — the model can call it if it suspects the embedded schema is stale — but it's no longer forced on round 1.

---

## 5. Guardrails — Defence in Depth

```
                    User Input
                        │
            ┌───────────▼────────────┐
  LAYER 1   │    Input Guardrail     │  Blocks: off-topic questions,
            │  guardrails/input_     │  prompt injection attempts,
            │  guardrail.py          │  jailbreak patterns
            └───────────┬────────────┘
                        │
            ┌───────────▼────────────┐
  LAYER 2   │   Role-Scoped System   │  Blocks: role-specific rules
            │   Prompt               │  embedded in LLM context.
            │   agent/system_prompt  │  VIEWER → templates only.
            └───────────┬────────────┘
                        │
            ┌───────────▼────────────┐
  LAYER 3   │    SQL Guardrail       │  Blocks: non-SELECT statements,
            │  guardrails/           │  applies row-limit per role,
            │  sql_guardrail.py      │  strips dangerous clauses
            └───────────┬────────────┘
                        │
                    DuckDB Query
```

---

## 6. RBAC Model

| Role | Free-form Query | Raw Row Access | Row Limit | Allowed Charts | Schema Accordion | Can Query query_logs | LLM Call Log (§9) |
|------|:--------------:|:--------------:|:---------:|:--------------:|:----------------:|:--------------------:|:------------------:|
| ADMIN | ✅ | ✅ | 10,000 | All | ✅ | ✅ | ✅ |
| ANALYST | ✅ | ❌ (aggregates only) | 1,000 | All | ✅ | ❌ | ❌ |
| VIEWER | ❌ (templates only) | ❌ | 100 | Limited | ❌ | ❌ | ❌ |

Credentials loaded from environment variables at startup — never hardcoded.

---

## 7. Multi-Agent Design

The system uses two specialised agents that run sequentially per user turn.

### QueryAgent (`agent/gemini_agent.py`)
Owns data retrieval. Runs a tool loop (max 8 rounds):

```
Round 1:  LLM receives user question, schema already embedded in system prompt
                                      → calls query_database(sql)
Round 2:  LLM receives rows (capped to 40 for context, full set kept for charting)
                                      → writes text answer
          Loop exits → returns (text, rows)
```

**Why the schema is embedded, not fetched:** The model still can't write correct SQL without knowing column names — that hasn't changed. What changed (2026-07) is *how* it learns them: `agent/system_prompt.py::build()` inlines a compact listing from `get_schema_compact()` instead of forcing a `get_schema` tool round every turn. That saved a full round trip per query, which mattered once Groq's free-tier TPM dropped from 30K to 8K on the models that replaced `llama-4-scout`. `get_schema` is still a declared tool, used as a fallback.

**Schema caching:** `get_schema()` (and the compact variant built from it) queries DuckDB once at startup and stores the result in `_schema_cache`. Every subsequent call returns instantly with no DB round-trip.

**Context budget:** `cap_rows_for_llm()` (`mcp/tools.py`) caps any tool result's row list to 40 before it re-enters the conversation — the RBAC row limit (up to 10,000 for admins) governs what reaches the chart/export path, not what the model needs to see to write a sentence.

### ChartAgent (`agent/chart_agent.py`)
Owns visualisation and insight. Runs only when QueryAgent returns rows. Two modes:

**Standard mode** (max 3 rounds, 1024 tokens):
```
Round 1:  Receives rows + user question → decides chart type → calls build_chart()
Round 2:  Receives chart confirmation   → writes 3 insight bullets
          Loop exits → returns (chart_json, insights)
```

**Deep insights mode** (max 6 rounds, 2048 tokens) — activated by UI checkbox:
```
Round 1:  Receives rows + user question → calls build_chart() [+ get_schema() in parallel]
          [Code check: if get_schema called but query_database not yet → inject user message]
Round 2:  Forced by injected message   → calls query_database() for time/comparison dimension
Round 3:  Receives enrichment rows     → writes 3 narrative insight bullets
          Loop exits → returns (chart_json, insights)
```
Deep mode uses a completely separate system prompt (`_SYSTEM_PROMPT_DEEP`). The model tends to call `build_chart` and `get_schema` together in round 1 then skip straight to bullets — the code detects this and injects a nudge before the next LLM call to force `query_database`. Enrichment errors are silently ignored; model falls back to original data.

**Chart type selection rules:**
- **line** — time-series or sequential data
- **bar** — categorical comparisons
- **pie** — part-of-whole with ≤ 6 categories
- **scatter** — correlation between two numeric columns
- **histogram** — distribution of a single numeric column

**Insight narrative frames** (model picks the best fit):
- **Time** — trend arc using specific months/periods
- **Contrast** — biggest divergence between two categories with numbers
- **Outlier** — one value significantly above/below the rest
- **Distribution** — concentration across a ranking
- **Near-parity** — values within 5% of each other (tight competition IS the story)

Bullets are always structured: headline → story beat → exploration hook.

**Key implementation detail — `data` not in tool schema:** The ChartAgent's `build_chart` schema deliberately omits the `data` parameter. The agent injects `fn_args["data"] = rows` before calling dispatch. This avoids a Groq validation error where the LLM would JSON-stringify the array into a string. The LLM only specifies `chart_type`, `x_col`, `y_col`, and `title`.

**Defensive guard — duplicate axis columns:** the model occasionally picks the same column for both `x_col` and `y_col` (e.g. charting `order_status` against itself), producing a meaningless chart. `build_chart` in `mcp/tools.py` detects this and auto-substitutes a different numeric column for `y_col` rather than rendering the broken result — a code-level fix for an LLM mistake that can't be reliably prompted away.

**Context budget — `build_chart`'s own tool result:** the raw Plotly figure (`fig.to_json()`) used to be sent straight back into the conversation, then resent on every later round. Since the model never needs the figure spec to write insight bullets, `ChartAgent.analyze()` now swaps it for a `{"status": "chart created", ...}` confirmation before appending it — one more piece of the 2026-07 TPM cleanup (see `cap_rows_for_llm()` above).

### Why separate agents?
| Concern | QueryAgent | ChartAgent |
|---------|-----------|------------|
| Tools | get_schema, query_database, get_sample_data | build_chart (+ get_schema, query_database in deep mode) |
| Skill | SQL reasoning, schema navigation | Visual storytelling, pattern recognition |
| Rounds | Up to 8 | Up to 3 (standard) / 6 (deep) |
| Failure mode | Bad SQL → guardrail catches it | Bad chart choice → benign, still shows something |

Each agent can be tuned, swapped, or scaled independently. In production, ChartAgent could use a smaller/cheaper model since chart selection is a simpler task than SQL generation.

The tool loop uses the **OpenAI function-calling format** (Groq is OpenAI-compatible), making both agents portable to GPT-4o, Claude, or any other OpenAI-compatible provider with zero code changes.

---

## 8. Voice Input ("Ask Aloud")

Users can speak their question instead of typing it. The recording is transcribed to text via Groq's hosted Whisper model, then fed into the **exact same** `respond()` pipeline used for typed input — voice is not a separate trust boundary; the same guardrails and RBAC apply unchanged.

```
Click record → speak → click stop
        │
        ▼
gr.Audio (type="filepath") saves the browser recording to disk
        │
        ▼
agent/voice.py :: transcribe_audio()  ──▶  Groq Whisper (whisper-large-v3-turbo)
        │
        ▼
app.py :: voice_respond()
        │
   ┌────┴──────┐
   │  empty /   │──▶ "I didn't catch that — please try recording again…"
   │  <3 chars  │    (mirrors the input guardrail's own length threshold,
   └────┬──────┘     but gives a clearer, voice-specific message)
        │ real text
        ▼
respond() — identical pipeline to typed input (Layer 1 guardrail → QueryAgent → ChartAgent)
```

**Why a separate `voice_respond()` wrapper:** Whisper occasionally returns an empty or near-empty transcript when a recording is mostly silence — e.g. speech starting right as the mic activates. Left alone, that empty string falls through to the generic input-guardrail rejection ("Please ask a more specific question."), which is a confusing message when the real cause was a bad recording, not a bad question. `voice_respond()` intercepts that specific case before the guardrail sees it and prompts a retry instead.

**A real production incident:** the Docker image originally shipped without `ffmpeg`. Gradio's `Audio` component needs it to convert the browser's recorded webm/ogg stream into a file Whisper can read; without it, every voice query transcribed to an empty string and silently failed — with zero trace in the logs, because a guardrail rejection happens *before* any Groq call is made, so there's nothing to log. See §16 for how that was diagnosed.

**TTS ("Listen to answer"):** the browser's built-in `speechSynthesis` API, entirely client-side JS — zero API calls, zero new dependencies. Deliberately avoids Groq's paid per-character TTS endpoint.

---

## 9. Admin Observability — LLM Call Log

Every Groq `chat.completions` call made by QueryAgent or ChartAgent is recorded — model, round number, message count, and prompt/completion/total token usage — to two places:

1. **stdout**, via the standard `logging` module (visible in the HF Space's container logs).
2. **An in-memory, per-user ring buffer** (`agent/call_log.py`, capped at 50 calls/user), surfaced live in the UI.

Admins click their role badge (the "username · ADMIN" pill, top right) to open a popup listing these calls, most recent first; clicking again refreshes it. Gated by the existing `can_see_logs` RBAC flag — Analyst and Viewer see the same badge, but clicking it is a server-side no-op (checked in `toggle_llm_log()`, not merely hidden in the UI).

**Why in-memory instead of a DB table:** this is a developer/debugging aid, not an audit trail — that's what `query_logs` is for. It doesn't need to survive an app restart, and a dict-of-deques avoids adding DuckDB write load on every LLM round-trip.

**Two implementation dead-ends worth knowing, since both looked reasonable and both failed:**

- *Styling the badge as a `gr.Button`.* CSS was applied to make a real Gradio Button look like the original pill (first `all:unset` + hand-rolled styles, then Gradio's own `size="sm"`/`variant="secondary"`). Neither ever visibly changed the button's size — it kept rendering at Gradio's compiled default, most likely because the selectors weren't reaching whatever element actually governs the Button component's box model in this Gradio version, and there was no easy way to inspect that without a live browser session. Rather than keep guessing at internal markup, the badge was rebuilt as plain HTML — the *original* pill `<span>`, pixel-identical by construction — with an `onclick` that triggers a separate, permanently `display:none` Gradio Button (`#llm-log-trigger`) via a few lines of JS DOM traversal. This fully decouples "what it looks like" (HTML/CSS we fully control) from "how the click reaches Python" (a native Gradio event listener we never have to style).

- *Toggling the popup via the component's own `visible=True/False`.* Custom CSS on the overlay (`position:fixed`, full-screen backdrop) needed a `display` value to lay itself out, and any `display` declaration there — even without `!important` — kept winning the cascade against whatever Gradio does internally to hide a `visible=False` component. Net effect: the modal was permanently open and its full-screen `z-index:1000` overlay blocked every click on the page, including login. Fixed by never toggling `visible` for this component at all — it stays permanently `visible=True`, and open/closed state is driven purely by our own `llm-modal-open` CSS class via `elem_classes`, so there's nothing left for Gradio's internals to conflict with.

---

## 10. Technology Decisions

### LLM — Groq + openai/gpt-oss-120b

| Option considered | Decision |
|------------------|----------|
| OpenAI GPT-4o | ❌ Paid API, cost unpredictable at scale |
| Anthropic Claude | ❌ No free tier for production |
| Groq + gpt-oss-120b | ✅ Free tier, ~500 tokens/sec, tool-use capable, OpenAI-compatible |

**Key point:** Groq's inference speed (~10× faster than typical cloud APIs) matters here because the agent makes 3–4 LLM calls per user question. Slow inference would make the UX feel broken.

**Migration note (2026-07):** originally `meta-llama/llama-4-scout-17b-16e-instruct`; Groq deprecated it (shutdown 2026-07-17) and its free-tier replacements dropped TPM from 30K to 8K. Moved to `gpt-oss-120b` (Groq's recommended, production-status replacement) with `reasoning_effort="low"` to keep its hidden chain-of-thought from eating into that smaller budget, plus the context-trimming changes described in §7.

---

### Database — DuckDB

| Option considered | Decision |
|------------------|----------|
| PostgreSQL | ❌ Needs a separate server process — incompatible with HF free tier single-process model |
| SQLite | ❌ Row-oriented, poor analytics performance on aggregation queries |
| BigQuery / Snowflake | ❌ Cloud dependency, latency, cost |
| DuckDB | ✅ In-process (runs inside Python), columnar storage, optimised for GROUP BY/SUM/analytics |

**Key point:** DuckDB runs entirely inside the Python process — no network calls, no servers, zero infrastructure. A `SELECT SUM(revenue) GROUP BY month` on 100K rows completes in milliseconds.

---

### UI — Gradio

| Option considered | Decision |
|------------------|----------|
| React + FastAPI | ❌ Two processes, complex Docker config, JS build pipeline |
| Streamlit | ❌ State management limitations for agentic chat |
| Gradio | ✅ Native HF Spaces support, built-in auth, Plotly integration, single Python process |

**Key point:** HuggingFace Spaces is optimised for Gradio. Built-in auth means no session management code to write or secure.

---

### Hosting — HuggingFace Spaces (Docker)

- Free tier, public portfolio URL, built-in HTTPS
- Docker SDK gives full control over the runtime environment
- Secrets management via HF UI (no `.env` files in production)
- Two-Space strategy: `customerserve-analytics` (stable) and `customerserve-dev` (experimental)

---

### Tool Format — OpenAI Function Calling

- Industry standard supported by Groq, OpenAI, Azure OpenAI, and many others
- Switching LLM providers requires only changing the model name and API key
- Schema declared once in `mcp/tools.py`, used by both agent and dispatcher

---

## 11. Database Tables

All tables live in a single DuckDB file (`customerserve.duckdb`).

---

### `orders` — one row per customer order
| Column | Type | Description |
|--------|------|-------------|
| `order_id` | VARCHAR | Unique order identifier (e.g. `Byk-0`) |
| `customer_id` | INTEGER | Customer identifier |
| `order_date` | DATE | Date the order was placed |
| `order_ts` | TIMESTAMP | Full timestamp of the order |
| `city` | VARCHAR | City where the order was placed |
| `state` | VARCHAR | State code (e.g. `DL`, `MH`) |
| `payment_method` | VARCHAR | e.g. `Wallet`, `Card`, `COD` |
| `order_status` | VARCHAR | e.g. `Delivered`, `Cancelled`, `Returned` |
| `total_amount` | DOUBLE | Total order value in INR |

---

### `order_items` — one row per product line within an order
| Column | Type | Description |
|--------|------|-------------|
| `order_id` | VARCHAR | Foreign key → `orders.order_id` |
| `product_id` | INTEGER | Foreign key → `products.product_id` |
| `quantity` | INTEGER | Number of units ordered |
| `unit_price` | DOUBLE | Price per unit at time of order |
| `discount` | DOUBLE | Discount applied (INR) |
| `net_amount` | DOUBLE | Final line amount after discount |

---

### `products` — product catalogue
| Column | Type | Description |
|--------|------|-------------|
| `product_id` | INTEGER | Unique product identifier |
| `brand` | VARCHAR | Brand name (e.g. `Himalaya`, `Maybelline`) |
| `category` | VARCHAR | Top-level category (e.g. `Fragrance`, `Skincare`) |
| `sub_category` | VARCHAR | Sub-category (e.g. `Compact`, `Serum`) |
| `mrp` | DOUBLE | Maximum retail price in INR |

No product-name column exists — `product_id` is a raw numeric ID with no display meaning. The system prompt tells QueryAgent to group/label generic "products" questions by `brand` instead.

---

### `query_logs` — audit trail of every agent query
| Column | Type | Description |
|--------|------|-------------|
| `log_id` | VARCHAR | UUID primary key |
| `ts` | TIMESTAMP | When the query was executed |
| `username` | VARCHAR | Logged-in user |
| `role` | VARCHAR | `admin`, `analyst`, or `viewer` |
| `user_query` | TEXT | The original plain-English question |
| `generated_sql` | TEXT | SQL produced by the QueryAgent |
| `exec_ms` | INTEGER | DuckDB execution time in milliseconds |
| `rows_returned` | INTEGER | Number of rows the query returned |
| `chart_type` | VARCHAR | Chart type selected by ChartAgent (if any) |
| `status` | VARCHAR | `success`, `blocked`, or `error` |
| `guardrail_layer` | VARCHAR | Which guardrail blocked the query (if blocked) |
| `guardrail_reason` | TEXT | Human-readable reason for the block |
| `error_message` | TEXT | Exception message (if status = `error`) |

---

### `scheduled_reports` — user-created report schedules
| Column | Type | Description |
|--------|------|-------------|
| `id` | VARCHAR | UUID primary key |
| `username` | VARCHAR | User who created the schedule |
| `email` | VARCHAR | Recipient email address |
| `question` | TEXT | Original question — re-run each delivery for fresh data |
| `frequency` | VARCHAR | `weekly`, `biweekly`, or `monthly` |
| `days_of_week` | VARCHAR | JSON array of days e.g. `["Mon","Wed"]` (weekly/biweekly only) |
| `start_date` | DATE | Date the schedule becomes active |
| `end_date` | DATE | Date the schedule expires (NULL = indefinite) |
| `next_send_date` | DATE | Next date a delivery is due |
| `created_at` | TIMESTAMP | When the schedule was saved |
| `last_sent_at` | TIMESTAMP | When the last email was successfully sent (NULL if never) |
| `active` | BOOLEAN | `TRUE` = active, `FALSE` = cancelled |

---

## 12. Data Flow — Startup

```
Docker container starts
        │
        ▼
database/setup.py runs
        │
        ├─ Does customerserve.duckdb exist?
        │         │
        │    NO   ▼
        │   Download CSVs from HuggingFace Dataset
        │   Load into DuckDB tables
        │   Create query_logs table
        │         │
        │   YES ──┘
        │
        ▼
get_schema() called → result stored in _schema_cache
        │
        ▼
Gradio UI starts (app.py)
        │
        ▼
Agent singleton created (QueryAgent)
        │
        ▼
Ready to serve requests
```

---

## 13. Deployment Architecture

```
GitHub (origin)
    │
    ├── main branch ──────────────────▶ HF Space: customerserve-analytics
    │                                             (interview / stable)
    │
    └── dev branch ───────────────────▶ HF Space: customerserve-dev
                                                  (experimental)

Tag v1.0 = last known-good interview version (rollback point)
```

**Branch workflow:**
- All new work happens on `dev`
- Deploy to `customerserve-dev` to test live
- Merge to `main` and push to `customerserve-analytics` only when satisfied

---

## 14. What Is Out of Scope

| Feature | Why excluded |
|---------|-------------|
| Real-time / live data | Uses a static retail dataset; no database write path |
| Data export (CSV / PDF) | Chart PNG download is implemented; CSV/PDF export is not |
| Conversation persistence | Chat history resets on page refresh (Gradio session-scoped) |
| Multi-language support | English only |
| Mobile-optimised UI | Gradio is desktop-first |
| User self-registration | Credentials are env-var configured; no user management UI |
| Fine-tuned model | Uses a general-purpose instruction model |

---

## 15. Known Limitations & Critical Missing Items

These are gaps you should be ready to discuss in interviews:

| Gap | Impact | Production fix |
|-----|--------|---------------|
| **Basic auth (Gradio built-in)** | Passwords sent over HTTP if not behind HTTPS; no token expiry | Replace with OAuth2 / JWT; Gradio's HTTPS on HF mitigates this partially |
| **No response streaming** | User waits 10–20 seconds with no feedback while agent runs all rounds | Implement `yield`-based streaming in the agent loop |
| **No rate limiting** | A single user can flood the Groq API or exhaust free-tier quota | Add per-user request throttling (e.g. Redis + token bucket) |
| **No test suite** | Regressions in SQL guardrails or tool dispatch go undetected | Add pytest suite covering guardrail edge cases and tool dispatcher |
| **Static dataset** | Insights are not from live business data | Add a data ingestion pipeline (e.g. nightly CSV refresh from an S3 bucket) |
| **Single-process / single-instance** | Cannot scale horizontally; one crash kills all users | Move to a queue-backed architecture (Celery + Redis) for the agent |
| **No persistent observability** | `query_logs` table exists, and Admins can see live per-session LLM call/token usage (§9), but neither has dashboards, alerts, or history beyond the current process — the call log resets on every restart/redeploy | Persist LLM call records to a table (or Grafana on top of `query_logs`) for historical token-usage trends and alerting |
| **Deep insights enrichment** | Model may call `get_schema` and `build_chart` together then skip `query_database` — code-enforced nudge mitigates this but is a workaround for model non-compliance | Use `tool_choice` to enforce specific tool call order, or move enrichment into deterministic code rather than relying on the LLM to call it |
| **LLM hallucination on SQL** | The model occasionally generates wrong column names or logic | Add a SQL validation step that runs EXPLAIN before execution |
| **Groq free-tier limits** | Rate limits and monthly token caps can break the app silently. TPM dropped 30K→8K in the 2026-07 model migration; mitigated via schema embedding, row-capping, and history trimming (§7), but still a hard ceiling | Add fallback error messaging and consider a paid tier for demos |
| **No prompt versioning** | System prompt changes are not tracked or A/B tested | Store prompt versions in code and log which version was used per query |
| **Insights capped at 200 rows** | `ChartAgent` only shows the AI the first 200 rows of a result set (`_MAX_ROWS_TO_CHART` in `agent/chart_agent.py`). For aggregated queries (GROUP BY month/category) this is rarely hit, but a large, non-aggregated result set would have its insights based on a partial, arbitrarily-ordered sample rather than the full data | Aggregate before sending to the AI, or explicitly flag to the model when it's seeing a partial sample so it can caveat its insights |

---

## 16. Interview Talking Points

**"Walk me through your architecture."**
> Single-process Python app with a two-agent pipeline. Gradio handles UI and auth. A QueryAgent talks to Groq to write SQL and retrieve data. The rows are handed off to a ChartAgent, which independently decides the best visualisation and surfaces 3 narrative insight bullets structured as headline → story beat → exploration hook. There's also an optional deep insights mode where the ChartAgent runs a follow-up enrichment query — `get_schema` then `query_database` — to fetch the time or comparison dimension missing from the original result, producing richer narrative bullets. The model tends to bundle `get_schema` with `build_chart` and skip the enrichment query, so the code detects that pattern and injects a prompt nudge to force it. Everything runs in one Docker container on HuggingFace Spaces free tier.

**"Why two agents instead of one?"**
> QueryAgent and ChartAgent have genuinely different skills. QueryAgent needs to reason about schema, write correct SQL, and understand business intent. ChartAgent needs to understand visual storytelling — which chart type fits the data shape, which narrative frame (time trend, contrast, outlier, near-parity) best tells the story, and what to explore next. Separating them means each has a focused system prompt, a minimal tool set, and can be tuned or swapped independently. In production, ChartAgent could run on a smaller, cheaper model since chart selection is a simpler task than SQL generation.

**"Why DuckDB instead of PostgreSQL?"**
> DuckDB is an in-process analytical database — it runs inside the Python process with no server, no network, and no configuration. For read-heavy analytics workloads (GROUP BY, SUM, window functions), it outperforms SQLite significantly. It was the right choice for a single-container deployment where I couldn't run a separate database server.

**"How does the agent know what SQL to write?"**
> It doesn't hardcode any schema knowledge in the sense of a static prompt someone wrote by hand — `get_schema_compact()` builds the listing from DuckDB itself at startup and it's inlined into the system prompt. That eliminates hallucinated column names and keeps the system schema-agnostic — swap in a different database and the prompt regenerates itself. It used to be a `get_schema` tool call the model was forced to make on round 1 of every query; I moved it into the prompt in 2026-07 once Groq's free-tier TPM dropped enough that the extra round trip became the biggest avoidable cost. The `get_schema` tool is still there as a fallback, and the same underlying cache powers the Schema Reference accordion in the UI for ADMIN and ANALYST users.

**"How do you prevent SQL injection or data leaks?"**
> Three layers. Layer 1 filters the raw user input for prompt injection patterns. Layer 2 is the role-scoped system prompt — the model is instructed what it can and cannot do. Layer 3 validates the generated SQL before execution: only SELECT is allowed, dangerous clauses are stripped, and row limits are enforced per role. Even if the LLM were somehow manipulated, it cannot write a DELETE or expose another user's data.

**"What would you do differently in production?"**
> Three things immediately: streaming responses (users shouldn't wait 15 seconds), a proper auth layer with JWT instead of Gradio's basic auth, and rate limiting per user so the Groq free tier isn't exhausted. After that, a test suite for the guardrails — those are security-critical and currently untested.

**"How does the report scheduling work?"**
> After any chart is rendered, a schedule panel appears. Users can send the report immediately or set up weekly, bi-weekly, or monthly recurring deliveries with a start/end date. Schedules are stored in a `scheduled_reports` DuckDB table. On each page load, a background thread checks for overdue schedules and re-runs the original query to generate fresh data before emailing the chart via Resend. It's best-effort on HuggingFace free tier — it fires when the app is active — which is appropriate for a portfolio demo but would need a dedicated scheduler in production.

**"Why two HuggingFace Spaces?"**
> Staging vs production. The `main` branch deploys to the stable interview Space which I never touch mid-demo. The `dev` branch deploys to a private dev Space where I iterate freely. When a change is validated on dev, I merge to main and promote it. The `v1.0` git tag gives me a rollback point if something goes badly wrong.

**"Tell me about a bug you had to debug in production."**
> Users started getting "Please ask a more specific question" on every voice query — the input guardrail's message for queries under 3 characters, which was odd for real spoken questions. The container logs showed successful runs immediately before and after each failure, with zero trace of the failure itself — because a guardrail rejection happens *before* any Groq call is made, so there's genuinely nothing to log. That absence of evidence was the actual clue: it meant Whisper was returning an empty transcript for some recordings. Root cause was a missing `ffmpeg` in the Docker image — Gradio's `Audio` component needs it to convert the browser's mic recording into a file Whisper can read. I fixed the missing dependency, then separately improved the UX so an empty/near-empty transcription shows a "try recording again" prompt instead of the generic guardrail message, since the two failure causes look identical to the guardrail but mean very different things to the user.

**"How would you debug something you can't reproduce locally?"**
> This came up building the LLM Call Log popup — my local Python version couldn't install the project's pinned dependencies, so every CSS/layout iteration had to be verified live on the `hf-dev` Space instead of in a local browser. Two rounds of guesses at Gradio's internal component markup (trying to restyle a `gr.Button`, then trying to toggle a modal via its `visible` prop) both failed in ways that weren't obvious from reading the code — the fixes only became clear from what the user actually saw happen. Eventually I stopped guessing at Gradio's internals altogether: rebuilt the badge as plain HTML I fully control, and made the popup's visibility depend only on our own CSS class rather than Gradio's own show/hide — removing the guesswork instead of trying to out-guess it.
