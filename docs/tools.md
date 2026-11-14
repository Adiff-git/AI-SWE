# Read-only tool interfaces — SWE-68 / SWE-165

These are internal tool/LLM interfaces. SWE-165 implements a real
`BackendProductProvider` for the existing public Backend catalog APIs; see
[mapping, source inspection and remaining decisions](backend-catalog-integration.md).
Application lifespan wires the provider into `app.state.shopping_agent` using the
shared Backend client. `create_product_tools()` without an injected provider remains
unavailable; fake catalogs live only in tests. Public chat is still a placeholder.

## Definitions and execution

`agent/tools/schemas.py` defines strict Pydantic arguments and bounded product DTOs.
`registry.py` registers trusted `Tool[Arguments]` handlers, exposes generated JSON
Schema and validates/dispatches proposed calls. Names match
`^[a-z][a-z0-9_]{0,63}$`; duplicates and definitions marked as mutating are rejected.
Registration is an application-code operation, never an LLM capability. There is
no eval, dynamic import, arbitrary HTTP/URL tool, or cart/order/payment handler.

`products.py:create_product_tools(provider=None, timeout=5)` registers:

| Tool | Arguments | Result data |
| --- | --- | --- |
| `search_products` | Required `query` (1–200 characters), optional `category` (1–128), `min_price`, `max_price`, `currency` | Up to five product DTOs and `truncated` |
| `get_product_details` | Required `product_id` (1–128 characters; Backend requires lowercase UUID) | One product DTO with variant details, or `not_found` |

Unknown argument fields, wrong types, blank/control-character text, malformed or
non-object JSON, duplicate JSON keys and non-finite numbers are rejected. Price
constraints are exact finite nonnegative numbers or decimal strings, at most `1e15`,
with minimum no greater
than maximum. They require explicit uppercase three-letter currency (e.g. `VND`);
no currency is inferred by the tool. Values represent currency units, parsed as
`Decimal`, never binary floats. JSON amounts serialize as decimal strings. The
Backend provider supports only whole VND and rejects unsupported filters before HTTP.

Product DTOs contain `product_id`, `name`, category ID/name, optional
`price: {amount, currency}`, representative variant ID, image URLs, bounded
variant data and up to ten bounded text specifications per variant. Extra
provider fields, including private/internal fields, are discarded before LLM
serialization. Invalid allowed fields fail validation. Missing price/spec fields
do not imply values. No stock, discount, warranty or order facts are synthesized.

## Structured outcomes and bounds

Every result contains `tool_call_id`, `name`, `status`, `source`, `data` and
`error_code`. Sources are `backend`, `fake` and `unavailable`.

- `ok`: validated data; an empty search is an explicit successful empty result.
- `not_found`: details provider returned no record.
- `not_available`: no configured product provider; not an empty catalog.
- `error`: fixed code `unknown_tool`, `invalid_arguments`, `timeout`, `tool_error`,
  `invalid_result`, `result_too_large`, `unsupported_filter` or `backend_unavailable`.
  Raw exceptions and validation inputs are
  not sent to the model or logged.

The model can correct a failed request or explain a limitation within the same
budgets. The registry itself does not retry. Calls execute sequentially, including
when a provider returns multiple calls despite `parallel_tool_calls=false`.

| Bound | Default |
| --- | --- |
| Tool rounds / total LLM turns | 2 / 3 |
| Calls per assistant reply / total tool calls | 2 / 4 |
| Individual tool timeout / overall agent deadline | 5 s / 30 s |
| Arguments / structured result | 4 KiB / 8 KiB UTF-8 |
| Search products / specifications per variant | 5 / 10 |
| Detail variants / gallery URLs | 5 / 5, with explicit truncation flags |
| Tool-mode serialized context, including schemas and results | 32,000 characters |
| Assistant text | 8,000 characters |

Excess provider search results are capped and labeled `truncated`; oversized
structured results become an error instead of silently truncating JSON. Final
allowed model turn uses `tool_choice="none"`; ignored limits, replayed IDs and
inconsistent replies stop with controlled agent errors. Cancellation propagates.
The tool HTTP response has a 64 KiB post-download envelope check. Neither this
check nor reply-size validation is a streaming download or generation-token limit.

## LLM adapter and context

Existing `LLMClient.complete(messages)` is unchanged. Opt-in
`ToolCallingLLMClient.complete_with_tools(messages, definitions, tool_choice=...)`
supports typed `ToolCall`, `ToolAssistantMessage`, `ToolResultMessage` and
`ToolLLMResponse`. `create_llm_client()` supplies both interfaces. Providers must
support OpenAI-compatible Chat Completions function tools and tool-choice fields.

Inject `create_product_tools()` into `ShoppingAgent(llm, tools=...)` to enable this
path. Without a registry, or with an empty one, the old text path still makes one
LLM call. Tool-only output remains invalid on the old text-only interface.
The prompt version is 1.2.0, selected with trusted capability context. Tool results
stay under the tool role and are untrusted data even when schema-valid. Field
validation is not a semantic prompt-injection detector or proof of model grounding.

## Offline sample — no provider key or network

From the repository root after `uv sync --locked`:

```bash
uv run python - <<'PY'
import asyncio

from ai_service.agent.tools import create_product_tools
from ai_service.integrations.llm import ToolCall, ToolFunction

call = ToolCall(
    id="demo_search",
    function=ToolFunction(name="search_products", arguments='{"query":"laptop học lập trình"}'),
)
print(asyncio.run(create_product_tools().execute(call)).model_dump_json())
PY
```

Result (not a live catalog result):

```json
{
  "tool_call_id": "demo_search",
  "name": "search_products",
  "status": "not_available",
  "source": "unavailable",
  "data": null,
  "error_code": null
}
```

`tests/test_tools.py` supplies synthetic products to verify `ok` search/details and
`not_found`. `tests/test_agent_tools.py` scripts search → details → final text,
error recovery, correlation, context/iteration bounds and deadline cancellation.
`tests/test_llm_tools.py` uses HTTPX `MockTransport` for the wire-format round trip.
No test uses a real API key or external network service.

## Backend provider — implemented in SWE-165

`BackendProductProvider(shared_httpx_client)` implements the existing injection
boundary. Search maps to `GET /api/products` with actual camelCase filters and
numbered-page metadata; details map to `GET /api/products/{id}`. Only fixed GET
paths execute. Backend responses are streamed with a 64 KiB decoded-body cap.
HTTPX status/network errors and timeouts are sanitized; unexpected payloads fail
validation rather than becoming empty results. Comparison uses multiple calls to
the existing details tool, within the same limits.

`AgentResult.catalog_evidence` retains request-local tool outcomes.
`catalog_verified` is true only with at least one lookup and all attempted lookups
from Backend returning `ok` or `not_found`; this verifies lookup outcomes, not all
generated prose. Mixed success/failure is labeled partial; fake or unavailable
results are never certified. See the [implemented mapping](backend-catalog-integration.md)
for precise variant, currency, image and specification behavior.

The [SWE-69 contract proposal](backend-api-contract-proposal.md) remains unapproved.
Its internal routes, cursor API, availability/freshness, service authentication,
correlation and future chat HTTP/error contract are not implemented by SWE-165.
