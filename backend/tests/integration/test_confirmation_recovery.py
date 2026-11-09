"""Confirmation-specific restart, authorization and no-spend contracts."""

from dataclasses import replace
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from dunvyr.adventures.infrastructure.snapshots import SqlSnapshotReader
from dunvyr.infrastructure.db import create_db_engine
from dunvyr.main import create_app
from tests.integration.test_game_session import command
from tests.integration.test_gameplay import queue_command, setup_queue
from tests.integration.test_gameplay_presence import add_player
from tests.integration.test_proposals import payload, post

pytest_plugins = ["tests.integration.test_gameplay_concurrency"]
pytestmark = pytest.mark.integration


def stored(client: Any) -> dict[str, list[tuple[Any, ...]]]:
    tables = (
        "adventures_progression",
        "gameplay_proposal_collections",
        "gameplay_queues",
        "gameplay_check_audits",
        "communication_events",
        "gameplay_proposal_receipts",
    )
    with client.app.state.engine.connect() as conn:
        return {
            table: sorted(map(tuple, conn.execute(text(f"SELECT * FROM {table}"))), key=repr)
            for table in tables
        }


def ready(client: Any) -> tuple[str, dict[str, Any], dict[str, Any], str]:
    cid, card, encounter = setup_queue(client)
    proposal = post(client, cid, payload(card, encounter)).json()["proposals"][0]["id"]
    assert (
        queue_command(
            client, cid, character_id=card["id"], encounter_id=encounter["id"]
        ).status_code
        == 201
    )
    return cid, card, encounter, proposal


@pytest.mark.parametrize("action", ["pause", "end"])
def test_inactive_meeting_rejects_without_any_writes(client, action):
    cid, _, _, proposal = ready(client)
    sid = client.get(f"/api/campaigns/{cid}/game-session").json()["session"]["id"]
    assert command(client, cid, action, 1, sid).status_code == 200
    before = stored(client)
    body = {"expected_version": 1, "expected_queue_version": 1, "expected_lifecycle_revision": 2}
    response = post(client, cid, body, f"/{proposal}/confirm")
    assert response.status_code == 409 and response.json()["detail"] == "meeting_not_running"
    assert stored(client) == before


def test_wrong_turn_and_other_owner_reject_without_writes(client):
    cid, card, encounter = setup_queue(client)
    other, other_card, _ = add_player(client, cid)
    owner = post(client, cid, payload(card, encounter)).json()["proposals"][0]["id"]
    theirs = post(other, cid, payload(other_card, encounter)).json()["proposals"][0]["id"]
    assert (
        queue_command(
            client, cid, character_id=card["id"], encounter_id=encounter["id"]
        ).status_code
        == 201
    )
    body = {"expected_version": 1, "expected_queue_version": 1, "expected_lifecycle_revision": 1}
    before = stored(client)
    wrong_turn = post(other, cid, body, f"/{theirs}/confirm")
    assert wrong_turn.status_code == 409 and wrong_turn.json()["detail"] == "not_your_turn"
    wrong_owner = post(client, cid, body, f"/{theirs}/confirm")
    assert wrong_owner.status_code == 404 and wrong_owner.json()["detail"] == "not_found"
    assert owner != theirs and stored(client) == before


@pytest.mark.parametrize("case", ["fingerprint", "unavailable"])
def test_stale_or_unavailable_selection_rejects_without_writes(client, monkeypatch, case):
    cid, _, _, proposal = ready(client)
    original = SqlSnapshotReader.available_encounters

    def changed(self, campaign_id):
        catalog = original(self, campaign_id)
        assert catalog is not None
        return (
            replace(catalog, fingerprint="stale")
            if case == "fingerprint"
            else replace(catalog, encounters=())
        )

    monkeypatch.setattr(SqlSnapshotReader, "available_encounters", changed)
    before = stored(client)
    body = {"expected_version": 1, "expected_queue_version": 1, "expected_lifecycle_revision": 1}
    response = post(client, cid, body, f"/{proposal}/confirm")
    assert response.status_code == 409 and response.json()["detail"] == "selection_unavailable"
    assert stored(client) == before


def test_new_engine_and_application_replay_without_reroll(file_client):
    cid, _, _, proposal = ready(file_client)
    body = {"expected_version": 1, "expected_queue_version": 1, "expected_lifecycle_revision": 1}
    key = str(uuid4())
    first = post(file_client, cid, body, f"/{proposal}/confirm", key)
    assert first.status_code == 200
    before = stored(file_client)
    engine = create_db_engine(str(file_client.app.state.engine.url))
    app = create_app(engine=engine, presence_sweep_interval=3600)
    original = app.state.confirmation_service_factory

    def factory(session):
        service = original(session)

        def forbidden_roll():
            raise AssertionError("replay rerolled")

        service.roller = forbidden_roll
        return service

    app.state.confirmation_service_factory = factory
    try:
        with TestClient(app) as restarted:
            restarted.cookies.update(file_client.cookies)
            replay = post(restarted, cid, body, f"/{proposal}/confirm", key)
            assert replay.status_code == 200
            assert replay.json() == {**first.json(), "replayed": True}
            assert stored(restarted) == before
    finally:
        engine.dispose()
