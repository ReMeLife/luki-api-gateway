# luki-api-gateway  
*Unified HTTP interface for the LUKi agent & modules (auth, routing, rate limits)*

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

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
luki-api-gateway/
├── README.md
├── pyproject.toml
├── requirements.txt
├── env.example                  # environment template (copy to .env)
├── .env                         # actual environment file (gitignored)
├── luki_api/                    # main package
│   ├── __init__.py
│   ├── config.py                # env vars, service URLs, rate limits
│   ├── main.py                  # FastAPI app entry
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── api_key.py           # API key authentication
│   │   ├── jwt.py               # JWT token handling
│   │   └── rbac.py              # role-based access control
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── auth.py              # authentication middleware
│   │   ├── logging.py           # structured logging
│   │   ├── metrics.py           # metrics collection
│   │   ├── rate_limit.py        # rate limiting
│   │   └── tracing.py           # request tracing
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── chat.py              # /v1/chat endpoints
│   │   ├── elr.py               # /v1/elr proxy routes
│   │   ├── activities.py        # /v1/activities proxy (planned)
│   │   ├── reports.py           # /v1/reports proxy (planned)
│   │   ├── health.py            # /health endpoint
│   │   └── metrics.py           # /metrics endpoint
│   ├── clients/
│   │   ├── __init__.py
│   │   ├── agent_client.py      # LUKi core agent client
│   │   ├── memory_service.py    # memory service client
│   │   ├── cognitive_client.py  # cognitive module client (planned)
│   │   ├── engagement_client.py # engagement module client (planned)
│   │   └── reporting_client.py  # reporting module client (planned)
│   ├── schemas/
│   │   ├── __init__.py          # (planned)
│   │   ├── chat.py              # request/response models (planned)
│   │   ├── elr.py               # ELR models (planned)
│   │   ├── activities.py        # activity models (planned)
│   │   └── common.py            # shared models (planned)
│   ├── models/
│   │   └── errors.py            # error models and handling
│   └── utils/
│       ├── errors.py            # error mapping (planned)
│       └── responses.py         # response utilities (planned)
├── docker/
│   └── Dockerfile               # container build (planned)
├── scripts/
│   ├── run_dev.sh               # bash development script
│   └── run_dev_api_gateway.py   # python development script
└── tests/
    ├── integration/             # integration tests
    └── unit/                    # unit tests (when added)
~~~

---

## 5. Quick Start  
~~~bash
git clone https://github.com/your-org/luki-api-gateway.git
cd luki-api-gateway
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn luki_api.main:app --reload --port 8081
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

### Health Check  
`GET /health` - Service health and status

### Metrics  
`GET /metrics` - Prometheus metrics for monitoring

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

## 12. Contributing  

We welcome contributions to the LUKi API Gateway! Please follow these guidelines:

### Development Workflow
1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes and add tests
4. Run the test suite: `pytest`
5. Submit a pull request

### Code Standards
- Follow PEP 8 style guidelines
- Add type hints for all functions
- Write tests for new functionality
- No hard-coded secrets; use environment variables
- Keep OpenAPI schema updated
- PR requires review + passing CI

---

## 13. License  

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## 14. Support

- **Documentation:** Check the `/docs` endpoint when running the server
- **Issues:** Report bugs and feature requests via GitHub Issues
- **Discussions:** Join community discussions for questions and ideas

---

**One door in. Everything safe, fast, and consistent out.**
