"""The single FastAPI application and its process entry point."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ai_service.api.v1.router import router
from ai_service.core.config import get_settings
from ai_service.core.logging import configure_logging
from ai_service.integrations.backend_client import create_backend_client
from ai_service.integrations.llm import create_llm_client
from ai_service.recommendation.internal_router import authorize, configured_weights
from ai_service.recommendation.internal_router import router as inference_router

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging(settings.log_level)
    configured_weights()  # Invalid scoring configuration fails startup clearly.
    async with (
        create_backend_client(settings) as backend_client,
        create_llm_client(settings) as llm_client,
    ):
        app.state.backend_client = backend_client
        app.state.llm_client = llm_client
        logger.info("Starting %s (environment=%s)", settings.app_name, settings.app_env)
        yield
    logger.info("Stopped %s", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Electronics AI service with protected recommendation inference and agent APIs.",
    lifespan=lifespan,
)
app.include_router(router)
app.include_router(inference_router)


@app.middleware("http")
async def bound_inference_body(request, call_next):
    # Bound actual streamed bytes as well as Content-Length (including chunked requests).
    if request.url.path.startswith("/internal/recommendations"):
        try:
            authorize(request.headers.get("X-Recommendation-Key"))
        except HTTPException as exc:
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 12_000_000:
                return JSONResponse({"detail": "Inference request too large"}, status_code=413)
        request._body = bytes(body)
    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def safe_validation_error(request, exc):
    # Never echo behavior/query bodies in internal error responses.
    if request.url.path.startswith("/internal/recommendations"):
        return JSONResponse({"detail": "Invalid inference payload"}, status_code=422)
    from fastapi.exception_handlers import request_validation_exception_handler

    return await request_validation_exception_handler(request, exc)


def run() -> None:
    """Launch using HOST and PORT from centralized settings."""
    configure_logging(settings.log_level)
    uvicorn.run(app, host=settings.host, port=settings.port, log_config=None)


if __name__ == "__main__":
    run()
