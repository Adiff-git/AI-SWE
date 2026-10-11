"""Recommendation boundary. Algorithms and Backend calls will be added later."""

from ai_service.recommendation.schemas import RecommendationRequest, RecommendationResponse


async def recommend_products(request: RecommendationRequest) -> RecommendationResponse:
    """Eventually consume authorized Backend history and product data.

    The request is intentionally unused until recommendation logic exists.
    No personalization, user profiling or synthetic product IDs are generated.
    """
    return RecommendationResponse()
