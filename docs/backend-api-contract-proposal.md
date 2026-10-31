# Agent–Backend Integration Contract — SWE-69

**Status: DRAFT / PROPOSED — NOT APPROVED, NOT IMPLEMENTED.** Contract revision:
`0.1.0-draft`. Backend Team approval: **Pending**. AI Team approval: **Pending**.
Writing or merging this proposal does not approve its API or enable live access.

All proposed paths, authentication claims, payloads, budgets and mappings below
require agreement. All example products, amounts, availability and timestamps are
synthetic fixtures, not real catalog facts. No example establishes deployed support.
The draft's revision is distinct from API URL version `v1` and the application's
package version. Current runtime contracts remain authoritative until an approved
implementation and coordinated rollout replace them.

## 1. Confirmed current behavior

| Direction/component | CURRENT behavior verified in this repository |
| --- | --- |
| Backend → AI: `GET /api/v1/health` | HTTP 200, `{"status":"ok"}`; process liveness, no dependency check |
| Backend → AI: `POST /api/v1/chat` | HTTP 200 fixed `not_implemented` response; no agent, LLM or Backend invocation |
| Backend → AI: `POST /api/v1/recommendations` | HTTP 200 `{"product_ids":[],"status":"not_implemented"}`; not a computed empty recommendation |
| Chat input | Required `message`: 1–4,000 characters after trimming; optional `session_id`: null or 1–128 trimmed characters; unknown fields rejected |
| Validation | FastAPI HTTP 422 `detail` response; not the draft error envelope in section 6 |
| Sessions | A supplied ID is echoed; no creation, ownership lookup, authentication or persistence |
| Authentication/correlation | No service-auth enforcement or request-ID propagation implemented by the application |
| AI → Backend client | Shared HTTPX async pool, configured base URL, 10-second default per-operation timeout, raises on non-2xx including redirects; no automatic retry, no concrete endpoint methods |
| Agent tools | Internal `search_products`/`get_product_details` interfaces; sources only `fake`/`unavailable`; default `not_available`; `catalog_verified=False` |

CURRENT chat request and response (HTTP 200):

```json
{"message":"Tư vấn laptop giúp mình.","session_id":null}
```

```json
{
  "status": "not_implemented",
  "message": "AI shopping assistance is not implemented yet.",
  "session_id": null
}
```

Source of truth: [chat schemas](../src/ai_service/agent/schemas.py),
[chat service](../src/ai_service/agent/service.py),
[routers](../src/ai_service/api/v1/router.py),
[Backend client](../src/ai_service/integrations/backend_client.py) and
[settings](../src/ai_service/core/config.py). Live `/openapi.json` describes CURRENT
FastAPI routes only. This draft schema is not mounted there. CURRENT chat rejects
the proposed `history` field and cannot return `answered` or `needs_clarification`.

## 2. Ownership, scope and trust — PROPOSED

- Backend owns authentication, authorization, catalog, product visibility, prices,
  availability, users, orders and business decisions. AI uses agreed REST APIs;
  it never accesses Backend's database or invents missing business data.
- MVP is catalog-only, read-only purchase advice. Cart mutations, order creation,
  payment, order-status access and unconfirmed warranty/discount lookups are out
  of scope. Availability is informational, not a reservation or delivery promise.
- No new recommendation or user-history endpoint is proposed for MVP. Personalized
  recommendations/context would need an explicit use case, allowed fields,
  consent/retention and Backend-authorized subject before extending this contract.
  The existing recommendation placeholder remains CURRENT.
- Service identity and end-user identity are distinct. A body `user_id`, role,
  session ID, tool argument or self-declared `X-User-ID` is never authentication.
  The proposed chat body contains no auth/permissions fields.
- Backend authenticates its customer and authorizes/selects any history before
  calling AI. A session ID grants no rights. AI stores no history; Backend must
  resupply allowed completed turns. Caller-supplied system/tool roles are rejected.
- MVP catalog scope exposes only the audience-visible catalog. If visibility or
  pricing is customer/tenant-specific, a verified delegated-subject mechanism is
  required before enabling it; AI must not infer one from an unverified identifier.
- Model output and user/catalog/tool text are untrusted instructions. Tool data
  cannot override system policy. Only application-registered read-only handlers
  may execute; model arguments never select a host, URL, SQL query or executable.

### Service authentication — PROPOSED, mechanism pending D02

Recommend separate, audience-bound bearer service credentials for each direction,
over authenticated internal transport. Illustrative audience/scope pairs are
`ai-service` / `ai:chat` and `backend-service` / `catalog:read`; these are not existing
claims. Backend and AI must agree issuance, JWT versus opaque-token validation,
issuer/audience, scopes, expiry, rotation, revocation and transport/TLS deployment.
Network membership alone is not service authentication. Secrets come from runtime
configuration, never prompts, request bodies or committed examples. This proposal
does not introduce an auth setting or implementation.

### Privacy and correlation — PROPOSED

Log an allowlist only: operation, HTTP status, duration, safe error code and
validated correlation ID. Do not log bearer tokens, raw user messages/history,
tool arguments, provider/Backend bodies or customer records. Do not forward auth
headers, session IDs or raw errors to the LLM. Select only approved product fields;
catalog descriptions remain untrusted. Retention and external-LLM data policy are
pending D11; no replacement customer/history store is introduced in AI.
Apply the same allowlist to proxy/access and HTTP-client logs: query strings and
authorization headers must not bypass redaction through transport logging.

Use `X-Request-ID` on both directions and responses. Accept only
`^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`; otherwise generate a new opaque ID. It carries no
PII and is not authorization or idempotency. Preserve the root ID across downstream
calls, and associate tool-call IDs locally for individual operations. Body
`request_id` must equal the response header. Do not copy arbitrary header text into
logs. Generation/propagation are not CURRENT features.

## 3. Backend → AI chat — PROPOSED future profile

**PROPOSED future behavior on `POST /api/v1/chat`, not a new live endpoint.** Keeping
this path and changing its placeholder response requires D10 approval, consumer
coordination and rollout/version decisions; deployed clients must not assume the
draft shape already works.

| Request field | Proposed type/rule |
| --- | --- |
| `message` | Required nonblank string, 1–4,000 characters; trim outer whitespace |
| `session_id` | Omitted/null or opaque non-whitespace string up to 128 characters; echo only, not a persisted/authenticated session |
| `history` | Optional, default `[]`; at most 20 messages in completed alternating user/assistant pairs; each content nonblank, at most 4,000 characters; Backend-authorized context only |

Unknown fields are rejected. Bound the assembled context including trusted system
text, schemas and tool results to the current 32,000-character agent budget;
request-size failures are 422, later tool-context expansion failures are 503.
Do not silently truncate authorized history or promote text containing role markers.
The request schema describes canonical values after trimming outer whitespace from
message/history content. This normalization is application logic, not a JSON Schema
transform. Opaque IDs are preserved, not trimmed or case-normalized in this proposal;
their stricter draft syntax and future history support require D03/D10 agreement.

Future HTTP 200 uses `status=answered` or `needs_clarification`, `message`, echoed
`session_id`, `products`, `evidence`, `warnings` and `request_id`. Message is bounded
to 8,000 characters. Products are at most five allowlisted summaries. Evidence
is at most four records containing Backend capability, outcome, product IDs and
observation time; it is not a dump of tool arguments or transport headers.

- General advice/clarification can have empty products/evidence and no Backend call.
- Product-specific facts must match successful authoritative evidence. Every
  returned product ID must appear in successful evidence; IDs are unique in cards.
  Evidence does not certify every sentence generated by the LLM.
- A successful empty search can return 200 with no cards, `CATALOG_EMPTY` warning
  and `outcome=empty`. It means no matching visible records, not a global empty store.
- Expected structured product 404 can be explained with no product card and a
  `PRODUCT_NOT_FOUND` warning; it does not mean the AI chat route is missing.
- **Required catalog lookup timeout/unavailability fails closed with HTTP 503.**
  Do not turn it into an empty result, cached/unverified product answer or HTTP 200
  `degraded`. Optional general-advice requests need not perform catalog lookup.
- Do not return partial product cards if a lookup required to support the answer
  failed. General advisory prose must not imply that missing prices/stock were checked.

The JSON Schema is structural. Completed history pairs, total size, evidence/card
consistency and the required-lookup policy are additional semantic requirements.
No implementation of this future HTTP profile is included in SWE-69.

## 4. AI → Backend catalog — PROPOSED, not deployed APIs

Both paths below are illustrative **PROPOSED** Backend routes relative to the
agreed Backend base URL. Do not derive deployed support from the names. API URL
version is proposed as `v1`; final routes/base URLs remain D01.

### PROPOSED search/filter

`GET /internal/ai/v1/products` — no GET body. Requires authenticated service identity
and catalog-read permission. Backend applies visibility before filtering/pagination.

| Query parameter | Proposed type/rule |
| --- | --- |
| `q` | Required nonblank string, 1–200 characters; maps from tool `query` |
| `category_id` | Optional opaque ID, maps from tool `category`; valid but unknown category yields an empty result |
| `min_price`, `max_price` | Optional nonnegative decimal strings in currency major units; inclusive bounds, numeric minimum ≤ maximum |
| `currency` | Required with a price bound; proposed MVP whitelist `VND`; unsupported currency is 422, never implicitly converted |
| `limit` | Integer 1–5, default 5; bounded AI use, not a claimed Backend-global limit |
| `cursor` | Optional opaque non-whitespace string up to 512 characters; URL-encode, do not inspect; omit on first page |

Success is HTTP 200 with `items`, `page: {limit, next_cursor}` and `request_id`.
`next_cursor=null` means no further visible matches. Items cannot exceed the
requested limit or repeat an ID. An empty terminal page has `items=[]` and
`next_cursor=null`. Invalid/expired cursors and invalid bounds/filters return 422,
not empty success. Backend owns deterministic ordering and cursor validity; D09
must settle cursor lifetime and concurrent-catalog-change semantics. AI MVP reads
one page; no automatic pagination loop. A next cursor means a partial search result,
not permission to manufacture more records.

### PROPOSED details and specifications

`GET /internal/ai/v1/products/{product_id}` — no GET body. Same service-auth/catalog
permission boundary as search. Treat IDs as opaque, case-sensitive strings of
1–128 non-whitespace characters; percent-encode one path segment. Never parse them
as integers or UUIDs. Whether an ID identifies a model or sellable variant/SKU is D03.

Success is HTTP 200 with `product` and `request_id`. Details include the summary
fields below and `specifications`: up to ten nonblank keys (64 characters) and
nonblank string values (200 characters). Units are explicit in values, e.g. `16 GB`.
Unknown specifications are absent; do not infer them. A separate specs endpoint
is not needed for MVP. A mismatched returned product ID is an invalid upstream
response, never a successful lookup for another product.

### Proposed product representation and outcomes

| Field | Proposed representation/meaning |
| --- | --- |
| `product_id` | Opaque ID; preserved in evidence/cards and mapped to tool DTO |
| `name` | Nonblank display string up to 200 characters |
| `category_id` | Opaque ID or null; not an invented category label |
| `price` | Null if unavailable, otherwise `{amount, currency, observed_at}`; null is not zero/free |
| `price.amount` | Decimal string of 1–15 digits, no sign/exponent/leading zero except `0`; VND major units with zero fractional digits in this MVP proposal |
| `price.currency` | Explicit `VND` for proposed MVP; currency expansion/precision, tax/promotion treatment require D06 |
| `availability` | `{status, observed_at}`; status `in_stock`, `out_of_stock`, `preorder` or `unknown`; known statuses require an RFC 3339 timestamp |
| Observation times | RFC 3339, examples use UTC; describe returned evidence, not a promise that price/stock cannot change |

No stock quantities, private supplier costs, customer data, arbitrary fetch URLs,
discounts, warranties or order information are required. Response text is data,
never instructions. Proposed Backend body cap is 64 KiB; the provider mapper must
also respect the stricter current 8 KiB tool-result budget. Price/availability are
observations only; freshness SLA and stale-data handling require D07.

For both proposed catalog paths: missing/invalid service auth → 401; valid service
identity without required scope → 403; malformed parameters → 422; own rate limit →
429; temporary unavailability → 503. Details missing/invisible to the catalog
audience → structured 404 `PRODUCT_NOT_FOUND`, to avoid enumeration (D04 pending).
Search filters invisible records. Permissions never come from an LLM-supplied ID.
These errors use the draft envelope below, not presumed existing Backend payloads.

## 5. Timeouts, limits and retry policy — PROPOSED

| Boundary | CURRENT | PROPOSED for integration review |
| --- | --- | --- |
| Backend caller → AI | Not implemented here | 35 s caller deadline; proxy budget greater than caller budget |
| AI overall agent turn | 30 s default total | Retain 30 s; share remaining deadline across all operations |
| Individual tool | 5 s default total | Retain 5 s, including argument/result processing |
| AI → Backend product read | HTTPX setting defaults to 10 s per operation; no reads implemented | 3 s total per read, bounded by remaining agent deadline; example HTTPX ceilings connect 1 s/read 2 s/write 1 s/pool 1 s inside that total deadline |
| Tool/LLM loop | 2 tool rounds, 2 calls/reply, 4 tools total, 3 LLM turns | Retain these caps; model error correction uses the same budget |
| HTTP retries | None | Zero automatic retries in MVP; `retryable=true` means a later caller attempt may be appropriate, not a retry instruction |

HTTPX operation timeouts do not add up to an overall deadline by themselves.
Future implementation must enforce the total read/agent deadlines and cancel
outstanding work on timeout/disconnect. A final LLM turn must fit remaining budget;
no guarantee that all maximum calls can complete within 30 seconds. No automatic
cursor traversal or request replay. Honor agreed `Retry-After` before a new request,
and never blindly retry auth/validation errors. Numeric budgets await D13 approval.

## 6. Error mappings — PROPOSED, not current exception handlers

Draft envelope: `error: {code, message, retryable}` and `request_id`. Messages are
short safe descriptions, not raw exception text, URLs, secrets, validation `input`
or Backend payloads. Proposed response `Content-Type: application/json` and
`X-Request-ID` apply to success and failure. CURRENT FastAPI 422 still uses `detail`.
If bearer auth is adopted, proposed 401 responses also carry the generic
`WWW-Authenticate: Bearer` challenge, without token or account details.

| Condition | Proposed AI HTTP/code | Handling |
| --- | --- | --- |
| Invalid caller chat payload/history/input budget | 422 `INVALID_REQUEST` | No LLM/Backend call; not retryable |
| Missing/invalid service credential at AI | 401 `UNAUTHENTICATED` | Generic auth failure, not retryable |
| Authenticated caller lacks AI scope, or verified delegated subject denied under an agreed future contract | 403 `FORBIDDEN` | No data leak; not retryable |
| AI's own caller rate limit | 429 `RATE_LIMITED` | Bounded valid `Retry-After` seconds (proposed 1–300); retryable later |
| Downstream service-token 401 or service-scope 403 | 502 `UPSTREAM_AUTH_ERROR` | Integration failure; do not ask the customer to log in; not retryable automatically |
| Backend rejects an AI-built request with 422, or an unexpected route/status reveals a contract mismatch | 502 `UPSTREAM_CONTRACT_ERROR` | Do not pass through as customer validation error |
| Invalid JSON/schema, mismatched product ID or unexpected Backend body | 502 `INVALID_BACKEND_RESPONSE` | No catalog claims from invalid data |
| Required catalog read times out without response | 503 `BACKEND_TIMEOUT` | Retryable later; no invented downstream HTTP status/body |
| Connection failure or Backend temporary 5xx/unavailable response | 503 `BACKEND_UNAVAILABLE` | Retryable later; no empty-success substitution |
| Downstream 429 | 503 `UPSTREAM_RATE_LIMITED` | Not AI's own user quota; relay only validated bounded `Retry-After` when present |
| LLM unavailable | 503 `LLM_UNAVAILABLE` | No fabricated answer; no automatic retry |
| Tool call/context/iteration cap or whole AI deadline | 503 `AGENT_LIMIT_EXCEEDED` / `AI_TIMEOUT` | Controlled stop; limits not retryable, timeout may be transient |
| Unexpected local implementation failure | 500 `INTERNAL_ERROR` | Safe generic message, no traceback or internal data |

Proposed `retryable=true` codes are only `RATE_LIMITED`, `BACKEND_TIMEOUT`,
`BACKEND_UNAVAILABLE`, `UPSTREAM_RATE_LIMITED`, `LLM_UNAVAILABLE` and `AI_TIMEOUT`.
All other draft error codes use false. This does not enable automatic retries.

Only a contract-conforming details 404 with `PRODUCT_NOT_FOUND` maps to tool
`not_found`. An HTML 404, missing-route response or unknown error body is a 502
contract/response failure. A future genuine delegated-user 403 can map to caller
403 only with verified authorization context; service-account misconfiguration
always remains an integration failure. D12 must approve status/code/Retry-After
semantics before either team implements these mappings.

## 7. Complete example exchanges — ALL PROPOSED, synthetic data

The adjacent `schema` annotations identify a named definition in the
[draft JSON Schema](schemas/backend-api-contract-proposal.schema.json). They are
documentation validation hints, not HTTP fields. Header credentials are placeholders.

### 7.1 Normal purchase advice — PROPOSED

Backend → AI request:

```http
POST /api/v1/chat HTTP/1.1
Authorization: Bearer <backend-to-ai-service-token>
X-Request-ID: req-advice-001
Content-Type: application/json
```

<!-- schema: schemas/backend-api-contract-proposal.schema.json#/$defs/ChatRequest -->
```json
{"message":"Mình cần laptop học lập trình, ngân sách tối đa 15 triệu đồng Việt Nam.","session_id":null,"history":[]}
```

AI → Backend search; no GET body:

```http
GET /internal/ai/v1/products?q=laptop&max_price=15000000&currency=VND&limit=5 HTTP/1.1
Authorization: Bearer <ai-to-backend-catalog-token>
X-Request-ID: req-advice-001
```

Normalized query values for schema validation only (not a wire JSON body):

<!-- schema: schemas/backend-api-contract-proposal.schema.json#/$defs/ProductSearchQuery -->
```json
{"q":"laptop","max_price":"15000000","currency":"VND","limit":5}
```

Backend → AI response: HTTP 200, `Content-Type: application/json`,
`X-Request-ID: req-advice-001`:

<!-- schema: schemas/backend-api-contract-proposal.schema.json#/$defs/ProductSearchResponse -->
```json
{
  "items": [{
    "product_id": "demo-product-001",
    "name": "Laptop minh họa A",
    "category_id": "demo-laptops",
    "price": {"amount":"14990000","currency":"VND","observed_at":"2026-10-30T09:00:00Z"},
    "availability": {"status":"in_stock","observed_at":"2026-10-30T09:00:00Z"}
  }],
  "page": {"limit":5,"next_cursor":null},
  "request_id": "req-advice-001"
}
```

AI → Backend response: HTTP 200, same content type and request-ID header:

<!-- schema: schemas/backend-api-contract-proposal.schema.json#/$defs/ChatSuccess -->
```json
{
  "status": "answered",
  "message": "Theo dữ liệu vừa trả về, Laptop minh họa A có giá 14.990.000 VND và trạng thái còn hàng tại thời điểm kiểm tra. Bạn ưu tiên máy nhẹ hay khả năng nâng cấp để mình tư vấn thêm?",
  "session_id": null,
  "products": [{
    "product_id": "demo-product-001",
    "name": "Laptop minh họa A",
    "category_id": "demo-laptops",
    "price": {"amount":"14990000","currency":"VND","observed_at":"2026-10-30T09:00:00Z"},
    "availability": {"status":"in_stock","observed_at":"2026-10-30T09:00:00Z"}
  }],
  "evidence": [{
    "source":"backend","capability":"product_search","outcome":"ok",
    "product_ids":["demo-product-001"],"observed_at":"2026-10-30T09:00:00Z"
  }],
  "warnings": [],
  "request_id": "req-advice-001"
}
```

This is a future target with synthetic evidence, not the output of the CURRENT
`ShoppingAgent` or chat endpoint. Backend constructs display links from approved
IDs; this example does not introduce an arbitrary URL-fetch capability.

### 7.2 Product lookup, specifications and 404 — PROPOSED

AI → Backend request; no GET body:

```http
GET /internal/ai/v1/products/demo-product-001 HTTP/1.1
Authorization: Bearer <ai-to-backend-catalog-token>
X-Request-ID: req-lookup-001
```

Backend → AI: HTTP 200, `Content-Type: application/json`,
`X-Request-ID: req-lookup-001`:

<!-- schema: schemas/backend-api-contract-proposal.schema.json#/$defs/ProductDetailsResponse -->
```json
{
  "product": {
    "product_id":"demo-product-001","name":"Laptop minh họa A","category_id":"demo-laptops",
    "price":{"amount":"14990000","currency":"VND","observed_at":"2026-10-30T09:00:00Z"},
    "availability":{"status":"in_stock","observed_at":"2026-10-30T09:00:00Z"},
    "specifications":{"RAM":"16 GB","storage":"512 GB SSD"}
  },
  "request_id":"req-lookup-001"
}
```

For a separate request `GET /internal/ai/v1/products/demo-missing` with the same
auth scheme and `X-Request-ID: req-missing-001`, Backend → AI is HTTP 404 with
`Content-Type: application/json` and `X-Request-ID: req-missing-001`:

<!-- schema: schemas/backend-api-contract-proposal.schema.json#/$defs/ErrorResponse -->
```json
{
  "error":{"code":"PRODUCT_NOT_FOUND","message":"Không tìm thấy sản phẩm trong phạm vi được phép xem.","retryable":false},
  "request_id":"req-missing-001"
}
```

### 7.3 Empty matching catalog result — PROPOSED

Backend → AI: same proposed POST/auth/content-type as 7.1, with
`X-Request-ID: req-empty-001` and body:

<!-- schema: schemas/backend-api-contract-proposal.schema.json#/$defs/ChatRequest -->
```json
{"message":"Tìm mẫu demo-no-match giúp mình.","session_id":null,"history":[]}
```

AI → Backend: `GET /internal/ai/v1/products?q=demo-no-match&limit=5`, catalog service
auth and `X-Request-ID: req-empty-001`; no GET body. Backend → AI: HTTP 200,
JSON content type and the same request-ID header:

<!-- schema: schemas/backend-api-contract-proposal.schema.json#/$defs/ProductSearchResponse -->
```json
{"items":[],"page":{"limit":5,"next_cursor":null},"request_id":"req-empty-001"}
```

AI → Backend: HTTP 200, JSON content type and `X-Request-ID: req-empty-001`:

<!-- schema: schemas/backend-api-contract-proposal.schema.json#/$defs/ChatSuccess -->
```json
{
  "status":"answered",
  "message":"Không tìm thấy sản phẩm khớp yêu cầu trong kết quả tra cứu. Bạn có muốn nới tiêu chí hoặc mô tả lại nhu cầu không?",
  "session_id":null,
  "products":[],
  "evidence":[{"source":"backend","capability":"product_search","outcome":"empty","product_ids":[],"observed_at":"2026-10-30T09:00:00Z"}],
  "warnings":[{"code":"CATALOG_EMPTY","message":"Không có sản phẩm khớp tiêu chí tra cứu."}],
  "request_id":"req-empty-001"
}
```

### 7.4 Required Backend lookup timeout — PROPOSED

Backend → AI: proposed POST/auth/content-type as 7.1, with
`X-Request-ID: req-timeout-001` and body:

<!-- schema: schemas/backend-api-contract-proposal.schema.json#/$defs/ChatRequest -->
```json
{"message":"Kiểm tra laptop còn hàng giá dưới 15 triệu VND giúp mình.","session_id":null,"history":[]}
```

AI → Backend: `GET /internal/ai/v1/products?q=laptop&max_price=15000000&currency=VND&limit=5`,
catalog service auth and `X-Request-ID: req-timeout-001`; no GET body.
No HTTP response is received before the proposed 3-second total read deadline.
The following is a documentation-only transport observation, **not a Backend
response, wire error payload or log containing user data**:

<!-- schema: schemas/backend-api-contract-proposal.schema.json#/$defs/TransportFailure -->
```json
{"dependency":"backend","operation":"product_search","failure":"timeout","elapsed_ms":3000,"request_id":"req-timeout-001"}
```

AI → Backend: HTTP 503, `Content-Type: application/json`,
`X-Request-ID: req-timeout-001`; no invented `Retry-After` if no backoff is known:

<!-- schema: schemas/backend-api-contract-proposal.schema.json#/$defs/ErrorResponse -->
```json
{
  "error":{"code":"BACKEND_TIMEOUT","message":"Chưa thể kiểm tra dữ liệu sản phẩm. Vui lòng thử lại sau.","retryable":true},
  "request_id":"req-timeout-001"
}
```

There are no product cards, price/stock claims or empty-search success in this
response. The existing tool-loop behavior alone does not implement this HTTP policy.

## 8. Decision Needed From Backend Team

Every row is **Pending**. Suggested values are for review, not approval or deployed
support. Backend and AI must record accepted revisions before live implementation.

| ID | Decision needed | Draft recommendation | Owner / impact if unresolved |
| --- | --- | --- | --- |
| D01 | Base URLs, method/path and API version | Proposed internal catalog `v1` routes above | Backend + AI / cannot implement endpoint mapping |
| D02 | Service auth, transport, scopes, credential lifecycle and delegated subject | Separate audience-bound service credentials; no self-declared user auth | Backend + platform + AI / cannot authenticate live calls |
| D03 | Product/variant IDs and allowed identifier syntax | Opaque case-sensitive IDs; decide model vs sellable SKU | Backend / ambiguous price/stock association |
| D04 | Visibility and missing/hidden records | Filter search; details 404 for invisible/missing; scope denial 403 | Backend / disclosure and error-mapping ambiguity |
| D05 | Query/category/filter semantics and ordering | Inclusive bounds, unknown category gives empty match, deterministic Backend order | Backend / search results cannot be interpreted reliably |
| D06 | Price amount/currency, precision, tax and promotions | Decimal strings; VND, zero fractional digits for MVP; explicit currency filters | Backend + AI / float DTO is not a final money contract |
| D07 | Availability states, freshness SLA and stale-data treatment | Four states with observation time; unknown is not in stock | Backend / unsupported live-availability claims |
| D08 | Specification names/units and approved product fields | Bounded allowlist; specs in details; no private fields | Backend + AI / schema/sanitization mapping blocked |
| D09 | Cursor lifecycle, ordering, page bounds and catalog changes | One AI page, limit ≤5, explicit next cursor, 422 expired cursor | Backend + AI / provider pagination DTO needs agreement |
| D10 | Future chat fields/statuses, versioning and coordinated rollout | Explicit future profile, preserve CURRENT until deployed replacement | Backend + AI / existing consumers cannot assume generated replies |
| D11 | Authorized history, session ownership, retention, logs and external-LLM data policy | Backend supplies only permitted history; no AI persistence or raw content logs | Backend + AI / personalized context cannot be enabled |
| D12 | Error envelope, 404 distinctions, downstream mappings and required-lookup failure policy | 503 on required catalog timeout; no 200 degraded/empty substitution | Backend + AI / outage can be mistaken for valid catalog evidence |
| D13 | Deadlines, response budgets, rate limits, `Retry-After` and retry policy | 35/30/5/3-second boundaries, bounded responses, zero automatic retries | Backend + platform + AI / failure/latency behavior not agreed |
| D14 | Correlation generation/propagation and safe log metadata | Validated `X-Request-ID`, header/body equality, no PII | Backend + AI / cross-service debugging inconsistent |
| D15 | Recommendation/user-context extensions and MVP exclusions | Catalog-only MVP; separate justified/authorized contracts for extensions | Backend + AI / no expanded data access or mutation authority |

## 9. Implementation gaps and short integration test plan

### Gaps — not changed by this documentation

| CURRENT implementation gap | Work needed only after approval |
| --- | --- |
| Public chat returns placeholder | Wire approved HTTP request/result/error profile to the agent and coordinate consumers |
| No service auth or correlation middleware | Implement agreed authentication, permissions, request-ID propagation and safe error handling |
| Internal tool money uses floats | Review DTO and precision-preserving conversion for approved decimal-string money; never use float for payments |
| Tool DTO lacks availability/provenance/time | Introduce approved fields and Backend source; current source validation rejects `backend` |
| Search provider returns only a product sequence | Extend provider result to preserve page/next-cursor and honest `truncated` semantics; do not fabricate an extra product to signal another page |
| Tool errors can yield advisory text; final agent result omits dependency outcomes | Carry required-lookup outcome/evidence to HTTP mapping so timeout cannot become 200 success |
| `catalog_verified=False` and unavailable prompt/notice | Review live-grounding semantics and prompt capability wording; do not flip a boolean merely because one tool succeeded |
| Backend client has no route/auth methods and per-operation timeout only | Implement approved fixed paths, strict response validation and total deadlines |

After both teams approve, use deterministic provider/LLM mocks plus a separate
agreed Backend staging environment. The minimum integration matrix is:

1. Keep CURRENT health/recommendation/chat tests until the coordinated profile
   change; then validate approved requests/responses and consumer compatibility.
2. Service auth missing/invalid/expired, wrong audience/scope, forged user headers,
   session ownership and hidden products; no unauthorized field reaches the LLM.
3. Search filters/currency/price bounds, lookup/specs, null price, unknown availability,
   empty matches, missing product, wrong product ID and cursor continuation/expiry.
4. Invalid JSON/schema/private fields, non-2xx, own/downstream 429 and safe
   `Retry-After`, service-account 401/403 versus verified user denial.
5. 3-second Backend read failure within 5-second tool and 30-second agent budgets,
   cancellation/disconnect, required-lookup HTTP 503, no fabricated fallback or retry.
6. End-to-end header/body request IDs, bounded payloads/calls, source/evidence/card
   consistency and safe logs. No cart/payment mutation or direct database access.

These are planned tests, not executed Backend integration evidence.

### Documentation verification

The [schema bundle](schemas/backend-api-contract-proposal.schema.json) uses JSON
Schema Draft 2020-12 (compatible with OpenAPI 3.1 schema concepts), not a deployed
OpenAPI server description. Validate each annotated JSON block against its named
`$defs` using a Draft 2020-12 validator with date-time format checking. Parse every
JSON block, including CURRENT examples, for syntax. Check links/anchors and run
`git diff --check`; docs-only changes need no application dependency changes.

Also check semantic invariants: history pairs, numeric price ordering, requested
page limits, unique product IDs, empty-page cursors, matching lookup IDs, correlation
continuity, and cards matching Backend evidence. Schema validation alone cannot
compare independent HTTP messages or prove model factuality. No live endpoints,
Backend services or new auth behavior are exercised by these documentation checks.
