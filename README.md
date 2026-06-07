# Schema Mapping Studio

> **LLM-powered, config-driven canonical schema normalization microservice.**  
> Onboard any JSON source system in minutes — zero new code per connector.

[![CI](https://github.com/your-org/schema-mapping-studio/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/schema-mapping-studio/actions)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## The problem it solves

Every customer-care source system (Zendesk, Genesys, Salesforce, custom CRMs) speaks a different JSON dialect. Traditional connectors require a new Python class per source — schema changes break them silently.

SMS replaces that with a single, reusable pipeline:

```
Any source JSON  →  LLM generates JSONata mapping  →  Human approves  →  Canonical event
```

The generated mapping is stored in a registry, versioned, and applied at runtime via a Node.js JSONata subprocess — so adding a new source is a one-API-call operation.

---

## Quick start

```bash
git clone https://github.com/your-org/schema-mapping-studio
cd schema-mapping-studio

cp .env.example .env          # set ANTHROPIC_API_KEY and API_KEY

# Option A — Docker (recommended)
docker compose up --build

# Option B — Local
pip install -r requirements.txt
cd scripts && npm install && cd ..
uvicorn app.main:app --reload --port 8080
```

API docs: http://localhost:8080/docs

---

## Usage

### 1. Onboard a source

```bash
curl -X POST http://localhost:8080/sources \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "source_name": "Zendesk",
    "source_category": "CRM",
    "sample_payload": {
      "id": 9823,
      "created_at": "2026-06-07T09:14:33Z",
      "subject": "Payment not going through",
      "status": "solved",
      "requester_id": "USR-4421",
      "satisfaction_rating": {"score": "bad"}
    }
  }'
```

Response includes the generated JSONata expression and field coverage scores.

### 2. Approve the mapping

```bash
curl -X PUT http://localhost:8080/sources/{id}/approve \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Optionally pass `"expression": "..."` to override before approving.

### 3. Transform events

```bash
curl -X POST http://localhost:8080/transform \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "source_id": "your-mapping-id",
    "payload": { "id": 9824, "created_at": "2026-06-07T10:00:00Z", ... }
  }'
```

Returns a normalized canonical event — same 12-field structure regardless of source.

---

## API reference

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | — | Liveness / readiness probe |
| GET | `/metrics` | ✅ | Aggregate counts |
| POST | `/sources` | ✅ | Onboard new source |
| GET | `/sources` | ✅ | List all mappings |
| GET | `/sources/{id}` | ✅ | Mapping detail |
| PUT | `/sources/{id}/approve` | ✅ | Approve mapping |
| DELETE | `/sources/{id}` | ✅ | Deactivate mapping |
| POST | `/transform` | ✅ | Transform raw event |

Authentication: `X-API-Key` header.

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `API_KEY` | `changeme` | Service authentication key |
| `ANTHROPIC_API_KEY` | — | Anthropic API key |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-20250514` | Model to use |
| `LLM_MAX_RETRIES` | `3` | Retry count before local fallback |
| `DATABASE_URL` | SQLite | Swap to `postgresql+asyncpg://...` for production |
| `PAYLOAD_MAX_BYTES` | `51200` | Max payload size (security cap) |
| `JSONATA_TIMEOUT` | `10` | JSONata runner subprocess timeout (seconds) |

See `.env.example` for full list.

---

## Reliability & security

- **LLM retries** — 3 attempts with exponential backoff; local heuristic generator as final fallback
- **Payload size cap** — 50 KB hard limit before any LLM call
- **Human approval gate** — mappings must be explicitly approved; < 60% coverage is rejected
- **Non-root container** — runs as UID 1001
- **Structured JSON logs** — every request, transform, and error logged with context
- **`/health`** — DB connectivity probe for K8s liveness/readiness

---

## Kubernetes

```bash
helm install sms ./helm/schema-mapping-studio \
  --set secrets.apiKey=prod-api-key \
  --set secrets.anthropicApiKey=sk-ant-...
```

---

## Running tests

```bash
pytest tests/ -v
```

---

## Architecture

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full design document including system diagram, request flows, security controls, and technology decisions.

---

## Roadmap

- [ ] PostgreSQL support (swap `DATABASE_URL`)
- [ ] Kafka consumer for streaming ingestion
- [ ] Semantic enrichment layer (intent classification + sentiment models)
- [ ] Schema drift detection + auto-regeneration
- [ ] Multi-tenant mapping registry
- [ ] Mapping version history + rollback

---

## License

MIT — see [LICENSE](LICENSE).
