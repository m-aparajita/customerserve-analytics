# CustomerServe Analytics Agent

Natural-language analytics agent for retail order data. Users ask questions in plain English; the agent writes SQL, queries DuckDB, and renders Plotly charts in a Gradio UI.

**Two live environments:** `hf` = interview Space (stable), `hf-dev` = dev Space (experimental). Active branch: `dev`. Promote to `main` only when ready.

---

## Stack

| Layer | File(s) | Notes |
|-------|---------|-------|
| UI | `app.py` | Gradio, single process, built-in auth, chart PNG download (kaleido) |
| Agent | `agent/gemini_agent.py` | Groq + llama-4-scout, OpenAI-compatible tool loop |
| Prompt | `agent/system_prompt.py` | Role-scoped, no schema embedded (model calls get_schema) |
| Tools | `mcp/tools.py` | `get_schema`, `query_database`, `get_sample_data`, `build_chart` |
| DB | `database/` | In-process DuckDB; CSVs downloaded from HF Dataset on first run |
| Auth | `auth/` | ADMIN / ANALYST / VIEWER roles from env vars |
| Guardrails | `guardrails/` | Layer 1 input, Layer 2 prompt, Layer 3 SQL |

---

## Key decisions (do not reverse)

- **LLM:** `meta-llama/llama-4-scout-17b-16e-instruct` via Groq (free tier). Env var: `GROQ_API_KEY`.
- **Tool schema:** OpenAI format. Do not add `"required": []` to tools with no required params — omit the key entirely.
- **System prompt:** Keep short. Do not embed schema JSON — the model calls `get_schema` tool instead.
- **Single process:** Everything runs through Gradio. `api/main.py` exists but is not wired in.
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
# Copy .env.example → .env, fill in GROQ_API_KEY + passwords
python app.py
```

## Deploy

| Target | Command | When |
|--------|---------|------|
| Dev Space (test) | `git push origin dev && git push hf-dev dev:main` | After any `dev` commit |
| Interview Space (stable) | `git checkout main && git merge dev && git push origin main && git push hf main` | Only when fully satisfied |

HF Spaces secrets (both Spaces): `GROQ_API_KEY`, `ADMIN_PASSWORD`, `ANALYST_PASSWORD`, `VIEWER_PASSWORD`.

Rollback: `git checkout v1.0` restores the last known-good interview version.
