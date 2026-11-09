"""Live proposal invalidations are private, content-free and reauthorized."""

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from starlette.websockets import WebSocketDisconnect

from tests.integration.support import receive_non_presence
from tests.integration.test_campaigns import login
from tests.integration.test_gameplay import setup_queue
from tests.integration.test_gameplay_presence import add_player
from tests.integration.test_proposals import ORIGIN, payload, post

pytestmark = pytest.mark.integration


def test_only_owner_tabs_receive_content_free_frame_and_history_remains_public(client):
    cid, _, encounter = setup_queue(client)
    player, card, _ = add_player(client, cid)
    other = TestClient(client.app)
    login(other, "Another")
    assert (
        other.post(
            "/api/campaigns/join",
            json={"secret": client.queue_invitation},
            headers={"Origin": ORIGIN},
        ).status_code
        == 201
    )
    path = f"/api/campaigns/{cid}/chat"
    headers = {"Origin": ORIGIN}
    with (
        client.websocket_connect(path, headers=headers) as organizer,
        other.websocket_connect(path, headers=headers) as another,
        player.websocket_connect(path, headers=headers) as first,
        player.websocket_connect(path, headers=headers) as second,
    ):
        key = str(uuid4())
        body = payload(card, encounter)
        result = post(player, cid, body, key=key)
        assert result.status_code == 201
        proposal_id = result.json()["proposals"][0]["id"]
        marker = {"type": "test_marker"}
        client.app.state.realtime_hub.broadcast(UUID(cid), marker)
        expected = {"type": "proposals_changed", "campaign_id": cid}
        assert receive_non_presence(first) == expected
        assert receive_non_presence(second) == expected
        assert receive_non_presence(first) == marker
        assert receive_non_presence(second) == marker
        assert receive_non_presence(organizer) == marker
        assert receive_non_presence(another) == marker
        assert post(player, cid, body, key=key).json()["replayed"] is True
        client.app.state.realtime_hub.broadcast(UUID(cid), marker)
        assert receive_non_presence(first) == marker
        assert receive_non_presence(second) == marker
        for member in (client, other, player):
            history = member.get(f"/api/campaigns/{cid}/chat/events").text
            assert proposal_id not in history and "proposals_changed" not in history
        assert client.get(f"/api/campaigns/{cid}/proposals").json()["proposals"] == []
        assert other.get(f"/api/campaigns/{cid}/proposals").json()["proposals"] == []


def test_private_frame_rechecks_membership_before_delivery(client):
    cid, _, _ = setup_queue(client)
    player, card, _ = add_player(client, cid)
    with player.websocket_connect(
        f"/api/campaigns/{cid}/chat", headers={"Origin": ORIGIN}
    ) as socket:
        with client.app.state.engine.begin() as conn:
            conn.execute(
                text("DELETE FROM campaigns_members WHERE campaign_id=:cid AND guest_id=:guest"),
                {"cid": cid, "guest": card["guest_id"]},
            )
        client.app.state.realtime_hub.proposals_changed(UUID(cid), UUID(card["guest_id"]))
        with pytest.raises(WebSocketDisconnect) as rejected:
            receive_non_presence(socket)
        assert rejected.value.code == 4403


def test_receipt_replay_rechecks_membership(client):
    cid, _, encounter = setup_queue(client)
    player, card, _ = add_player(client, cid)
    body, key = payload(card, encounter), str(uuid4())
    assert post(player, cid, body, key=key).status_code == 201
    with client.app.state.engine.begin() as conn:
        conn.execute(
            text("DELETE FROM campaigns_members WHERE campaign_id=:cid AND guest_id=:guest"),
            {"cid": cid, "guest": card["guest_id"]},
        )
    assert post(player, cid, body, key=key).status_code == 403
    assert player.get(f"/api/campaigns/{cid}/proposals").status_code == 403
