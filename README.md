# Formula Chat

## Description

An AI-powered Formula One chatbot that can answer questions about the sport's history, regulations, and session data. The system uses an agentic architecture built on the OpenAI Agents SDK, with tools for structured data querying, session telemetry retrieval, and a pgvector-based RAG pipeline for unstructured knowledge search.

![Formula Chat home screen](resources/home.png)

## Project Vision

The end goal is an AI-powered Formula One chatbot capable of answering the full spectrum of F1 questions — from all-time championship records and career statistics, to session-specific telemetry from a particular qualifying lap, to rich narrative questions about team history or regulation changes. The system will use an agentic architecture that autonomously decides how to retrieve and combine data from multiple sources, rather than relying on hand-crafted logic for each question type.

The agent will eventually have access to three distinct tools:

- A **structured data tool** for querying historical race results, standings, and statistics (not yet implemented in the MVP)
- A **session data tool** for telemetry, lap times, and tyre strategy from specific race weekends (not yet implemented in the MVP)
- A **knowledge search tool** for driver profiles, team history, regulations, and race narratives

This design means the agent can handle questions that require combining statistics with context — answering not just "who won" but "why it mattered."

---

## MVP Scope

For this initial release, I have implemented the **RAG (Retrieval-Augmented Generation) pipeline and knowledge search** — the third tool described above. This gives the chatbot a strong foundation for answering narrative and contextual F1 questions right away, while the remaining tools are built out incrementally in future iterations.

---

## What's Included

### Knowledge Base & RAG Pipeline

An offline ingestion pipeline scrapes and indexes F1 content from multiple sources into a pgvector database. The pipeline runs in four stages:

1. **Scrape** — Playwright-based scraper extracts clean text from Wikipedia articles, FIA regulation PDFs, and HTML news pages. Boilerplate (navigation bars, infoboxes, references) is stripped before storage. (list of sources defined in the `scripts/ingest/sources.json` file)
2. **Chunk** — Content is split into overlapping ~400-token chunks using tiktoken, respecting paragraph and sentence boundaries to preserve semantic coherence.
3. **Embed** — Each chunk is embedded using OpenAI's `text-embedding-3-small` model, processed in batches of 100 with exponential backoff retry logic.
4. **Load** — Embeddings are upserted into PostgreSQL with the pgvector extension. Idempotent logic (source + content hash) means re-running the pipeline replaces stale chunks without creating duplicates.

The knowledge base currently covers 40+ sources across four categories: driver profiles, team histories, circuit guides, and FIA regulations. Each source is tagged with a refresh cadence (quarterly for historical material, monthly for regulations), which can be used to filter a targeted re-ingest run rather than re-processing all sources at once. Refresh runs are triggered manually at this stage — automation will be added in a future iteration.

### Agent & API

A FastAPI backend hosts the agent built on the OpenAI Agents SDK. The agent has a single tool available at this stage — `f1_knowledge` — which performs a cosine similarity search over the pgvector store and returns the most relevant chunks to inform the response.

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
DATABASE_URL=postgresql://f1_user:your_password@postgres:5432/f1
POSTGRES_PASSWORD=your_password
```

The `DATABASE_URL` should use the Docker Compose service name as the host when running inside the stack:

```env
DATABASE_URL=postgresql://f1_user:your_password@postgres:5432/f1
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

Then apply the vector index for the knowledge base (skip the other indexes for now — they belong to tables added in future iterations):

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

### 4. Run the ingest pipeline

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

### 5. Verify the API

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

### 6. Start the frontend

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

The agentic architecture is already designed to support additional tools. Future iterations will introduce:

- **Structured historical data** — race results, championship standings, driver and constructor statistics spanning the full history of the sport
- **Session telemetry** — lap times, tyre strategy, sector splits, and weather data from specific race weekends

Both of these will be added as additional tools that the agent can invoke alongside the existing RAG search, enabling it to answer the full range of questions the project ultimately targets.

---

## 📝 License

This project is licensed under the MIT License.

---

## ⚠️ Disclaimer

No copyright infringement intended. Formula 1 and related trademarks are the property of their respective owners. All data used is sourced from publicly available APIs and is used for educational and non-commercial purposes only.

---

Built with ❤️ by [Tom Shaw](https://tomshaw.dev)