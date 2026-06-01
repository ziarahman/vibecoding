# IPO Signal Intelligence

A production-grade, open-source platform that continuously monitors the internet
for **IPO financial signals**, runs them through a **multi-agent AI verification
pipeline**, and separates **verified facts** from **speculative noise** and
**contradicted/false** claims — surfaced on a sleek, dark-mode-first financial
dashboard.

> Bloomberg-style density meets Vercel-style polish, built on a fully decoupled
> FastAPI + Next.js architecture.

---

## ✨ What it does

```
        ┌─────────────┐   ┌─────────────┐   ┌──────────────┐   ┌──────────────┐
  RSS / │  DISCOVERY  │──▶│ EXTRACTION  │──▶│ VERIFICATION │──▶│ ADJUDICATION │
  Web / │  (scrape)   │   │  (Pydantic) │   │ (SEC EDGAR + │   │ (adversarial │
  EDGAR └─────────────┘   └─────────────┘   │  consensus)  │   │  truth judge)│
                                            └──────────────┘   └──────────────┘
                                                                       │
                                            SQLite/Postgres  ◀─────────┘
                                                   │
                                            FastAPI REST API
                                                   │
                                          Next.js dashboard (this repo)
```

Each discovered signal is adjudicated into one of:

| Status         | Meaning                                              | Badge |
|----------------|------------------------------------------------------|-------|
| `VERIFIED`     | Corroborated by a primary source (e.g. SEC filing)   | 🟢 green |
| `SPECULATIVE`  | Plausible but unconfirmed rumor / single source      | 🟡 amber |
| `CONTRADICTED` | Disproven or officially denied                       | 🔴 red |

---

## 🧱 Architecture

| Layer       | Stack                                                                 |
|-------------|-----------------------------------------------------------------------|
| **Backend** | Python 3.11+, FastAPI, **LangGraph** 4-node `StateGraph`, SQLAlchemy  |
| **AI**      | Pluggable LLM: local **Ollama** or cloud **OpenAI / Anthropic**       |
| **Storage** | SQLite by default, drop-in **PostgreSQL** via `DATABASE_URL`          |
| **Frontend**| Next.js 14 (App Router), TypeScript, Tailwind, Shadcn-style UI, Lucide |

> **Zero-credential demo:** with no API keys configured, the pipeline runs in
> deterministic heuristic mode against a built-in seed of realistic documents,
> so the full stack works end-to-end out of the box.

---

## 🚀 Quick start

### 1. Backend (FastAPI)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # optional — sane defaults
uvicorn main:app --reload --port 8000
```

The API is now live at <http://localhost:8000> (docs at `/docs`).

Trigger the first scan to populate the database:

```bash
curl -X POST "http://localhost:8000/api/signals/scan"
```

### 2. Frontend (Next.js)

```bash
cd frontend
npm install
cp .env.local.example .env.local                       # optional
npm run dev
```

Open <http://localhost:3000>. The dev server proxies `/api/*` to the backend,
so no CORS configuration is needed locally. Hit **Run Scan** in the header.

---

## 🔌 Switching LLM providers

All provider selection is environment-driven (`backend/.env`):

```bash
# Local (default)
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.1

# OpenAI
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

# Anthropic
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-6
```

Optional discovery enrichment:

```bash
TAVILY_API_KEY=tvly-...   # enables live web discovery + consensus search
```

---

## 📡 API reference

| Method | Path                      | Description                                              |
|--------|---------------------------|----------------------------------------------------------|
| `GET`  | `/api/health`             | Liveness + active LLM provider                            |
| `GET`  | `/api/stats`              | Aggregate counts for the stat cards                      |
| `GET`  | `/api/signals`            | List signals — `status`, `category`, `search`, `sort_by`, `sort_dir`, `page`, `page_size` |
| `GET`  | `/api/signals/{id}`       | Single hydrated signal                                   |
| `POST` | `/api/signals/scan`       | Run the pipeline. `?background=true` for a worker thread |

---

## 🗂️ Project layout

```
backend/
  schemas.py     # Pydantic contracts (ExtractedClaim, AdjudicationResult, …)
  agents.py      # 4-node LangGraph pipeline + prompts + heuristic fallbacks
  database.py    # SQLAlchemy ORM (Signal table, JSON evidence column)
  llm.py         # Provider-agnostic LLM factory (Ollama/OpenAI/Anthropic)
  config.py      # Env-driven settings
  main.py        # FastAPI app: routing, DB init, CORS

frontend/
  app/                          # Next.js App Router (layout, page, globals)
  components/
    dashboard.tsx               # Stat cards + enterprise data table
    signal-detail-sheet.tsx     # Drill-down Sheet (Overview / Audit / Judgment)
    veracity.tsx                # Shared veracity badge + metadata
    ui/                         # Shadcn-style Tailwind primitives
  lib/                          # api client, types, formatting utils
```

---

## 🧪 Design highlights

- **Strict structured output** — every LLM node is bound to a Pydantic schema
  (`with_structured_output`), so malformed completions fail fast instead of
  corrupting the store.
- **Graceful degradation** — missing keys/network never crash the pipeline;
  deterministic heuristics keep it runnable.
- **Server + client filtering** — veracity filter & date sort are server-side;
  global fuzzy search is client-side for instant feedback.
- **Explicit UX states** — loading skeletons, empty states, and error retry are
  all first-class.

## 📄 License

MIT — see [`LICENSE`](LICENSE).
