"""Isolation test: the full migration + app flow must not touch a file database."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dunvyr.infrastructure.db import create_db_engine
from dunvyr.main import create_app

from .support import IN_MEMORY_URL, apply_migrations


@pytest.mark.integration
def test_full_flow_creates_no_database_file_on_disk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DUNVYR_DATABASE_URL", raising=False)

    engine = create_db_engine(IN_MEMORY_URL)
    try:
        apply_migrations(engine)
        app = create_app(engine=engine)
        with TestClient(app) as client:
            response = client.get("/health")
    finally:
        engine.dispose()

    assert response.status_code == 200
    assert list(tmp_path.rglob("*.db")) == []
    assert list(tmp_path.rglob("*.db-wal")) == []
