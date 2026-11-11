# Recommendation verification evidence (2026-11-11)

AI: Python 3.12, FastAPI, Pydantic v2, scikit-learn TF-IDF/cosine, NumPy/SciPy.
Backend: Java 25, Spring Boot 4.1.2, Spring Security JWT, JPA/JDBC, PostgreSQL 17 Testcontainers, Flyway V20.
No new migration, persistent customer state, dataset ID mapping or database access from AI.

Tests: `uv run --locked pytest -q` -> 255 passed, zero failures/errors; Ruff passes.
One existing Starlette warning advises a future httpx2 migration; no assertions are skipped.
Compose configuration validates with an ephemeral environment credential.

## Evaluation

`tests/test_hybrid.py` checks controlled gaming/office laptop, smartphone, tablet,
brand/price, conflicting/repeated/old signals, exact search, cold start, diversity,
wishlist state and concurrent isolation. `tests/test_recommendation_corpus.py`
checks 90 sanitized real titles (10 per each of 9 source categories), excluding source,
no duplicate output, and same-category top alternative in 90/90 checks. Source category
and proposed brand metadata are fixture assumptions, not human relevance judgments.
Catalog-Data c5dcfaa was read only; no source IDs/prices/specifications copied.
No precision, recall, NDCG or accuracy claim.

## Engine performance observation

Reproducible: `uv run python scripts/benchmark_recommendation.py`.
1500 synthetic products; all timings milliseconds, 3 independent request-scoped fits:

| Distinct product events | Observations |
|---|---|
| 2 | 36.343, 36.323, 36.599 |
| 50 | 106.936, 62.997, 57.461 |
| 500 | 250.648, 242.431, 242.797 |

Initial 500-event run took 5460.894ms before precomputing normalized metadata and
vectorizing category/brand/price signals; these changes preserve ranking expectations.
Timings include TF-IDF fitting, not process startup or HTTP. They are observations on
this local machine, not production SLOs. No cross-request feature cache was required.

## Full system verification

See [Backend verification](../../Backend-SWE/docs/recommendation-verification.md) for
serial regression results, actual Backend HTTP -> FastAPI -> sklearn verification,
1500 Backend-owned fixture products, final HTTP measurements, hashes and limitations.

## Changed AI files

- `.env.example`
- `README.md`
- `RECOMMENDATION_CHECKPOINT.md`
- `compose.yaml`
- `docs/SWE-62-recommendation-data-requirements.md`
- `docs/SWE-63-recommendation-architecture.md`
- `docs/SWE-64-recommendation-baseline-design.md`
- `docs/api-contracts.md`
- `docs/architecture.md`
- `docs/backend-api-contract-proposal.md`
- `docs/recommendation-verification.md`
- `docs/recommendation.md`
- `pyproject.toml`
- `scripts/benchmark_recommendation.py`
- `src/ai_service/core/config.py`
- `src/ai_service/main.py`
- `src/ai_service/recommendation/engine.py`
- `src/ai_service/recommendation/inference.py`
- `src/ai_service/recommendation/internal_router.py`
- `tests/fixtures/recommendation_content.json`
- `tests/test_health.py`
- `tests/test_hybrid.py`
- `tests/test_recommendation_corpus.py`
- `uv.lock`

## Local integration and postmerge verification

Feature commit `ac6a6ee4291cabdce9a458de68e84f9d99f8f221`; merge commit `f57856d3c06dd68ef04ca7b5af57441f3d4b6f9f` into `main`.
Feature branch retained; 255 AI tests pass again on merged code, Ruff passes.
Backend merged independently into draft/version-1 with 752 full-regression tests and
357 unit +167 selected postmerge IT cases passing, including actual HTTP/AI outage verification.
No push/deployment; final documentation-only commit records evidence and checkpoints.
