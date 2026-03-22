# luki-api-gateway

> **This repository is archived.** Active development continues in a private repository. This public version reflects the architecture from the ReMeLife integration era and is no longer maintained.

Single entry point for clients to access LUKi AI services: chat, memory, cognitive modules, and reporting.

## What It Does

- Routes requests to downstream microservices (core agent, memory, cognitive, engagement, reporting)
- Authenticates via JWT and API keys
- Rate-limits per user with Redis (in-memory fallback)
- Streams chat responses via SSE
- Proxies ELR memory operations and module endpoints
- Adds correlation IDs to all requests for tracing

## Stack

- **Framework:** FastAPI + Uvicorn
- **Auth:** python-jose (JWT), custom middleware
- **Rate Limiting:** Custom Redis-based limiter with in-memory fallback
- **HTTP Clients:** httpx (async) to downstream services
- **Deployment:** Docker on Railway

## Structure

```
luki_api/
├── main.py                  # FastAPI app, middleware registration
├── config.py                # Env vars, service URLs, rate limit settings
├── middleware/
│   ├── auth.py              # JWT + API key authentication
│   ├── rate_limit.py        # Redis + in-memory rate limiting
│   ├── metrics.py           # Prometheus metrics collection
│   ├── cache.py             # Response cache layer
│   ├── circuit_breaker.py   # Circuit breaker for downstream calls
│   ├── correlation.py       # Request correlation IDs
│   └── logging.py           # Structured request logging
├── routes/
│   ├── chat.py              # POST /api/chat/{user_id}/stream (SSE)
│   ├── conversation.py      # Conversation management
│   ├── conversations.py     # Conversation listing
│   ├── elr.py               # ELR memory proxy
│   ├── memories.py          # Memory operations
│   ├── uploads.py           # File upload handling
│   ├── health.py            # GET /health
│   ├── metrics.py           # GET /metrics
│   ├── cognitive.py         # Cognitive module proxy
│   └── wallet.py            # Wallet verification proxy
├── clients/
│   ├── agent_client.py      # Core agent HTTP client (SSE streaming)
│   ├── memory_service.py    # Memory service HTTP client
│   ├── base_client.py       # Shared HTTP client base
│   ├── security_service.py  # Security service HTTP client
│   └── wallet_client.py     # Solana wallet verification client
└── monitoring/
    └── health_monitor.py    # Downstream service health tracking
```

## Prerequisites

This gateway proxies requests to other LUKi microservices. You need running instances of:

- **luki-core-agent** — AI chat engine (required for `/api/chat`)
- **luki-memory-service** — ELR memory storage (required for `/api/elr`)
- **Redis** — rate limiting (optional, falls back to in-memory)

## Setup

```bash
git clone git@github.com:ReMeLife/luki-api-gateway.git
cd luki-api-gateway
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn luki_api.main:app --reload --port 8081
```

Environment variables (set in `.env` or export):

```bash
export SUPABASE_URL=https://your-project.supabase.co
export SUPABASE_JWT_SECRET=your-jwt-secret
export LUKI_CORE_AGENT_URL=http://localhost:9000
export LUKI_MEMORY_SERVICE_URL=http://localhost:8002
export LUKI_COGNITIVE_SERVICE_URL=http://localhost:8101
export REDIS_URL=redis://localhost:6379
```

## Key Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/chat/{user_id}/stream` | SSE streaming chat |
| POST | `/api/elr/ingest_text` | Ingest text to memory |
| POST | `/api/elr/search` | Semantic memory search |
| GET | `/health` | Service health check |
| GET | `/metrics` | Prometheus metrics |

## License

Apache License 2.0. See [LICENSE](LICENSE).
