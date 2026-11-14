# Backend catalog integration — SWE-165 (implemented)

The existing `ShoppingAgent` now uses `BackendProductProvider` through the existing
`search_products` and `get_product_details` tools. Application lifespan wires it as
`app.state.shopping_agent`, using `app.state.backend_client` and the existing LLM
adapter. Construction performs no network I/O. Standalone callers can inject the
same provider into `create_product_tools(provider)`.

## Backend inspection and contract differences

Inspected **Adiff-git/Backend-SWE main at
`e2bd5478bcf7580aebb240507186e34c5a8620a8`**. Source references below are relative to
`demo/src/main/java/com/example/demo/` in that repository:

- `catalog/controller/ProductCatalogController.java`: actual routes and UUID validation.
- `catalog/search/ProductSearchParameterParser.java` and
  `catalog/dto/request/ProductSearchRequest.java`: parameter names, pagination,
  whole-VND filters, accepted sort/filter syntax.
- `catalog/dto/response/{ProductPage,ProductSummary,ProductListingItem,ProductDetail,
  CategorySummary,SellingPrice,VariantSummary,ProductImageSummary}.java` and
  `catalog/converter/ProductCatalogConverter.java`: actual response representations.
- `catalog/validator/TechnicalSpecificationValidator.java`: versioned typed specs.
- `catalog/service/ProductCatalogServiceImpl.java`: published-product visibility,
  variant ownership and publication rechecks; details do not supply stock state.
- `common/security/CatalogSecurityConfiguration.java`: catalog GETs permit public access.
- `common/exception/ApiError.java` and `catalog/exception/ProductNotFoundException.java`:
  actual ProblemDetail errors. Backend `ProductDetailApiIT` also checks large integer
  VND amounts, variant specifications and signed image URLs.

| Concern | SWE-69 draft | Actual Backend / implemented adapter |
| --- | --- | --- |
| Routes | `/internal/ai/v1/products[/{product_id}]` | `GET /api/products` and `GET /api/products/{id}` |
| Authentication | Proposed service credential/scopes | Existing public catalog GETs; no user/token forwarding or new credential mechanism |
| IDs | Arbitrary opaque strings | Canonical lowercase UUID product/category IDs; preserved without normalization; variant IDs remain distinct |
| Search | `q`, `category_id`, `min_price`, `max_price`, `currency`, `limit`, `cursor` | `q`, `categoryId`, `minPrice`, `maxPrice`, `page=0`, `size<=5`; no `currency` parameter |
| Pagination | Cursor envelope | `items`, `page`, `size`, `totalItems`, `totalPages`; one page only |
| Category | ID/null | Required `{id,name}` mapped separately to `category` and `category_name` |
| Listing price | Decimal-string flat product price | `displayPrice` integer VND plus paired `representativeVariantId`, both nullable |
| Details | `product` envelope, flat price/specs | Bare product with `variants[].sellingPrice`, `options`, `technicalSpecifications` |
| Specifications | String map | `{schema_version:1, values:{...}}`; strings, booleans, numbers and `{value,unit}` quantities |
| Images | Not specified | Nullable `primaryImageUrl`, details `images[].url`; display-only HTTP(S) URLs, never fetched |
| Availability / freshness | States and observation timestamps | Absent; never inferred from publication, images, variants or a successful GET |
| Missing product | `PRODUCT_NOT_FOUND` envelope | HTTP 404 ProblemDetail, `detail="Product not found"`, matching `instance` and `status=404` |

The [SWE-69 proposal](backend-api-contract-proposal.md) and its JSON Schema remain
**unapproved future proposals**. This adapter targets the actual public API and does
not establish approval or implementation of the draft internal routes or HTTP chat profile.

## Implemented mapping and limits

- Money is parsed without binary floats. Backend integer amounts up to 30 digits
  are converted directly to `Decimal`; Agent tool JSON emits decimal **strings**.
  Tool filters accept exact JSON numbers or decimal strings and retain the existing
  `0..1e15` bounds and explicit-currency rule. Only whole-VND filters are supported
  by this Backend; unsupported currencies, fractional VND and non-UUID categories
  return `unsupported_filter` before HTTP. No conversion or ignored filter occurs.
- Listing price retains its representative variant ID. Details retain each
  variant's ID, SKU, options, price and specifications. For a single variant, its
  price/specs are also exposed at product level with that variant ID. For multiple
  variants, product-level price is null and specs are empty: callers compare the
  explicit variant data rather than assuming one variant describes all others.
- Numeric specs use exact decimal formatting; quantities keep their explicit units;
  booleans become `true`/`false` text. Unknown/invalid document shapes are rejected.
  No unit, stock, promotion or warranty is synthesized.
- Projection caps: five products, five variants, five gallery URLs, ten specs per
  variant, ten option pairs per variant, 2,048 characters per image URL. Existing
  bounded product text validation still applies. Omitted variants/images/specs have
  explicit `*_truncated` flags. Search `truncated` uses Backend totals, including
  short pages after publication rechecks, without a fabricated sentinel product.
  Wider product text/options that cannot fit validated tool schemas fail closed.
- Only allowlisted fields reach the model. Descriptions, raw errors, supplier/private
  fields and storage internals are not selected. Catalog text remains untrusted
  tool-role data, even when its source is authoritative.
- The shared HTTPX client retains configured timeouts and connection pooling.
  Catalog reads stream at most **64 KiB decoded bytes**; non-success response hooks
  also preserve only bounded error bodies on HTTPX exceptions. No redirects,
  retries, automatic pagination, arbitrary URL fetches or database access.
- Existing tool/agent budgets remain: 5-second total tool deadline, 30-second agent
  deadline, 2 rounds, 2 calls/reply, 4 calls total, 3 LLM turns, 4 KiB arguments,
  8 KiB results, 32,000-character tool context. HTTPX's configured operation timeout
  is bounded by enclosing deadlines. Oversized tool results fail explicitly.
- Comparison uses repeated `get_product_details` calls for product IDs, including
  two calls in one reply. No comparison tool or business mutation is introduced.

## Outcomes and evidence

Tool `source` is `backend`, `fake` or `unavailable`; it identifies provenance, not
success. A validated empty search is `ok`; a matching Backend product ProblemDetail
404 is `not_found`. An HTML/proxy/unknown 404 is `invalid_result`. Malformed JSON,
duplicate keys, invalid schemas, mismatched IDs and oversized payloads are also
`invalid_result`. Connection/HTTP failures produce `backend_unavailable`; HTTPX
timeouts and tool deadlines produce `timeout`. Error text/bodies are not returned
to the LLM. Missing provider behavior remains `not_available`.

`AgentResult.catalog_evidence` contains up to four request-local validated tool
outcomes. `catalog_verified=True` means **every attempted lookup in this turn** was
from Backend with `ok` or `not_found`, with at least one lookup. This includes an
empty or missing outcome, not a claim that a product was found. It does **not**
certify every sentence of generated advice. No lookups, fake/unavailable data or any
failed lookup leave it false. Mixed success/failure retains individual evidence and
uses a partial-evidence notice; verified Backend data is not labeled fake or wholly
unverified. Evidence is never reused for a later request.

Prompt **1.2.0** explains these sources, variant associations, comparison, truncation,
money and missing-field boundaries. Tool data cannot become system instructions.

## Team decisions still pending

Inspection establishes current behavior, not team approval of the future contract:

| SWE-69 decisions | What still needs agreement |
| --- | --- |
| D01, D02, D04 | Whether to introduce internal/versioned service-authenticated routes or retain public published-catalog reads; deployment URL and delegated visibility/pricing scope |
| D03, D05, D08 | Product-versus-variant presentation policy, category discovery, additional brand/spec filters and field/variant/spec projection priorities; current adapter preserves Backend associations |
| D06, D07 | Tax/promotion semantics, currencies beyond current whole VND, availability/freshness fields and guarantees; no supported observation timestamp currently exists |
| D09 | Any future cursor API/lifecycle; current numbered-page behavior is implemented |
| D10–D12 | Generated-answer HTTP contract, authorized history/session ownership, external-LLM data policy, public error envelope and required-lookup failure policy |
| D13, D14 | Revised coordinated deadlines/rate limits/Retry-After policy and request-ID propagation; current limits remain implemented |
| D15 | Any future extension beyond read-only catalog advice |

The public `/api/v1/chat` route still returns its existing placeholder. Wiring a
generated-answer HTTP route and its required-lookup failure policy requires the
separate contract decision above. Cart, checkout, payment and autonomous shopping
are outside this implementation.

## Verification and operational blockers

`tests/test_backend_products.py` exercises the real provider and shared HTTPX hooks
with synthetic DTOs and mocked HTTP: filters, money beyond binary-float precision,
categories, images, single/multiple variants, typed specs, truncation, empty/missing
results, invalid payloads/IDs, redirects/status failures, network errors and deadline
cancellation. It also runs the existing ShoppingAgent with the real LLM adapter and
mocked HTTP for two-product comparison, partial failure and request-local evidence.
Existing tool-loop/security-boundary tests remain in the full suite.

Run `uv run ruff check .` and `uv run pytest`. These are deterministic integration
tests, not a deployed two-service/staging run or a live-model grounding evaluation.
A reachable Backend deployment/base URL and configured tool-capable LLM are needed
for live use. Pending HTTP/auth/data-policy decisions above are rollout follow-ups,
not presumed approvals created by this change.
