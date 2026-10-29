# AI-SWE — Electronics AI Service

Initial AI repository for our university electronics e-commerce project. One
FastAPI application contains two independent feature modules: product
recommendation and an AI shopping agent. **Both public feature endpoints are placeholders.**
The service runs without a Backend connection, database, model or LLM credentials.
An independent async LLM client supports OpenAI-compatible Chat Completions APIs;
the chat endpoint still returns its original placeholder without calling it.
A separate shopping-agent core can produce bounded, advisory text through an
injected LLM; it has no catalog tools or conversation persistence.

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
│   │   ├── orchestrator.py
│   │   ├── conversation.py
│   │   ├── exceptions.py
│   │   ├── prompts/__init__.py
│   │   └── tools/__init__.py
│   ├── integrations/
│   │   ├── backend_client.py
│   │   └── llm/{__init__,client,schemas,exceptions}.py
│   └── core/{config,logging}.py
├── tests/{conftest,test_health,test_recommendation,test_agent,test_agent_core,test_config,test_llm_client}.py
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
configuration and the independent LLM adapter. `agent/orchestrator.py` owns the
independent core; `agent/conversation.py` defines its internal request/result
contracts. `agent/tools/` contains only a metadata protocol for a future registry;
the prompts directory is reserved for future prompt design.

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
| `LLM_API_KEY` | Unset | Provider API key, required only when invoking the LLM |
| `LLM_BASE_URL` | Unset | HTTP(S) API root, e.g. `https://api.openai.com/v1` |
| `LLM_MODEL` | Unset | Provider-specific model identifier |
| `LLM_TIMEOUT` | `30` | Positive, finite timeout in seconds per HTTPX network operation |

Never commit credentials. `.env` files are ignored by Git and excluded from the
Docker build context. Credentials are optional for startup and all existing API
endpoints. Blank LLM settings are treated as unset; incomplete configuration raises
`LLMConfigurationError` only when `complete()` is called. Invalid nonempty URLs or
timeouts are configuration validation errors. The API key uses Pydantic
`SecretStr`; do not log raw credentials, headers or provider response bodies.

## LLM connection test

The client uses HTTPX directly, without a provider SDK or orchestration framework.
`LLMClient` is a provider-independent protocol; `OpenAICompatibleLLMClient` sends
non-streaming text conversations to `{LLM_BASE_URL}/chat/completions` and returns a
validated `LLMResponse` with `.message`, `.model` and `.finish_reason`. The base URL
must include any provider API prefix (such as `/v1`), **not** `/chat/completions`.
Either form with or without a trailing slash works.

For a real connection test, run `uv sync --locked`, copy `.env.example` to `.env`
if needed, then set these values in `.env` using your provider's credentials and
an available Chat Completions model:

```dotenv
LLM_API_KEY=replace-with-your-provider-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=replace-with-an-available-model-id
LLM_TIMEOUT=30
```

From the repository root, run this snippet. It reads `.env` through the same
settings as the application, calls the real provider, prints the assistant's text,
and closes the HTTP pool. This is a manual network test and may incur provider
charges; automated tests below use only mock responses.

```bash
uv run python - <<'PY'
import asyncio

from ai_service.core.config import get_settings
from ai_service.integrations.llm import LLMError, LLMMessage, create_llm_client


async def main():
    async with create_llm_client(get_settings()) as client:
        response = await client.complete([
            LLMMessage(role="user", content="Reply with a short greeting.")
        ])
        print(response.message.content)


try:
    asyncio.run(main())
except LLMError as exc:
    raise SystemExit(f"{type(exc).__name__}: {exc}") from None
PY
```

A successful invocation prints a nonempty assistant greeting. An unset key, API
root or model reports `LLMConfigurationError` before any HTTP request. Other
failures raise `LLMProviderError` (with `.status_code`), `LLMTimeoutError`,
`LLMConnectionError`, or `LLMResponseError`. Messages omit credentials and raw
provider bodies; requests are not retried and redirects are not followed.

Only text messages with `system`, `user` and `assistant` roles are supported in
this initial adapter. Streaming, tool calls, multimodal messages and conversation
storage are future work. A tool-only or otherwise non-text
response raises `LLMResponseError`. The `/api/v1/chat` route is still a placeholder;
use the snippet above to test the LLM connection directly.

## Shopping-agent foundation

`ShoppingAgent` accepts the SWE-65 `LLMClient` protocol by constructor injection.
It has no global client or conversation store. Its `respond(AgentTurn)` method
can be exercised directly with a fake LLM, as in `tests/test_agent_core.py`, or
with the configured real client inside an async function:

```python
import asyncio

from ai_service.agent.conversation import AgentTurn, ConversationMessage
from ai_service.agent.orchestrator import ShoppingAgent
from ai_service.core.config import get_settings
from ai_service.integrations.llm import create_llm_client


async def ask_agent():
    async with create_llm_client(get_settings()) as llm:
        result = await ShoppingAgent(llm).respond(
            AgentTurn(
                message="Mostly programming and travel.",
                history=(
                    ConversationMessage(role="user", content="Help me choose a laptop."),
                    ConversationMessage(role="assistant", content="What will you use it for?"),
                ),
                session_id="opaque-example",
            )
        )
        print(result.answer)


asyncio.run(ask_agent())
```

This example uses the same provider configuration as the LLM connection test.
For network-free checks, run
`uv run pytest tests/test_agent_core.py`.

Each turn supplies its own current message and optional completed user/assistant
history pairs. The core prepends its own system capability instruction and copies
the history; caller-supplied system roles are rejected. `session_id` is echoed
exactly as an opaque identifier, not loaded, authenticated or persisted. Reusing a
session ID does not recover previous turns. The caller must supply history again.

Processing is bounded to 20 history messages, a 4,000-character current message,
32,000 total input characters including the system instruction, one LLM call,
and 8,000 characters of model reply. The overall async invocation deadline defaults
to 30 seconds (`ShoppingAgent(llm, timeout=...)`); it is distinct from HTTPX's
per-operation `LLM_TIMEOUT`. Input is rejected rather than silently truncated.
The reply limit is checked after generation, not a provider token budget.

`AgentResult.answer` always includes a fixed catalog-unavailable notice, and
`catalog_verified` is always `false`. The capability instruction requests general
guidance and clarifying questions, without invented or verified catalog facts.
This is unverified model advice: unit tests establish orchestration and output
labeling, not factual accuracy or a guarantee against model hallucinations. Real
product/price/stock claims require authoritative Backend data and further grounding
work before exposing the core through HTTP.

Invalid input schemas raise Pydantic `ValidationError`; invalid history order or
input budget raises `AgentInputError`. LLM failures map to `AgentLLMError`, invalid,
oversized or incomplete replies to `AgentReplyError`, unsupported tools to
`AgentCapabilityError`, and deadline expiry to `AgentTimeoutError`. These inherit
`AgentError` from `agent.exceptions`; errors omit provider details and sensitive
messages. There is no retry or automatic success fallback. Caller cancellation
propagates normally.

For SWE-68, `ToolRegistry.names()` is a metadata-only injection point. Only absent
or empty registries are accepted; registered tools and LLM tool requests fail
closed. There are no concrete tools, tool loops, Backend endpoints or business
actions. The public `/api/v1/chat` response remains unchanged until a separate
contract agrees its generated-answer shape and error mapping.

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
and request validation with FastAPI TestClient. Endpoint tests reject outbound
HTTP calls. LLM unit tests use HTTPX `MockTransport` for successful responses,
configuration failures, invalid responses, provider errors, timeouts and network
failures; they use no real API keys or external services. To format source, run
`uv run ruff format .`.
Agent core tests additionally cover injected fakes, history isolation, concurrent
turns, budgets, deadlines/cancellation, invalid replies and disabled tools while
rejecting outbound HTTP calls.

## Integration and next steps

The application lifespan owns a reusable Backend `httpx.AsyncClient`, exposed as
`app.state.backend_client`, and a separate LLM HTTP pool through
`app.state.llm_client`. Both close at shutdown, and creation performs no network
I/O. The Backend client has a configured base URL and timeout, rejects unsuccessful
HTTP status codes, and preserves HTTPX connection/timeout exceptions. No Backend
paths or product methods are assumed. Future feature code can receive the shared
client through a FastAPI dependency once it is needed.

Backend must authenticate callers and authorize the supplied `user_id`. No AI
authentication or authorization is implemented in this scaffold. The teams must
agree service authentication, product/history payloads, error translation,
timeouts, session semantics and the final public contract before integration.

See [architecture](docs/architecture.md) and
[proposed API contracts](docs/api-contracts.md). The LLM connection layer and agent
core are available independently; feature endpoints do not invoke them. No algorithms,
conversation memory, product tools, database models or migrations exist yet.
