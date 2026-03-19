# Formula Chat — API Build Progress

## Status: Initial version complete

---

## Completed

### Phase 1 — FastAPI + OpenAI Agents SDK (initial version)

| Item | Status | Notes |
|---|---|---|
| Project structure | ✅ Done | `api/app/{routers,tools,models}/` |
| `requirements.txt` | ✅ Done | All dependencies pinned |
| `.env.example` | ✅ Done | All env vars documented |
| `app/config.py` | ✅ Done | pydantic-settings, typed settings |
| `app/models/schemas.py` | ✅ Done | `ChatRequest`, `ChatResponse`, `StreamChunk`, `HealthResponse` |
| `app/tools/sql_query.py` | ✅ Done | sqlglot validation, asyncpg, 5s timeout |
| `app/tools/session_data.py` | ✅ Done | FastF1 integration, thread executor |
| `app/tools/f1_knowledge.py` | ✅ Done | pgvector RAG, OpenAI embeddings |
| `app/agent.py` | ✅ Done | OpenAI Agents SDK, system prompt with full DB schema, 3 tools |
| `app/routers/chat.py` | ✅ Done | `POST /api/v1/chat` + `POST /api/v1/chat/stream` (SSE) |
| `app/routers/health.py` | ✅ Done | `GET /health` — checks Postgres, FastF1 cache |
| `app/main.py` | ✅ Done | FastAPI app, CORS, rate limiting, lifespan |
| `Dockerfile` | ✅ Done | Python 3.12-slim, health check |
| `docker-compose.yml` | ✅ Done | API + Postgres (pgvector/pgvector:pg16) |

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Component health check |
| `POST` | `/api/v1/chat` | Single-turn, blocking response |
| `POST` | `/api/v1/chat/stream` | Streaming response (SSE) |

---

## Agent Architecture

- **Model:** `gpt-4o` (configurable via `OPENAI_MODEL`)
- **Framework:** OpenAI Agents SDK (`openai-agents`)
- **Tools registered:**
  - `sql_query` — SELECT queries against Ergast PostgreSQL database
  - `session_data` — FastF1 lap times, tyre strategy, telemetry
  - `f1_knowledge` — pgvector semantic search (RAG)
- **System prompt:** includes full Ergast DB schema so agent writes its own SQL

---

## Remaining Phases

### Phase 2 — Database & Data

- [x] PostgreSQL schema creation (`scripts/db/schema.sql`)
- [x] Index definitions (`scripts/db/indexes.sql`)
- [x] Read-only user setup (`scripts/db/users.sql`)
- [x] Full historical import script (`scripts/build_db.py` — Jolpica API)
- [x] Post-race sync script (`scripts/sync_current.py`)

### Phase 3 — RAG Ingestion

- [x] Playwright scraper — Wikipedia, FIA, HTML, PDF (`scripts/ingest/scraper.py`)
- [x] Text chunker — ~400 tokens, 50-token overlap (`scripts/ingest/chunker.py`)
- [x] Embedder — OpenAI text-embedding-3-small, batched (`scripts/ingest/embedder.py`)
- [x] Loader — idempotent pgvector upsert (`scripts/ingest/loader.py`)
- [x] Source seed list — 44 URLs across drivers/teams/circuits/regulations (`scripts/ingest/sources.json`)
- [x] Pipeline CLI — scrape → chunk → embed → load (`scripts/ingest/run_ingest.py`)

### Phase 4 — FastF1 Cache

- [x] Cache pre-warm script — R+Q sessions, `telemetry=False` (`scripts/warm_fastf1_cache.py`)

### Phase 5 — Security Hardening

- [ ] Validate rate limiting under load
- [ ] Nginx config (reverse proxy, TLS termination)
- [ ] HSTS + security headers
- [ ] Fail2ban rules

### Phase 6 — Deployment

- [ ] VPS provisioning (Ubuntu 24, Docker, UFW)
- [ ] Docker Compose production deployment
- [ ] Let's Encrypt TLS
- [ ] Uptime + error monitoring

### Phase 7 — Frontend Integration

- [x] Wire React frontend to `/api/v1/chat/stream`
- [x] Streaming SSE client (ReadableStream reader in `useChat`)
- [x] Multi-turn conversation state (`conversationId` tracked across turns)

---

## Notes

- SQL validation uses `sqlglot` — only `SELECT` is permitted, multi-statement queries rejected
- FastF1 loads run in a thread executor to avoid blocking the async event loop
- `docker-compose.yml` uses `pgvector/pgvector:pg16` image for built-in pgvector support
- Docs available at `/docs` and `/redoc` in non-production environments
