# AI-SWE — Electronics AI Service

Initial AI repository for our university electronics e-commerce project. One
FastAPI application contains two independent feature modules: product
recommendation and an AI shopping agent. **Both features are placeholders.**
The service runs without a Backend connection, database, model or LLM credentials.

The repository directory `AI-SWE/` corresponds to the proposed `ai-service/` root.

## Stack and boundaries

Python 3.12+, FastAPI, Pydantic v2, pydantic-settings, HTTPX, Uvicorn, uv,
pytest, Ruff, Docker and Docker Compose. Development and Docker use Python 3.12.
The Backend owns authentication, authorization and all business data. The AI
service uses HTTP REST only and never accesses the Backend database.

## Structure

```text
AI-SWE/
├── src/ai_service/
│   ├── __init__.py
│   ├── main.py
│   ├── api/v1/{router,health}.py
│   ├── recommendation/{router,schemas,service}.py
│   ├── agent/
│   │   ├── router.py
│   │   ├── schemas.py
│   │   ├── service.py
│   │   ├── prompts/__init__.py
│   │   └── tools/__init__.py
│   ├── integrations/backend_client.py
│   └── core/{config,logging}.py
├── tests/{conftest,test_health,test_recommendation,test_agent}.py
├── docs/{architecture,api-contracts}.md
├── Dockerfile
├── compose.yaml
├── .dockerignore
├── .gitignore
├── .env.example
├── .python-version
├── pyproject.toml
├── uv.lock
└── README.md
```

Every Python package directory includes `__init__.py`. Routers handle HTTP;
schemas validate API data; service functions own future feature behavior.
`core/` contains settings and logging, and `integrations/` owns Backend HTTP
configuration. Prompts and tools directories are reserved and contain no logic.

## Local setup and run

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and Python 3.12.
From the repository root:

```bash
cp .env.example .env
uv sync --locked
uv run ai-service
```

`ai-service` reads `HOST` and `PORT` from settings. For automatic reload during
development, use explicit server binding arguments:

```bash
uv run uvicorn ai_service.main:app --reload --host 0.0.0.0 --port 8001
```

The reload command's CLI host/port arguments control binding, independently of
the application's `HOST`/`PORT` settings. Stop either server with Ctrl+C.

- Health: <http://localhost:8001/api/v1/health>
- Swagger UI: <http://localhost:8001/docs>
- ReDoc: <http://localhost:8001/redoc>
- OpenAPI: <http://localhost:8001/openapi.json>

```bash
curl http://localhost:8001/api/v1/health
curl -X POST http://localhost:8001/api/v1/recommendations \
  -H 'Content-Type: application/json' -d '{"user_id":"123","limit":10}'
curl -X POST http://localhost:8001/api/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Recommend a laptop for programming","session_id":null}'
```

## Configuration

Settings load from defaults, then `.env` in the current working directory, with
process environment variables taking precedence. Start from the repository root.
Environment names are case insensitive; `LOG_LEVEL` values must be uppercase.
Settings are cached for the process; restart after editing configuration.

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_NAME` | `Electronics AI Service` | API title and startup log |
| `APP_ENV` | `development` | Environment label; does not enable security controls |
| `HOST` | `0.0.0.0` | Binding for `ai-service` |
| `PORT` | `8001` | Binding port, 1–65535 |
| `LOG_LEVEL` | `INFO` | DEBUG, INFO, WARNING, ERROR or CRITICAL |
| `BACKEND_API_BASE_URL` | `http://localhost:8000` | Backend HTTP(S) base URL |
| `BACKEND_API_TIMEOUT` | `10` | Positive timeout in seconds for HTTPX operations |

Never commit credentials. `.env` files are ignored by Git and excluded from the
Docker build context. No credentials are currently needed.

## Docker

The Python 3.12 slim image uses uv with the committed lockfile and contains only
runtime dependencies in its final stage. It runs as a non-root user and includes
a liveness health check. Installation follows uv's
[Docker guidance](https://docs.astral.sh/uv/guides/integration/docker/).

```bash
docker compose config --quiet
docker compose up --build
# In another terminal, or after stopping the attached command:
docker compose down
```

Compose contains **only the AI service**, published at `127.0.0.1:8001` for local
development. It fixes the container binding to `0.0.0.0:8001`. It works without
`.env`; the default Backend address is `http://backend:8000`, which need not
resolve until a future integration actually sends requests. Compose also reads
`.env` for variable substitution: if you copied the local example, override its
`localhost` Backend address when connecting containers on a shared network.

Build and run the image independently:

```bash
docker build -t electronics-ai-service:local .
docker run --rm -p 127.0.0.1:8001:8001 \
  -e BACKEND_API_BASE_URL=http://backend:8000 electronics-ai-service:local
```

If Docker requires administrator access on your machine, prefix the Docker
commands with `sudo` and enter the password in your own terminal.

Production uses a **separate deployment repository/root Compose configuration**
that builds this Dockerfile and joins AI and Backend to the same Docker network.
Set `BACKEND_API_BASE_URL=http://backend:8000` (or the agreed service name/port),
and configure Backend to call `http://ai:8001`. Omit AI host `ports` in production;
only Backend should be publicly routed. Do not merge this development Compose
unchanged into production. No Backend or database container is defined here.

## Tests and quality checks

```bash
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run python -c 'from ai_service.main import app; print(app.title)'
```

Tests exercise lifespan startup, health, OpenAPI routing, placeholder responses
and request validation with FastAPI TestClient. They reject Backend client calls
and need no external service. To format source, run `uv run ruff format .`.

## Integration and next steps

The application lifespan owns one reusable `httpx.AsyncClient`, exposed as
`app.state.backend_client`, and closes it at shutdown. Creation performs no
network I/O. The client has a configured base URL and timeout, rejects unsuccessful
HTTP status codes, and preserves HTTPX connection/timeout exceptions. No Backend
paths or product methods are assumed. Future feature code can receive the shared
client through a FastAPI dependency once it is needed.

Backend must authenticate callers and authorize the supplied `user_id`. No AI
authentication or authorization is implemented in this scaffold. The teams must
agree service authentication, product/history payloads, error translation,
timeouts, session semantics and the final public contract before integration.

See [architecture](docs/architecture.md) and
[proposed API contracts](docs/api-contracts.md). No algorithms, LLM calls,
conversation memory, product tools, database models or migrations exist yet.
