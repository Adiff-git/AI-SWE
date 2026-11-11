"""Synthetic 1500-product workload; timings are observations, never quality/latency claims."""

import json
from datetime import UTC, datetime
from time import perf_counter
from uuid import UUID

from ai_service.recommendation.engine import rank
from ai_service.recommendation.inference import Event, InferenceRequest, Product

now = datetime(2026, 11, 10, tzinfo=UTC)
products = [
    Product(
        productId=UUID(int=i + 1),
        name=f"Laptop RTX {i}",
        category="Laptop",
        brand="Dell" if i % 2 else "Asus",
        price=15000000 + i * 1000,
    )
    for i in range(1500)
]
results = {}
for count in (2, 50, 500):
    request = InferenceRequest(
        candidates=products,
        recentEvents=[
            Event(eventType="PRODUCT_VIEW", productId=p.productId, occurredAt=now)
            for p in products[:count]
        ],
        asOf=now,
    )
    times = []
    for _ in range(3):
        start = perf_counter()
        result = rank(request)
        times.append(round((perf_counter() - start) * 1000, 3))
        assert len(result.items) == len({p.productId for p in result.items}) == 10
    results[f"1500_products_{count}_distinct_events_ms"] = times
print(json.dumps(results, indent=2))
