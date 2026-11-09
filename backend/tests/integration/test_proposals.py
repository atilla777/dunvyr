"""Private proposal REST lifecycle and transactional protection."""

from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from tests.integration.test_campaigns import login
from tests.integration.test_gameplay import queue_command, setup_queue
from tests.integration.test_gameplay_concurrency import race
from tests.integration.test_gameplay_presence import add_player

pytest_plugins = ["tests.integration.test_gameplay_concurrency"]
pytestmark = pytest.mark.integration
ORIGIN = "http://localhost:5173"


def payload(card: Any, encounter: Any, **overrides: Any) -> dict[str, Any]:
    return {
        "expected_version": 0,
        "expected_queue_version": 0,
        "expected_lifecycle_revision": 1,
        "character_id": card["id"],
        "encounter_id": encounter["id"],
        "object_id": encounter["object_id"],
        "solution_id": encounter["solutions"][0]["id"],
        **overrides,
    }


def post(
    client: Any, cid: str, body: dict[str, Any], suffix: str = "", key: str | None = None
) -> Response:
    return cast(
        Response,
        client.post(
            f"/api/campaigns/{cid}/proposals{suffix}",
            json=body,
            headers={"Origin": ORIGIN, "Idempotency-Key": key or str(uuid4())},
        ),
    )


def test_create_prequeue_private_receipt_and_catalog_acl(client):
    cid, _card, encounter = setup_queue(client)
    player, other, _ = add_player(client, cid)
    key = str(uuid4())
    body = payload(other, encounter)
    assert post(client, cid, body).status_code == 403
    result = post(player, cid, body, key=key)
    assert result.status_code == 201, result.text
    state = result.json()
    assert state["version"] == 1 and len(state["proposals"]) == 1
    assert state["replayed"] is False
    assert result.headers["cache-control"] == "private, no-store"
    replay = post(player, cid, body, key=key)
    assert replay.json() == {**state, "replayed": True}
    assert post(player, cid, {**body, "solution_id": "hidden"}, key=key).status_code == 409
    assert client.get(f"/api/campaigns/{cid}/proposals").json() == {"version": 0, "proposals": []}
    assert player.get(f"/api/campaigns/{cid}/proposals").json() == {
        k: v for k, v in state.items() if k != "replayed"
    }
    outsider = TestClient(client.app)
    login(outsider, "Outsider")
    assert outsider.get(f"/api/campaigns/{cid}/proposals").status_code == 403
    assert (
        post(player, cid, {**body, "expected_version": 1, "solution_id": "hidden"}).status_code
        == 409
    )


def test_edit_cancel_require_own_current_turn_and_do_not_spend_queue(client):
    cid, card, encounter = setup_queue(client)
    player, other, _ = add_player(client, cid)
    created = post(player, cid, payload(other, encounter)).json()
    proposal_id = created["proposals"][0]["id"]
    versions = {
        "expected_version": 1,
        "expected_queue_version": 0,
        "expected_lifecycle_revision": 1,
    }
    assert post(player, cid, versions, f"/{proposal_id}/cancel").status_code == 409
    assert (
        queue_command(
            client, cid, character_id=card["id"], encounter_id=encounter["id"]
        ).status_code
        == 201
    )
    queue = client.get(f"/api/campaigns/{cid}/queue").json()
    versions["expected_queue_version"] = 1
    assert post(player, cid, versions, f"/{proposal_id}/cancel").status_code == 409
    edit = {
        **versions,
        **{k: payload(other, encounter)[k] for k in ("encounter_id", "object_id", "solution_id")},
    }
    assert post(player, cid, edit, f"/{proposal_id}/edit").status_code == 409
    assert client.get(f"/api/campaigns/{cid}/queue").json() == queue


def test_owner_can_edit_cancel_without_spending_and_replay_after_cancel(client):
    cid, card, encounter = setup_queue(client)
    created = post(client, cid, payload(card, encounter)).json()
    proposal_id = created["proposals"][0]["id"]
    assert (
        queue_command(
            client, cid, character_id=card["id"], encounter_id=encounter["id"]
        ).status_code
        == 201
    )
    before = client.get(f"/api/campaigns/{cid}/queue").json()
    edit = {
        k: v
        for k, v in payload(card, encounter, expected_version=1, expected_queue_version=1).items()
        if k != "character_id"
    }
    key = str(uuid4())
    edited = post(client, cid, edit, f"/{proposal_id}/edit", key)
    assert edited.status_code == 200 and edited.json()["version"] == 2
    cancel = {
        k: edit[k]
        for k in ("expected_version", "expected_queue_version", "expected_lifecycle_revision")
    }
    cancel["expected_version"] = 2
    assert post(client, cid, cancel, f"/{proposal_id}/cancel").json()["proposals"] == []
    assert post(client, cid, edit, f"/{proposal_id}/edit", key).json() == {
        **edited.json(),
        "replayed": True,
    }
    cancel["expected_version"] = 3
    assert post(client, cid, cancel, f"/{proposal_id}/cancel").status_code == 404
    assert client.get(f"/api/campaigns/{cid}/queue").json() == before


@pytest.mark.parametrize(
    "field,value,status",
    [
        ("expected_version", True, 422),
        ("expected_queue_version", "0", 422),
        ("expected_lifecycle_revision", -1, 422),
        ("character_id", "bad", 422),
        ("encounter_id", "", 422),
        ("solution_id", "x" * 129, 422),
        ("extra", "no", 422),
        ("object_id", "other", 409),
        ("encounter_id", "hidden", 409),
        ("solution_id", "hidden", 409),
        ("expected_queue_version", 1, 409),
        ("expected_lifecycle_revision", 9, 409),
    ],
)
def test_strict_input_and_selection_validation(client, field, value, status):
    cid, card, encounter = setup_queue(client)
    assert post(client, cid, payload(card, encounter, **{field: value})).status_code == status
    assert client.get(f"/api/campaigns/{cid}/proposals").json() == {"version": 0, "proposals": []}


def test_origin_and_key_required_and_private_errors(client):
    cid, card, encounter = setup_queue(client)
    url = f"/api/campaigns/{cid}/proposals"
    body = payload(card, encounter)
    for headers, status in [
        ({"Idempotency-Key": str(uuid4())}, 403),
        ({"Origin": "https://evil.example", "Idempotency-Key": str(uuid4())}, 403),
        ({"Origin": ORIGIN}, 422),
        ({"Origin": ORIGIN, "Idempotency-Key": "bad"}, 422),
    ]:
        response = client.post(url, json=body, headers=headers)
        assert response.status_code == status
        assert response.headers["cache-control"] == "private, no-store"


def test_stale_projection_is_generic_and_cancel_does_not_require_old_selection(client, monkeypatch):
    from dataclasses import replace

    from dunvyr.adventures.infrastructure.snapshots import SqlSnapshotReader

    cid, card, encounter = setup_queue(client)
    created = post(client, cid, payload(card, encounter)).json()
    proposal_id = created["proposals"][0]["id"]
    assert (
        queue_command(
            client, cid, character_id=card["id"], encounter_id=encounter["id"]
        ).status_code
        == 201
    )
    original = SqlSnapshotReader.available_encounters

    def empty(self, campaign_id):
        catalog = original(self, campaign_id)
        return replace(catalog, encounters=()) if catalog else None

    monkeypatch.setattr(SqlSnapshotReader, "available_encounters", empty)
    state = client.get(f"/api/campaigns/{cid}/proposals").json()
    assert state["proposals"][0]["selection"] is None
    assert state["proposals"][0]["availability"] == "unavailable"
    assert encounter["id"] not in str(state)
    versions = {
        "expected_version": 1,
        "expected_queue_version": 1,
        "expected_lifecycle_revision": 1,
    }
    assert post(client, cid, versions, f"/{proposal_id}/cancel").status_code == 200


def test_receipt_failure_rolls_back_and_notification_failure_is_postcommit(client, monkeypatch):
    from sqlalchemy import text

    from dunvyr.communication.infrastructure.proposals import ProposalNotifier
    from dunvyr.gameplay.infrastructure.proposals import SqlProposalUnitOfWork

    cid, card, encounter = setup_queue(client)
    notifications = []
    monkeypatch.setattr(
        client.app.state.realtime_hub, "proposals_changed", lambda *args: notifications.append(args)
    )
    original = SqlProposalUnitOfWork.record

    def fail_record(self, command, state):
        original(self, command, state)
        raise RuntimeError("receipt failure")

    monkeypatch.setattr(SqlProposalUnitOfWork, "record", fail_record)
    with pytest.raises(RuntimeError, match="receipt failure"):
        post(client, cid, payload(card, encounter))
    assert notifications == []
    with client.app.state.engine.connect() as conn:
        assert (
            conn.execute(text("SELECT count(*) FROM gameplay_proposal_collections")).scalar_one()
            == 0
        )
        assert (
            conn.execute(text("SELECT count(*) FROM gameplay_proposal_receipts")).scalar_one() == 0
        )
    monkeypatch.setattr(SqlProposalUnitOfWork, "record", original)

    def fail_delivery(self, campaign_id, actor_id):
        with client.app.state.engine.connect() as conn:
            assert (
                conn.execute(text("SELECT version FROM gameplay_proposal_collections")).scalar_one()
                == 1
            )
            assert (
                conn.execute(text("SELECT count(*) FROM gameplay_proposal_receipts")).scalar_one()
                == 1
            )
        raise RuntimeError("notification failure")

    monkeypatch.setattr(ProposalNotifier, "notify", fail_delivery)
    assert post(client, cid, payload(card, encounter)).status_code == 201
    assert client.get(f"/api/campaigns/{cid}/proposals").json()["version"] == 1


@pytest.mark.parametrize("same_key", [False, True])
def test_concurrent_creates_are_serialized_and_retries_deduplicated(file_client, same_key):
    cid, card, encounter = setup_queue(file_client)
    key = str(uuid4()) if same_key else None

    def call():
        return post(file_client, cid, payload(card, encounter), key=key)

    results = race(call, call)
    assert sorted(r.status_code for r in results) == ([200, 201] if same_key else [201, 409])
    assert file_client.get(f"/api/campaigns/{cid}/proposals").json()["version"] == 1


@pytest.mark.parametrize("second", ["edit", "cancel"])
def test_concurrent_edits_and_cancel_have_one_winner(file_client, second):
    cid, card, encounter = setup_queue(file_client)
    proposal_id = post(file_client, cid, payload(card, encounter)).json()["proposals"][0]["id"]
    assert (
        queue_command(
            file_client, cid, character_id=card["id"], encounter_id=encounter["id"]
        ).status_code
        == 201
    )
    edit = {
        k: v
        for k, v in payload(card, encounter, expected_version=1, expected_queue_version=1).items()
        if k != "character_id"
    }
    cancel = {
        k: edit[k]
        for k in ("expected_version", "expected_queue_version", "expected_lifecycle_revision")
    }
    results = race(
        lambda: post(file_client, cid, edit, f"/{proposal_id}/edit"),
        lambda: post(
            file_client, cid, edit if second == "edit" else cancel, f"/{proposal_id}/{second}"
        ),
    )
    assert sorted(r.status_code for r in results) == [200, 409]
    assert file_client.get(f"/api/campaigns/{cid}/proposals").json()["version"] == 2


def test_persisted_collection_and_receipt_survive_new_app(file_client):
    from dunvyr.main import create_app

    cid, card, encounter = setup_queue(file_client)
    key = str(uuid4())
    body = payload(card, encounter)
    created = post(file_client, cid, body, key=key).json()
    app = create_app(engine=file_client.app.state.engine, presence_sweep_interval=3600)
    with TestClient(app) as restarted:
        restarted.cookies.update(file_client.cookies)
        assert restarted.get(f"/api/campaigns/{cid}/proposals").json() == {
            k: v for k, v in created.items() if k != "replayed"
        }
        assert post(restarted, cid, body, key=key).json() == {**created, "replayed": True}


def test_rate_limit_and_no_proposal_content_in_public_history(client):
    from dunvyr.campaigns.application.rate_limit import (
        CampaignRateLimitPolicy,
        CampaignSlidingWindowRateLimiter,
    )
    from dunvyr.identity.infrastructure.clock import utc_now

    cid, card, encounter = setup_queue(client)
    client.app.state.proposal_rate_limiter = CampaignSlidingWindowRateLimiter(
        policy=CampaignRateLimitPolicy(), clock=utc_now
    )
    key = str(uuid4())
    body = payload(card, encounter)
    result = post(client, cid, body, key=key)
    proposal_id = result.json()["proposals"][0]["id"]
    for _ in range(9):
        assert post(client, cid, body, key=key).status_code == 200
    limited = post(client, cid, body, key=key)
    assert limited.status_code == 429 and int(limited.headers["Retry-After"]) > 0
    history = client.get(f"/api/campaigns/{cid}/chat/events").text
    assert proposal_id not in history and "proposals" not in history


def test_replay_after_lifecycle_change_and_unknown_cross_campaign(client):
    from tests.integration.test_campaigns import create_campaign
    from tests.integration.test_game_session import command

    cid, card, encounter = setup_queue(client)
    key = str(uuid4())
    body = payload(card, encounter)
    created = post(client, cid, body, key=key).json()
    other_campaign = create_campaign(client).json()["id"]
    assert post(client, other_campaign, body).status_code == 409
    sid = client.get(f"/api/campaigns/{cid}/game-session").json()["session"]["id"]
    assert command(client, cid, "pause", 1, sid).status_code == 200
    assert post(client, cid, body, key=key).json() == {**created, "replayed": True}
    assert (
        post(client, cid, {**body, "expected_version": 1, "expected_lifecycle_revision": 2}).json()[
            "detail"
        ]
        == "meeting_not_running"
    )


def test_capacity_race(file_client):
    cid, card, encounter = setup_queue(file_client)
    # Use fresh limiters between bursts; only the proposal limiter is test-local.
    from dunvyr.campaigns.application.rate_limit import (
        CampaignRateLimitPolicy,
        CampaignSlidingWindowRateLimiter,
    )
    from dunvyr.identity.infrastructure.clock import utc_now

    for version in range(19):
        file_client.app.state.proposal_rate_limiter = CampaignSlidingWindowRateLimiter(
            policy=CampaignRateLimitPolicy(), clock=utc_now
        )
        assert (
            post(file_client, cid, payload(card, encounter, expected_version=version)).status_code
            == 201
        )

    def call():
        return post(file_client, cid, payload(card, encounter, expected_version=19))

    assert sorted(r.status_code for r in race(call, call)) == [201, 409]
    assert len(file_client.get(f"/api/campaigns/{cid}/proposals").json()["proposals"]) == 20


def test_lifecycle_race(file_client):
    from tests.integration.test_game_session import command

    cid, card, encounter = setup_queue(file_client)
    sid = file_client.get(f"/api/campaigns/{cid}/game-session").json()["session"]["id"]
    attempted, paused = race(
        lambda: post(file_client, cid, payload(card, encounter)),
        lambda: command(file_client, cid, "pause", 1, sid),
    )
    assert paused.status_code == 200 and attempted.status_code in (201, 409)
    if attempted.status_code == 409:
        assert attempted.json()["detail"] == "stale_lifecycle"
    assert file_client.get(f"/api/campaigns/{cid}/proposals").json()["version"] == (
        1 if attempted.status_code == 201 else 0
    )


def test_presence_disconnect_waits_for_guarded_edit_commit(file_client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from uuid import UUID

    from dunvyr.gameplay.infrastructure.proposals import SqlProposalUnitOfWork

    cid, card, encounter = setup_queue(file_client)
    proposal_id = post(file_client, cid, payload(card, encounter)).json()["proposals"][0]["id"]
    assert (
        queue_command(
            file_client, cid, character_id=card["id"], encounter_id=encounter["id"]
        ).status_code
        == 201
    )
    connection = uuid4()
    file_client.app.state.presence.connect(UUID(cid), UUID(card["guest_id"]), connection)
    saving, release, disconnected = Event(), Event(), Event()
    original = SqlProposalUnitOfWork.save

    def save(self, *args):
        original(self, *args)
        saving.set()
        assert release.wait(3)

    monkeypatch.setattr(SqlProposalUnitOfWork, "save", save)
    edit = {
        k: v
        for k, v in payload(card, encounter, expected_version=1, expected_queue_version=1).items()
        if k != "character_id"
    }

    def disconnect():
        file_client.app.state.presence.disconnect(connection)
        disconnected.set()

    with ThreadPoolExecutor(2) as pool:
        pending = pool.submit(post, file_client, cid, edit, f"/{proposal_id}/edit")
        try:
            assert saving.wait(3)
            leaving = pool.submit(disconnect)
            assert not disconnected.wait(0.05)
        finally:
            release.set()
        assert pending.result(timeout=3).status_code == 200
        leaving.result(timeout=3)
    assert file_client.get(f"/api/campaigns/{cid}/proposals").json()["version"] == 2


def test_foreign_proposal_cannot_be_edited_or_cancelled_on_own_turn(client):
    cid, card, encounter = setup_queue(client)
    player, other, _ = add_player(client, cid)
    proposal_id = post(client, cid, payload(card, encounter)).json()["proposals"][0]["id"]
    assert (
        queue_command(
            client, cid, character_id=card["id"], encounter_id=encounter["id"]
        ).status_code
        == 201
    )
    assert (
        queue_command(
            client, cid, "swap", expected_version=1, target_guest_id=other["guest_id"]
        ).status_code
        == 200
    )
    edit = {
        k: v
        for k, v in payload(other, encounter, expected_version=0, expected_queue_version=2).items()
        if k != "character_id"
    }
    cancel = {
        k: edit[k]
        for k in ("expected_version", "expected_queue_version", "expected_lifecycle_revision")
    }
    assert post(player, cid, edit, f"/{proposal_id}/edit").status_code == 404
    assert post(player, cid, cancel, f"/{proposal_id}/cancel").status_code == 404
    assert len(client.get(f"/api/campaigns/{cid}/proposals").json()["proposals"]) == 1
