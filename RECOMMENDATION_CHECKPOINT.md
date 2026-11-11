# Recommendation checkpoint
Current branch: features/AIRecommendation. Integration contract: v1, canonical
AI-SWE/src/ai_service/recommendation/inference.py; generated internal OpenAPI agrees.
Completed: request-local hybrid TF-IDF, configurable scoring, bounded recent interests,
authoritative wishlist state, popularity/diversity, protected keyed inference; Backend 3 APIs,
strict result validation and publication/variant/media-safe batch hydration, documentation.
Files changed: see docs/recommendation-verification.md and git diff --cached --stat.
Tests passed: AI 255 + Ruff; Backend complete serial mvnw verify 752 distinct cases
(357 unit +395 IT), zero failures/errors/skips. Real 1500-product two-service HTTP passed:
JWT owner data, minimized payload, general/cold start, similar, source exclusion, 401 and outage.
Latest full-run first133ms, warm71-105ms, AI47-52ms, hydration2-5ms, outage46ms;
500-event standalone engine242-251ms. Synthetic/local observations, no quality/SLO claims.
Resolved failures: fixture option constraints/stubbing, unbounded diversity penalty, missing
empty-vocabulary wishlist fallback, and initial full-run JDK spawn-helper mismatch after
in-place JDK25.0.4.1->25.0.5.0.3 update. Final full regression used fresh JVM and passed.
Remaining blockers: none. Next: final staged review, independent feature commits, local merges
(AI main; Backend draft/version-1), postmerge focused/HTTP tests, update this checkpoint.
No push/deployment. Catalog-Data read-only c5dcfaa. No historical/new migrations modified.
NOT VERIFIED: deployed browser/production load/network. DEFERRED: human relevance evaluation,
unapproved technical-specification features. Frontend instrumentation remains outside scope.
