"""The database writer lock serializes confirmation on independent connections."""

from uuid import uuid4

import pytest
from sqlalchemy import text

from tests.integration.test_gameplay import queue_command, setup_queue
from tests.integration.test_gameplay_concurrency import race
from tests.integration.test_proposals import payload, post

pytest_plugins = ["tests.integration.test_gameplay_concurrency"]
pytestmark = pytest.mark.integration


@pytest.mark.parametrize("same_key", [True, False])
def test_concurrent_confirmation_only_one_execution(file_client, same_key):
    client = file_client
    cid, card, encounter = setup_queue(client)
    proposal = post(client, cid, payload(card, encounter)).json()["proposals"][0]["id"]
    queue_command(client, cid, character_id=card["id"], encounter_id=encounter["id"])
    body = {"expected_version": 1, "expected_queue_version": 1, "expected_lifecycle_revision": 1}
    key = str(uuid4()) if same_key else None
    first, second = race(
        lambda: post(client, cid, body, f"/{proposal}/confirm", key),
        lambda: post(client, cid, body, f"/{proposal}/confirm", key),
    )
    assert sorted([first.status_code, second.status_code]) == (
        [200, 200] if same_key else [200, 409]
    )
    with client.app.state.engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM gameplay_check_audits")).scalar_one() == 1
        assert (
            conn.execute(
                text("SELECT count(*) FROM communication_events WHERE kind='check_resolved'")
            ).scalar_one()
            == 1
        )
