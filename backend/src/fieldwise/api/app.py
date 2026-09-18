"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fieldwise import __version__
from fieldwise.api.routers import documents, evals, meta, runs, schemas
from fieldwise.config import get_settings
from fieldwise.logging import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(
        title="fieldwise",
        version=__version__,
        description="Schema-driven document extraction with a review UI and per-field evals.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(meta.router)
    app.include_router(schemas.router)
    app.include_router(documents.router)
    app.include_router(runs.router)
    app.include_router(evals.router)
    return app


app = create_app()
