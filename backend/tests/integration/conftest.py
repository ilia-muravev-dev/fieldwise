"""A real Postgres with pgvector per test session; every test runs inside a rolled-back
transaction so `session.commit()` in application code is harmless."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session
from testcontainers.community.postgres import PostgresContainer

from fieldwise.db import migrate
from fieldwise.storage import LocalStorage

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    with PostgresContainer("pgvector/pgvector:pg17", driver="psycopg") as postgres:
        yield postgres.get_connection_url()


@pytest.fixture(scope="session")
def engine(database_url: str) -> Iterator[Engine]:
    engine = create_engine(database_url, future=True)
    migrate.upgrade(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            yield session
        transaction.rollback()


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorage:
    return LocalStorage(tmp_path / "storage")
