"""Integration tests for Alembic auto-migration and file-backed persistence."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from dunvyr.main import create_app

from .support import BACKEND_DIR

ORIGIN = "http://localhost:5173"
SESSION_COOKIE = "dunvyr_session"


@pytest.mark.integration
def test_auto_migration_is_disabled_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DUNVYR_AUTO_MIGRATE", raising=False)
    database_file = tmp_path / "not-migrated.db"
    app = create_app(database_url=f"sqlite:///{database_file}")
    try:
        assert not database_file.exists()
    finally:
        app.state.engine.dispose()


@pytest.mark.integration
def test_file_database_is_created_by_alembic_and_session_survives_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_file = tmp_path / "dunvyr.db"
    database_url = f"sqlite:///{database_file}"
    monkeypatch.setenv("DUNVYR_AUTO_MIGRATE", "1")
    monkeypatch.setenv("DUNVYR_MIGRATIONS_DIR", str(BACKEND_DIR / "migrations"))

    first_app = create_app(database_url=database_url)
    try:
        assert database_file.exists()
        with first_app.state.engine.connect() as connection:
            version = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            tables = set(inspect(connection).get_table_names())
        assert version == "0007"
        assert {
            "identity_guests",
            "identity_sessions",
            "campaigns_campaigns",
            "campaigns_members",
        } <= tables

        with TestClient(first_app) as client:
            created = client.post(
                "/api/identity/sessions",
                json={"nickname": "Alice"},
                headers={"Origin": ORIGIN},
            )
            assert created.status_code == 201
            guest_id = created.json()["id"]
            token = created.cookies.get(SESSION_COOKIE)
            assert token is not None
    finally:
        first_app.state.engine.dispose()

    # Simulate a server restart: a fresh app on the same file must resolve the
    # cookie to the same guest because the session lives in SQLite, not memory.
    second_app = create_app(database_url=database_url)
    try:
        with TestClient(second_app) as client:
            me = client.get(
                "/api/identity/me",
                headers={"Cookie": f"{SESSION_COOKIE}={token}"},
            )
    finally:
        second_app.state.engine.dispose()

    assert me.status_code == 200
    assert me.json() == {"id": guest_id, "nickname": "Alice"}
