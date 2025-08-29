# luki-api-gateway  
*Unified HTTP interface for the LUKi agent & modules (auth, routing, rate limits)*  
**PRIVATE / PROPRIETARY – Internal use only**
---

## License

This project is licensed under the [Apache 2.0 License with ReMeLife custom clauses]

---

## 1. Overview  
`luki-api-gateway` is the **single entry point** for clients (SDKs, web apps, partner services) to access all LUKi capabilities:

- **Chat / Agent endpoints** (`/v1/chat`, streaming)  
- **Memory & ELR ops proxy** (`/v1/elr/...`)  
- **Module endpoints pass-through** (cognitive, engagement, reporting)  
- **AuthN/AuthZ, rate limiting, request logging & tracing**  
- **Versioning, schema validation, error normalization**

It hides internal topology, giving external consumers a stable, documented REST surface.

---

## 2. Core Responsibilities  
- **Routing & Aggregation:** Fan-out to underlying services (memory, modules, token service)  
- **Authentication:** API keys, OAuth/JWT, service-to-service tokens  
- **Authorization:** Enforce scopes/roles (integration with `luki-security-privacy`)  
- **Throttling & Quotas:** Per-user and per-key rate limits  
- **Observability:** Structured logs, metrics, traces, correlation IDs  
- **Schema & Version Control:** Pydantic models and OpenAPI spec management

---

## 3. Tech Stack  
- **Framework:** FastAPI (ASGI), Uvicorn/Gunicorn  
- **Auth:** PyJWT, custom middleware, RBAC from security module  
- **Rate Limit:** `slowapi` or custom Redis-based limiter  
- **Schema / Docs:** Pydantic v2, OpenAPI auto-docs, Redoc UI  
- **HTTP Clients:** `httpx` async clients to downstream services  
- **Tracing:** OpenTelemetry exporters (Jaeger/Tempo), structlog for logs  
- **Deployment:** Docker/K8s, behind NGINX/API Gateway (cloud)

---

## 4. Repository Structure  
~~~text
luki_api_gateway/
├── README.md
├── pyproject.toml
├── luki_gateway/
│   ├── __init__.py
│   ├── config.py                # env vars, service URLs, rate limits
│   ├── main.py                  # FastAPI app entry
│   ├── auth/
│   │   ├── middleware.py        # authn/z middleware
│   │   ├── tokens.py            # API key/JWT utils
│   │   └── scopes.py            # scope constants
│   ├── middleware/
│   │   ├── tracing.py           # request IDs, OTEL
│   │   └── rate_limit.py        # limiter
│   ├── routers/
│   │   ├── chat.py              # /v1/chat endpoints
│   │   ├── elr.py               # /v1/elr proxy routes
│   │   ├── activities.py        # /v1/activities proxy
│   │   ├── reports.py           # /v1/reports proxy
│   │   └── health.py            # /healthz, /metrics
│   ├── clients/
│   │   ├── agent_client.py      # call luki-core-agent internal API
│   │   ├── memory_client.py     # call luki-memory-service
│   │   ├── cognitive_client.py  # call luki-modules-cognitive
│   │   ├── engagement_client.py # call luki-modules-engagement
│   │   └── reporting_client.py  # call luki-modules-reporting
│   ├── schemas/
│   │   ├── chat.py              # request/response models
│   │   ├── elr.py
│   │   ├── activities.py
│   │   └── common.py
│   └── utils/
│       ├── errors.py            # error mapping
│       └── responses.py
├── docker/
│   └── Dockerfile
├── scripts/
│   └── run_dev.sh
└── tests/
    ├── unit/
    └── integration/
~~~

---

## 5. Quick Start (Internal Dev)  
~~~bash
git clone git@github.com:REMELife/luki-api-gateway.git
cd luki-api-gateway
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn luki_gateway.main:app --reload --port 8080
~~~

Set env vars in `.env` or export:

~~~bash
export AGENT_URL=http://localhost:9000
export MEMORY_URL=http://localhost:8002
export COG_URL=http://localhost:8101
export ENG_URL=http://localhost:8102
export REP_URL=http://localhost:8103
export JWT_PUBLIC_KEY_PATH=keys/jwt_pub.pem
export RATE_LIMIT_PER_MIN=60
export LOG_LEVEL=INFO
~~~

---

## 6. Sample Endpoints

### Chat (sync)  
`POST /v1/chat`

~~~json
{
  "user_id": "user_123",
  "message": "I feel anxious today, can you help?",
  "context": {"mood": "anxious"}
}
~~~

Response:
~~~json
{
  "text": "I’m here for you. Let's try a breathing exercise...",
  "tool_calls": [],
  "meta": {"trace_id": "abc-123"}
}
~~~

### Chat (stream)  
`GET /v1/chat/stream?user_id=user_123&message=Tell%20me%20a%20joke`  
- Server-Sent Events (SSE) or WebSocket (if enabled)

### ELR Ingest Text  
`POST /v1/elr/ingest_text` → proxies to memory service.

### Activities Recommend  
`GET /v1/activities/recommend?user_id=user_123&k=3`

### Reports Generate  
`POST /v1/reports/generate` with `{"user_id":"...", "window_days":7}`

---

## 7. Auth & Rate Limiting  
- **Modes:** API key (`Authorization: Bearer <key>`), JWT, or internal service tokens.  
- **Scopes:** `chat:write`, `elr:read`, `elr:write`, etc. checked in `auth/scopes.py`.  
- **Rate limits:** global + per-user/per-key using Redis backend.

---

## 8. Observability  
- Request/response logs (no PHI) with trace IDs.  
- `/healthz` for liveness; `/metrics` for Prometheus.  
- OpenTelemetry tracing to Jaeger/Tempo (configured via ENV).

---

## 9. Error Handling  
- All downstream errors normalized to JSON:
~~~json
{
  "error": {
    "code": "DOWNSTREAM_TIMEOUT",
    "message": "Memory service did not respond",
    "trace_id": "abc-123"
  }
}
~~~

---

## 10. Testing & CI  
- **Unit tests:** routers, schema validation, auth.  
- **Integration:** spin up mock downstreams via docker-compose.  
~~~bash
pytest -q
~~~

- CI pipeline: lint, test, build Docker, push to registry.

---

## 11. Roadmap  
- GraphQL gateway (optional)  
- gRPC passthrough for high-throughput clients  
- Webhook callback support (push instead of poll)  
- Canary releases & blue/green deploy helpers  
- Advanced quota system with billing hooks

---

## 12. Contributing (Internal Only)  
- Branch naming: `gw/<feature>`  
- No hard-coded secrets; rely on env or Vault.  
- Keep OpenAPI schema updated (`/openapi.json` diff in CI).  
- PR requires 1 reviewer + green CI.

---

## 13. License  
**Proprietary – All Rights Reserved**  
Copyright © 2025 Singularities Ltd / ReMeLife.  
Unauthorized copying, modification, distribution, or disclosure is strictly prohibited.

---

**One door in. Everything safe, fast, and consistent out.**
