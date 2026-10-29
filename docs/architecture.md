# Architecture

One FastAPI process and one AI container host both feature modules.

```mermaid
flowchart TD
    Frontend --> Backend
    Backend -->|HTTP REST| API
    subgraph AI[AI Service — one FastAPI application]
        API[Versioned API routers]
        API --> Recommendation[Recommendation Module]
        API --> Agent[Agent Module]
        Agent -. future product retrieval .-> Client[Shared Backend HTTP client]
        Recommendation -. future history and product retrieval .-> Client
    end
    Client -. proposed HTTP REST APIs .-> Backend
    Backend --> DB[(Backend-owned database)]
```

Solid arrows show the intended request entry path; dotted arrows are future
integrations. Currently both feature endpoints return placeholders and make no
outbound requests. The diagram does not imply an existing Backend API contract.

## Ownership and module boundaries

| Component | Responsibility |
| --- | --- |
| Frontend repository | Customer interface; calls Backend |
| Backend repository | Authentication, authorization, users, products, categories, inventory, orders, payments, carts, promotions, search history and interaction tracking |
| AI `api/v1/` | API versioning, router composition and process health |
| AI `recommendation/` | Request/response schemas, HTTP endpoint and future recommendation logic |
| AI `agent/` | Placeholder HTTP endpoint, request-local conversation models and independent bounded shopping-agent core |
| AI `integrations/` | Reusable async Backend HTTP configuration and independent LLM connection layer |
| AI `core/` | Environment settings and standard Python console logging |
| AI `main.py` | Single application, lifecycle and entry point |

Routers call feature service functions. Feature modules do not import each other.
HTTP-facing service functions currently only construct placeholder responses. The
independent `ShoppingAgent` core consumes the provider-independent LLM protocol;
the chat router does not invoke it yet.

## Communication and lifecycle

1. Frontend sends customer requests to Backend.
2. Backend authenticates and authorizes the user and calls the internal AI API.
3. The AI router validates the payload and delegates to its feature service.
4. Today the service returns `status: not_implemented` without any external call.
5. Later, AI can request Backend-owned products/history through agreed HTTP APIs.

The lifespan initializes logging and opens separate Backend and LLM HTTPX pools.
Constructing the pools makes no network calls; shutdown closes both. Health is a
liveness endpoint and does not claim that recommendations, an LLM, or Backend are
operational.

The Backend client uses a configurable HTTP(S) base URL and positive timeout,
reuses connections, and raises `httpx.HTTPStatusError` for non-success responses.
Timeouts and network failures remain `httpx.TimeoutException`/`httpx.RequestError`.
There are no automatic retries. When real calls are introduced, feature code must
translate failures into an agreed API error response without exposing Backend
payloads or credentials. No current feature endpoint uses this client.

### LLM connection layer

`integrations/llm/` separates the `LLMClient` protocol, typed text messages and
responses, connection exceptions, and `OpenAICompatibleLLMClient` implementation.
The adapter posts non-streaming Chat Completions requests using HTTPX and validates
the provider envelope with Pydantic before returning an assistant response.
Unrecognized provider metadata is ignored; invalid or non-text responses raise a
controlled error. This boundary can be extended for tool calling in a later task.

`create_llm_client()` is an async context manager that owns the adapter's HTTP
pool. FastAPI exposes the adapter as `app.state.llm_client`; standalone callers
can use the same context manager. API keys use `SecretStr`, and key/base URL/model
are optional at startup but required before invocation. HTTP errors, network
failures, timeouts and malformed responses map to provider-independent exceptions
without raw provider bodies or credentials. There are no retries or redirects.
The client does not call Backend, orchestrate an agent or change endpoint behavior.

### Shopping-agent foundation

`agent/orchestrator.py` owns `ShoppingAgent`, injected with `LLMClient`. It has no
HTTP or Backend dependency and creates no client pool. Callers own the injected
client's lifecycle. The public `agent/service.py:chat` function remains a
placeholder, preserving the current API response and error contract.

`AgentTurn` and `ConversationMessage` in `agent/conversation.py` are internal,
immutable per-request contracts. History consists of completed user/assistant
pairs, followed by the current user message. The agent prepends a controlled
system instruction and copies messages for each call. It stores no history,
including when requests share a session ID; IDs are opaque metadata, never an
authorization or persistence mechanism. Caller-supplied system messages are not
accepted. Callers remain responsible for selecting authorized history.

The core allows one LLM call, no retries or tool loop, a default 30-second overall
async deadline, 20 history messages, 4,000 characters in the current message,
32,000 input characters including system context and 8,000 model-reply characters.
Budgets reject excess input/replies rather than truncating them. Reply size is a
post-generation check, not a provider token limit. Invalid schemas use Pydantic
validation; invalid order/budgets, LLM errors, incomplete/invalid replies,
unsupported capabilities and deadline expiry have controlled agent exceptions.
Cancellation from the caller is preserved. The core does not log messages or
provider details.

Without catalog access, the instruction requests general guidance and clarifying
questions. Every `AgentResult.answer` has a fixed unavailable/unverified catalog
notice, and `catalog_verified` is always false. This labels advice as unverified;
it does not prove model factuality. Grounded product/price/stock answers require
authoritative Backend tools and separate evaluation before public integration.

For SWE-68, `agent/tools/ToolRegistry` exposes only `names()` for capability
discovery. The constructor accepts an absent or empty registry and rejects any
registered tool. LLM tool requests are rejected, not executed. Tool definitions,
arguments, authorization and execution remain future work. The prompts package
is reserved; the core contains only a minimal capability instruction, not a prompt
management framework. Deterministic fake-based tests verify these boundaries
without any Backend or provider HTTP request.

## Deployment

Development Compose defines only AI and publishes port 8001 on loopback.
The image binds to `0.0.0.0`, runs as UID 10001, and contains a locked Python 3.12
runtime environment. The image is reusable by the deployment repository.

Production initially uses one VPS and a separate root Compose configuration for
Backend, AI and the Backend-managed database as appropriate. Both applications
share an internal Docker network: Backend calls `http://ai:8001`, and AI uses an
agreed Backend address such as `http://backend:8000`. `localhost` inside a container
refers to that container itself. Do not publish AI ports or route it through the
public reverse proxy. Decide service authentication with Backend before release.

## Future extension points

- Recommendation service: personalized, search/view-based and similarity ranking
  once data access and evaluation requirements are agreed.
- Agent HTTP integration: connect the tested core after generated-answer payloads,
  grounding expectations and error mappings are agreed.
- Agent prompts/tools: add only the prompts and Backend product tools required by
  the first implemented use case.
- Backend integration: add concrete methods only after endpoint paths, payloads,
  authorization and failure behavior are agreed.

No extension currently requires another application/container, direct database
access, a queue, vector database or ML framework.
