from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from fieldwise.db.engine import get_db
from fieldwise.storage import Storage, get_storage


def _db() -> Iterator[Session]:
    yield from get_db()


def _storage() -> Storage:
    return get_storage()


DbSession = Annotated[Session, Depends(_db)]
Blobs = Annotated[Storage, Depends(_storage)]
