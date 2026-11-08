"""Game meeting authorization and durable stream consistency."""

from typing import cast
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from tests.integration.test_campaigns import ORIGIN, create_campaign, login


def command(
    client: TestClient,
    campaign_id: str,
    action: str = "start",
    revision: object = 0,
    session_id: str | None = None,
    key: str | None = None,
) -> Response:
    suffix = f"{session_id}/{action}" if session_id else action
    return cast(
        Response,
        client.post(
            f"/api/campaigns/{campaign_id}/game-session/{suffix}",
            json={"expected_revision": revision},
            headers={"Origin": ORIGIN, "Idempotency-Key": key or str(uuid4())},
        ),
    )


@pytest.mark.integration
def test_lifecycle_original_receipts_and_new_session_preserve_history(client):
    from dunvyr.campaigns.application.rate_limit import (
        CampaignRateLimitPolicy,
        CampaignSlidingWindowRateLimiter,
    )
    from dunvyr.identity.infrastructure.clock import utc_now

    client.app.state.game_session_rate_limiter = CampaignSlidingWindowRateLimiter(
        policy=CampaignRateLimitPolicy(limit=100), clock=utc_now
    )
    login(client)
    cid = create_campaign(client).json()["id"]
    assert client.get(f"/api/campaigns/{cid}/game-session").json() == {
        "revision": 0,
        "session": None,
    }
    key = str(uuid4())
    first = command(client, cid, key=key)
    assert first.status_code == 201
    sid = first.json()["session"]["id"]
    assert command(client, cid, revision=1).json()["detail"] == "invalid_action"
    assert command(client, cid, "resume", 1, sid).json()["detail"] == "invalid_action"
    assert command(client, cid, "pause", 0, sid).json()["detail"] == "stale_state"
    assert command(client, cid, "pause", 1, str(uuid4())).json()["detail"] == "invalid_action"
    assert command(client, cid, "pause", 1, sid).json()["session"]["status"] == "paused"
    assert command(client, cid, "resume", 2, sid).json()["session"]["status"] == "running"
    ended = command(client, cid, "end", 3, sid)
    assert ended.json()["session"]["ended_at"] is not None
    assert command(client, cid, "pause", 4, sid).json()["detail"] == "invalid_action"
    replay = command(client, cid, key=key)
    assert replay.json() == {**first.json(), "replayed": True}
    assert command(client, cid, revision=4, key=key).json()["detail"] == "conflict"
    second = command(client, cid, revision=4)
    assert second.status_code == 201
    assert second.json()["session"]["id"] != sid
    history = client.get(f"/api/campaigns/{cid}/chat/events").json()
    assert [e["game_session_state"]["revision"] for e in history["events"]] == [1, 2, 3, 4, 5]
    assert history["game_session_state"] == {
        k: v for k, v in second.json().items() if k != "replayed"
    }
    empty = client.get(f"/api/campaigns/{cid}/chat/events?after=5").json()
    assert empty["events"] == []
    assert empty["game_session_state"] == history["game_session_state"]


@pytest.mark.integration
@pytest.mark.parametrize("revision", [-1, True, 1.5, "0", None])
def test_revision_is_strict(client, revision):
    login(client)
    cid = create_campaign(client).json()["id"]
    assert command(client, cid, revision=revision).status_code == 422


@pytest.mark.integration
def test_auth_origin_key_and_member_read(client):
    login(client)
    campaign = create_campaign(client).json()
    cid = campaign["id"]
    path = f"/api/campaigns/{cid}/game-session"
    with TestClient(client.app) as other:
        assert other.get(path).status_code == 403
        login(other, "Другой")
        assert other.get(path).status_code == 403
        assert command(other, cid).status_code == 403
        other.post(
            "/api/campaigns/join",
            json={"secret": campaign["invitation"]["secret"]},
            headers={"Origin": ORIGIN},
        )
        assert other.get(path).json() == {"revision": 0, "session": None}
        assert command(other, cid).status_code == 403
    for origin in [None, "https://evil.example"]:
        headers = {"Idempotency-Key": str(uuid4())}
        if origin:
            headers["Origin"] = origin
        assert (
            client.post(path + "/start", json={"expected_revision": 0}, headers=headers).status_code
            == 403
        )
    for key in [None, "invalid"]:
        headers = {"Origin": ORIGIN}
        if key:
            headers["Idempotency-Key"] = key
        assert (
            client.post(path + "/start", json={"expected_revision": 0}, headers=headers).status_code
            == 422
        )
    assert command(client, str(uuid4())).status_code == 404


@pytest.mark.integration
def test_live_delivery_and_delivery_failure_recovers_history(client, monkeypatch):
    login(client)
    cid = create_campaign(client).json()["id"]
    with client.websocket_connect(
        f"/api/campaigns/{cid}/chat", headers={"Origin": ORIGIN}
    ) as socket:
        result = command(client, cid)
        event = socket.receive_json()
    assert event["type"] == "game_session_changed"
    assert event["game_session_state"]["revision"] == result.json()["revision"]

    def fail(*args):
        raise RuntimeError("offline delivery")

    monkeypatch.setattr(client.app.state.realtime_hub, "broadcast", fail)
    sid = result.json()["session"]["id"]
    assert command(client, cid, "end", 1, sid).status_code == 200
    history = client.get(f"/api/campaigns/{cid}/chat/events?after=1").json()
    assert history["events"][0]["game_session_state"]["session"]["status"] == "ended"
    assert history["game_session_state"]["revision"] == 2


@pytest.mark.integration
@pytest.mark.parametrize("failure", ["stage", "receipt", "commit"])
def test_failure_rolls_back_everything_and_never_notifies(client, monkeypatch, failure):
    from sqlalchemy import event, text

    from dunvyr.campaigns.infrastructure.game_sessions import SqlGameSessionUnitOfWork
    from dunvyr.communication.infrastructure.game_sessions import (
        GameSessionEventStager,
        GameSessionNotifier,
    )

    login(client)
    cid = create_campaign(client).json()["id"]
    notified = []
    monkeypatch.setattr(GameSessionNotifier, "notify", lambda *args: notified.append(args))

    def fail(*args, **kwargs):
        raise RuntimeError("injected failure")

    def fail_receipt(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO campaigns_session_receipts"):
            raise RuntimeError("injected receipt failure")

    if failure == "stage":
        original = GameSessionEventStager.stage

        def fail_stage(self, fact):
            original(self, fact)
            raise RuntimeError("after event insert")

        monkeypatch.setattr(GameSessionEventStager, "stage", fail_stage)
    elif failure == "receipt":
        event.listen(client.app.state.engine, "before_cursor_execute", fail_receipt)
    else:
        monkeypatch.setattr(SqlGameSessionUnitOfWork, "commit", fail)
    try:
        with pytest.raises(RuntimeError):
            command(client, cid)
    finally:
        if failure == "receipt":
            event.remove(client.app.state.engine, "before_cursor_execute", fail_receipt)
    assert notified == []
    assert client.get(f"/api/campaigns/{cid}/game-session").json() == {
        "revision": 0,
        "session": None,
    }
    with client.app.state.engine.connect() as conn:
        for table in [
            "campaigns_game_sessions",
            "campaigns_session_receipts",
            "communication_events",
        ]:
            assert conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0


@pytest.mark.integration
def test_snapshot_includes_state_beyond_recent_200(client):
    from uuid import UUID

    from dunvyr.communication.application.service import SendMessage

    login(client)
    campaign = create_campaign(client).json()
    cid = campaign["id"]
    command(client, cid)
    for _ in range(201):
        with client.app.state.session_factory() as session:
            client.app.state.chat_service_factory(session).send_message(
                SendMessage(UUID(cid), UUID(campaign["organizer_id"]), uuid4(), "Ещё сообщение")
            )
    history = client.get(f"/api/campaigns/{cid}/chat/events").json()
    assert len(history["events"]) == 200
    assert all(e["type"] == "message" for e in history["events"])
    assert history["game_session_state"]["session"]["status"] == "running"


@pytest.mark.integration
def test_start_is_organizer_only_and_records_one_event(client: TestClient) -> None:
    login(client)
    campaign = create_campaign(client).json()
    campaign_id = campaign["id"]
    secret = campaign["invitation"]["secret"]
    key = str(uuid4())
    headers = {"Origin": ORIGIN, "Idempotency-Key": key}
    path = f"/api/campaigns/{campaign_id}/game-session/start"

    # Use another cookie jar for the player, not the organizer's session.
    with TestClient(client.app) as player:
        login(player, "Борис")
        joined = player.post(
            "/api/campaigns/join", json={"secret": secret}, headers={"Origin": ORIGIN}
        )
        assert joined.status_code == 201
        denied = player.post(path, json={"expected_revision": 0}, headers=headers)
        assert denied.status_code == 403

    before = client.get(f"/api/campaigns/{campaign_id}/chat/events").json()["events"]
    started = client.post(path, json={"expected_revision": 0}, headers=headers)
    assert started.status_code == 201
    replay = client.post(path, json={"expected_revision": 0}, headers=headers)
    assert replay.status_code == 200
    events = client.get(f"/api/campaigns/{campaign_id}/chat/events").json()["events"]
    assert len(events) == len(before) + 1
    assert events[-1]["type"] == "game_session_changed"


@pytest.mark.integration
def test_mutation_rate_limit_is_separate_from_creation_and_join(client):
    login(client)
    campaign = create_campaign(client).json()
    cid = campaign["id"]
    key = str(uuid4())
    for index in range(10):
        assert command(client, cid, key=key).status_code == (201 if index == 0 else 200)
    limited = command(client, cid, key=key)
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) > 0
    assert create_campaign(client).status_code == 201
    assert client.get(f"/api/campaigns/{cid}/game-session").status_code == 200


@pytest.mark.integration
def test_new_meeting_retains_character_adventure_and_map(client):
    from tests.integration.test_characters import character_context

    cid, headers, body = character_context(client)
    card = client.post(f"/api/campaigns/{cid}/character", json=body, headers=headers)
    assert card.status_code == 201
    paths = ["character", "adventure", "map"]
    before = {}
    for path in paths:
        response = client.get(f"/api/campaigns/{cid}/{path}")
        assert response.status_code == 200
        before[path] = response.json()
    first = command(client, cid).json()
    sid = first["session"]["id"]
    assert command(client, cid, "end", 1, sid).status_code == 200
    assert command(client, cid, revision=2).status_code == 201
    for path in paths:
        assert client.get(f"/api/campaigns/{cid}/{path}").json() == before[path]


@pytest.mark.integration
def test_player_cannot_transition_or_replay_organizer_commands(client):
    login(client)
    campaign = create_campaign(client).json()
    cid = campaign["id"]
    key = str(uuid4())
    started = command(client, cid, key=key).json()
    sid = started["session"]["id"]
    with TestClient(client.app) as player:
        login(player, "Борис")
        assert (
            player.post(
                "/api/campaigns/join",
                json={"secret": campaign["invitation"]["secret"]},
                headers={"Origin": ORIGIN},
            ).status_code
            == 201
        )
        assert command(player, cid, key=key).status_code == 403
        for action in ["pause", "resume", "end"]:
            assert command(player, cid, action, 1, sid).status_code == 403
        assert player.get(f"/api/campaigns/{cid}/game-session").json()["revision"] == 1
    assert client.get(f"/api/campaigns/{cid}/game-session").json()["revision"] == 1


@pytest.mark.integration
def test_transition_receipt_replays_original_state_and_rejects_reused_target(client):
    login(client)
    cid = create_campaign(client).json()["id"]
    sid = command(client, cid).json()["session"]["id"]
    key = str(uuid4())
    paused = command(client, cid, "pause", 1, sid, key)
    assert paused.status_code == 200
    assert command(client, cid, "end", 2, sid).status_code == 200
    replay = command(client, cid, "pause", 1, sid, key)
    assert replay.status_code == 200
    assert replay.json() == {**paused.json(), "replayed": True}
    conflict = command(client, cid, "pause", 1, str(uuid4()), key)
    assert conflict.status_code == 409 and conflict.json()["detail"] == "conflict"
    assert client.get(f"/api/campaigns/{cid}/game-session").json()["revision"] == 3
