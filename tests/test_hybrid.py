from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID

import numpy as np
import pytest
from pydantic import ValidationError
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from ai_service.core.config import get_settings
from ai_service.recommendation.engine import Weights, normalize, price_similarity, rank
from ai_service.recommendation.inference import Event, InferenceRequest, Product

NOW = datetime(2026, 11, 10, tzinfo=UTC)


def product(i, name, category="Laptop", brand="Dell", price=15000000, **kwargs):
    return Product(
        productId=UUID(int=i), name=name, category=category, brand=brand, price=price, **kwargs
    )


@pytest.fixture
def catalog():
    return [
        product(1, "Gaming RTX laptop"),
        product(2, "Gaming RTX laptop", brand="Asus"),
        product(3, "Office lightweight laptop", price=8000000),
        product(4, "Samsung smartphone", "Smartphone", "Samsung", 7000000),
        product(5, "Apple tablet", "Tablet", "Apple", 10000000),
    ]


def request(catalog, events=(), wishlist=(), source=None, limit=5):
    return InferenceRequest(
        candidates=catalog,
        recentEvents=events,
        wishlist=wishlist,
        sourceProductId=source,
        asOf=NOW,
        limit=limit,
    )


def event(kind, i=None, days=0, query=None):
    return Event(
        eventType=kind,
        productId=UUID(int=i) if i else None,
        query=query,
        occurredAt=NOW - timedelta(days=days),
    )


def ids(result):
    return [item.productId.int for item in result.items]


def test_tfidf_cosine_and_model_tokens():
    assert normalize("Điện thoại RTX-4060 A51") == "dien thoai rtx 4060 a51"
    matrix = TfidfVectorizer().fit_transform(
        [normalize("Gaming RTX 4060"), normalize("Gaming RTX 4060"), "tablet apple"]
    )
    similarity = cosine_similarity(matrix)
    assert similarity[0, 1] == pytest.approx(1)
    assert similarity[0, 2] == 0
    assert np.isfinite(similarity).all()


def test_similar_category_and_source(catalog):
    result = ids(rank(request(catalog, source=UUID(int=1))))
    assert result[0] == 2
    assert 1 not in result
    assert len(result) == len(set(result)) == 4


@pytest.mark.parametrize("i", [1, 3, 4, 5])
def test_product_view_interests(catalog, i):
    assert ids(rank(request(catalog, [event("PRODUCT_VIEW", i)])))[0] == i


def test_search_only_exact_conservative(catalog):
    assert ids(rank(request(catalog, [event("SEARCH", query="smartphone samsung")])))[0] == 4
    baseline = rank(request(catalog))
    assert rank(request(catalog, [event("SEARCH", query="samsnug")])) == baseline


def test_brand_and_price():
    products = [
        product(1, "Laptop"),
        product(2, "Laptop", brand="Dell"),
        product(3, "Laptop", brand="HP"),
        product(4, "Laptop", price=100000000),
    ]
    scores = {i.productId.int: i.score for i in rank(request(products, source=UUID(int=1))).items}
    assert scores[2] > scores[3]
    assert scores[2] > scores[4]
    assert price_similarity(10, 20) == 0.5
    assert price_similarity(None, 20) == price_similarity(0, 20) == 0


def test_weights_decay_and_expiry(catalog):
    recent = rank(request(catalog, [event("PRODUCT_VIEW", 1), event("PRODUCT_VIEW", 4, days=80)]))
    assert ids(recent)[0] == 1
    assert rank(request(catalog, [event("PRODUCT_VIEW", 4, days=91)])) == rank(request(catalog))
    assert rank(request(catalog, [event("PRODUCT_VIEW", 4, days=-1)])) == rank(request(catalog))
    conflicting = [event("PRODUCT_VIEW", 4), event("PRODUCT_CLICK", 1)]
    assert ids(rank(request(catalog, conflicting), Weights(view=20, click=1)))[0] == 4


def test_duplicate_event_cap(catalog):
    a = rank(request(catalog, [event("PRODUCT_VIEW", 4)] * 3))
    b = rank(request(catalog, [event("PRODUCT_VIEW", 4)] * 500))
    assert a == b


def test_wishlist_order_and_current_state(catalog):
    history = [
        event("WISHLIST_ADD", 4, days=3),
        event("WISHLIST_REMOVE", 4, days=2),
        event("WISHLIST_ADD", 4, days=1),
    ]
    assert ids(rank(request(catalog, history, wishlist=[UUID(int=4)])))[0] == 4
    assert rank(request(catalog, history)) == rank(request(catalog))
    assert rank(request(catalog, history, wishlist=[UUID(int=4)])) == rank(
        request(catalog, wishlist=[UUID(int=4)])
    )


@pytest.mark.parametrize("name", ["!!!", "X", "Identical product"])
def test_sparse_identical_missing(name):
    products = [product(i, name, category=None, brand=None, price=None) for i in range(1, 4)]
    result = rank(request(products, source=UUID(int=1)))
    assert ids(result) == [2, 3]
    assert all(np.isfinite(p.score) for p in result.items)


def test_cold_popularity_ties_limits(catalog):
    assert ids(rank(request(catalog, limit=2))) == [1, 4]
    catalog[4] = catalog[4].model_copy(update={"popularity": 20})
    assert ids(rank(request(catalog)))[0] == 5
    assert rank(request([])).items == []
    assert rank(request([catalog[0]], source=UUID(int=1))).items == []


def test_diversity():
    products = [product(i, "Laptop", brand="Dell" if i < 5 else "HP") for i in range(1, 7)]
    assert ids(rank(request(products, limit=2))) == [1, 5]


def test_concurrent_profiles_isolated(catalog):
    requests = [request(catalog, [event("PRODUCT_CLICK", 4 if i % 2 else 1)]) for i in range(24)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        actual = list(pool.map(rank, requests))
    assert [ids(r)[0] for r in actual] == [4 if i % 2 else 1 for i in range(24)]


@pytest.mark.parametrize(
    "update",
    [
        {"limit": 0},
        {"limit": 21},
        {"limit": True},
        {"customerId": "secret"},
        {"asOf": "2026-11-10T00:00:00"},
    ],
)
def test_invalid_contract(catalog, update):
    payload = request(catalog).model_dump()
    with pytest.raises(ValidationError):
        InferenceRequest.model_validate(payload | update)


def test_internal_api_auth_payload_bounds(client, monkeypatch, catalog):
    monkeypatch.setenv("RECOMMENDATION_SERVICE_KEY", "x" * 40)
    get_settings.cache_clear()
    payload = request(catalog).model_dump(mode="json")
    path = "/internal/recommendations/personalized"
    try:
        assert client.post(path, json=payload).status_code == 401
        headers = {"X-Recommendation-Key": "x" * 40}
        assert client.post(path, json=payload, headers=headers).status_code == 200
        response = client.post(path, json=payload | {"customerId": "sensitive"}, headers=headers)
        assert response.status_code == 422
        assert "sensitive" not in response.text
        assert client.post(path, content=b"x" * 12_000_001, headers=headers).status_code == 413
        assert (
            client.post(
                "/internal/recommendations/similar", json=payload, headers=headers
            ).status_code
            == 422
        )
        monkeypatch.delenv("RECOMMENDATION_SERVICE_KEY")
        get_settings.cache_clear()
        assert client.post(path, json=payload).status_code == 503
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize(
    "update",
    [
        {"price": -1},
        {"price": float("inf")},
        {"price": float("nan")},
        {"popularity": -1},
        {"name": ""},
        {"technicalSpecifications": {"unapproved": "fact"}},
    ],
)
def test_invalid_candidate_attributes(update):
    payload = product(1, "Laptop").model_dump() | update
    with pytest.raises(ValidationError):
        Product.model_validate(payload)


def test_snapshot_and_event_bounds(catalog):
    with pytest.raises(ValidationError):
        request(catalog + [catalog[0]])
    with pytest.raises(ValidationError):
        request(catalog, [event("PRODUCT_VIEW", 1)] * 501)
    with pytest.raises(ValidationError):
        request(catalog, wishlist=[UUID(int=999)])
    for invalid in [
        {"eventType": "SEARCH", "query": "   ", "occurredAt": NOW},
        {"eventType": "PRODUCT_VIEW", "occurredAt": NOW},
        {"eventType": "PRODUCT_VIEW", "productId": UUID(int=1), "query": "leak", "occurredAt": NOW},
    ]:
        with pytest.raises(ValidationError):
            Event.model_validate(invalid)


def test_unusable_wishlist_content_uses_full_popularity_fallback():
    products = [
        product(1, "!!!", category=None, brand=None, price=None),
        product(2, "???", category=None, brand=None, price=None, popularity=10),
    ]
    assert rank(request(products, wishlist=[UUID(int=1)])) == rank(request(products))
