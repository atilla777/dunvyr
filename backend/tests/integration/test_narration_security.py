"""Retry permissions, strict commands, cooldown and immutable public context."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from dunvyr.communication.infrastructure.narrations import NarrationRepository
from tests.integration.test_campaigns import create_campaign, login
from tests.integration.test_game_session import command
from tests.integration.test_gameplay_presence import add_player
from tests.integration.test_narrations import confirm, retry

pytestmark = pytest.mark.integration


def test_retry_current_membership_cross_campaign_origin_and_strict_input(client):
    cid, *_ = confirm(client)
    state = client.get(f"/api/campaigns/{cid}/chat/events").json()["narrations"][0]
    rid, revision = state["result_event_id"], state["revision"]
    outsider = TestClient(client.app)
    login(outsider, "Outsider")
    assert retry(outsider, cid, rid, revision).status_code == 403
    other = create_campaign(client).json()["id"]
    assert retry(client, other, rid, revision).status_code == 404
    assert retry(client, cid, str(uuid4()), revision).status_code == 404
    url = f"/api/campaigns/{cid}/narrations/{rid}/retry"
    for headers, status in [
        ({"Idempotency-Key": str(uuid4())}, 403),
        ({"Origin": "https://evil.test", "Idempotency-Key": str(uuid4())}, 403),
        ({"Origin": "http://localhost:5173"}, 422),
        ({"Origin": "http://localhost:5173", "Idempotency-Key": "bad"}, 422),
    ]:
        assert (
            client.post(url, json={"expected_revision": revision}, headers=headers).status_code
            == status
        )
    headers = {"Origin": "http://localhost:5173", "Idempotency-Key": str(uuid4())}
    for body in [
        {"expected_revision": True},
        {"expected_revision": "1"},
        {"expected_revision": -1},
        {"expected_revision": 1, "extra": "secret"},
    ]:
        assert client.post(url, json=body, headers=headers).status_code == 422
    key = str(uuid4())
    player, card, _ = add_player(client, cid)
    assert retry(player, cid, rid, revision, key).status_code == 200
    # Revoke using the owning context's table in this boundary fixture.
    from dunvyr.campaigns.infrastructure.tables import members

    with client.app.state.session_factory() as session:
        session.execute(
            members.delete().where(
                members.c.campaign_id == cid, members.c.guest_id == card["guest_id"]
            )
        )
        session.commit()
    assert retry(player, cid, rid, revision, key).status_code == 403
    assert player.get(f"/api/campaigns/{cid}/chat/events").status_code == 403


def test_retry_cooldown_rate_and_paused_ended_are_not_gameplay_commands(client):
    cid, *_ = confirm(client)
    sessions = client.app.state.session_factory
    now = datetime.now(UTC)
    with sessions() as session:
        repo = NarrationRepository(session)
        claim = repo.claim(now)
        assert claim is not None
        repo.complete(claim, None, "failed", now)
        session.commit()
    rid, revision = claim["result_event_id"], claim["revision"] + 1
    assert retry(client, cid, rid, revision).status_code == 429
    client.app.state.narration_clock = lambda: now + timedelta(seconds=10)
    sid = client.get(f"/api/campaigns/{cid}/game-session").json()["session"]["id"]
    assert command(client, cid, "pause", 1, sid).status_code == 200
    assert retry(client, cid, rid, revision).status_code == 200
    assert command(client, cid, "end", 2, sid).status_code == 200
    for _ in range(4):
        assert retry(client, cid, rid, revision).status_code == 200
    assert retry(client, cid, rid, revision).status_code == 429
    with sessions() as session:
        assert NarrationRepository(session).get(UUID(cid), UUID(rid))["state"] == "pending"


def test_retry_notification_failure_does_not_report_committed_retry_as_failure(client):
    cid, *_ = confirm(client)
    now = datetime.now(UTC) - timedelta(seconds=20)
    with client.app.state.session_factory() as session:
        repo = NarrationRepository(session)
        claim = repo.claim(now)
        assert claim is not None
        repo.complete(claim, None, "failure", now)
        session.commit()

    def fail(*_):
        raise RuntimeError("delivery unavailable")

    client.app.state.narration_notify = fail
    result = retry(client, cid, claim["result_event_id"], claim["revision"] + 1)
    assert result.status_code == 200
    assert result.json()["state"] == "pending"


def test_revoked_member_does_not_receive_narration_live(client):
    import asyncio

    from dunvyr.campaigns.infrastructure.tables import members
    from dunvyr.narration.infrastructure.providers import FakeModel

    cid, *_ = confirm(client)
    player, card, _ = add_player(client, cid)
    with player.websocket_connect(
        f"/api/campaigns/{cid}/chat", headers={"Origin": "http://localhost:5173"}
    ) as socket:
        with client.app.state.session_factory() as session:
            session.execute(
                members.delete().where(
                    members.c.campaign_id == cid, members.c.guest_id == card["guest_id"]
                )
            )
            session.commit()
        worker = client.app.state.narration_worker
        worker.model = FakeModel()
        asyncio.run(worker.process_once())
        while True:
            frame = socket.receive()
            if frame["type"] == "websocket.close":
                assert frame["code"] == 4403
                break
            assert '"narration_changed"' not in frame.get("text", ""), frame


def test_hidden_scenario_sentinel_never_enters_request_or_provider(client, monkeypatch):
    import asyncio
    import json

    from dunvyr.adventures.infrastructure.package_loader import parse_package as original
    from dunvyr.narration.infrastructure.providers import FakeModel

    sentinel = "SECRET-SCENARIO-SENTINEL-NEVER-PUBLIC"

    def package(data):
        raw = original(data).model_dump()
        for location in raw["locations"]:
            if location["id"] != raw["initial_location_id"]:
                location["public_description"] = sentinel
            for obj in location["objects"]:
                if obj["visibility"] != "visible":
                    obj["public_description"] = sentinel
        return original(raw)

    monkeypatch.setattr("dunvyr.adventures.infrastructure.snapshots.parse_package", package)
    cid, *_ = confirm(client)
    with client.app.state.session_factory() as session:
        state = NarrationRepository(session).list(UUID(cid))[0]
        row = NarrationRepository(session).get(UUID(cid), UUID(state["result_event_id"]))
        context = json.loads(row["context"])
        assert set(context) == {"success", "facts"}
        assert sentinel not in row["context"] and "terminal-diagnostics" not in row["context"]
    calls = []

    class Spy:
        async def generate(self, success, facts):
            calls.append((success, facts))
            assert sentinel not in str(facts)
            return await FakeModel().generate(success, facts)

    client.app.state.narration_worker.model = Spy()
    asyncio.run(client.app.state.narration_worker.process_once())
    assert len(calls) == 1
    assert sentinel not in client.get(f"/api/campaigns/{cid}/chat/events").text
