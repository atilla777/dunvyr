"""Presence uses the authorized chat transport, not durable chat events."""

import asyncio
import threading
import time
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine
from starlette.websockets import WebSocketDisconnect

from dunvyr.campaigns.application.presence import PresenceRuntime
from dunvyr.communication.infrastructure.realtime import RealtimeHub
from dunvyr.main import create_app

from .test_communication_chat import (
    ORIGIN,
    chat_url,
    create_campaign,
    join_campaign,
    login,
    use_guest,
)


@pytest.mark.integration
def test_presence_tabs_snapshot_and_autonomous_offline(migrated_engine: Engine) -> None:
    app = create_app(
        engine=migrated_engine,
        presence_ping_interval=10,
        presence_lease=10,
        presence_grace=0.05,
        presence_sweep_interval=0.01,
    )
    with TestClient(app) as client:
        guest, _ = login(client)
        campaign = create_campaign(client).json()["id"]
        url = f"/api/campaigns/{campaign}/chat/events?after=0"
        empty = client.get(url).json()["presence_state"]
        assert empty["revision"] == 0
        with client.websocket_connect(chat_url(campaign), headers={"origin": ORIGIN}) as first:
            online = first.receive_json()
            assert online["type"] == "presence_state"
            assert online["presence_state"]["online_guest_ids"] == [guest["id"]]
            with client.websocket_connect(chat_url(campaign), headers={"origin": ORIGIN}):
                state = client.get(url).json()["presence_state"]
                assert state == online["presence_state"]
            assert client.get(url).json()["presence_state"] == state
        # Observe the sweeper via an independent subscriber, without issuing a snapshot query.
        hub = app.state.realtime_hub

        async def observe_expiry() -> dict[str, Any]:
            token, queue = hub.subscribe(UUID(campaign))
            try:
                return await asyncio.wait_for(queue.get(), timeout=1.0)
            finally:
                hub.unsubscribe(UUID(campaign), token)

        offline = asyncio.run(observe_expiry())
        assert offline["presence_state"]["online_guest_ids"] == []
        assert offline["presence_state"]["revision"] == state["revision"] + 1
        snapshot = client.get(url).json()
        assert snapshot["events"] == []
        assert snapshot["presence_state"] == offline["presence_state"]


@pytest.mark.integration
def test_server_nonce_renews_only_matching_pong(migrated_engine: Engine) -> None:
    app = create_app(
        engine=migrated_engine,
        presence_ping_interval=0.03,
        presence_pong_timeout=0.2,
        presence_lease=0.12,
        presence_grace=0.01,
        presence_sweep_interval=0.01,
    )
    with TestClient(app) as client:
        guest, _ = login(client)
        campaign = create_campaign(client).json()["id"]
        with client.websocket_connect(chat_url(campaign), headers={"origin": ORIGIN}) as socket:
            assert socket.receive_json()["type"] == "presence_state"
            ping = socket.receive_json()
            assert ping["type"] == "ping"
            socket.send_json({"type": "pong", "nonce": "not-the-server-nonce"})
            socket.send_json({"type": "pong", "nonce": ping["nonce"]})
            next_ping = socket.receive_json()
            assert next_ping["type"] == "ping"
            socket.send_json({"type": "pong", "nonce": next_ping["nonce"]})
            snapshot = client.get(f"/api/campaigns/{campaign}/chat/events").json()
            assert snapshot["presence_state"]["online_guest_ids"] == [guest["id"]]
            # A stale nonce cannot keep this lease alive after the last valid pong.
            socket.send_json({"type": "pong", "nonce": ping["nonce"]})
            time.sleep(0.15)
            snapshot = client.get(f"/api/campaigns/{campaign}/chat/events").json()
            assert snapshot["presence_state"]["online_guest_ids"] == []


@pytest.mark.integration
def test_restart_and_handshake_acl_do_not_change_membership(migrated_engine: Engine) -> None:
    first_app = create_app(engine=migrated_engine)
    with TestClient(first_app) as client:
        guest, token = login(client)
        campaign = create_campaign(client).json()["id"]
        url = f"/api/campaigns/{campaign}/chat/events"
        before = client.get(f"/api/campaigns/{campaign}").json()["members"]
        with (
            pytest.raises(WebSocketDisconnect),
            client.websocket_connect(chat_url(campaign), headers={"origin": "https://evil.test"}),
        ):
            pass
        state = client.get(url).json()["presence_state"]
        assert state["online_guest_ids"] == []
        assert state["revision"] == 0
        with client.websocket_connect(chat_url(campaign), headers={"origin": ORIGIN}) as socket:
            live = socket.receive_json()
            assert live["presence_state"]["online_guest_ids"] == [guest["id"]]
            assert client.get(url).json()["presence_state"] == live["presence_state"]
        assert client.get(f"/api/campaigns/{campaign}").json()["members"] == before
    second_app = create_app(engine=migrated_engine)
    with TestClient(second_app) as client:
        use_guest(client, token)
        restart = client.get(url).json()["presence_state"]
        assert restart["epoch"] != live["presence_state"]["epoch"]
        assert restart["revision"] == 0
        assert restart["online_guest_ids"] == []
        assert client.get(f"/api/campaigns/{campaign}").json()["members"] == before


@pytest.mark.integration
def test_matching_pong_revalidates_membership(migrated_engine: Engine) -> None:
    app = create_app(engine=migrated_engine, presence_ping_interval=0.03)
    with TestClient(app) as client:
        login(client)
        created = create_campaign(client).json()
        guest, token = login(client, "Боб")
        assert join_campaign(client, created["invitation"]["secret"]).status_code == 201
        use_guest(client, token)
        with client.websocket_connect(
            chat_url(created["id"]), headers={"origin": ORIGIN}
        ) as socket:
            assert socket.receive_json()["type"] == "presence_state"
            ping = socket.receive_json()
            assert ping["type"] == "ping"
            with migrated_engine.begin() as connection:
                connection.execute(
                    text("DELETE FROM campaigns_members WHERE campaign_id=:c AND guest_id=:g"),
                    {"c": created["id"], "g": guest["id"]},
                )
            socket.send_json({"type": "pong", "nonce": ping["nonce"]})
            with pytest.raises(WebSocketDisconnect) as rejected:
                socket.receive_json()
            assert rejected.value.code == 4403


@pytest.mark.integration
def test_presence_snapshot_live_barrier_with_delayed_publication() -> None:
    async def scenario() -> None:
        hub = RealtimeHub()
        entered, release = threading.Event(), threading.Event()

        class DelayedPublisher:
            def publish(self, campaign_id, state):
                if state.revision == 1:
                    entered.set()
                    assert release.wait(timeout=2)
                hub.publish(campaign_id, state)

        runtime = PresenceRuntime(DelayedPublisher())
        campaign, alice, bob = uuid4(), uuid4(), uuid4()
        token, queue = hub.subscribe(campaign)
        first = asyncio.create_task(asyncio.to_thread(runtime.connect, campaign, alice, uuid4()))
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            snapshot = runtime.read(campaign)
            assert snapshot.revision == 1 and snapshot.online_guest_ids == (alice,)
            await asyncio.to_thread(runtime.connect, campaign, bob, uuid4())
            newer = cast(dict[str, Any], await asyncio.wait_for(queue.get(), 2))
            assert newer["presence_state"]["revision"] == 2
            release.set()
            await first
            older = cast(dict[str, Any], await asyncio.wait_for(queue.get(), 2))
            assert older["presence_state"]["revision"] == snapshot.revision
            assert set(newer["presence_state"]["online_guest_ids"]) == {str(alice), str(bob)}
        finally:
            release.set()
            await first
            hub.unsubscribe(campaign, token)

    asyncio.run(scenario())
