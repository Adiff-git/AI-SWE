# Hybrid recommendation MVP

The single FastAPI application serves protected request-scoped inference. Backend owns
identity, current wishlist, behavior, prices, publication, media, and final DTO hydration.
AI has no PostgreSQL connection and never stores incoming behavior. The legacy
`/api/v1/recommendations` scaffold remains unchanged for compatibility; frontend uses Backend.

## Canonical contract v1

`src/ai_service/recommendation/inference.py` and its generated `/openapi.json` are the
canonical schema. Backend documentation links here rather than maintaining a second schema.
`POST /internal/recommendations/personalized` or `/similar`, with
`X-Recommendation-Key` service credential (never a Customer JWT).
Body: `candidates`, `recentEvents`, `wishlist` (current candidate UUID memberships),
`sourceProductId` (null for personalized), `asOf` (timezone-aware Backend clock), `limit`.
Candidates carry Backend-owned `productId`, name, category, brand, representative price
(VND or null), bounded description and aggregate popularity. Event fields: eventType,
productId or normalized query, occurredAt. No customerId or personal account fields.
Similar requests have a source in candidates and no events/wishlist.
Response: `{ "items": [{ "productId": "UUID", "score": 0.72 }] }`.
All objects forbid unexpected properties; candidates <=3000, events <=500, wishlist <=3000,
limit 1..20, streamed body <=12 MB. Invalid payloads return sanitized 422 errors,
oversize 413, invalid credentials 401, absent/short configured key 503 (fail closed).

## Ranking

scikit-learn TF-IDF, sublinear term frequency, L2 normalization and cosine similarity.
Text: product name twice, category, brand, description <=2000 characters. Unicode NFD,
lowercase, Vietnamese diacritic removal and đ->d; punctuation separates alphanumeric
model tokens, without replacing model identifiers. This matches Backend accent/case
normalization, with a conservative word tokenizer rather than Backend search's numeric parser.
Empty vocabulary produces zero text similarity. No specifications are included: current
source data does not establish blanket reliability. Price remains a separate numeric signal.
Content score = .55 cosine + .25 equal category + .08 equal brand + .12 price ratio.
Price ratio = min/max for two positive prices; otherwise 0. Missing fields never match.
Categories matter strongly but do not prohibit cross-category results.

Behavior: views 2, clicks 3, searches 1, current wishlist 5. Events outside [asOf-90d,asOf]
are ignored. Each event decays by 2^(-ageDays/21); summed decayed influence per
(type,product,normalized query) capped at 3. Weighted content signals are averaged.
Search uses cosine only when every exact normalized query token occurs in the candidate;
no fuzzy matching or assumption that a search identifies a product.
Wishlist history is deliberately preference-reducing through removal of current membership,
not a permanent negative penalty: current membership overrides all add/remove ordering.
This handles add/remove/add and membership older than retained events.
Popularity contributes .10 times normalized log1p aggregate score. Backend caps counts at
3 per Customer/product/type over 90d before applying views 2/clicks 3/adds 5.
Without usable interests, normalized popularity at full scale plus deterministic UUID ties
supplies cold start.

Greedy selection subtracts .08 for each previously selected same brand and .04 for each
same category, with each repetition count capped at 2. This prevents cumulative
penalties from eventually overwhelming relevance. Soft penalties preserve high relevance and improve variety without strict
quotas. Stable UUID tie-breaking; no randomness. Similar uses content score and excludes source.
Weights are centralized in immutable `Weights`; override named fields through
`RECOMMENDATION_WEIGHTS` JSON (0..100; half_life_days >0). Invalid config fails startup.
No global customer state, external vector store, training, Redis or persistent cache.
TF-IDF is fit per snapshot; normalized metadata is precomputed and numeric scoring is vectorized; per-request source
and query similarities are cached up to 500 entries. Saturated repeats skip further work.

## Security and startup

Run from AI-SWE: `uv sync --locked`, then set `RECOMMENDATION_SERVICE_KEY` to a freshly
generated random value with at least 32 characters, shared only with Backend.
`HOST=127.0.0.1 uv run ai-service` starts local inference on 8001.
Compose binds the host port to loopback. Deployment must deny internet ingress to
`/internal/*`, restrict network access to Backend, and use TLS or a trusted private network
behind TLS termination. Shared credentials authenticate services; rotate them together.
Never log service keys or request bodies. Body validation errors do not echo inputs.

## Verification and limits

`uv run pytest` and `uv run ruff check src tests`.
Synthetic expectation suite: gaming/office laptops, phone, tablet, brand/price, conflicts,
search-only, new Customer, sparse/identical metadata, repeat caps, retention/decay,
wishlist state, diversity, concurrent isolation and protected API invalid input.
These are reproducible engineering expectations, not human relevance labels or accuracy.
Backend `RecommendationHttpIT` starts this real service with 1500 synthetic Backend UUID
products in a disposable PostgreSQL container and calls Backend over real HTTP.
See Backend evidence for measured stages, cold/warm calls and outage fallback.

Limitations: no human-reviewed relevance labels, online quality assessment or browser
instrumentation. Generic category/brand names can be incomplete; description truncation
and exact-token search reduce recall. Repeated snapshot fitting costs CPU; measure before
adding caching. Latest 500 events bound recent history; extreme activity may crowd out
older diverse interests. Catalog capacity is 3000, explicitly surfaced rather than silently
ranking an arbitrary page. No production-readiness claim.

Benchmark: `uv run python scripts/benchmark_recommendation.py` measures 1500 synthetic products
with 2, 50 and 500 distinct events. No timing assertions or relevance quality claim.
