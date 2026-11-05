"""Integration tests for invitation joins and invitation revocation."""

from __future__ import annotations

import logging
from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

ORIGIN = "http://localhost:5173"
SESSION_COOKIE = "dunvyr_session"


def login(client: TestClient, nickname: str = "Алиса") -> tuple[dict[str, object], str]:
    client.cookies.clear()
    response = client.post(
        "/api/identity/sessions",
        json={"nickname": nickname},
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 201
    token = client.cookies.get(SESSION_COOKIE)
    assert token is not None
    return cast(dict[str, object], response.json()), token


def use_guest(client: TestClient, token: str) -> None:
    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE, token, domain="testserver.local", path="/")


def create_campaign(
    client: TestClient,
    *,
    name: str = "Ночная смена",
    max_seats: int = 6,
):
    return client.post(
        "/api/campaigns",
        json={"name": name, "max_seats": max_seats},
        headers={"Origin": ORIGIN, "Idempotency-Key": str(uuid4())},
    )


def join_campaign(
    client: TestClient,
    secret: str,
    *,
    origin: str | None = ORIGIN,
):
    headers = {"Origin": origin} if origin is not None else {}
    return client.post("/api/campaigns/join", json={"secret": secret}, headers=headers)


def revoke_invitation(
    client: TestClient,
    campaign_id: str,
    *,
    origin: str | None = ORIGIN,
):
    headers = {"Origin": origin} if origin is not None else {}
    return client.post(f"/api/campaigns/{campaign_id}/invitation/revoke", headers=headers)


@pytest.mark.integration
def test_second_guest_joins_by_link_and_both_members_see_the_roster(
    client: TestClient,
) -> None:
    alice, alice_token = login(client)
    created = create_campaign(client, max_seats=4)
    assert created.status_code == 201
    campaign_id = created.json()["id"]
    secret = created.json()["invitation"]["secret"]

    bob, _bob_token = login(client, nickname="Боб")
    joined = join_campaign(client, secret)

    assert joined.status_code == 201
    body = joined.json()
    UUID(body["id"])
    assert body["id"] == campaign_id
    assert [(member["nickname"], member["role"]) for member in body["members"]] == [
        ("Алиса", "organizer"),
        ("Боб", "player"),
    ]
    bob_member = body["members"][1]
    assert bob_member["guest_id"] == bob["id"]
    assert isinstance(bob_member["joined_at"], str)
    assert body["invitation"] == {"active": True, "secret": None, "path": None}
    assert secret not in joined.text

    bob_read = client.get(f"/api/campaigns/{campaign_id}")
    assert bob_read.status_code == 200
    assert len(bob_read.json()["members"]) == 2

    # The organizer sees the updated roster after a fresh page read.
    use_guest(client, alice_token)
    alice_read = client.get(f"/api/campaigns/{campaign_id}")
    assert alice_read.status_code == 200
    assert [member["nickname"] for member in alice_read.json()["members"]] == ["Алиса", "Боб"]
    assert alice_read.json()["organizer_id"] == alice["id"]

    # A third guest who has not joined learns nothing about the campaign.
    outsider, _outsider_token = login(client, nickname="Кэрол")
    assert outsider["id"] != alice["id"]
    forbidden = client.get(f"/api/campaigns/{campaign_id}")
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "forbidden"


@pytest.mark.integration
def test_repeat_join_replays_the_membership_without_consuming_a_seat(
    client: TestClient,
    migrated_engine: Engine,
) -> None:
    login(client)
    created = create_campaign(client, max_seats=4)
    campaign_id = created.json()["id"]
    secret = created.json()["invitation"]["secret"]
    login(client, nickname="Боб")

    first = join_campaign(client, secret)
    replay = join_campaign(client, secret)

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["id"] == campaign_id
    assert [member["nickname"] for member in replay.json()["members"]] == ["Алиса", "Боб"]
    with migrated_engine.connect() as connection:
        members = connection.execute(
            text("SELECT COUNT(*) FROM campaigns_members WHERE campaign_id = :campaign_id"),
            {"campaign_id": campaign_id},
        ).scalar_one()
    assert members == 2


@pytest.mark.integration
def test_join_rejects_a_campaign_without_free_seats(client: TestClient) -> None:
    login(client)
    created = create_campaign(client, max_seats=2)
    secret = created.json()["invitation"]["secret"]
    login(client, nickname="Боб")
    assert join_campaign(client, secret).status_code == 201

    login(client, nickname="Кэрол")
    full = join_campaign(client, secret)

    assert full.status_code == 409
    assert full.json()["detail"] == "campaign_full"


@pytest.mark.integration
def test_join_rejects_a_nickname_already_used_in_the_campaign(client: TestClient) -> None:
    login(client)
    created = create_campaign(client, max_seats=4)
    secret = created.json()["invitation"]["secret"]
    login(client, nickname="Алиса")

    taken = join_campaign(client, secret)

    assert taken.status_code == 409
    assert taken.json()["detail"] == "nickname_taken"


@pytest.mark.integration
def test_unknown_and_revoked_secrets_are_not_found_while_members_keep_access(
    client: TestClient,
) -> None:
    _alice, alice_token = login(client)
    created = create_campaign(client)
    campaign_id = created.json()["id"]
    secret = created.json()["invitation"]["secret"]
    _bob, _bob_token = login(client, nickname="Боб")

    unknown = join_campaign(client, "x" * 43)
    assert unknown.status_code == 404
    assert unknown.json()["detail"] == "not_found"

    use_guest(client, alice_token)
    revoked = revoke_invitation(client, campaign_id)
    assert revoked.status_code == 200
    assert revoked.json()["invitation"]["active"] is False

    login(client, nickname="Кэрол")
    rejected = join_campaign(client, secret)
    assert rejected.status_code == 404
    assert rejected.json()["detail"] == "not_found"

    use_guest(client, alice_token)
    assert client.get(f"/api/campaigns/{campaign_id}").status_code == 200


@pytest.mark.integration
def test_join_requires_authentication_an_allowed_origin_and_a_valid_body(
    client: TestClient,
) -> None:
    anonymous = join_campaign(client, "secret")
    assert anonymous.status_code == 403
    assert anonymous.json()["detail"] == "forbidden"

    login(client)
    missing_origin = join_campaign(client, "secret", origin=None)
    foreign_origin = join_campaign(client, "secret", origin="http://evil.example")
    assert missing_origin.status_code == 403
    assert foreign_origin.status_code == 403

    for payload in ({}, {"secret": ""}, {"secret": 42}):
        invalid = client.post(
            "/api/campaigns/join",
            json=payload,
            headers={"Origin": ORIGIN},
        )
        assert invalid.status_code == 422


@pytest.mark.integration
def test_join_secret_is_never_logged_or_repeated(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    login(client)
    created = create_campaign(client)
    secret = created.json()["invitation"]["secret"]
    login(client, nickname="Боб")

    with caplog.at_level(logging.DEBUG):
        joined = join_campaign(client, secret)

    assert joined.status_code == 201
    assert secret not in caplog.text
    assert secret not in joined.text
    assert joined.json()["invitation"]["secret"] is None
    assert joined.json()["invitation"]["path"] is None


@pytest.mark.integration
def test_join_rate_limit_uses_its_own_bucket(client: TestClient) -> None:
    login(client)
    for _ in range(10):
        assert join_campaign(client, "unknown-secret").status_code == 404

    limited = join_campaign(client, "unknown-secret")

    assert limited.status_code == 429
    retry_after = int(limited.headers["Retry-After"])
    assert 1 <= retry_after <= 60

    # Creating a campaign still works: the create bucket was untouched.
    assert create_campaign(client).status_code == 201


@pytest.mark.integration
def test_revoke_invitation_is_organizer_only_idempotent_and_keeps_member_access(
    client: TestClient,
) -> None:
    _alice, alice_token = login(client)
    created = create_campaign(client)
    campaign_id = created.json()["id"]
    secret = created.json()["invitation"]["secret"]
    _bob, bob_token = login(client, nickname="Боб")
    assert join_campaign(client, secret).status_code == 201

    not_organizer = revoke_invitation(client, campaign_id)
    assert not_organizer.status_code == 403
    assert not_organizer.json()["detail"] == "forbidden"

    login(client, nickname="Кэрол")
    use_guest(client, bob_token)
    still_member = client.get(f"/api/campaigns/{campaign_id}")
    assert still_member.status_code == 200

    use_guest(client, alice_token)
    first = revoke_invitation(client, campaign_id)
    second = revoke_invitation(client, campaign_id)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["invitation"]["active"] is False
    assert second.json()["invitation"]["active"] is False
    assert first.json()["id"] == campaign_id

    use_guest(client, bob_token)
    assert client.get(f"/api/campaigns/{campaign_id}").status_code == 200

    use_guest(client, alice_token)
    assert client.get(f"/api/campaigns/{uuid4()}").status_code == 404
    missing = revoke_invitation(client, str(uuid4()))
    assert missing.status_code == 404
    assert missing.json()["detail"] == "not_found"

    client.cookies.clear()
    anonymous_revoke = client.post(
        f"/api/campaigns/{campaign_id}/invitation/revoke",
        headers={"Origin": ORIGIN},
    )
    assert anonymous_revoke.status_code == 403


@pytest.mark.integration
def test_revoke_invitation_requires_an_allowed_origin(client: TestClient) -> None:
    login(client)
    created = create_campaign(client)
    campaign_id = created.json()["id"]

    missing = revoke_invitation(client, campaign_id, origin=None)
    foreign = revoke_invitation(client, campaign_id, origin="http://evil.example")

    assert missing.status_code == 403
    assert foreign.status_code == 403
