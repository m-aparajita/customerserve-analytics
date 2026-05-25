---
title: CustomerServe Analytics Agent
emoji: 📊
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# CustomerServe Analytics Agent

A natural-language data analytics agent for retail order/product data.
Type a question in plain English → the agent writes SQL, queries the database, and renders an interactive chart.

## Architecture

```
User (browser)
  └── Gradio UI  (login, chat panel, Plotly chart panel)
        └── Gemini 2.0 Flash Agent  (function-calling loop)
              ├── MCP Tool: get_schema
              ├── MCP Tool: query_database   ← Layer 3 SQL guardrail
              ├── MCP Tool: get_sample_data
              └── MCP Tool: build_chart
                    └── DuckDB  (orders, order_items, products, query_logs)
```

**Guardrails (3 layers)**
| Layer | Where | What it blocks |
|-------|-------|----------------|
| 1 — Input | Before the LLM | Off-topic queries, injection patterns, prompt hacks |
| 2 — Prompt | System prompt | LLM instructed to refuse non-domain questions and non-SELECT SQL |
| 3 — SQL | Before DuckDB | Non-SELECT statements, unauthorised tables, row-limit enforcement |

**Role-Based Access**
| Role | Free-form queries | Raw rows | Row limit | Logs |
|------|-------------------|----------|-----------|------|
| ADMIN | ✅ | ✅ | 10 000 | ✅ |
| ANALYST | ✅ | ❌ (aggregated only) | 1 000 | ❌ |
| VIEWER | ❌ (templates only) | ❌ | 100 | ❌ |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| LLM | Google Gemini 2.0 Flash (free tier) |
| Agent pattern | MCP-compatible function-calling tools |
| Database | DuckDB (in-process, no server) |
| Backend API | FastAPI |
| UI | Gradio |
| Deployment | HuggingFace Spaces (Docker, free) |

## Local Setup

```bash
# 1. Clone
git clone <repo-url>
cd CustomerServe

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy and fill in your credentials
cp .env.example .env
# Edit .env: add GEMINI_API_KEY and set passwords

# 4. Place CSV files in ./Data/
#    orders.csv, order_items.csv, products.csv

# 5. Run
python app.py
# Open http://localhost:7860
```

## Demo Users

| Username | Password (default) | Role |
|----------|--------------------|------|
| admin    | admin123           | ADMIN |
| alice    | alice123           | ANALYST |
| bob      | bob123             | VIEWER |

> **Change all passwords** via environment variables before deploying publicly.

## Deployment (HuggingFace Spaces)

1. Create a new Space → **Docker** runtime
2. Connect your GitHub repo
3. In Space Settings → **Variables and Secrets**, add:
   - `GEMINI_API_KEY`
   - `ADMIN_PASSWORD`, `ANALYST_PASSWORD`, `VIEWER_PASSWORD`
4. Enable **Persistent Storage** (free, 50 GB) — DuckDB file is stored at `/data/`
5. Push to GitHub → Space auto-deploys

## Sample Questions

- *Show me monthly revenue for 2024*
- *What are the top 10 brands by net sales?*
- *How many orders were cancelled vs delivered?*
- *Show revenue by product category as a pie chart*
- *Which state has the highest average order value?*
- *[Admin] Show me all queries blocked by the guardrail today*
