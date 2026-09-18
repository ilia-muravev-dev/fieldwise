"""FastAPI application factory."""

from fastapi import FastAPI

from fieldwise import __version__
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

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
