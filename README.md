# MultiAgent DataSpider

A general-purpose, multi-agent web scraping backend built on FastAPI, Redis Streams, and PostgreSQL. Users create "Missions" via HTTP API; multiple autonomous Worker agents consume tasks through a Redis Streams pipeline, crawl the targets, extract structured data, validate it, and persist results to PostgreSQL. A WebSocket endpoint delivers real-time system telemetry to frontends.

## Architecture

```
HTTP Client
    │
    ▼
┌─────────────┐     ┌──────────────────────────────────────────────────────────┐
│ API Gateway │────▶│  Redis Streams Pipeline                                  │
│  (FastAPI)  │     │  crawl_jobs → raw_data → clean_data → validated_data     │
│  :8080      │     │      │              │            │             │          │
└─────────────┘     │  Crawlers(3)  Processors(2) Validators(2)  Store(1)      │
                    └──────────────────────────────────────────────────────────┘
                              │                                      │
                    ┌─────────────────┐                   ┌──────────────────┐
                    │  Coordinator(1) │                   │   PostgreSQL     │
                    │  (Leader elect) │                   │  missions        │
                    └─────────────────┘                   │  raw_events      │
                                                          │  scraped_data    │
                                                          └──────────────────┘
```

### Services

| Service | Scale | Role |
|---|---|---|
| `api-gateway` | 1 | FastAPI REST + WebSocket |
| `coordinator` | 1 | Leader election, scheduling, completion detection |
| `crawler` | 3 (scalable) | Fetch URLs (HTTP/API), circuit-break, retry |
| `processor` | 2 | Extract fields, dedup, write raw_events |
| `validator` | 2 | Validate + score extracted data |
| `store` | 1 | Write scraped_data, update mission counters |

## Quick Start

### 1. Prerequisites

- Docker Engine 24+ and Docker Compose v2
- (No Python installation required on the host)

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env if you need to change passwords or ports
```

### 3. Start all services

```bash
docker compose up -d
```

Watch logs:

```bash
docker compose logs -f api-gateway coordinator crawler
```

Check health:

```bash
curl http://localhost:8080/health
# {"status":"ok"}
```

### 4. Scale crawlers on demand

```bash
docker compose up -d --scale crawler=6
```

### 5. Stop everything

```bash
docker compose down
# To also delete persisted data:
docker compose down -v
```

---

## Creating Your First Scraping Mission

### API scraping (JSON endpoint)

```bash
curl -s -X POST http://localhost:8080/api/missions \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Hacker News Top Stories",
    "description": "Fetch HN API for top story IDs",
    "targets": [
      {
        "url": "https://hacker-news.firebaseio.com/v0/topstories.json",
        "type": "api",
        "method": "GET",
        "headers": {},
        "extract": {
          "type": "json_path",
          "rules": {
            "story_ids": "$[*]"
          }
        }
      }
    ],
    "schedule": {
      "type": "once"
    }
  }' | python -m json.tool
```

### HTML page scraping

```bash
curl -s -X POST http://localhost:8080/api/missions \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Example.com Headline",
    "targets": [
      {
        "url": "https://example.com",
        "type": "html",
        "extract": {
          "type": "css",
          "rules": {
            "title": "h1",
            "paragraph": "p"
          }
        }
      }
    ],
    "schedule": {"type": "once"}
  }' | python -m json.tool
```

### Recurring mission (every 5 minutes)

```bash
curl -s -X POST http://localhost:8080/api/missions \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Repeated Check",
    "targets": [{"url": "https://httpbin.org/get", "type": "api"}],
    "schedule": {"type": "interval", "interval_seconds": 300}
  }'
```

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/missions` | Create and start a new mission |
| `GET` | `/api/missions` | List missions (`?page=1&page_size=20`) |
| `GET` | `/api/missions/{id}` | Get mission detail + progress |
| `DELETE` | `/api/missions/{id}` | Cancel a running mission |
| `GET` | `/api/data` | Query scraped data (`?mission_id=…&page=1`) |
| `GET` | `/api/agents` | List all active agent workers |
| `GET` | `/api/streams` | Redis Stream queue depths |
| `GET` | `/api/circuits` | Circuit breaker states per domain |
| `WS` | `/ws/console` | Real-time push stream |

### WebSocket events (`/ws/console`)

Connect with any WebSocket client. On connect you receive a `snapshot` of the full system state; thereafter incremental events are pushed:

```
ws://localhost:8080/ws/console
```

Event types: `snapshot`, `agent_update`, `stream_update`, `circuit_update`, `mission_event`

Example with `websocat`:
```bash
websocat ws://localhost:8080/ws/console
```

---

## Monitoring Dashboard

The system ships a lightweight monitoring frontend at:

```
http://localhost:8080/
```

> If you have the `frontend/` directory connected, serve it separately and point it at `http://localhost:8080`.

Stream depths, agent status, and circuit breaker states are also available via REST:

```bash
# Stream queue depths
curl http://localhost:8080/api/streams

# Active agents
curl http://localhost:8080/api/agents

# Circuit breaker states
curl http://localhost:8080/api/circuits
```

---

## Configuration

All configuration is via environment variables (see `.env.example`):

| Variable | Default | Description |
|---|---|---|
| `REDIS_URL` | `redis://redis:6379` | Redis connection URL |
| `DATABASE_URL` | `postgresql+asyncpg://...` | PostgreSQL DSN |
| `POSTGRES_PASSWORD` | `postgres` | Database password |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

---

## Data Pipeline

```
Mission created
     │
     ▼
crawl_jobs  ──[Crawler x3]──▶  raw_data  ──[Processor x2]──▶  clean_data
                                                                     │
                                                             [Validator x2]
                                                                     │
                                                              validated_data
                                                                     │
                                                              [Store x1]
                                                                     │
                                                              PostgreSQL
                                                            (scraped_data)
```

Failed messages after MAX_RETRIES (3) go to `dead_letters` stream.
Circuit breakers auto-open after rate-limit (HTTP 429/503) and auto-close after 5 minutes.

---

## Development

### Running services locally (without Docker)

```bash
# Install dependencies
pip install uv
uv pip install -e ".[dev]"

# Start infrastructure only
docker compose up -d redis postgres

# Set env vars
export REDIS_URL=redis://localhost:6379
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/spiderdb

# Run API gateway
cd services
python -m uvicorn api_gateway.main:app --reload --port 8080

# In separate terminals:
python -m coordinator.main
python -m crawler.main
python -m processor.main
python -m validator.main
python -m store.main
```

### Running tests

```bash
pytest tests/ -v
```
