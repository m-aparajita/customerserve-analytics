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
│                    │  query_database    │     llama-4-scout    │
│                    └─────────┬──────────┘                      │
│                         rows │                                  │
│                    ┌─────────▼──────────┐                      │
│                    │   ChartAgent       │                      │
│                    │  build_chart +     │◀──▶ Groq API         │
│                    │  key insights      │     llama-4-scout    │
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
│                     database/scheduler   │
│                     Resend API (v1.x)    │
│                     scheduled_reports    │
│                     table in DuckDB      │
├──────────────────────────────────────────┤
│  DATA               DuckDB (in-process)  │
│                     CSV → HF Dataset     │
│                     query_logs table     │
│                     scheduled_reports    │
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
 │         │       │        │  messages ──────────▶│         │        │         │
 │         │       │        │           │◀─tool: get_schema  │        │         │
 │         │       │        │           │─────────────────────▶       │         │
 │         │       │        │           │◀──────── schema ────│        │         │
 │         │       │        │  ROUND 2  │          │         │        │         │
 │         │       │        │  (schema)───────────▶│         │        │         │
 │         │       │        │           │◀─tool: query_db    │        │         │
 │         │       │        │  L3 check │          │         │        │         │
 │         │       │        │  PASS     │──────────────────────▶      │         │
 │         │       │        │           │◀────────── rows ────│        │         │
 │         │       │        │  ROUND 3  │          │         │        │         │
 │         │       │        │  (rows) ──────────── ▶│         │        │         │
 │         │       │        │           │◀─ text answer       │        │         │
 │         │       │        │           │          │         │        │         │
 │         │  ── rows passed to ChartAgent ──────────────────────────▶│         │
 │         │       │        │           │          │         │  ROUND 1          │
 │         │       │        │           │          │         │  (rows+question)──▶
 │         │       │        │           │          │         │        │◀─tool: build_chart
 │         │       │        │           │          │         │        │ render Plotly fig
 │         │       │        │           │          │         │  ROUND 2          │
 │         │       │        │           │          │         │  (chart done)─────▶
 │         │       │        │           │          │         │        │◀─insights text
 │         │       │        │           │          │         │        │         │
 │◀─ text + chart + insights ─────────────────────────────────────────│         │
```

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

| Role | Free-form Query | Raw Row Access | Row Limit | Allowed Charts | Schema Accordion | Can Query query_logs |
|------|:--------------:|:--------------:|:---------:|:--------------:|:----------------:|:--------------------:|
| ADMIN | ✅ | ✅ | 10,000 | All | ✅ | ✅ |
| ANALYST | ✅ | ❌ (aggregates only) | 1,000 | All | ✅ | ❌ |
| VIEWER | ❌ (templates only) | ❌ | 100 | Limited | ❌ | ❌ |

Credentials loaded from environment variables at startup — never hardcoded.

---

## 7. Multi-Agent Design

The system uses two specialised agents that run sequentially per user turn.

### QueryAgent (`agent/gemini_agent.py`)
Owns data retrieval. Runs a tool loop (max 8 rounds):

```
Round 1:  LLM receives user question → calls get_schema()   ← cache hit (pre-warmed at startup)
Round 2:  LLM receives schema        → calls query_database(sql)
Round 3:  LLM receives rows          → writes text answer
          Loop exits → returns (text, rows)
```

**Why get_schema first:** The model cannot write correct SQL without knowing column names. This eliminates hallucinated columns — a common failure mode in text-to-SQL systems.

**Schema caching:** `get_schema()` queries DuckDB once at startup and stores the result in `_schema_cache`. Every subsequent call returns instantly with no DB round-trip.

### ChartAgent (`agent/chart_agent.py`)
Owns visualisation and insight. Runs only when QueryAgent returns rows. Tool loop (max 3 rounds):

```
Round 1:  Receives rows + user question → decides chart type → calls build_chart()
Round 2:  Receives chart confirmation   → writes 1–2 insight bullets
          Loop exits → returns (chart_json, insights)
```

ChartAgent prompt rules for chart selection:
- **line** — time-series or sequential data
- **bar** — categorical comparisons
- **pie** — part-of-whole with ≤ 6 categories
- **scatter** — correlation between two numeric columns
- **histogram** — distribution of a single numeric column

**Key implementation detail — `data` not in tool schema:** The ChartAgent's `build_chart` schema deliberately omits the `data` parameter. The agent injects `fn_args["data"] = rows` before calling dispatch. This avoids a Groq validation error where the LLM would JSON-stringify the array into a string, which fails schema validation (`expected array, got string`). The LLM only specifies `chart_type`, `x_col`, `y_col`, and `title`.

### Why separate agents?
| Concern | QueryAgent | ChartAgent |
|---------|-----------|------------|
| Tools | get_schema, query_database, get_sample_data | build_chart only |
| Skill | SQL reasoning, schema navigation | Visual storytelling, pattern recognition |
| Rounds | Up to 8 | Up to 3 |
| Failure mode | Bad SQL → guardrail catches it | Bad chart choice → benign, still shows something |

Each agent can be tuned, swapped, or scaled independently. In production, ChartAgent could use a smaller/cheaper model since chart selection is a simpler task than SQL generation.

The tool loop uses the **OpenAI function-calling format** (Groq is OpenAI-compatible), making both agents portable to GPT-4o, Claude, or any other OpenAI-compatible provider with zero code changes.

---

## 8. Technology Decisions

### LLM — Groq + llama-4-scout-17b

| Option considered | Decision |
|------------------|----------|
| OpenAI GPT-4o | ❌ Paid API, cost unpredictable at scale |
| Anthropic Claude | ❌ No free tier for production |
| Groq + llama-4-scout | ✅ Free tier, ~300 tokens/sec, tool-use capable, OpenAI-compatible |

**Key point:** Groq's inference speed (~10× faster than typical cloud APIs) matters here because the agent makes 3–4 LLM calls per user question. Slow inference would make the UX feel broken.

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

## 9. Database Tables

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

## 10. Data Flow — Startup

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

## 11. Deployment Architecture

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

## 12. What Is Out of Scope

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

## 13. Known Limitations & Critical Missing Items

These are gaps you should be ready to discuss in interviews:

| Gap | Impact | Production fix |
|-----|--------|---------------|
| **Basic auth (Gradio built-in)** | Passwords sent over HTTP if not behind HTTPS; no token expiry | Replace with OAuth2 / JWT; Gradio's HTTPS on HF mitigates this partially |
| **No response streaming** | User waits 10–20 seconds with no feedback while agent runs all rounds | Implement `yield`-based streaming in the agent loop |
| **No rate limiting** | A single user can flood the Groq API or exhaust free-tier quota | Add per-user request throttling (e.g. Redis + token bucket) |
| **No test suite** | Regressions in SQL guardrails or tool dispatch go undetected | Add pytest suite covering guardrail edge cases and tool dispatcher |
| **Static dataset** | Insights are not from live business data | Add a data ingestion pipeline (e.g. nightly CSV refresh from an S3 bucket) |
| **Single-process / single-instance** | Cannot scale horizontally; one crash kills all users | Move to a queue-backed architecture (Celery + Redis) for the agent |
| **No observability** | query_logs table exists but no dashboards or alerts | Add Grafana or a lightweight monitoring layer on top of query_logs |
| **LLM hallucination on SQL** | The model occasionally generates wrong column names or logic | Add a SQL validation step that runs EXPLAIN before execution |
| **Groq free-tier limits** | Rate limits and monthly token caps can break the app silently | Add fallback error messaging and consider a paid tier for demos |
| **No prompt versioning** | System prompt changes are not tracked or A/B tested | Store prompt versions in code and log which version was used per query |

---

## 14. Interview Talking Points

**"Walk me through your architecture."**
> Single-process Python app with a two-agent pipeline. Gradio handles UI and auth. A QueryAgent talks to Groq to write SQL and retrieve data. The rows are then handed off to a ChartAgent, which independently decides the best visualisation and surfaces 1–2 key insights — trends, anomalies, standout figures. Everything runs in one Docker container on HuggingFace Spaces free tier.

**"Why two agents instead of one?"**
> QueryAgent and ChartAgent have genuinely different skills. QueryAgent needs to reason about schema, write correct SQL, and understand business intent. ChartAgent needs to understand visual storytelling — which chart type fits the data shape, and what pattern is worth surfacing. Separating them means each has a focused system prompt, a minimal tool set, and can be tuned or swapped independently. In production, ChartAgent could run on a smaller, cheaper model since chart selection is a simpler task than SQL generation.

**"Why DuckDB instead of PostgreSQL?"**
> DuckDB is an in-process analytical database — it runs inside the Python process with no server, no network, and no configuration. For read-heavy analytics workloads (GROUP BY, SUM, window functions), it outperforms SQLite significantly. It was the right choice for a single-container deployment where I couldn't run a separate database server.

**"How does the agent know what SQL to write?"**
> It doesn't hardcode any schema knowledge. Round 1 of the QueryAgent loop always calls `get_schema()` to discover the current tables and column names. This eliminates hallucinated column names and makes the system schema-agnostic — you can swap in a different database and it still works. The schema is pre-warmed into a module-level cache at startup, so the `get_schema` call is instant. The same cache powers the Schema Reference accordion in the UI for ADMIN and ANALYST users.

**"How do you prevent SQL injection or data leaks?"**
> Three layers. Layer 1 filters the raw user input for prompt injection patterns. Layer 2 is the role-scoped system prompt — the model is instructed what it can and cannot do. Layer 3 validates the generated SQL before execution: only SELECT is allowed, dangerous clauses are stripped, and row limits are enforced per role. Even if the LLM were somehow manipulated, it cannot write a DELETE or expose another user's data.

**"What would you do differently in production?"**
> Three things immediately: streaming responses (users shouldn't wait 15 seconds), a proper auth layer with JWT instead of Gradio's basic auth, and rate limiting per user so the Groq free tier isn't exhausted. After that, a test suite for the guardrails — those are security-critical and currently untested.

**"How does the report scheduling work?"**
> After any chart is rendered, a schedule panel appears. Users can send the report immediately or set up weekly, bi-weekly, or monthly recurring deliveries with a start/end date. Schedules are stored in a `scheduled_reports` DuckDB table. On each page load, a background thread checks for overdue schedules and re-runs the original query to generate fresh data before emailing the chart via Resend. It's best-effort on HuggingFace free tier — it fires when the app is active — which is appropriate for a portfolio demo but would need a dedicated scheduler in production.

**"Why two HuggingFace Spaces?"**
> Staging vs production. The `main` branch deploys to the stable interview Space which I never touch mid-demo. The `dev` branch deploys to a private dev Space where I iterate freely. When a change is validated on dev, I merge to main and promote it. The `v1.0` git tag gives me a rollback point if something goes badly wrong.
