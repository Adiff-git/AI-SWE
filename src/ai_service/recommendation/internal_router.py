"""Protected inference, synchronous CPU work runs in FastAPI's thread pool."""

import hmac
import json
import os
from dataclasses import fields

from fastapi import APIRouter, Depends, Header, HTTPException

from ai_service.core.config import get_settings
from ai_service.recommendation.engine import Weights, rank
from ai_service.recommendation.inference import InferenceRequest, InferenceResponse

router = APIRouter(prefix="/internal/recommendations", tags=["internal recommendations"])


def authorize(x_recommendation_key: str | None = Header(default=None)):
    configured = get_settings().recommendation_service_key
    if configured is None or len(configured.get_secret_value()) < 32:
        raise HTTPException(503, "Recommendation service authentication is not configured")
    if not x_recommendation_key or not hmac.compare_digest(
        configured.get_secret_value().encode(), x_recommendation_key.encode()
    ):
        raise HTTPException(401, "Unauthorized inference request")


def configured_weights():
    values = json.loads(os.getenv("RECOMMENDATION_WEIGHTS", "{}"))
    allowed = {f.name for f in fields(Weights)}
    if not isinstance(values, dict) or set(values) - allowed:
        raise ValueError("Invalid recommendation weights")
    for value in values.values():
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not 0 <= value <= 100:
            raise ValueError("Invalid recommendation weight")
    if values.get("half_life_days", 21) <= 0:
        raise ValueError("Half life must be positive")
    return Weights(**values)


@router.post("/personalized", response_model=InferenceResponse, dependencies=[Depends(authorize)])
def personalized(request: InferenceRequest):
    if request.sourceProductId is not None:
        raise HTTPException(422, "Unexpected source product")
    return rank(request, configured_weights())


@router.post("/similar", response_model=InferenceResponse, dependencies=[Depends(authorize)])
def similar(request: InferenceRequest):
    if request.sourceProductId is None or request.sourceProductId not in {
        p.productId for p in request.candidates
    }:
        raise HTTPException(422, "Source must be in snapshot")
    if request.recentEvents or request.wishlist:
        raise HTTPException(422, "Similar ranking does not accept customer behavior")
    return rank(request, configured_weights())
