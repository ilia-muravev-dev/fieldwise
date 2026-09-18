"""Programmatic Alembic entry points (used by the CLI, tests and the compose `migrate` service)."""

from collections.abc import Callable
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def alembic_config(url: str | None = None) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option("file_template", "%%(rev)s_%%(slug)s")
    if url:
        config.set_main_option("sqlalchemy.url", url)
    return config


def upgrade(engine: Engine, revision: str = "head") -> None:
    with engine.begin() as connection:
        _run(connection, lambda cfg: command.upgrade(cfg, revision))


def downgrade(engine: Engine, revision: str = "base") -> None:
    with engine.begin() as connection:
        _run(connection, lambda cfg: command.downgrade(cfg, revision))


def _run(connection: Connection, action: Callable[[Config], None]) -> None:
    config = alembic_config()
    config.attributes["connection"] = connection
    action(config)
