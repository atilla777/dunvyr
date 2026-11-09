"""Confirmation commits the result once and leaves a recoverable shared fact."""

from uuid import uuid4

import pytest

from tests.integration.test_gameplay import queue_command, setup_queue
from tests.integration.test_proposals import payload, post

pytestmark = pytest.mark.integration


def test_confirmation_replay_and_public_aftermath(client):
    cid, card, encounter = setup_queue(client)
    proposal = post(client, cid, payload(card, encounter)).json()["proposals"][0]["id"]
    assert (
        queue_command(
            client, cid, character_id=card["id"], encounter_id=encounter["id"]
        ).status_code
        == 201
    )
    body = {"expected_version": 1, "expected_queue_version": 1, "expected_lifecycle_revision": 1}
    key = str(uuid4())
    first = post(client, cid, body, f"/{proposal}/confirm", key)
    assert first.status_code == 200, first.text
    result = first.json()
    assert len(result["result"]["dice"]) == 4
    assert result["result"]["difficulty"] == 5
    assert post(client, cid, body, f"/{proposal}/confirm", key).json() == {
        **result,
        "replayed": True,
    }
    assert (
        post(client, cid, {**body, "expected_version": 2}, f"/{proposal}/confirm", key).status_code
        == 409
    )
    assert post(client, cid, body, f"/{proposal}/confirm").status_code == 409
    assert client.get(f"/api/campaigns/{cid}/proposals").json()["proposals"] == []
    assert client.get(f"/api/campaigns/{cid}/queue").json()["queue"]["current_guest_id"] is None
    assert not client.get(f"/api/campaigns/{cid}/encounters").json()["catalog"]["encounters"][0][
        "solutions"
    ]
    history = client.get(f"/api/campaigns/{cid}/chat/events").json()
    fact = next(e for e in history["events"] if e["type"] == "check_resolved")
    assert fact["type"] == "check_resolved" and fact["result"] == result["result"]
    assert proposal not in str(fact) and "terminal-diagnostics-success" not in str(fact)
    assert client.get(f"/api/campaigns/{cid}/check-result").json()["result"] == result["result"]


@pytest.mark.parametrize("fault", ["apply", "record", "stage", "commit"])
def test_confirmation_rolls_back_every_participant(client, monkeypatch, fault):
    from dunvyr.adventures.infrastructure.snapshots import SqlSnapshotReader
    from dunvyr.communication.infrastructure.checks import CheckEventStager
    from dunvyr.gameplay.infrastructure.checks import SqlCheckRepository
    from dunvyr.gameplay.infrastructure.proposals import SqlProposalUnitOfWork

    cid, card, encounter = setup_queue(client)
    proposal = post(client, cid, payload(card, encounter)).json()["proposals"][0]["id"]
    queue_command(client, cid, character_id=card["id"], encounter_id=encounter["id"])
    before = client.get(f"/api/campaigns/{cid}/chat/events").json()["last_sequence"]
    body = {"expected_version": 1, "expected_queue_version": 1, "expected_lifecycle_revision": 1}
    targets = {
        "apply": (SqlSnapshotReader, "apply_check"),
        "record": (SqlCheckRepository, "record"),
        "stage": (CheckEventStager, "stage"),
        "commit": (SqlProposalUnitOfWork, "commit"),
    }

    def fail(*args, **kwargs):
        raise RuntimeError("injected")

    with monkeypatch.context() as patch:
        cls, name = targets[fault]
        patch.setattr(cls, name, fail)
        with pytest.raises(RuntimeError, match="injected"):
            post(client, cid, body, f"/{proposal}/confirm")
    assert client.get(f"/api/campaigns/{cid}/chat/events").json()["last_sequence"] == before
    assert len(client.get(f"/api/campaigns/{cid}/proposals").json()["proposals"]) == 1
    assert client.get(f"/api/campaigns/{cid}/queue").json()["version"] == 1
    assert client.get(f"/api/campaigns/{cid}/check-result").json()["result"] is None
    assert client.get(f"/api/campaigns/{cid}/encounters").json()["catalog"]["encounters"][0][
        "solutions"
    ]


def test_delivery_failure_does_not_lose_receipt(client, monkeypatch):
    from dunvyr.communication.infrastructure.game_sessions import GameSessionNotifier

    cid, card, encounter = setup_queue(client)
    proposal = post(client, cid, payload(card, encounter)).json()["proposals"][0]["id"]
    queue_command(client, cid, character_id=card["id"], encounter_id=encounter["id"])

    def fail(*args):
        raise RuntimeError("delivery")

    monkeypatch.setattr(GameSessionNotifier, "notify", fail)
    body = {"expected_version": 1, "expected_queue_version": 1, "expected_lifecycle_revision": 1}
    key = str(uuid4())
    first = post(client, cid, body, f"/{proposal}/confirm", key)
    assert first.status_code == 200
    assert post(client, cid, body, f"/{proposal}/confirm", key).json() == {
        **first.json(),
        "replayed": True,
    }
    assert (
        client.get(f"/api/campaigns/{cid}/check-result").json()["result"] == first.json()["result"]
    )
