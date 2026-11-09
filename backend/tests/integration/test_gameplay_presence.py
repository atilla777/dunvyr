"""Queue swap, lifecycle and bounded offline reconciliation."""

from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from tests.integration.test_campaigns import login
from tests.integration.test_gameplay import queue_command, setup_queue


def add_player(client: Any, cid: str) -> tuple[TestClient, dict[str, Any], UUID]:
    player = TestClient(client.app)
    login(player, "Boris")
    joined = player.post(
        "/api/campaigns/join",
        json={"secret": client.queue_invitation},
        headers={"Origin": "http://localhost:5173"},
    )
    assert joined.status_code == 201, joined.text
    card = player.post(
        f"/api/campaigns/{cid}/character",
        json={"name": "Boris", "appearance": "coat", "archetype_id": "scout"},
        headers={"Origin": "http://localhost:5173"},
    ).json()
    connection = uuid4()
    client.app.state.presence.connect(UUID(cid), UUID(card["guest_id"]), connection)
    return player, card, connection


@pytest.mark.integration
def test_start_includes_offline_valid_cards_and_normalizes_initial_queue(client):
    from dunvyr.campaigns.application.presence import PresenceRuntime

    cid, card, encounter = setup_queue(client)
    _, second, _ = add_player(client, cid)
    client.app.state.presence = PresenceRuntime(client.app.state.realtime_hub)
    client.app.state.presence.connect(UUID(cid), UUID(second["guest_id"]), uuid4())
    result = queue_command(client, cid, character_id=card["id"], encounter_id=encounter["id"])
    assert result.status_code == 201
    assert len(result.json()["queue"]["participants"]) == 2
    assert result.json()["queue"]["skipped"] == [card["guest_id"]]
    assert result.json()["queue"]["current_guest_id"] == second["guest_id"]


@pytest.mark.integration
def test_swap_current_with_online_later_once_and_preserve_receipt(client):
    cid, card, encounter = setup_queue(client)
    player, second, _ = add_player(client, cid)
    start = queue_command(client, cid, character_id=card["id"], encounter_id=encounter["id"])
    assert start.json()["queue"]["round_order"] == [card["guest_id"], second["guest_id"]]
    key = str(uuid4())
    swap = queue_command(
        client, cid, "swap", key=key, expected_version=1, target_guest_id=second["guest_id"]
    )
    assert swap.status_code == 200, swap.text
    assert swap.json()["version"] == 2
    assert swap.json()["queue"]["current_guest_id"] == second["guest_id"]
    assert swap.json()["queue"]["cursor"] == 0 and swap.json()["queue"]["skipped"] == []
    assert (
        queue_command(
            client, cid, "swap", expected_version=2, target_guest_id=second["guest_id"]
        ).status_code
        == 409
    )
    assert queue_command(
        client, cid, "swap", key=key, expected_version=1, target_guest_id=second["guest_id"]
    ).json() == {**swap.json(), "replayed": True}
    assert (
        queue_command(
            player, cid, "swap", expected_version=2, target_guest_id=card["guest_id"]
        ).status_code
        == 200
    )


@pytest.mark.integration
def test_reconciliation_skips_offline_waits_all_offline_and_reconnect_next_round(client):
    cid, card, encounter = setup_queue(client)
    _, second, connection = add_player(client, cid)
    queue_command(client, cid, character_id=card["id"], encounter_id=encounter["id"])
    swapped = queue_command(
        client, cid, "swap", expected_version=1, target_guest_id=second["guest_id"]
    )
    assert swapped.status_code == 200
    from dunvyr.campaigns.application.presence import PresenceRuntime

    client.app.state.presence = PresenceRuntime(client.app.state.realtime_hub)
    with client.app.state.session_factory() as session:
        client.app.state.queue_service_factory(session).reconcile(UUID(cid))
    exhausted = client.get(f"/api/campaigns/{cid}/queue").json()
    assert exhausted["queue"]["current_guest_id"] is None
    assert exhausted["queue"]["skipped"] == [second["guest_id"], card["guest_id"]]
    for _ in range(3):
        with client.app.state.session_factory() as session:
            client.app.state.queue_service_factory(session).reconcile(UUID(cid))
    assert client.get(f"/api/campaigns/{cid}/queue").json() == exhausted
    client.app.state.presence.connect(UUID(cid), UUID(second["guest_id"]), connection)
    with client.app.state.session_factory() as session:
        client.app.state.queue_service_factory(session).reconcile(UUID(cid))
    resumed = client.get(f"/api/campaigns/{cid}/queue").json()
    assert resumed["queue"]["round_number"] == 2
    assert resumed["queue"]["round_order"] == [card["guest_id"], second["guest_id"]]
    assert resumed["queue"]["skipped"] == [card["guest_id"]]
    assert resumed["queue"]["current_guest_id"] == second["guest_id"]
