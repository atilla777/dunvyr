"""Chat messages survive a simulated server restart on file-backed SQLite."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from dunvyr.main import create_app

from .support import BACKEND_DIR, receive_non_presence

ORIGIN = "http://localhost:5173"
SESSION_COOKIE = "dunvyr_session"


@pytest.mark.integration
def test_chat_message_survives_a_server_restart(
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
        assert "communication_events" in tables

        with TestClient(first_app) as client:
            login = client.post(
                "/api/identity/sessions",
                json={"nickname": "Алиса"},
                headers={"Origin": ORIGIN},
            )
            assert login.status_code == 201
            token = login.cookies.get(SESSION_COOKIE)
            assert token is not None

            created = client.post(
                "/api/campaigns",
                json={"name": "Ночная смена", "max_seats": 4},
                headers={"Origin": ORIGIN, "Idempotency-Key": str(uuid4())},
            )
            assert created.status_code == 201
            campaign_id = created.json()["id"]

            with client.websocket_connect(
                f"/api/campaigns/{campaign_id}/chat",
                headers={"origin": ORIGIN},
            ) as socket:
                socket.send_text(
                    json.dumps(
                        {
                            "type": "message",
                            "client_message_id": str(uuid4()),
                            "content": "Переживёт рестарт",
                        }
                    )
                )
                event = receive_non_presence(socket)
                assert event["type"] == "message"
    finally:
        first_app.state.engine.dispose()

    second_app = create_app(database_url=database_url)
    try:
        with TestClient(second_app) as client:
            client.cookies.set(SESSION_COOKIE, token, domain="testserver.local", path="/")
            response = client.get(f"/api/campaigns/{campaign_id}/chat/events")
    finally:
        second_app.state.engine.dispose()

    assert response.status_code == 200
    body = response.json()
    assert body["last_sequence"] == 1
    assert [event["type"] for event in body["events"]] == ["message"]
    assert body["events"][0]["message"]["content"] == "Переживёт рестарт"
