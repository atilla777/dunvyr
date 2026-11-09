"""Confirmation rejects unsupported checks and unauthorized actors without spending."""

from dataclasses import replace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from dunvyr.adventures.infrastructure.snapshots import SqlSnapshotReader
from tests.integration.test_campaigns import login
from tests.integration.test_gameplay import queue_command, setup_queue
from tests.integration.test_proposals import payload, post

pytestmark = pytest.mark.integration


def test_unsupported_difficulty_and_nonmember_cannot_spend(client, monkeypatch):
    cid, card, encounter = setup_queue(client)
    proposal = post(client, cid, payload(card, encounter)).json()["proposals"][0]["id"]
    queue_command(client, cid, character_id=card["id"], encounter_id=encounter["id"])
    body = {"expected_version": 1, "expected_queue_version": 1, "expected_lifecycle_revision": 1}
    outsider = TestClient(client.app)
    login(outsider, "outsider")
    assert post(outsider, cid, body, f"/{proposal}/confirm").status_code == 403
    original = SqlSnapshotReader.available_encounters

    def altered(self, campaign_id):
        catalog = original(self, campaign_id)
        assert catalog is not None
        item = catalog.encounters[0]
        solution = item.solutions[0]
        return replace(
            catalog,
            encounters=(
                replace(
                    item,
                    solutions=(replace(solution, check=replace(solution.check, difficulty=6)),),
                ),
            ),
        )

    monkeypatch.setattr(SqlSnapshotReader, "available_encounters", altered)
    response = post(client, cid, body, f"/{proposal}/confirm", str(uuid4()))
    assert response.status_code == 409 and response.json()["detail"] == "unsupported_check"
    assert client.get(f"/api/campaigns/{cid}/queue").json()["version"] == 1
    assert client.get(f"/api/campaigns/{cid}/check-result").json()["result"] is None


@pytest.mark.parametrize(
    "dice,success,description",
    [
        ((1, 1, 1, 1), True, "интерфейс терминала работает устойчиво"),
        ((-1, -1, -1, -1), False, "экран показывает сообщение о неисправности"),  # noqa: RUF001
    ],
)
def test_authored_branches_and_replay_are_deterministic(client, dice, success, description):
    cid, card, encounter = setup_queue(client)
    proposal = post(client, cid, payload(card, encounter)).json()["proposals"][0]["id"]
    queue_command(client, cid, character_id=card["id"], encounter_id=encounter["id"])
    original = client.app.state.confirmation_service_factory

    def factory(session):
        service = original(session)
        service.roller = lambda: dice
        return service

    client.app.state.confirmation_service_factory = factory
    body = {"expected_version": 1, "expected_queue_version": 1, "expected_lifecycle_revision": 1}
    key = str(uuid4())
    first = post(client, cid, body, f"/{proposal}/confirm", key)
    assert first.status_code == 200
    assert first.json()["result"]["success"] is success
    assert description in str(client.get(f"/api/campaigns/{cid}/scene").json())
    assert (
        post(client, cid, body, f"/{proposal}/confirm", key).json()["result"]
        == first.json()["result"]
    )
