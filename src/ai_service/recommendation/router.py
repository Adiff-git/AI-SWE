from fastapi import APIRouter

from ai_service.recommendation.schemas import RecommendationRequest, RecommendationResponse
from ai_service.recommendation.service import recommend_products

router = APIRouter(tags=["recommendations"])


@router.post("/recommendations", response_model=RecommendationResponse)
async def recommendations(request: RecommendationRequest) -> RecommendationResponse:
    """Return an explicit placeholder until recommendations are implemented."""
    return await recommend_products(request)
