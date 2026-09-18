import pytest
from sqlalchemy import Engine, create_engine, inspect, text

from fieldwise.db import migrate

pytestmark = pytest.mark.integration


def test_upgrade_creates_tables_and_downgrade_removes_them(
    database_url: str, engine: Engine
) -> None:
    names = set(inspect(engine).get_table_names())
    assert {"schemas", "documents", "golden_labels", "alembic_version"} <= names
    with engine.connect() as connection:
        extensions = connection.execute(text("SELECT extname FROM pg_extension")).scalars().all()
    assert "vector" in extensions

    scratch = create_engine(database_url.replace("/test", "/test"), future=True)
    try:
        migrate.downgrade(scratch)
        assert "documents" not in inspect(scratch).get_table_names()
        migrate.upgrade(scratch)
        assert "documents" in inspect(scratch).get_table_names()
    finally:
        scratch.dispose()
