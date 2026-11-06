"""Integration tests for the accepted chat reconnect protocol.

Reconnect is an existing contract (REST snapshot cursor + WS stream); these
tests exercise it from a client perspective: snapshot first, then resume the
live stream, with no duplicate or missing events.
"""

from __future__ import annotations

import json
from typing import cast
from uuid import uuid4

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


def create_campaign(client: TestClient, *, max_seats: int = 6):
    return client.post(
        "/api/campaigns",
        json={"name": "Ночная смена", "max_seats": max_seats},
        headers={"Origin": ORIGIN, "Idempotency-Key": str(uuid4())},
    )


def join_campaign(client: TestClient, secret: str):
    return client.post("/api/campaigns/join", json={"secret": secret}, headers={"Origin": ORIGIN})


def chat_url(campaign_id: str) -> str:
    return f"/api/campaigns/{campaign_id}/chat"


def message_frame(client_message_id: str, content: str) -> str:
    return json.dumps(
        {"type": "message", "client_message_id": client_message_id, "content": content}
    )


def snapshot(client: TestClient, campaign_id: str, after: int | None = None):
    query = "" if after is None else f"?after={after}"
    response = client.get(f"/api/campaigns/{campaign_id}/chat/events{query}")
    assert response.status_code == 200
    return response.json()


def event_count(engine: Engine, campaign_id: str, kind: str | None = None) -> int:
    query = "SELECT COUNT(*) FROM communication_events WHERE campaign_id = :campaign_id"
    params = {"campaign_id": campaign_id}
    if kind is not None:
        query += " AND kind = :kind"
        params["kind"] = kind
    with engine.connect() as connection:
        return int(connection.execute(text(query), params).scalar_one())


@pytest.mark.integration
def test_reconnect_snapshot_recovers_the_gap_without_duplicates_or_loss(
    client: TestClient,
    migrated_engine: Engine,
) -> None:
    alice, alice_token = login(client)
    created = create_campaign(client)
    campaign_id = created.json()["id"]
    secret = created.json()["invitation"]["secret"]
    bob, bob_token = login(client, nickname="Боб")
    assert join_campaign(client, secret).status_code == 201

    use_guest(client, alice_token)
    # What the client already has before the live connection: member_joined (seq 1).
    initial = snapshot(client, campaign_id)["events"]
    assert [event["sequence"] for event in initial] == [1]

    with TestClient(client.app) as bob_client:
        use_guest(client, alice_token)
        use_guest(bob_client, bob_token)
        with bob_client.websocket_connect(
            chat_url(campaign_id),
            headers={"origin": ORIGIN},
        ) as bob_ws:
            seen: list[dict[str, object]] = []
            with client.websocket_connect(
                chat_url(campaign_id),
                headers={"origin": ORIGIN},
            ) as alice_ws:
                alice_ws.send_text(message_frame(str(uuid4()), "До разрыва"))
                seen.append(alice_ws.receive_json())
                assert bob_ws.receive_json()["event_id"] == seen[-1]["event_id"]

            # Alice is offline now. Bob keeps playing.
            missed: list[dict[str, object]] = []
            bob_ws.send_text(message_frame(str(uuid4()), "Пока Алиса офлайн"))
            missed.append(bob_ws.receive_json())

            carol, carol_token = login(client, nickname="Кэрол")
            use_guest(client, carol_token)
            assert join_campaign(client, secret).status_code == 201
            missed.append(bob_ws.receive_json())

            assert [event["sequence"] for event in missed] == [3, 4]
            joined = missed[1]
            assert joined["type"] == "member_joined"
            joined_member = joined["member"]
            assert isinstance(joined_member, dict)
            assert joined_member["guest_id"] == carol["id"]

            # Reconnect: the REST snapshot with the last seen cursor restores
            # exactly the events missed while the socket was gone.
            use_guest(client, alice_token)
            cursor = seen[-1]["sequence"]
            assert isinstance(cursor, int)
            recovered = snapshot(client, campaign_id, after=cursor)["events"]
            assert [event["event_id"] for event in recovered] == [
                event["event_id"] for event in missed
            ]
            assert [event["sequence"] for event in recovered] == [3, 4]

            merged = {event["event_id"]: event for event in initial + seen + recovered}
            assert len(merged) == len(initial) + len(seen) + len(recovered)
            assert [event["sequence"] for event in merged.values()] == [1, 2, 3, 4]

            # Streaming continues after the snapshot without replaying the gap.
            with client.websocket_connect(
                chat_url(campaign_id),
                headers={"origin": ORIGIN},
            ) as resumed_ws:
                bob_ws.send_text(message_frame(str(uuid4()), "После восстановления"))
                after_event = resumed_ws.receive_json()
                assert bob_ws.receive_json()["event_id"] == after_event["event_id"]
                assert after_event["sequence"] == 5
                assert after_event["event_id"] not in merged

    assert event_count(migrated_engine, campaign_id) == 5
    assert bob["id"] != alice["id"]


@pytest.mark.integration
def test_repeated_snapshot_for_the_same_cursor_does_not_duplicate_the_stream(
    client: TestClient,
    migrated_engine: Engine,
) -> None:
    _alice, alice_token = login(client)
    created = create_campaign(client)
    campaign_id = created.json()["id"]
    use_guest(client, alice_token)

    with client.websocket_connect(chat_url(campaign_id), headers={"origin": ORIGIN}) as socket:
        socket.send_text(message_frame(str(uuid4()), "Единственное сообщение"))
        live = socket.receive_json()
        assert live["sequence"] == 1

    first = snapshot(client, campaign_id, after=0)
    second = snapshot(client, campaign_id, after=0)
    assert first["last_sequence"] == second["last_sequence"] == 1
    assert [event["event_id"] for event in first["events"]] == [
        event["event_id"] for event in second["events"]
    ]
    assert [event["sequence"] for event in first["events"]] == [1]

    merged = {event["event_id"]: event for event in [live] + first["events"] + second["events"]}
    assert list(merged) == [live["event_id"]]

    tail = snapshot(client, campaign_id, after=1)
    assert tail["events"] == []
    assert tail["last_sequence"] == 1
    assert event_count(migrated_engine, campaign_id, "message") == 1


@pytest.mark.integration
def test_two_clients_of_one_identity_reconnect_without_duplicate_events(
    client: TestClient,
    migrated_engine: Engine,
) -> None:
    _alice, alice_token = login(client)
    created = create_campaign(client)
    campaign_id = created.json()["id"]

    with TestClient(client.app) as second_client:
        use_guest(client, alice_token)
        use_guest(second_client, alice_token)

        with second_client.websocket_connect(
            chat_url(campaign_id),
            headers={"origin": ORIGIN},
        ) as second_ws:
            with client.websocket_connect(
                chat_url(campaign_id),
                headers={"origin": ORIGIN},
            ) as first_ws:
                client_message_id = str(uuid4())
                first_ws.send_text(message_frame(client_message_id, "Один раз"))
                original = first_ws.receive_json()
                assert second_ws.receive_json()["event_id"] == original["event_id"]

            # The first client dropped; the second one keeps sending.
            second_ws.send_text(message_frame(str(uuid4()), "Пока первый был офлайн"))
            missed = second_ws.receive_json()
            assert missed["sequence"] == 2

            use_guest(client, alice_token)
            recovered = snapshot(client, campaign_id, after=original["sequence"])["events"]
            assert [event["event_id"] for event in recovered] == [missed["event_id"]]

            with client.websocket_connect(
                chat_url(campaign_id),
                headers={"origin": ORIGIN},
            ) as resumed:
                # The same server idempotency key replays instead of duplicating.
                resumed.send_text(message_frame(client_message_id, "Один раз"))
                assert resumed.receive_json() == {
                    "type": "ack",
                    "event_id": original["event_id"],
                }

    events = snapshot(client, campaign_id)["events"]
    event_ids = [event["event_id"] for event in events]
    assert len(event_ids) == len(set(event_ids)) == 2
    assert [event["sequence"] for event in events] == [1, 2]
    assert event_count(migrated_engine, campaign_id, "message") == 2


@pytest.mark.integration
def test_subscribe_precedes_accept_and_failed_accept_unsubscribes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio
    import importlib
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    module = importlib.import_module("dunvyr.communication.presentation.router")
    campaign_id = uuid4()
    calls: list[str] = []

    class Hub:
        def subscribe(self, requested):
            assert requested == campaign_id
            calls.append("subscribe")
            return "token", asyncio.Queue()

        def unsubscribe(self, requested, token):
            assert requested == campaign_id and token == "token"
            calls.append("unsubscribe")

    async def accept():
        calls.append("accept")
        raise RuntimeError("handshake failed")

    app = SimpleNamespace(
        state=SimpleNamespace(
            allowed_origins=SimpleNamespace(contains=lambda _: True), realtime_hub=Hub()
        )
    )
    socket = SimpleNamespace(
        app=app, headers={"origin": ORIGIN}, cookies={}, accept=accept, close=AsyncMock()
    )
    monkeypatch.setattr(
        module, "run_in_threadpool", AsyncMock(side_effect=[SimpleNamespace(id=uuid4()), object()])
    )
    with pytest.raises(RuntimeError, match="handshake failed"):
        asyncio.run(module.campaign_chat(socket, campaign_id))
    assert calls == ["subscribe", "accept", "unsubscribe"]
