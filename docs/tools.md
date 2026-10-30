# Read-only tool interfaces — SWE-68

These are internal tool/LLM interfaces, **not real Backend integration**. Public
FastAPI routes remain placeholders. No Backend paths, credentials or database
queries are assumed. The default provider is unavailable; fake catalogs live only
in tests. `AgentResult.catalog_verified` remains false, including after fake success.

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
| `get_product_details` | Required opaque `product_id` (1–128 characters) | One product DTO, or `not_found` |

Unknown argument fields, wrong types, blank/control-character text, malformed or
non-object JSON, duplicate JSON keys and non-finite numbers are rejected. Price
constraints are finite nonnegative numbers, at most `1e15`, with minimum no greater
than maximum. They require explicit uppercase three-letter currency (e.g. `VND`);
no currency is inferred by the tool. Values represent currency units and use
floats only for read-only filtering/display, not monetary arithmetic or payments.
SWE-69 must agree the real price/currency representation and mapping.

Product DTOs contain only `product_id`, `name`, optional `category`, optional
`price: {amount, currency}`, and up to ten bounded text specifications. Extra
provider fields, including private/internal fields, are discarded before LLM
serialization. Invalid allowed fields fail validation. Missing price/spec fields
do not imply values. No stock, discount, warranty or order facts are synthesized.

## Structured outcomes and bounds

Every result contains `tool_call_id`, `name`, `status`, `source`, `data` and
`error_code`. Current sources are only `fake` and `unavailable`.

- `ok`: validated data; an empty search is an explicit successful empty result.
- `not_found`: details provider returned no record.
- `not_available`: no approved product provider; not an empty catalog.
- `error`: fixed code `unknown_tool`, `invalid_arguments`, `timeout`, `tool_error`,
  `invalid_result` or `result_too_large`. Raw exceptions and validation inputs are
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
| Search products / specifications per product | 5 / 10 |
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
The prompt version is 1.1.0, selected with trusted capability context. Tool results
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

## Future Backend provider — after SWE-69 approval

The [SWE-69 contract proposal](backend-api-contract-proposal.md) is a **draft**, not
that approval. All [Backend Team decisions](backend-api-contract-proposal.md#8-decision-needed-from-backend-team)
remain pending. Its decimal-string prices, availability/evidence fields, cursor
metadata and HTTP failures are not implemented by the current tool DTOs. The draft
[gap table and integration test plan](backend-api-contract-proposal.md#9-implementation-gaps-and-short-integration-test-plan)
identify the required follow-up; merely creating this document must not change
sources to `backend`, mark catalog facts verified or enable endpoint requests.

Keep the `ProductProvider` injection boundary. After the Backend contract is
approved, implement its async search/details methods using the existing shared
Backend HTTP client with the agreed paths, HTTP methods, service auth, visibility,
pagination, identifiers, price/currency and error semantics. The interface already
receives typed filters and an explicit result limit. Map responses to allowlisted
DTOs, preserving authoritative product IDs and only approved fields.

This later work must explicitly introduce Backend provenance (currently rejected
as a source), update capability descriptions and review catalog-result semantics.
It must also test authorization, missing records, outages and field sanitization.
Do not obtain endpoints or URLs from model arguments or infer a Backend API from
these tool names. HTTP chat integration and its success/error contract remain
separate decisions. SWE-68 does not perform this mapping or approve SWE-69.
