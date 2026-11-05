"""Shared integration-test fixtures: migrated in-memory database plus app client."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

from dunvyr.infrastructure.db import create_db_engine
from dunvyr.main import create_app

from .support import IN_MEMORY_URL, apply_migrations


@pytest.fixture()
def migrated_engine() -> Iterator[Engine]:
    """A clean in-memory SQLite engine with the Alembic schema applied."""
    engine = create_db_engine(IN_MEMORY_URL)
    try:
        apply_migrations(engine)
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def client(migrated_engine: Engine) -> Iterator[TestClient]:
    """A TestClient wired to the migrated engine."""
    app = create_app(engine=migrated_engine)
    with TestClient(app) as test_client:
        yield test_client
