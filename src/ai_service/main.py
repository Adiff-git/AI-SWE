"""The single FastAPI application and its process entry point."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from ai_service.api.v1.router import router
from ai_service.core.config import get_settings
from ai_service.core.logging import configure_logging
from ai_service.integrations.backend_client import create_backend_client

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging(settings.log_level)
    async with create_backend_client(settings) as backend_client:
        app.state.backend_client = backend_client
        logger.info("Starting %s (environment=%s)", settings.app_name, settings.app_env)
        yield
    logger.info("Stopped %s", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Electronics AI service scaffold. Recommendation and chat are not implemented yet.",
    lifespan=lifespan,
)
app.include_router(router)


def run() -> None:
    """Launch using HOST and PORT from centralized settings."""
    configure_logging(settings.log_level)
    uvicorn.run(app, host=settings.host, port=settings.port, log_config=None)


if __name__ == "__main__":
    run()
