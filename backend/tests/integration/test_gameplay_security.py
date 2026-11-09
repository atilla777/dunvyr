"""Server-authoritative eligibility, ACL and strict input; no control transfer to organizer."""

import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.integration.test_campaigns import login
from tests.integration.test_game_session import command
from tests.integration.test_gameplay import queue_command, setup_queue
from tests.integration.test_gameplay_presence import add_player


@pytest.mark.integration
@pytest.mark.parametrize(
    "field,value,status",
    [
        ("character_id", str(uuid4()), 403),
        ("encounter_id", "hidden", 409),
        ("expected_version", 9, 409),
        ("expected_lifecycle_revision", 0, 409),
        ("expected_version", True, 422),
        ("expected_version", "0", 422),
        ("expected_lifecycle_revision", 1.1, 422),
        ("extra", "private", 422),
    ],
)
def test_start_rejects_invalid_or_stale_inputs(client, field, value, status):
    cid, card, encounter = setup_queue(client)
    payload = {"character_id": card["id"], "encounter_id": encounter["id"], field: value}
    assert queue_command(client, cid, **payload).status_code == status
    assert client.get(f"/api/campaigns/{cid}/queue").json() == {"version": 0, "queue": None}


@pytest.mark.integration
def test_acl_origin_csrf_rate_limit_and_no_unrequested_actions(client):
    cid, card, encounter = setup_queue(client)
    path = f"/api/campaigns/{cid}/queue"
    payload = {
        "character_id": card["id"],
        "encounter_id": encounter["id"],
        "expected_version": 0,
        "expected_lifecycle_revision": 1,
    }
    outsider = TestClient(client.app)
    assert outsider.get(path).status_code == 403
    login(outsider, "Outsider")
    assert outsider.get(path).status_code == 403
    assert (
        queue_command(
            outsider, cid, character_id=card["id"], encounter_id=encounter["id"]
        ).status_code
        == 403
    )
    for origin in [None, "https://evil.example"]:
        headers = {"Idempotency-Key": str(uuid4())}
        if origin:
            headers["Origin"] = origin
        assert client.post(path + "/start", json=payload, headers=headers).status_code == 403
    for key in [None, "invalid"]:
        headers = {"Origin": "http://localhost:5173"}
        if key:
            headers["Idempotency-Key"] = key
        assert client.post(path + "/start", json=payload, headers=headers).status_code == 422
    key = str(uuid4())
    # ACL/malformed requests may already count, so use a fresh limiter.
    from dunvyr.campaigns.application.rate_limit import (
        CampaignRateLimitPolicy,
        CampaignSlidingWindowRateLimiter,
    )
    from dunvyr.identity.infrastructure.clock import utc_now

    client.app.state.queue_rate_limiter = CampaignSlidingWindowRateLimiter(
        policy=CampaignRateLimitPolicy(), clock=utc_now
    )
    for index in range(10):
        assert queue_command(
            client, cid, key=key, character_id=card["id"], encounter_id=encounter["id"]
        ).status_code == (201 if index == 0 else 200)
    limited = queue_command(
        client, cid, key=key, character_id=card["id"], encounter_id=encounter["id"]
    )
    assert limited.status_code == 429 and int(limited.headers["Retry-After"]) > 0
    assert client.get(path).status_code == 200
    for action in ["skip", "consume", "roll", "resolve", "action", "proposal"]:
        assert client.post(path + "/" + action, json=payload).status_code == 404


@pytest.mark.integration
@pytest.mark.parametrize("corruption", ["owner", "allocation", "archetype", "id"])
def test_saved_card_is_validated_not_only_present(client, corruption):
    cid, card, encounter = setup_queue(client)
    if corruption == "owner":
        card["guest_id"] = str(uuid4())
    elif corruption == "allocation":
        card["characteristics"]["strength"] = 999
    elif corruption == "archetype":
        card["archetype_id"] = "unknown"
    else:
        card["id"] = "not-a-uuid"
    with client.app.state.engine.begin() as conn:
        conn.execute(
            text("UPDATE characters_characters SET content=:content WHERE campaign_id=:cid"),
            {"content": json.dumps(card), "cid": cid},
        )
    # Use a syntactically valid command even if the saved id is corrupt.
    assert (
        queue_command(
            client, cid, character_id=str(uuid4()), encounter_id=encounter["id"]
        ).status_code
        == 403
    )


@pytest.mark.integration
def test_player_can_start_but_organizer_cannot_use_player_character(client):
    cid, card, encounter = setup_queue(client)
    player, second, _ = add_player(client, cid)
    assert (
        queue_command(
            client, cid, character_id=second["id"], encounter_id=encounter["id"]
        ).status_code
        == 403
    )
    result = queue_command(player, cid, character_id=second["id"], encounter_id=encounter["id"])
    assert result.status_code == 201
    assert result.json()["queue"]["current_guest_id"] == card["guest_id"]


@pytest.mark.integration
@pytest.mark.parametrize("content", ["invalid json", "null", "[]", '"text"'])
def test_malformed_saved_card_fails_closed_without_runtime(client, content):
    cid, card, encounter = setup_queue(client)
    with client.app.state.engine.begin() as conn:
        conn.execute(
            text("UPDATE characters_characters SET content=:content WHERE campaign_id=:cid"),
            {"content": content, "cid": cid},
        )
    result = queue_command(client, cid, character_id=card["id"], encounter_id=encounter["id"])
    assert result.status_code == 403
    assert client.get(f"/api/campaigns/{cid}/queue").json() == {"version": 0, "queue": None}


@pytest.mark.integration
def test_start_requires_running_meeting(client):
    cid, card, encounter = setup_queue(client)
    sid = client.get(f"/api/campaigns/{cid}/game-session").json()["session"]["id"]
    command(client, cid, "pause", 1, sid)
    assert (
        queue_command(
            client,
            cid,
            expected_lifecycle_revision=2,
            character_id=card["id"],
            encounter_id=encounter["id"],
        ).json()["detail"]
        == "meeting_not_running"
    )
