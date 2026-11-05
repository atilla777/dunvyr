"""Integration tests for the organizer campaign creation slice."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from dunvyr.campaigns.domain.invitation import hash_invitation_secret

ORIGIN = "http://localhost:5173"
SESSION_COOKIE = "dunvyr_session"
URL_SAFE = re.compile(r"[A-Za-z0-9_-]+")


def login(client: TestClient, nickname: str = "Алиса") -> dict[str, object]:
    response = client.post(
        "/api/identity/sessions",
        json={"nickname": nickname},
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 201
    return cast(dict[str, object], response.json())


def create_campaign(
    client: TestClient,
    *,
    name: str = "Ночная смена",
    max_seats: int | None = None,
    idempotency_key: str | None = None,
    origin: str | None = ORIGIN,
):
    payload: dict[str, object] = {"name": name}
    if max_seats is not None:
        payload["max_seats"] = max_seats
    headers = {"Idempotency-Key": idempotency_key or str(uuid4())}
    if origin is not None:
        headers["Origin"] = origin
    return client.post("/api/campaigns", json=payload, headers=headers)


@pytest.mark.integration
def test_create_campaign_returns_campaign_secret_and_organizer(client: TestClient) -> None:
    guest = login(client)

    response = create_campaign(client, max_seats=4)

    assert response.status_code == 201
    body = response.json()
    UUID(body["id"])
    assert body["name"] == "Ночная смена"
    assert body["max_seats"] == 4
    assert body["organizer_id"] == guest["id"]
    assert datetime.fromisoformat(body["created_at"]).tzinfo is not None
    assert body["members"] == [
        {
            "guest_id": guest["id"],
            "nickname": "Алиса",
            "role": "organizer",
            "joined_at": body["created_at"],
        }
    ]
    secret = body["invitation"]["secret"]
    assert body["invitation"]["active"] is True
    assert len(secret) == 43
    assert URL_SAFE.fullmatch(secret)
    assert body["invitation"]["path"] == f"/join/{secret}"
    assert secret not in response.headers.get("location", "")


@pytest.mark.integration
def test_create_campaign_defaults_to_six_seats(client: TestClient) -> None:
    login(client)

    response = create_campaign(client)

    assert response.status_code == 201
    assert response.json()["max_seats"] == 6


@pytest.mark.integration
def test_database_stores_only_the_invitation_hash_and_identity_rows_unchanged(
    client: TestClient,
    migrated_engine: Engine,
) -> None:
    login(client)
    response = create_campaign(client)
    secret = response.json()["invitation"]["secret"]

    with migrated_engine.connect() as connection:
        stored_hash = connection.execute(
            text("SELECT invitation_token_hash FROM campaigns_campaigns")
        ).scalar_one()
        campaign_columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(campaigns_campaigns)")).all()
        }
        identity_guests = connection.execute(
            text("SELECT COUNT(*) FROM identity_guests")
        ).scalar_one()
        identity_sessions = connection.execute(
            text("SELECT COUNT(*) FROM identity_sessions")
        ).scalar_one()
        campaigns = connection.execute(
            text("SELECT COUNT(*) FROM campaigns_campaigns")
        ).scalar_one()
        members = connection.execute(text("SELECT COUNT(*) FROM campaigns_members")).scalar_one()

    assert stored_hash == hash_invitation_secret(secret)
    assert stored_hash != secret
    assert "invitation_secret" not in campaign_columns
    assert identity_guests == 1
    assert identity_sessions == 1
    assert campaigns == 1
    assert members == 1


@pytest.mark.integration
def test_repeat_create_with_the_same_key_returns_one_campaign_without_secret(
    client: TestClient,
    migrated_engine: Engine,
) -> None:
    login(client)
    key = str(uuid4())
    first = create_campaign(client, idempotency_key=key)
    assert first.status_code == 201

    replay = create_campaign(client, idempotency_key=key)

    assert replay.status_code == 200
    assert replay.json()["id"] == first.json()["id"]
    assert replay.json()["invitation"]["active"] is True
    assert replay.json()["invitation"]["secret"] is None
    assert replay.json()["invitation"]["path"] is None
    with migrated_engine.connect() as connection:
        count = connection.execute(text("SELECT COUNT(*) FROM campaigns_campaigns")).scalar_one()
    assert count == 1


@pytest.mark.integration
@pytest.mark.parametrize("header", [None, "", "not-a-uuid"])
def test_missing_or_invalid_idempotency_key_is_422(
    client: TestClient,
    header: str | None,
) -> None:
    login(client)
    headers = {"Origin": ORIGIN}
    if header is not None:
        headers["Idempotency-Key"] = header

    response = client.post("/api/campaigns", json={"name": "Ночная смена"}, headers=headers)

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


@pytest.mark.integration
def test_anonymous_guest_cannot_create_a_campaign(client: TestClient) -> None:
    response = create_campaign(client)

    assert response.status_code == 403
    assert response.json()["detail"] == "forbidden"


@pytest.mark.integration
def test_creation_requires_an_allowed_origin(client: TestClient) -> None:
    login(client)

    missing = create_campaign(client, origin=None)
    foreign = create_campaign(client, origin="http://evil.example")

    assert missing.status_code == 403
    assert foreign.status_code == 403


@pytest.mark.integration
def test_member_reads_the_campaign_without_repeating_the_secret(client: TestClient) -> None:
    login(client)
    created = create_campaign(client)
    secret = created.json()["invitation"]["secret"]
    campaign_id = created.json()["id"]

    response = client.get(f"/api/campaigns/{campaign_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == campaign_id
    assert body["invitation"] == {"active": True, "secret": None, "path": None}
    assert secret not in response.text


@pytest.mark.integration
def test_non_member_reads_are_forbidden_without_disclosure(client: TestClient) -> None:
    first_guest = login(client)
    created = create_campaign(client)
    campaign_id = created.json()["id"]
    assert created.json()["organizer_id"] == first_guest["id"]

    login(client, nickname="Боб")
    response = client.get(f"/api/campaigns/{campaign_id}")

    assert response.status_code == 403
    assert response.json()["detail"] == "forbidden"
    assert created.json()["invitation"]["secret"] not in response.text


@pytest.mark.integration
def test_anonymous_read_is_forbidden(client: TestClient) -> None:
    response = client.get(f"/api/campaigns/{uuid4()}")

    assert response.status_code == 403
    assert response.json()["detail"] == "forbidden"


@pytest.mark.integration
def test_authenticated_read_of_a_missing_campaign_is_not_found(client: TestClient) -> None:
    login(client)

    response = client.get(f"/api/campaigns/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "not_found"


@pytest.mark.integration
@pytest.mark.parametrize(
    "payload",
    [
        {"name": "Ночная смена", "max_seats": 1},
        {"name": "Ночная смена", "max_seats": 21},
        {"name": "   "},
        {"name": "x" * 61},
        {"name": "Ночная смена", "max_seats": "many"},
    ],
)
def test_invalid_payload_is_422(client: TestClient, payload: dict[str, object]) -> None:
    login(client)

    response = client.post(
        "/api/campaigns",
        json=payload,
        headers={"Origin": ORIGIN, "Idempotency-Key": str(uuid4())},
    )

    assert response.status_code == 422


@pytest.mark.integration
def test_invitation_secret_is_never_logged(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    login(client)

    with caplog.at_level(logging.DEBUG):
        response = create_campaign(client)

    secret = response.json()["invitation"]["secret"]
    assert secret not in caplog.text


@pytest.mark.integration
def test_campaign_creation_is_rate_limited_in_its_own_bucket(client: TestClient) -> None:
    login(client)
    for _ in range(10):
        assert create_campaign(client).status_code == 201

    limited = create_campaign(client)

    assert limited.status_code == 429
    retry_after = int(limited.headers["Retry-After"])
    assert 1 <= retry_after <= 60

    # Identity session creation keeps its own bucket after campaigns is limited.
    second_guest = client.post(
        "/api/identity/sessions",
        json={"nickname": "Боб"},
        headers={"Origin": ORIGIN},
    )
    assert second_guest.status_code == 201


@pytest.mark.integration
def test_cors_preflight_allows_the_idempotency_key_header(client: TestClient) -> None:
    response = client.options(
        "/api/campaigns",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,idempotency-key",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert "idempotency-key" in response.headers["access-control-allow-headers"].lower()
