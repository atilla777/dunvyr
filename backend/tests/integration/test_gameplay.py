"""Durable queue API and cross-context transaction contract."""

from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from httpx import Response

from tests.integration.test_campaigns import create_campaign, login
from tests.integration.test_game_session import command


def setup_queue(client: Any) -> tuple[str, dict[str, Any], dict[str, Any]]:
    login(client)
    campaign = create_campaign(client).json()
    cid = campaign["id"]
    client.queue_invitation = campaign["invitation"]["secret"]
    headers = {"Origin": "http://localhost:5173"}
    item = client.get(f"/api/campaigns/{cid}/adventures").json()["adventures"][0]
    assert (
        client.post(
            f"/api/campaigns/{cid}/adventure",
            json={key: item[key] for key in ("adventure_id", "fingerprint")},
            headers=headers,
        ).status_code
        == 201
    )
    body = {"name": "Ada", "appearance": "coat", "archetype_id": "engineer"}
    card = client.post(f"/api/campaigns/{cid}/character", json=body, headers=headers).json()
    client.app.state.presence.connect(UUID(cid), UUID(card["guest_id"]), uuid4())
    command(client, cid)
    encounter = client.get(f"/api/campaigns/{cid}/encounters").json()["catalog"]["encounters"][0]
    return cid, card, encounter


def queue_command(
    client: Any, cid: str, action: str = "start", *, key: str | None = None, **overrides: object
) -> Response:
    body = {"expected_version": 0, "expected_lifecycle_revision": 1, **overrides}
    return cast(
        Response,
        client.post(
            f"/api/campaigns/{cid}/queue/{action}",
            json=body,
            headers={"Origin": "http://localhost:5173", "Idempotency-Key": key or str(uuid4())},
        ),
    )


@pytest.mark.integration
def test_start_persists_single_queue_exact_receipt_and_safe_projection(client):
    cid, card, encounter = setup_queue(client)
    key = str(uuid4())
    payload = {"character_id": card["id"], "encounter_id": encounter["id"]}
    result = queue_command(client, cid, key=key, **payload)
    assert result.status_code == 201, result.text
    state = result.json()
    assert state["version"] == 1
    assert state["queue"]["participants"] == [
        {"guest_id": card["guest_id"], "character_id": card["id"]}
    ]
    assert state["queue"]["encounter_id"] == encounter["id"]
    assert "solutions" not in result.text and "fingerprint" not in result.text
    replay = queue_command(client, cid, key=key, **payload)
    assert replay.json() == {**state, "replayed": True}
    assert queue_command(client, cid, **payload).status_code == 409
    assert client.get(f"/api/campaigns/{cid}/queue").json() == {
        k: v for k, v in state.items() if k != "replayed"
    }


@pytest.mark.integration
def test_queue_fact_and_authoritative_snapshot_ignore_cursor(client):
    cid, card, encounter = setup_queue(client)
    result = queue_command(client, cid, character_id=card["id"], encounter_id=encounter["id"])
    state = {k: v for k, v in result.json().items() if k != "replayed"}
    history = client.get(f"/api/campaigns/{cid}/chat/events")
    assert history.status_code == 200
    assert history.json()["events"][-1]["type"] == "queue_changed"
    assert history.json()["events"][-1]["queue_state"] == state
    empty = client.get(f"/api/campaigns/{cid}/chat/events?after=1000").json()
    assert empty["events"] == [] and empty["queue_state"] == state


@pytest.mark.integration
def test_wire_projection_cannot_mutate_durable_queue_fact(client):
    from dunvyr.communication.application.wire import event_to_wire

    cid, card, encounter = setup_queue(client)
    queue_command(client, cid, character_id=card["id"], encounter_id=encounter["id"])
    with client.app.state.session_factory() as session:
        history = client.app.state.chat_service_factory(session).get_history(
            UUID(cid), UUID(card["guest_id"]), after_sequence=None
        )
    fact = history.events[-1]
    payload: Any = event_to_wire(fact)
    payload["queue_state"]["queue"]["round_order"].clear()
    restored: Any = event_to_wire(fact)
    assert restored["queue_state"]["queue"]["round_order"] == [card["guest_id"]]


@pytest.mark.integration
@pytest.mark.parametrize("failure", ["stage", "receipt", "commit"])
def test_atomic_queue_receipt_event_rollback(client, monkeypatch, failure):
    from sqlalchemy import text

    from dunvyr.communication.infrastructure.queues import QueueEventStager
    from dunvyr.gameplay.infrastructure.repository import SqlQueueUnitOfWork

    cid, card, encounter = setup_queue(client)

    def fail(*args: object) -> None:
        raise RuntimeError("injected")

    if failure == "stage":
        original = QueueEventStager.stage

        def stage(self, *args):
            original(self, *args)
            fail()

        monkeypatch.setattr(QueueEventStager, "stage", stage)
    else:
        monkeypatch.setattr(
            SqlQueueUnitOfWork, "record" if failure == "receipt" else "commit", fail
        )
    with pytest.raises(RuntimeError, match="injected"):
        queue_command(client, cid, character_id=card["id"], encounter_id=encounter["id"])
    assert client.get(f"/api/campaigns/{cid}/queue").json() == {"version": 0, "queue": None}
    with client.app.state.engine.connect() as conn:
        for table in ["gameplay_queues", "gameplay_receipts"]:
            assert conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0
        assert (
            conn.execute(
                text("SELECT count(*) FROM communication_events WHERE kind='queue_changed'")
            ).scalar_one()
            == 0
        )
