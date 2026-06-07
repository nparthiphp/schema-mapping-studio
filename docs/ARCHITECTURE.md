# Schema Mapping Studio — Architecture Guide

## Overview

Schema Mapping Studio (SMS) is a production-grade microservice that eliminates the need to write a new Python connector class for every source system. Instead it uses an LLM to **generate a JSONata expression** that maps any source JSON payload to a fixed 12-field canonical schema, stores the expression in a registry, enforces a human-approval gate, then applies it at runtime.

---

## Canonical Schema

Every source system, regardless of its native structure, is normalised to these 12 fields:

| Field | Type | Description |
|---|---|---|
| `event_id` | string | Unique contact event identifier |
| `source` | string | Source system name |
| `timestamp_utc` | integer | UTC epoch milliseconds |
| `channel` | string | `voice \| chat \| email \| social \| web` |
| `raw_intent` | string | Raw customer issue text |
| `intent_category` | string | Classified intent label (nullable) |
| `sentiment_score` | float | -1.0 (very negative) to +1.0 (very positive) |
| `handle_time_seconds` | integer | Total handling time in seconds |
| `resolved` | boolean | Whether the issue was resolved |
| `escalated` | boolean | Whether the contact was escalated |
| `customer_id` | string | Customer identifier |
| `metadata` | object | Source-specific passthrough fields |

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Schema Mapping Studio                        │
│                                                                 │
│  ┌──────────────┐   ┌──────────────────────────────────────┐   │
│  │   FastAPI    │   │           Service Layer               │   │
│  │              │   │                                      │   │
│  │  /sources    │──▶│  LLM Service        Validator        │   │
│  │  /transform  │   │  (Anthropic API  +  (Field coverage  │   │
│  │  /health     │   │   local fallback)    analysis)       │   │
│  │  /metrics    │   │                                      │   │
│  └──────────────┘   │  JSONata Runner                      │   │
│         │           │  (Node.js subprocess)                │   │
│         │           └──────────────────────────────────────┘   │
│  ┌──────▼──────────────────────────────────────────────────┐   │
│  │                   SQLite / PostgreSQL                    │   │
│  │                   (MappingRecord table)                  │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
         │                          │
    Anthropic API           Node.js jsonata npm
```

---

## Request Flows

### Source Onboarding (`POST /sources`)

```
Client ──▶ APIKeyMiddleware ──▶ Router
                                  │
                           Payload size check (50 KB cap)
                                  │
                         LLM Service.generate_mapping()
                           ├── Try Anthropic API (up to 3 retries)
                           └── Fallback: local heuristic generator
                                  │
                         Validator.analyse_expression()
                         (static field coverage analysis)
                                  │
                         MappingRecord saved (status=pending)
                                  │
                         Response: expression + coverage scores
```

### Transform (`POST /transform`)

```
Client ──▶ Router
              │
       Lookup MappingRecord by source_id
       Assert status == "approved"
              │
       JSONata Runner (Node.js subprocess)
       ├── Write {expression, payload} to stdin
       ├── Read canonical result from stdout
       └── Increment transform_count
              │
       Return TransformResponse {canonical, duration_ms}
```

---

## Security Controls

| Layer | Control |
|---|---|
| Transport | `X-API-Key` header required on all non-health endpoints |
| Input | Payload capped at 50 KB before LLM call |
| Input | Pydantic validation on all request bodies |
| Process | Non-root Docker user (UID 1001) |
| Approval gate | Mappings must be explicitly approved before transforms are allowed |
| Coverage gate | Approve endpoint rejects mappings with < 60% field coverage |
| Subprocess | JSONata runner has configurable timeout (default 10 s) |

---

## Observability

- **Structured JSON logging** on every request, LLM call, transform, and error
- **`GET /health`** — liveness / readiness probe (DB connectivity check)
- **`GET /metrics`** — aggregate counts: mappings by status, total transforms, total errors
- **`transform_count` / `error_count`** — per-mapping counters updated on every call

---

## Reliability

- LLM retries: up to 3 attempts with exponential backoff (1.5 s, 3 s)
- Local fallback generator activates automatically when API is unavailable
- JSONata runner subprocess timeout prevents hung processes
- Database session rollback on any unhandled exception
- Global exception handler returns 500 without leaking stack traces

---

## Adding a New Source System

1. **No code required.** Call `POST /sources` with `source_name`, `source_category`, and a sample payload from the new system.
2. Review the generated JSONata expression in the response.
3. Edit if needed, then call `PUT /sources/{id}/approve`.
4. The source is now live — call `POST /transform` with any raw event.

---

## API Reference

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | ❌ | Liveness probe |
| GET | `/metrics` | ✅ | Aggregate metrics |
| POST | `/sources` | ✅ | Onboard new source (generates mapping) |
| GET | `/sources` | ✅ | List all mappings |
| GET | `/sources/{id}` | ✅ | Get mapping detail |
| PUT | `/sources/{id}/approve` | ✅ | Approve (optionally patch) mapping |
| DELETE | `/sources/{id}` | ✅ | Deactivate mapping |
| POST | `/transform` | ✅ | Transform raw event → canonical |

Full interactive docs at `/docs` (Swagger UI) or `/redoc`.

---

## Local Development

```bash
# 1. Clone and install
git clone https://github.com/your-org/schema-mapping-studio
cd schema-mapping-studio
pip install -r requirements.txt
cd scripts && npm install && cd ..

# 2. Configure
cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY

# 3. Run
uvicorn app.main:app --reload --port 8080

# 4. Test
pytest tests/ -v
```

## Docker

```bash
docker compose up --build
```

## Kubernetes (Helm)

```bash
helm install sms ./helm/schema-mapping-studio \
  --set secrets.apiKey=your-api-key \
  --set secrets.anthropicApiKey=sk-ant-...
```

---

## Technology Choices

| Component | Choice | Reason |
|---|---|---|
| API framework | FastAPI | Async, type-safe, auto-docs |
| ORM | SQLAlchemy 2.0 async | Clean async sessions, swap DB without code change |
| Database | SQLite (dev) / PostgreSQL (prod) | Zero-config locally; swap via `DATABASE_URL` |
| LLM | Anthropic Claude Sonnet 4 | Best instruction-following for code generation |
| JSONata engine | Node.js subprocess | JS-native; most complete JSONata 2.x support |
| Validation | Pydantic v2 | Runtime type safety on all I/O |
| Observability | stdlib logging + JSON format | Zero overhead, compatible with any log aggregator |
