"""Integration tests for the guest identity REST slice."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from dunvyr.identity.domain.session import SESSION_LIFETIME, hash_session_token
from dunvyr.main import create_app

ORIGIN = "http://localhost:5173"
SESSION_COOKIE = "dunvyr_session"


def create_guest(
    client: TestClient,
    nickname: str = "Alice",
    origin: str = ORIGIN,
) -> tuple[int, dict[str, object], str]:
    response = client.post(
        "/api/identity/sessions",
        json={"nickname": nickname},
        headers={"Origin": origin},
    )
    body = (
        response.json() if response.headers["content-type"].startswith("application/json") else {}
    )
    return response.status_code, body, response.headers.get("set-cookie", "")


@pytest.mark.integration
def test_create_session_returns_guest_and_sets_secure_cookie_flags(client: TestClient) -> None:
    status, body, set_cookie = create_guest(client)

    assert status == 201
    assert set(body) == {"id", "nickname"}
    assert body["nickname"] == "Alice"
    UUID(str(body["id"]))
    lowered = set_cookie.lower()
    assert set_cookie.startswith(f"{SESSION_COOKIE}=")
    assert "httponly" in lowered
    assert "samesite=lax" in lowered
    assert "path=/" in lowered
    assert f"max-age={int(SESSION_LIFETIME.total_seconds())}" in lowered
    assert "secure" not in lowered


@pytest.mark.integration
def test_session_token_never_appears_in_response_body_or_url(client: TestClient) -> None:
    response = client.post(
        "/api/identity/sessions",
        json={"nickname": "Alice"},
        headers={"Origin": ORIGIN},
    )

    token = response.cookies.get(SESSION_COOKIE)
    assert token is not None
    assert len(token) == 43
    assert token not in response.text
    assert "location" not in response.headers
    assert token not in response.headers.get("location", "")


@pytest.mark.integration
def test_session_token_is_not_logged(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        response = client.post(
            "/api/identity/sessions",
            json={"nickname": "Alice"},
            headers={"Origin": ORIGIN},
        )

    token = response.cookies.get(SESSION_COOKIE)
    assert token is not None
    assert token not in caplog.text


@pytest.mark.integration
def test_database_stores_only_the_token_hash(
    client: TestClient,
    migrated_engine: Engine,
) -> None:
    response = client.post(
        "/api/identity/sessions",
        json={"nickname": "Alice"},
        headers={"Origin": ORIGIN},
    )
    token = response.cookies.get(SESSION_COOKIE)
    assert token is not None

    with migrated_engine.connect() as connection:
        stored = connection.execute(text("SELECT token_hash FROM identity_sessions")).scalar_one()
        columns = {
            row[1] for row in connection.execute(text("PRAGMA table_info(identity_sessions)")).all()
        }

    assert stored == hash_session_token(token)
    assert stored != token
    assert "token" not in columns


@pytest.mark.integration
def test_repeat_request_with_cookie_restores_same_identity(client: TestClient) -> None:
    status, body, _set_cookie = create_guest(client)
    assert status == 201

    me = client.get("/api/identity/me")

    assert me.status_code == 200
    assert me.json() == {"id": body["id"], "nickname": "Alice"}


@pytest.mark.integration
def test_missing_session_returns_401_without_origin_header(client: TestClient) -> None:
    response = client.get("/api/identity/me")

    assert response.status_code == 401


@pytest.mark.integration
def test_expired_session_is_treated_as_missing(
    client: TestClient,
    migrated_engine: Engine,
) -> None:
    status, _body, _set_cookie = create_guest(client)
    assert status == 201
    token = client.cookies.get(SESSION_COOKIE)
    assert token is not None

    expired_created = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    expired_at = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    with migrated_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE identity_sessions "
                "SET created_at = :created_at, expires_at = :expires_at "
                "WHERE token_hash = :hash"
            ),
            {
                "created_at": expired_created,
                "expires_at": expired_at,
                "hash": hash_session_token(token),
            },
        )

    me = client.get("/api/identity/me")

    assert me.status_code == 401


@pytest.mark.integration
def test_creating_another_guest_yields_a_new_identity(client: TestClient) -> None:
    _status, first_body, _cookie = create_guest(client)
    first_id = first_body["id"]

    second_status, second_body, _second_cookie = create_guest(client, nickname="Bob")

    assert second_status == 201
    assert second_body["id"] != first_id
    assert second_body["nickname"] == "Bob"


@pytest.mark.integration
@pytest.mark.parametrize("nickname", ["", "   ", "x" * 33, "Alice\nSecond"])
def test_invalid_nickname_is_a_domain_error_not_500(client: TestClient, nickname: str) -> None:
    response = client.post(
        "/api/identity/sessions",
        json={"nickname": nickname},
        headers={"Origin": ORIGIN},
    )

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)
    assert response.json()["detail"]


@pytest.mark.integration
def test_duplicate_nicknames_create_distinct_guests(client: TestClient) -> None:
    first_status, first_body, _first_cookie = create_guest(client)
    second_status, second_body, _second_cookie = create_guest(client)

    assert first_status == second_status == 201
    assert first_body["id"] != second_body["id"]
    assert first_body["nickname"] == second_body["nickname"] == "Alice"


@pytest.mark.integration
def test_state_changing_endpoint_requires_allowed_origin(client: TestClient) -> None:
    without_origin = client.post("/api/identity/sessions", json={"nickname": "Alice"})
    foreign_origin = client.post(
        "/api/identity/sessions",
        json={"nickname": "Alice"},
        headers={"Origin": "http://evil.example"},
    )
    allowed_origin = client.post(
        "/api/identity/sessions",
        json={"nickname": "Alice"},
        headers={"Origin": ORIGIN},
    )

    assert without_origin.status_code == 403
    assert foreign_origin.status_code == 403
    assert allowed_origin.status_code == 201


@pytest.mark.integration
def test_cors_preflight_allows_configured_origin_with_credentials(client: TestClient) -> None:
    response = client.options(
        "/api/identity/sessions",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"


@pytest.mark.integration
def test_session_creation_is_rate_limited_per_client(client: TestClient) -> None:
    for _ in range(10):
        assert create_guest(client)[0] == 201

    limited = client.post(
        "/api/identity/sessions",
        json={"nickname": "Alice"},
        headers={"Origin": ORIGIN},
    )

    assert limited.status_code == 429
    retry_after = int(limited.headers["Retry-After"])
    assert 1 <= retry_after <= 60


@pytest.mark.integration
def test_cookie_secure_flag_can_be_enabled_by_environment(
    migrated_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DUNVYR_COOKIE_SECURE", "1")
    app = create_app(engine=migrated_engine)
    with TestClient(app) as client:
        status, _body, set_cookie = create_guest(client)

    assert status == 201
    assert "secure" in set_cookie.lower()
