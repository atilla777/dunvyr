"""Paused and ended meetings suspend, never reset a persisted queue."""

from typing import Any
from uuid import UUID, uuid4

import pytest

from dunvyr.campaigns.application.presence import PresenceRuntime
from tests.integration.test_game_session import command
from tests.integration.test_gameplay import queue_command, setup_queue
from tests.integration.test_gameplay_presence import add_player


def reconcile(client: Any, cid: str) -> None:
    with client.app.state.session_factory() as session:
        client.app.state.queue_service_factory(session).reconcile(UUID(cid))


@pytest.mark.integration
def test_pause_resume_end_new_meeting_and_exact_old_receipt(client):
    cid, card, encounter = setup_queue(client)
    _, second, _ = add_player(client, cid)
    key = str(uuid4())
    start = queue_command(
        client, cid, key=key, character_id=card["id"], encounter_id=encounter["id"]
    ).json()
    sid = client.get(f"/api/campaigns/{cid}/game-session").json()["session"]["id"]
    assert command(client, cid, "pause", 1, sid).status_code == 200
    client.app.state.presence = PresenceRuntime(client.app.state.realtime_hub)
    reconcile(client, cid)
    assert client.get(f"/api/campaigns/{cid}/queue").json()["version"] == 1
    assert (
        queue_command(
            client,
            cid,
            "swap",
            expected_version=1,
            expected_lifecycle_revision=2,
            target_guest_id=second["guest_id"],
        ).json()["detail"]
        == "meeting_not_running"
    )
    assert command(client, cid, "resume", 2, sid).status_code == 200
    reconcile(client, cid)
    exhausted = client.get(f"/api/campaigns/{cid}/queue").json()
    assert exhausted["version"] == 2 and exhausted["queue"]["current_guest_id"] is None
    assert command(client, cid, "end", 3, sid).status_code == 200
    client.app.state.presence.connect(UUID(cid), UUID(second["guest_id"]), uuid4())
    reconcile(client, cid)
    assert client.get(f"/api/campaigns/{cid}/queue").json() == exhausted
    assert command(client, cid, revision=4).status_code == 201
    reconcile(client, cid)
    resumed = client.get(f"/api/campaigns/{cid}/queue").json()
    assert resumed["version"] == 3 and resumed["queue"]["round_number"] == 2
    assert resumed["queue"]["current_guest_id"] == second["guest_id"]
    assert queue_command(
        client, cid, key=key, character_id=card["id"], encounter_id=encounter["id"]
    ).json() == {**start, "replayed": True}
    assert (
        queue_command(
            client,
            cid,
            key=key,
            expected_lifecycle_revision=5,
            character_id=card["id"],
            encounter_id=encounter["id"],
        ).json()["detail"]
        == "conflict"
    )


@pytest.mark.integration
def test_multiple_tabs_and_late_members_do_not_duplicate_frozen_roster(client):
    cid, card, encounter = setup_queue(client)
    connection = uuid4()
    client.app.state.presence.connect(UUID(cid), UUID(card["guest_id"]), connection)
    started = queue_command(
        client, cid, character_id=card["id"], encounter_id=encounter["id"]
    ).json()
    client.app.state.presence.disconnect(connection)
    reconcile(client, cid)
    assert (
        client.get(f"/api/campaigns/{cid}/queue").json()["queue"]["current_guest_id"]
        == card["guest_id"]
    )
    add_player(client, cid)
    reconcile(client, cid)
    assert (
        client.get(f"/api/campaigns/{cid}/queue").json()["queue"]["participants"]
        == started["queue"]["participants"]
    )
