"""Campaign persistence across a simulated server restart on file-backed SQLite."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from dunvyr.main import create_app

from .support import BACKEND_DIR

ORIGIN = "http://localhost:5173"
SESSION_COOKIE = "dunvyr_session"


@pytest.mark.integration
def test_campaign_survives_a_server_restart_and_never_repeats_the_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_file = tmp_path / "dunvyr.db"
    database_url = f"sqlite:///{database_file}"
    monkeypatch.setenv("DUNVYR_AUTO_MIGRATE", "1")
    monkeypatch.setenv("DUNVYR_MIGRATIONS_DIR", str(BACKEND_DIR / "migrations"))

    first_app = create_app(database_url=database_url)
    try:
        with first_app.state.engine.connect() as connection:
            version = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            tables = set(inspect(connection).get_table_names())
        assert version == "0010"
        assert {"campaigns_campaigns", "campaigns_members", "communication_events"} <= tables

        with TestClient(first_app) as client:
            login = client.post(
                "/api/identity/sessions",
                json={"nickname": "Алиса"},
                headers={"Origin": ORIGIN},
            )
            assert login.status_code == 201
            guest_id = login.json()["id"]
            token = login.cookies.get(SESSION_COOKIE)
            assert token is not None

            created = client.post(
                "/api/campaigns",
                json={"name": "Ночная смена", "max_seats": 5},
                headers={"Origin": ORIGIN, "Idempotency-Key": str(uuid4())},
            )
            assert created.status_code == 201
            campaign_id = created.json()["id"]
            secret = created.json()["invitation"]["secret"]
            assert secret is not None
    finally:
        first_app.state.engine.dispose()

    # Simulate a restart: a fresh app on the same file must return the campaign
    # to its organizer, and the one-time secret must not appear again.
    second_app = create_app(database_url=database_url)
    try:
        with TestClient(second_app) as client:
            response = client.get(
                f"/api/campaigns/{campaign_id}",
                headers={"Cookie": f"{SESSION_COOKIE}={token}"},
            )
    finally:
        second_app.state.engine.dispose()

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == campaign_id
    assert body["name"] == "Ночная смена"
    assert body["max_seats"] == 5
    assert body["organizer_id"] == guest_id
    assert body["invitation"]["secret"] is None
    assert secret not in response.text
