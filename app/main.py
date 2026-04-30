from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings)
    logger = get_logger(__name__)
    logger.info(
        "application_starting",
        extra={"app_name": settings.app_name, "environment": settings.environment},
    )
    yield
    logger.info("application_stopping", extra={"app_name": settings.app_name})


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or get_settings()
    configure_logging(active_settings)
    app = FastAPI(
        title=active_settings.app_name,
        version=__version__,
        docs_url=active_settings.docs_url,
        redoc_url=active_settings.redoc_url,
        openapi_url=active_settings.openapi_url,
        lifespan=lifespan,
    )
    app.include_router(api_router)
    return app


app = create_app()
