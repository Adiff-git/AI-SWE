"""Deterministic TF-IDF hybrid ranker. All customer state is local to rank()."""

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from ai_service.recommendation.inference import InferenceRequest, InferenceResponse, RankedProduct


def normalize(value: str | None) -> str:
    value = unicodedata.normalize("NFD", (value or "").lower().replace("đ", "d"))
    return " ".join(
        re.findall(r"[^\W_]+", "".join(c for c in value if not unicodedata.combining(c)))
    )


@dataclass(frozen=True)
class Weights:
    text: float = 0.55
    category: float = 0.25
    brand: float = 0.08
    price: float = 0.12
    popularity: float = 0.10
    view: float = 2
    click: float = 3
    search: float = 1
    wishlist: float = 5
    half_life_days: float = 21
    repeat_cap: float = 3
    diversity: float = 0.08


def price_similarity(a, b):
    return min(a, b) / max(a, b) if a and b and a > 0 and b > 0 else 0.0


def rank(request: InferenceRequest, weights: Weights | None = None) -> InferenceResponse:
    weights = weights or Weights()
    products = request.candidates
    n = len(products)
    if not n:
        return InferenceResponse(items=[])
    ids = {p.productId: i for i, p in enumerate(products)}
    texts = [
        normalize(f"{p.name} {p.name} {p.category or ''} {p.brand or ''} {p.description}")
        for p in products
    ]
    vectorizer = TfidfVectorizer(token_pattern=r"(?u)\b\w+\b", sublinear_tf=True)
    try:
        matrix = vectorizer.fit_transform(texts)
    except ValueError:  # punctuation-only catalog: no vocabulary
        matrix = None

    categories_normalized = [normalize(p.category) for p in products]
    brands_normalized = [normalize(p.brand) for p in products]
    category_values = np.array(categories_normalized)
    brand_values = np.array(brands_normalized)
    prices = np.array([p.price or 0 for p in products], dtype=float)
    text_tokens = [set(text.split()) for text in texts]

    @lru_cache(maxsize=500)
    def content(index):
        text = (
            cosine_similarity(matrix[index], matrix).ravel() if matrix is not None else np.zeros(n)
        )
        price = prices[index]
        ratios = np.divide(
            np.minimum(prices, price),
            np.maximum(prices, price),
            out=np.zeros(n),
            where=(prices > 0) & (price > 0),
        )
        category = categories_normalized[index]
        brand = brands_normalized[index]
        return (
            weights.text * text
            + weights.category * ((category_values == category) & bool(category))
            + weights.brand * ((brand_values == brand) & bool(brand))
            + weights.price * ratios
        )

    @lru_cache(maxsize=500)
    def search_signal(query):
        tokens = set(query.split())
        mask = np.array([tokens.issubset(candidate) for candidate in text_tokens])
        return cosine_similarity(vectorizer.transform([query]), matrix).ravel() * mask

    popularity = np.log1p([p.popularity for p in products])
    if popularity.max() > 0:
        popularity /= popularity.max()
    scores = np.zeros(n)
    total = 0.0
    source = request.sourceProductId
    if source is not None:
        if source not in ids:
            raise ValueError("Source not in authorized snapshot")
        scores = content(ids[source])
    else:
        # Newest first; cap decayed type/product/query influence.
        used = {}
        for event in sorted(request.recentEvents, key=lambda e: e.occurredAt, reverse=True):
            age = (request.asOf - event.occurredAt).total_seconds() / 86400
            if age < 0 or age > 90 or event.eventType.startswith("WISHLIST"):
                continue
            key = (event.eventType, event.productId, normalize(event.query))
            decay = 2 ** (-age / weights.half_life_days)
            influence = min(decay, max(0, weights.repeat_cap - used.get(key, 0)))
            used[key] = used.get(key, 0) + influence
            if influence <= 0:
                continue
            if event.eventType == "SEARCH":
                query = normalize(event.query)
                if not query or matrix is None:
                    continue
                # All exact query tokens must occur; no fuzzy association.
                signal = search_signal(query)
                strength = weights.search * influence
            elif event.productId in ids:
                signal = content(ids[event.productId])
                strength = (
                    weights.click if event.eventType == "PRODUCT_CLICK" else weights.view
                ) * influence
            else:
                continue
            if np.any(signal):
                scores += strength * signal
                total += strength
        # Current membership overrides add/remove history, including entries older than 90d.
        for product_id in sorted(set(request.wishlist), key=str):
            signal = content(ids[product_id])
            if np.any(signal):
                scores += weights.wishlist * signal
                total += weights.wishlist
        if total:
            scores /= total
        scores += (weights.popularity if total else 1.0) * popularity

    # Greedy soft penalty: relevance can outweigh diversity, no forced irrelevant category quotas.
    remaining = set(range(n)) - ({ids[source]} if source is not None else set())
    selected = []
    brands, categories = {}, {}
    while remaining and len(selected) < request.limit:

        def adjusted(i):
            penalty = weights.diversity * (
                min(2, brands.get(brands_normalized[i], 0))
                + min(2, categories.get(categories_normalized[i], 0)) * 0.5
            )
            return (-float(scores[i] - penalty), str(products[i].productId))

        index = min(remaining, key=adjusted)
        remaining.remove(index)
        selected.append(
            RankedProduct(productId=products[index].productId, score=max(0, float(scores[index])))
        )
        for counts, value in (
            (brands, products[index].brand),
            (categories, products[index].category),
        ):
            if value:
                key = normalize(value)
                counts[key] = counts.get(key, 0) + 1
    return InferenceResponse(items=selected)
