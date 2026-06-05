# CustomerServe Analytics — Architecture & Design Document

> **Purpose:** Interview preparation reference covering system design, technology choices, trade-offs, and known gaps.

---

## 1. What It Does

CustomerServe is a **natural-language analytics agent** for retail order data. A user types a question in plain English; the system automatically writes SQL, queries a database, and renders an interactive chart — no coding required.

**Core user journey:**
> *"Show me monthly revenue for 2024"* → SQL generated → DuckDB queried → Plotly bar chart rendered + text summary

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
│  │   → Query Box → Templates → Chat Response → Chart      │    │
│  │   → Download Chart (PNG via kaleido)                   │    │
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
│                    │  (agentic loop,    │◀──▶ Groq API         │
│                    │   max 8 rounds)    │     llama-4-scout    │
│                    └──┬──────┬──────┬───┘                      │
│                       │      │      │                           │
│              ┌────────▼┐  ┌──▼───┐ ┌▼──────────┐             │
│              │get_schema│  │query_│ │build_chart│             │
│              │          │  │  db  │ │  (Plotly) │             │
│              └──────────┘  └──┬───┘ └───────────┘             │
│                               │                                 │
│                    ┌──────────▼──────────┐                     │
│                    │   SQL Guardrail     │  ← Layer 3          │
│                    │  (SELECT-only,      │                     │
│                    │   row limits, RBAC) │                     │
│                    └──────────┬──────────┘                     │
│                               │                                 │
│                    ┌──────────▼──────────┐                     │
│                    │       DuckDB        │                     │
│                    │  orders / products  │                     │
│                    │  order_items /      │                     │
│                    │  query_logs         │                     │
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
│  AGENT              agent/gemini_agent.py│
│                     OpenAI tool loop     │
│                     System prompt (RBAC) │
├──────────────────────────────────────────┤
│  TOOLS (MCP-style)  get_schema           │
│                     query_database       │
│                     get_sample_data      │
│                     build_chart          │
├──────────────────────────────────────────┤
│  DATA               DuckDB (in-process)  │
│                     CSV → HF Dataset     │
│                     query_logs table     │
└──────────────────────────────────────────┘
```

---

## 4. User Query Flow — Sequence Diagram

```
User     Gradio    Auth     Guardrail    Agent      Groq        DuckDB
 │          │        │          │           │          │            │
 │─ login ─▶│        │          │           │          │            │
 │          │─verify─▶          │           │          │            │
 │◀─ role ──│        │          │           │          │            │
 │          │        │          │           │          │            │
 │─ query ─▶│        │          │           │          │            │
 │          │──── get_role() ──▶│           │          │            │
 │          │        │ L1 check  │           │          │            │
 │          │        │ (topic,   │           │          │            │
 │          │        │  inject.) │           │          │            │
 │          │        │  PASS     │           │          │            │
 │          │        │──────────────────────▶│          │            │
 │          │        │           │  ROUND 1  │          │            │
 │          │        │           │  messages ─────────▶│            │
 │          │        │           │           │◀─ tool_call: get_schema
 │          │        │           │           │──────────────────────▶│
 │          │        │           │           │◀─────── schema ───────│
 │          │        │           │  ROUND 2  │          │            │
 │          │        │           │  (schema) ─────────▶│            │
 │          │        │           │           │◀─ tool_call: query_db │
 │          │        │           │  L3 SQL check        │            │
 │          │        │           │  (SELECT-only,       │            │
 │          │        │           │   row limit RBAC)    │            │
 │          │        │           │           │──────────────────────▶│
 │          │        │           │           │◀──────── rows ────────│
 │          │        │           │  ROUND 3  │          │            │
 │          │        │           │  (rows) ──────────▶  │            │
 │          │        │           │           │◀─ tool_call: build_chart
 │          │        │           │           │ render Plotly fig      │
 │          │        │           │  ROUND 4  │          │            │
 │          │        │           │  (chart done)────── ▶│            │
 │          │        │           │           │◀─ text answer          │
 │          │ (text + chart_json)│           │          │            │
 │◀─ response + chart ──────────────────────────────────            │
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

## 7. Agentic Tool Loop

The agent does not call the LLM once — it runs a **multi-round loop** (max 8 rounds):

```
Round 1:  LLM receives user question → calls get_schema()   ← returns from cache (pre-warmed at startup)
Round 2:  LLM receives schema       → calls query_database(sql)
Round 3:  LLM receives rows         → calls build_chart(data)
Round 4:  LLM receives chart status → writes final text answer
          Loop exits (no tool calls in response)
```

**Why this matters:** The model cannot write correct SQL without knowing the schema first. Forcing `get_schema` as the first tool call eliminates hallucinated column names — a common failure mode in text-to-SQL systems.

**Schema caching:** `get_schema()` queries DuckDB once at startup and stores the result in a module-level variable (`_schema_cache`). Every subsequent call — whether from the agent loop or the UI accordion — returns the cached string instantly, with no DB round-trip. The cache is process-scoped; a Space restart refreshes it automatically.

The tool loop is implemented using the **OpenAI function-calling format** (Groq is OpenAI-compatible), making the agent portable to GPT-4o, Claude, or any other OpenAI-compatible provider with zero code changes.

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

## 9. Data Flow — Startup

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

## 10. Deployment Architecture

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

## 11. What Is Out of Scope

| Feature | Why excluded |
|---------|-------------|
| Real-time / live data | Uses a static retail dataset; no database write path |
| Scheduled email reports | Designed in Lovable prototype; not wired into this system |
| Data export (CSV / PDF) | Chart PNG download is implemented; CSV/PDF export is not |
| Conversation persistence | Chat history resets on page refresh (Gradio session-scoped) |
| Multi-language support | English only |
| Mobile-optimised UI | Gradio is desktop-first |
| User self-registration | Credentials are env-var configured; no user management UI |
| Fine-tuned model | Uses a general-purpose instruction model |

---

## 12. Known Limitations & Critical Missing Items

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

## 13. Interview Talking Points

**"Walk me through your architecture."**
> Single-process Python app: Gradio handles UI and auth, an agentic loop talks to Groq's LLM, tools execute SQL on DuckDB, and results render as Plotly charts. Everything runs in one Docker container on HuggingFace Spaces free tier.

**"Why DuckDB instead of PostgreSQL?"**
> DuckDB is an in-process analytical database — it runs inside the Python process with no server, no network, and no configuration. For read-heavy analytics workloads (GROUP BY, SUM, window functions), it outperforms SQLite significantly. It was the right choice for a single-container deployment where I couldn't run a separate database server.

**"How does the agent know what SQL to write?"**
> It doesn't hardcode any schema knowledge. Round 1 of the tool loop always calls `get_schema()` to discover the current tables and column names. This eliminates hallucinated column names and makes the system schema-agnostic — you can swap in a different database and it still works. The schema is also pre-warmed into a module-level cache at startup, so the agent's `get_schema` call is instant rather than a DB round-trip on every query. The same cache powers the Schema Reference accordion in the UI, which lets ADMIN and ANALYST users browse column names before they write a question.

**"How do you prevent SQL injection or data leaks?"**
> Three layers. Layer 1 filters the raw user input for prompt injection patterns. Layer 2 is the role-scoped system prompt — the model is instructed what it can and cannot do. Layer 3 validates the generated SQL before execution: only SELECT is allowed, dangerous clauses are stripped, and row limits are enforced per role. Even if the LLM were somehow manipulated, it cannot write a DELETE or expose another user's data.

**"What would you do differently in production?"**
> Three things immediately: streaming responses (users shouldn't wait 15 seconds), a proper auth layer with JWT instead of Gradio's basic auth, and rate limiting per user so the Groq free tier isn't exhausted. After that, a test suite for the guardrails — those are security-critical and currently untested.

**"Why two HuggingFace Spaces?"**
> Staging vs production. The `main` branch deploys to the stable interview Space which I never touch mid-demo. The `dev` branch deploys to a private dev Space where I iterate freely. When a change is validated on dev, I merge to main and promote it. The `v1.0` git tag gives me a rollback point if something goes badly wrong.
