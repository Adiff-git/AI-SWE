# API contracts — CURRENT behavior and proposed integration

The routes and placeholder payloads labeled **CURRENT** below are implemented.
They are not completed recommendation/chat features. Future Backend integration
is **PROPOSED**, not deployed or approved. See the review-ready
[SWE-69 Agent–Backend Integration Contract](backend-api-contract-proposal.md), its
[draft schema](schemas/backend-api-contract-proposal.schema.json), and the
[Decision Needed From Backend Team table](backend-api-contract-proposal.md#8-decision-needed-from-backend-team).
Creating this proposal does not enable live Backend access or replace CURRENT APIs.

All current routes use JSON. Interactive schema documentation is at `/docs`,
with the generated contract at `/openapi.json`.

## Health — CURRENT

`GET /api/v1/health` returns HTTP 200:

```json
{"status": "ok"}
```

This checks application liveness only, with no external dependency checks.

## Recommendations — CURRENT placeholder

`POST /api/v1/recommendations`

```json
{"user_id": "123", "limit": 10}
```

- `user_id`: required opaque string, 1–128 characters after trimming whitespace.
- `limit`: optional strict integer, default 10, range 1–100.
- Unknown fields are rejected. Backend must authorize the user ID before calling.

Current HTTP 200 response:

```json
{"product_ids": [], "status": "not_implemented"}
```

An empty array here means the feature is unfinished, not that a recommendation
algorithm found no matches. No personalization or user existence check runs.

Proposed future result data:

```json
{"product_ids": ["product_101", "product_205"]}
```

Real identifiers, ordering/ranking, eligibility (stock/promotions), response
status fields, cold-start behavior and failure semantics require team agreement.
The current literal status schema must change when actual functionality is added.

## Chat — CURRENT placeholder

`POST /api/v1/chat`

```json
{"message": "Recommend a laptop for programming", "session_id": null}
```

- `message`: required string, 1–4000 characters after trimming whitespace.
- `session_id`: optional, defaults to null; if provided as a string, 1–128
  characters after trimming whitespace.
- Unknown fields are rejected.

Current HTTP 200 response:

```json
{
  "status": "not_implemented",
  "message": "AI shopping assistance is not implemented yet.",
  "session_id": null
}
```

The message is a fixed capability notice, not an AI-generated answer. A supplied
session ID is echoed only: no session is created, authenticated, loaded or stored.
Future response fields, product references, session ownership, retention and
streaming decisions need agreement. This endpoint does not invoke an LLM, RAG or
product search.

SWE-66 adds an independent `ShoppingAgent` core that can call the SWE-65 LLM
interface. Its internal `AgentTurn`/`AgentResult` models are not new HTTP payloads.
The core uses caller-supplied request-local history, echoes an opaque session ID
without storing it, and returns advisory text explicitly labeled as unverified
because catalog access is unavailable. Its exception hierarchy is not mapped to
HTTP responses yet. Enabling generated answers requires a separate agreement on
success/error shapes, authorized history and grounding; the current route, schema,
fixed message and status remain unchanged.

SWE-68 adds internal read-only `search_products` and `get_product_details` tool
definitions and a bounded tool-calling loop. These are not new HTTP routes or
confirmed Backend endpoints. The default source is unavailable; test sources are
explicitly fake. Product DTOs, filters, price/currency representation and error
codes are internal contracts only. Real integration remains blocked on SWE-69
approval of Backend paths, authorization, payloads and failure semantics. See
[tool interfaces](tools.md) for the proposed provider mapping boundary.

## Validation and error boundary — CURRENT

Both POST endpoints return FastAPI HTTP 422 validation responses for missing,
malformed, out-of-range or unexpected input. Clients should use `detail` entries
and their `loc`/`type` fields; exact error messages can vary by dependency version.

HTTP 200 plus `not_implemented` is deliberate for this scaffold. Consumers must
inspect status and must not display a placeholder as a completed AI result.
No upstream errors occur in these endpoints because they do not call Backend.
Agree future timeout/unavailability/rate-limit mapping before enabling outbound
requests. The Backend client raises HTTPX exceptions and does not silently return
empty product data on failure.

## Proposed Backend capabilities — not existing endpoints

| Capability | Scope/status | Proposal and agreement required |
| --- | --- | --- |
| Product search/filter | PROPOSED read-only MVP | Query/category, explicit currency/price bounds, cursor pagination, visibility and authoritative product fields |
| Product details/specifications | PROPOSED read-only MVP | Opaque product/variant IDs, price representation, availability/freshness and bounded specs in details |
| Personalized recommendations | Deferred beyond catalog MVP | Agreed use case, product eligibility/ranking and authorized subject/data contract; CURRENT recommendation route stays a placeholder |
| User search/interaction history | Deferred beyond catalog MVP | Explicit justification, Backend authorization, consent, minimal fields and retention; no new user-data route proposed |

The [SWE-69 draft](backend-api-contract-proposal.md) is the canonical future proposal
for paths, fields, schemas, examples and error mappings. Its example paths are not
existing Backend endpoints. Specifications are proposed inside details. Backend
remains the source of truth and owns history collection/business authorization;
AI neither records replacement business tables nor connects to Backend's database.

## Decisions to agree before implementation

All D01–D15 decisions in the
[Backend Team decision table](backend-api-contract-proposal.md#8-decision-needed-from-backend-team)
are pending. In particular, draft chat success/error envelopes, service auth,
correlation IDs, 3-second Backend read budget and HTTP 503 for required catalog
timeouts are proposals, not CURRENT behavior. The draft also records implementation
gaps between SWE-68 DTOs and the target contract, plus an integration test plan.
