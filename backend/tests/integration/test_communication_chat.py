"""Integration tests for the campaign chat WebSocket and history snapshot."""

from __future__ import annotations

import json
from contextlib import nullcontext
from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine
from starlette.websockets import WebSocketDisconnect

from dunvyr.communication.infrastructure.repositories import SqlAlchemyChatEventRepository

from .support import receive_non_presence

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


def create_campaign(client: TestClient, *, max_seats: int = 4):
    return client.post(
        "/api/campaigns",
        json={"name": "Ночная смена", "max_seats": max_seats},
        headers={"Origin": ORIGIN, "Idempotency-Key": str(uuid4())},
    )


def join_campaign(client: TestClient, secret: str):
    return client.post("/api/campaigns/join", json={"secret": secret}, headers={"Origin": ORIGIN})


def chat_url(campaign_id: str) -> str:
    return f"/api/campaigns/{campaign_id}/chat"


def event_count(engine: Engine, campaign_id: str, kind: str | None = None) -> int:
    query = "SELECT COUNT(*) FROM communication_events WHERE campaign_id = :campaign_id"
    params = {"campaign_id": campaign_id}
    if kind is not None:
        query += " AND kind = :kind"
        params["kind"] = kind
    with engine.connect() as connection:
        return int(connection.execute(text(query), params).scalar_one())


def message_frame(client_message_id: str, content: str) -> str:
    return json.dumps(
        {"type": "message", "client_message_id": client_message_id, "content": content}
    )


@pytest.mark.integration
def test_messages_are_broadcast_to_all_connected_members_and_snapshotted(
    client: TestClient,
    migrated_engine: Engine,
) -> None:
    alice, alice_token = login(client)
    created = create_campaign(client)
    campaign_id = created.json()["id"]
    secret = created.json()["invitation"]["secret"]
    bob, bob_token = login(client, nickname="Боб")
    assert join_campaign(client, secret).status_code == 201

    with nullcontext(TestClient(client.app)) as bob_client:
        use_guest(client, alice_token)
        use_guest(bob_client, bob_token)

        with (
            client.websocket_connect(chat_url(campaign_id), headers={"origin": ORIGIN}) as alice_ws,
            bob_client.websocket_connect(
                chat_url(campaign_id),
                headers={"origin": ORIGIN},
            ) as bob_ws,
        ):
            client_message_id = str(uuid4())
            alice_ws.send_text(message_frame(client_message_id, "Привет, кампания"))

            for socket in (alice_ws, bob_ws):
                event = receive_non_presence(socket)
                assert event["type"] == "message"
                assert event["campaign_id"] == campaign_id
                assert event["sequence"] == 2
                assert event["message"]["content"] == "Привет, кампания"
                assert event["message"]["client_message_id"] == client_message_id
                assert event["message"]["author_id"] == alice["id"]
                assert event["message"]["author_nickname"] == "Алиса"

        snapshot = bob_client.get(f"/api/campaigns/{campaign_id}/chat/events")
        assert snapshot.status_code == 200
        body = snapshot.json()
        assert body["campaign_id"] == campaign_id
        assert body["last_sequence"] == 2
        assert [event["type"] for event in body["events"]] == ["member_joined", "message"]
        message_event = body["events"][1]
        assert message_event["message"]["content"] == "Привет, кампания"

    assert bob["id"] != alice["id"]
    assert event_count(migrated_engine, campaign_id) == 2


@pytest.mark.integration
def test_two_clients_of_one_identity_do_not_duplicate_a_message(
    client: TestClient,
    migrated_engine: Engine,
) -> None:
    _alice, alice_token = login(client)
    created = create_campaign(client)
    campaign_id = created.json()["id"]

    with nullcontext(TestClient(client.app)) as second_client:
        use_guest(client, alice_token)
        use_guest(second_client, alice_token)

        with (
            client.websocket_connect(chat_url(campaign_id), headers={"origin": ORIGIN}) as first_ws,
            second_client.websocket_connect(
                chat_url(campaign_id),
                headers={"origin": ORIGIN},
            ) as second_ws,
        ):
            client_message_id = str(uuid4())
            first_ws.send_text(message_frame(client_message_id, "Один раз"))

            first_event = receive_non_presence(first_ws)
            second_event = receive_non_presence(second_ws)
            assert first_event["event_id"] == second_event["event_id"]

            second_ws.send_text(message_frame(client_message_id, "Один раз"))
            ack = receive_non_presence(second_ws)
            assert ack == {"type": "ack", "event_id": first_event["event_id"]}

    assert event_count(migrated_engine, campaign_id, "message") == 1


@pytest.mark.integration
def test_handshake_rejects_missing_session_bad_origin_and_non_member(
    client: TestClient,
) -> None:
    _alice, alice_token = login(client)
    created = create_campaign(client)
    campaign_id = created.json()["id"]
    _bob, bob_token = login(client, nickname="Боб")

    # A signed-in guest who never joined the campaign.
    use_guest(client, bob_token)
    with (
        pytest.raises(WebSocketDisconnect) as non_member,
        client.websocket_connect(chat_url(campaign_id), headers={"origin": ORIGIN}),
    ):
        pass
    assert non_member.value.code == 4403

    # A member with an origin outside the configured allow-list.
    use_guest(client, alice_token)
    with (
        pytest.raises(WebSocketDisconnect) as bad_origin,
        client.websocket_connect(
            chat_url(campaign_id),
            headers={"origin": "http://evil.example"},
        ),
    ):
        pass
    assert bad_origin.value.code == 4403

    # No session cookie at all.
    client.cookies.clear()
    with (
        pytest.raises(WebSocketDisconnect) as anonymous,
        client.websocket_connect(chat_url(campaign_id), headers={"origin": ORIGIN}),
    ):
        pass
    assert anonymous.value.code == 4403

    # An authorized member handshake still succeeds.
    use_guest(client, alice_token)
    with client.websocket_connect(chat_url(campaign_id), headers={"origin": ORIGIN}) as socket:
        socket.send_text(message_frame(str(uuid4()), "Работает"))
        assert receive_non_presence(socket)["type"] == "message"


@pytest.mark.integration
def test_send_after_membership_loss_is_forbidden_and_not_persisted(
    client: TestClient,
    migrated_engine: Engine,
) -> None:
    _alice, _alice_token = login(client)
    created = create_campaign(client)
    campaign_id = created.json()["id"]
    secret = created.json()["invitation"]["secret"]
    bob, bob_token = login(client, nickname="Боб")
    assert join_campaign(client, secret).status_code == 201
    use_guest(client, bob_token)

    with client.websocket_connect(chat_url(campaign_id), headers={"origin": ORIGIN}) as socket:
        with migrated_engine.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM campaigns_members "
                    "WHERE campaign_id = :campaign_id AND guest_id = :guest_id"
                ),
                {"campaign_id": campaign_id, "guest_id": bob["id"]},
            )

        socket.send_text(message_frame(str(uuid4()), "Меня уже нет"))

        error = receive_non_presence(socket)
        assert error["type"] == "error"
        assert error["code"] == "forbidden"

    assert event_count(migrated_engine, campaign_id, "message") == 0


@pytest.mark.integration
def test_member_joined_is_delivered_live_and_persisted_in_the_same_stream(
    client: TestClient,
    migrated_engine: Engine,
) -> None:
    _alice, alice_token = login(client)
    created = create_campaign(client)
    campaign_id = created.json()["id"]
    secret = created.json()["invitation"]["secret"]
    bob, bob_token = login(client, nickname="Боб")
    use_guest(client, alice_token)

    with client.websocket_connect(chat_url(campaign_id), headers={"origin": ORIGIN}) as socket:
        socket.send_text(message_frame(str(uuid4()), "Добро пожаловать"))
        message_event = receive_non_presence(socket)
        assert message_event["sequence"] == 1

        use_guest(client, bob_token)
        assert join_campaign(client, secret).status_code == 201

        member_event = receive_non_presence(socket)
        assert member_event["type"] == "member_joined"
        assert member_event["sequence"] == 2
        assert member_event["member"]["guest_id"] == bob["id"]
        assert member_event["member"]["nickname"] == "Боб"
        assert member_event["member"]["role"] == "player"

    use_guest(client, alice_token)
    snapshot = client.get(f"/api/campaigns/{campaign_id}/chat/events")
    assert snapshot.status_code == 200
    assert [event["type"] for event in snapshot.json()["events"]] == [
        "message",
        "member_joined",
    ]
    assert event_count(migrated_engine, campaign_id, "member_joined") == 1


@pytest.mark.integration
def test_member_joined_is_broadcast_to_every_connected_member(
    client: TestClient,
) -> None:
    _alice, alice_token = login(client)
    created = create_campaign(client, max_seats=5)
    campaign_id = created.json()["id"]
    secret = created.json()["invitation"]["secret"]

    _carol, carol_token = login(client, nickname="Кэрол")
    assert join_campaign(client, secret).status_code == 201

    use_guest(client, alice_token)
    with client.websocket_connect(chat_url(campaign_id), headers={"origin": ORIGIN}) as alice_ws:
        use_guest(client, carol_token)
        with client.websocket_connect(
            chat_url(campaign_id),
            headers={"origin": ORIGIN},
        ) as carol_ws:
            _bob, bob_token = login(client, nickname="Боб")
            use_guest(client, bob_token)
            assert join_campaign(client, secret).status_code == 201

            for socket in (alice_ws, carol_ws):
                event = receive_non_presence(socket)
                assert event["type"] == "member_joined"
                assert event["member"]["nickname"] == "Боб"


@pytest.mark.integration
def test_broadcast_happens_only_after_the_message_is_committed(
    client: TestClient,
    migrated_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _alice, alice_token = login(client)
    created = create_campaign(client)
    campaign_id = created.json()["id"]
    use_guest(client, alice_token)
    hub = cast(FastAPI, client.app).state.realtime_hub
    original_broadcast = hub.broadcast
    committed_rows: list[int] = []

    def recording_broadcast(campaign_id_arg: UUID, payload: dict[str, object]) -> None:
        if payload["type"] == "message":
            committed_rows.append(event_count(migrated_engine, campaign_id, "message"))
        original_broadcast(campaign_id_arg, payload)

    monkeypatch.setattr(hub, "broadcast", recording_broadcast)

    with client.websocket_connect(chat_url(campaign_id), headers={"origin": ORIGIN}) as socket:
        socket.send_text(message_frame(str(uuid4()), "После коммита"))
        assert receive_non_presence(socket)["type"] == "message"

    assert committed_rows == [1]


@pytest.mark.integration
def test_persist_failure_never_broadcasts_and_stores_nothing(
    client: TestClient,
    migrated_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _alice, alice_token = login(client)
    created = create_campaign(client)
    campaign_id = created.json()["id"]
    use_guest(client, alice_token)
    broadcasts: list[dict[str, object]] = []
    monkeypatch.setattr(
        cast(FastAPI, client.app).state.realtime_hub,
        "broadcast",
        lambda _campaign_id, payload: broadcasts.append(payload),
    )

    def failing_append(_self: object, _event: object) -> None:
        raise RuntimeError("persist failed")

    monkeypatch.setattr(SqlAlchemyChatEventRepository, "append", failing_append)

    with client.websocket_connect(chat_url(campaign_id), headers={"origin": ORIGIN}) as socket:
        socket.send_text(message_frame(str(uuid4()), "persist failure"))
        error = receive_non_presence(socket)
        assert error["type"] == "error"
        assert error["code"] == "internal"

    assert [frame for frame in broadcasts if frame["type"] != "presence_state"] == []
    assert event_count(migrated_engine, campaign_id) == 0


@pytest.mark.integration
def test_delivery_failure_after_commit_keeps_the_message_saved(
    client: TestClient,
    migrated_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _alice, alice_token = login(client)
    created = create_campaign(client)
    campaign_id = created.json()["id"]
    use_guest(client, alice_token)

    def failing_broadcast(_campaign_id: object, _payload: dict[str, object]) -> None:
        raise RuntimeError("delivery failed")

    monkeypatch.setattr(
        cast(FastAPI, client.app).state.realtime_hub,
        "broadcast",
        failing_broadcast,
    )

    with client.websocket_connect(chat_url(campaign_id), headers={"origin": ORIGIN}) as socket:
        socket.send_text(message_frame(str(uuid4()), "Сохранится несмотря ни на что"))
        error = receive_non_presence(socket)
        assert error["type"] == "error"
        assert error["code"] == "delivery_failed"

    assert event_count(migrated_engine, campaign_id, "message") == 1
    snapshot = client.get(f"/api/campaigns/{campaign_id}/chat/events")
    assert snapshot.status_code == 200
    assert snapshot.json()["events"][0]["message"]["content"] == "Сохранится несмотря ни на что"


@pytest.mark.integration
def test_history_is_member_only_and_validates_the_cursor(client: TestClient) -> None:
    _alice, _alice_token = login(client)
    created = create_campaign(client)
    campaign_id = created.json()["id"]

    _bob, bob_token = login(client, nickname="Боб")
    use_guest(client, bob_token)
    forbidden = client.get(f"/api/campaigns/{campaign_id}/chat/events")
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "forbidden"

    client.cookies.clear()
    anonymous = client.get(f"/api/campaigns/{campaign_id}/chat/events")
    assert anonymous.status_code == 403

    _alice, alice_token = login(client)
    use_guest(client, alice_token)
    negative = client.get(f"/api/campaigns/{campaign_id}/chat/events?after=-1")
    assert negative.status_code == 422


FOREIGN_TABLES = (
    "campaigns_campaigns",
    "campaigns_members",
    "identity_guests",
    "identity_sessions",
)


def foreign_row_counts(engine: Engine) -> dict[str, int]:
    counts: dict[str, int] = {}
    with engine.connect() as connection:
        for table in FOREIGN_TABLES:
            counts[table] = int(
                connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
            )
    return counts


@pytest.mark.integration
def test_chat_operations_never_write_campaigns_or_identity_tables(
    client: TestClient,
    migrated_engine: Engine,
) -> None:
    _alice, alice_token = login(client)
    created = create_campaign(client)
    campaign_id = created.json()["id"]
    secret = created.json()["invitation"]["secret"]
    _bob, _bob_token = login(client, nickname="Боб")
    assert join_campaign(client, secret).status_code == 201

    before = foreign_row_counts(migrated_engine)
    use_guest(client, alice_token)
    with client.websocket_connect(chat_url(campaign_id), headers={"origin": ORIGIN}) as socket:
        client_message_id = str(uuid4())
        socket.send_text(message_frame(client_message_id, "чат не трогает чужие таблицы"))
        delivered = receive_non_presence(socket)
        assert delivered["type"] == "message"
        socket.send_text(message_frame(client_message_id, "чат не трогает чужие таблицы"))
        replay = receive_non_presence(socket)
        assert replay["type"] == "ack"

    snapshot = client.get(f"/api/campaigns/{campaign_id}/chat/events")
    assert snapshot.status_code == 200
    assert foreign_row_counts(migrated_engine) == before
