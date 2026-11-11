"""Representative content checks, not human relevance metrics."""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from ai_service.recommendation.engine import rank
from ai_service.recommendation.inference import InferenceRequest, Product


def test_sanitized_catalog_category_consistency():
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/recommendation_content.json").read_text()
    )
    products = [Product(productId=UUID(int=i + 1), **p) for i, p in enumerate(fixture["products"])]
    checks = []
    for source in products:
        request = InferenceRequest(
            candidates=products,
            sourceProductId=source.productId,
            asOf=datetime(2026, 11, 10, tzinfo=UTC),
            limit=5,
        )
        result = rank(request)
        assert len(result.items) == len({r.productId for r in result.items}) == 5
        assert source.productId not in {r.productId for r in result.items}
        category = {p.productId: p.category for p in products}
        checks.append(category[result.items[0].productId] == source.category)
    # Exact category signal is an engineering expectation on this fixed sanitized corpus.
    assert all(checks), f"Top alternative category matched in {sum(checks)}/{len(checks)} checks"
