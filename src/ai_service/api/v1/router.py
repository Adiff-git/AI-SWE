from fastapi import APIRouter

from ai_service.agent.router import router as agent_router
from ai_service.api.v1.health import router as health_router
from ai_service.recommendation.router import router as recommendation_router

router = APIRouter(prefix="/api/v1")
router.include_router(health_router)
router.include_router(recommendation_router)
router.include_router(agent_router)
