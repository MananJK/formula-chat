# Formula Chat

## Description

An AI-powered Formula One chatbot that can answer questions about the sport's history, regulations, and session data. The system uses an agentic architecture built on the OpenAI Agents SDK, with tools for structured data querying, session telemetry retrieval, and a pgvector-based RAG pipeline for unstructured knowledge search.

![Formula Chat home screen](resources/home.png)

## Project Vision

The end goal is an AI-powered Formula One chatbot capable of answering the full spectrum of F1 questions — from all-time championship records and career statistics, to session-specific telemetry from a particular qualifying lap, to rich narrative questions about team history or regulation changes. The system will use an agentic architecture that autonomously decides how to retrieve and combine data from multiple sources, rather than relying on hand-crafted logic for each question type.

The agent will eventually have access to three distinct tools:

- A **structured data tool** for querying historical race results, standings, and statistics
- A **session data tool** for telemetry, lap times, and tyre strategy from specific race weekends (not yet implemented)
- A **knowledge search tool** for driver profiles, team history, regulations, and race narratives

This design means the agent can handle questions that require combining statistics with context — answering not just "who won" but "why it mattered."

---

## What's Implemented

The current release includes two of the three tools described above:

- **Structured data tool (`sql_query`)** — the agent queries a PostgreSQL database populated with F1 data from 2018 through the current season, imported via FastF1. It can answer questions about race results, championship standings, qualifying times, pit stops, lap data, and driver/constructor statistics.
- **Knowledge search tool (`f1_knowledge`)** — semantic search over a curated pgvector knowledge base covering driver profiles, team histories, circuit guides, and FIA regulations.

---

## What's Included

### Knowledge Base & RAG Pipeline

An offline ingestion pipeline scrapes and indexes F1 content from multiple sources into a pgvector database. The pipeline runs in four stages:

1. **Scrape** — Playwright-based scraper extracts clean text from Wikipedia articles, FIA regulation PDFs, and HTML news pages. Boilerplate (navigation bars, infoboxes, references) is stripped before storage. (list of sources defined in the `scripts/ingest/sources.json` file)
2. **Chunk** — Content is split into overlapping ~400-token chunks using tiktoken, respecting paragraph and sentence boundaries to preserve semantic coherence.
3. **Embed** — Each chunk is embedded using OpenAI's `text-embedding-3-small` model, processed in batches of 100 with exponential backoff retry logic.
4. **Load** — Embeddings are upserted into PostgreSQL with the pgvector extension. Idempotent logic (source + content hash) means re-running the pipeline replaces stale chunks without creating duplicates.

The knowledge base currently covers 40+ sources across four categories: driver profiles, team histories, circuit guides, and FIA regulations. Each source is tagged with a refresh cadence (quarterly for historical material, monthly for regulations), which can be used to filter a targeted re-ingest run rather than re-processing all sources at once. Refresh runs are triggered manually at this stage — automation will be added in a future iteration.

### Structured Data Tool (`sql_query`)

The agent can query a PostgreSQL database containing F1 race data from 2018 through the current season, imported via [FastF1](https://docs.fastf1.dev/). The database schema covers:

- **Race results** — finishing positions, points, fastest laps, and status
- **Qualifying** — Q1/Q2/Q3 times and grid positions
- **Championship standings** — cumulative driver and constructor standings after each round
- **Lap times & pit stops** — per-lap positions and pit stop durations
- **Reference data** — drivers, constructors, circuits, and seasons

The agent writes its own SQL queries at runtime based on the schema provided in its system prompt. All queries are validated (SELECT-only, parsed with `sqlglot`) and executed with a timeout against a read-only database user.

### Agent & API

A FastAPI backend hosts the agent built on the OpenAI Agents SDK. The agent has two tools available — `sql_query` for structured race data and `f1_knowledge` for semantic search — and autonomously decides which tool (or combination of tools) to use for each question.

The API exposes two endpoints:

- `POST /api/v1/chat` — standard request/response
- `POST /api/v1/chat/stream` — Server-Sent Events for real-time token-by-token streaming

Rate limiting and CORS are applied at the middleware layer. The database runs with a read-only user. All secrets are managed via environment variables.

> NOTE: This MVP does not include authentication or authorization yet. Do not deploy it publicly until access controls are in place (for example: API keys or OAuth), along with HTTPS and abuse protections.

### Frontend

A React + TypeScript chat interface (Vite + Tailwind CSS) connects to the streaming endpoint. It displays messages in real time, shows a typing indicator while the agent is working, surfaces which tool is being invoked, and includes a welcome screen with suggested questions to help users get started.

### Infrastructure

The API and PostgreSQL (pgvector) are containerised with Docker Compose, with healthchecks on each service.

---

## Tech Stack (MVP)

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| Agent framework | OpenAI Agents SDK |
| Backend | FastAPI |
| Database | PostgreSQL + pgvector |
| Web scraping | Playwright |
| PDF parsing | pdfplumber |
| Tokenisation | tiktoken |
| Deployment | Docker Compose |
| Frontend | React + TypeScript + Tailwind CSS |

---

## Getting Started

### Prerequisites

- [Docker](https://www.docker.com/) and Docker Compose
- [Python 3.12](https://www.python.org/) (for the ingest pipeline)
- [Node.js](https://nodejs.org/) 18+ (for the frontend)
- An [OpenAI API key](https://platform.openai.com/)

---

### 1. Configure the API

Copy the example environment file and fill in your values:

```bash
cd api
cp .env.example .env
```

At minimum, set:

```env
OPENAI_API_KEY=sk-...
DATABASE_URL=postgresql://f1_user:your_password@postgres:5433/f1
POSTGRES_PASSWORD=your_password
```

The `DATABASE_URL` should use the Docker Compose service name as the host when running inside the stack:

```env
DATABASE_URL=postgresql://f1_user:your_password@postgres:5433/f1
```

---

### 2. Start the stack

```bash
cd api
docker compose up --build
```

This starts the API (port `8000`) and PostgreSQL with the pgvector extension. Both services must pass their healthchecks before the API accepts traffic.

---

### 3. Initialise the database

With the Postgres container running, apply the schema and create the database users (run from the `api/` directory):

```bash
docker compose exec -T postgres psql -U f1_user -d f1 -f /dev/stdin < ../scripts/db/schema.sql
docker compose exec -T postgres psql -U f1_user -d f1 -f /dev/stdin < ../scripts/db/users.sql
```

Then apply the vector index for the knowledge base (skip the other indexes for now — they will be applied after the F1 data import in the next step):

```bash
docker compose exec postgres psql -U f1_user -d f1 -c "
CREATE INDEX IF NOT EXISTS idx_knowledge_embedding
    ON f1_knowledge USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
CREATE INDEX IF NOT EXISTS idx_knowledge_category ON f1_knowledge(category);
CREATE INDEX IF NOT EXISTS idx_knowledge_source ON f1_knowledge(source);
"
```

---

### 4. Import the F1 structured data

The `build_db.py` script downloads F1 race and qualifying session data via [FastF1](https://docs.fastf1.dev/) and imports it into PostgreSQL. It covers 2018 through the current season and is safe to re-run (all inserts are idempotent).

Make sure the scripts virtual environment is set up first (see step 5 below for full setup), then run from the repo root:

```bash
cd scripts
source venv/bin/activate
```

```
# Apply the structured data indexes
docker compose exec -T postgres psql -U f1_user -d f1 -f /dev/stdin < ../scripts/db/indexes.sql

# Import all seasons from 2021 to current year (default)
python build_db.py

# Import a single season
python build_db.py --season 2024

# Import a specific range of seasons
python build_db.py --from-season 2022 --to-season 2024
```

> **Rate limits:** FastF1 fetches data from the official F1 timing API, and you will very likely hit rate limits during a full import. The script uses exponential backoff and will retry automatically, but if it fails persistently, it will print the exact command to resume from where it left off — for example:
>
> ```
> python build_db.py --from-season 2023 --from-round 5
> ```
>
> Use `--from-season` (and optionally `--from-round`) to continue the import without re-processing seasons you've already completed. Setting a longer `ROUND_DELAY` (seconds between rounds) in your `.env` can also reduce the likelihood of hitting rate limits:
>
> ```env
> ROUND_DELAY=30
> SESSION_DELAY=10
> ```

---

### 5. Run the ingest pipeline

The ingest pipeline runs locally and writes to the Dockerised Postgres instance. Install dependencies and run:

```bash
cd scripts
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# Copy the example environment file and set your OpenAI API key and database URL
cp .env.example .env

#Update the DATABASE_URL in .env to point to the Dockerised Postgres instance:

OPENAI_API_KEY=sk-...
DATABASE_URL=postgresql://f1_user:your_password@localhost:5433/f1

# Ingest all sources
python ingest/run_ingest.py

# Or ingest a single category
python ingest/run_ingest.py --category driver
python ingest/run_ingest.py --category regulation

# Dry run — scrape and chunk only, no DB writes
python ingest/run_ingest.py --dry-run
```

> This will scrape 40+ sources, generate embeddings via the OpenAI API, and load them into pgvector. Expect it to take several minutes and incur a small API cost.

---

### 6. Verify the API

```bash
curl http://localhost:8000/health
```

Then send a test message:

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Who is Lewis Hamilton?", "history": []}'
```

---

### 7. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

The chat interface will be available at `http://localhost:5173`.

---

### Refreshing the knowledge base

Each source in `sources.json` is tagged with a refresh cadence. To re-ingest only sources due for an update, use the `--refresh` flag:

```bash
python ingest/run_ingest.py --refresh monthly     # regulations
python ingest/run_ingest.py --refresh quarterly   # driver/team/circuit articles
```

The pipeline is idempotent — re-running it will replace stale chunks without creating duplicates.

You can add additional source URLs to `sources.json` as needed, following the existing structure. New sources will be picked up on the next ingest run. Make sure to include the object inside of the array.

```bash
{
  "url": "https://en.wikipedia.org/wiki/New_F1_Source",
  "category": "driver",
  "title": "New F1 Source",
  "refresh": "quarterly"
}
```

---

## What's Coming Next

The agentic architecture is designed to support additional tools. The structured data tool and knowledge search tool are now live. The remaining tool to be added is:

- **Session telemetry** — lap times, tyre strategy, sector splits, and weather data from specific race weekends

This will be added as a third tool that the agent can invoke alongside the existing tools, enabling it to answer the full range of questions the project ultimately targets.

---

## 📝 License

This project is licensed under the MIT License.

---

## ⚠️ Disclaimer

No copyright infringement intended. Formula 1 and related trademarks are the property of their respective owners. All data used is sourced from publicly available APIs and is used for educational and non-commercial purposes only.

---

Built with ❤️ by [Tom Shaw](https://tomshaw.dev)