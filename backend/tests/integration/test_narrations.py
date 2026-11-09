"""Durable narration is a separate, recoverable consequence of confirmation."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from tests.integration.test_gameplay import queue_command, setup_queue
from tests.integration.test_proposals import payload, post

pytestmark = pytest.mark.integration


def confirm(client: Any) -> tuple[Any, ...]:
    cid, card, encounter = setup_queue(client)
    proposal = post(client, cid, payload(card, encounter)).json()["proposals"][0]["id"]
    queue_command(client, cid, character_id=card["id"], encounter_id=encounter["id"])
    body = {"expected_version": 1, "expected_queue_version": 1, "expected_lifecycle_revision": 1}
    key = str(uuid4())
    response = post(client, cid, body, f"/{proposal}/confirm", key)
    assert response.status_code == 200, response.text
    return cid, proposal, body, key, response.json()


def test_confirmation_stages_one_immutable_request_and_pending_event(client):
    cid, proposal, body, key, result = confirm(client)
    history = client.get(f"/api/campaigns/{cid}/chat/events").json()
    states = history.get("narrations", [])
    assert len(states) == 1
    state = states[0]
    assert state["state"] == "pending" and state["revision"] == 1
    events = history["events"]
    resolved = next(e for e in events if e["type"] == "check_resolved")
    assert state["result_event_id"] == resolved["event_id"]
    assert events[-1]["type"] == "narration_changed"
    assert events[-1]["narration"] == state
    assert "terminal-diagnostics" not in str(state)
    assert post(client, cid, body, f"/{proposal}/confirm", key).json() == {
        **result,
        "replayed": True,
    }
    assert client.get(f"/api/campaigns/{cid}/chat/events").json() == history


def test_claim_completion_lease_and_retry_are_conditional(client):
    from dunvyr.communication.infrastructure.narrations import NarrationRepository

    cid, *_ = confirm(client)
    campaign = UUID(cid)
    sessions = client.app.state.session_factory
    now = datetime.now(UTC)
    with sessions() as session:
        repo = NarrationRepository(session)
        claim = getattr(repo, "claim", lambda *_: None)(now)
        assert claim is not None, "pending request must be claimed durably"
        session.commit()
    with sessions() as session:
        repo = NarrationRepository(session)
        assert repo.claim(now) is None
        assert repo.complete(claim, "Текст", None, now) is not None
        session.commit()
    with sessions() as session:
        repo = NarrationRepository(session)
        assert repo.complete(claim, "Перезаписать", None, now) is None
        assert repo.claim(now + timedelta(seconds=31)) is None
        state = repo.list(campaign)[0]
        assert state["text"] == "Текст" and state["state"] == "ready"
        session.commit()


def test_expired_attempt_fails_and_late_completion_cannot_publish(client):
    from dunvyr.communication.infrastructure.narrations import NarrationRepository

    cid, *_ = confirm(client)
    sessions = client.app.state.session_factory
    now = datetime.now(UTC)
    with sessions() as session:
        repo = NarrationRepository(session)
        claim = getattr(repo, "claim", lambda *_: None)(now)
        assert claim is not None, "claim required for recovery test"
        session.commit()
    with sessions() as session:
        repo = NarrationRepository(session)
        assert repo.recover(now + timedelta(seconds=31))
        assert repo.complete(claim, "Поздний текст", None, now + timedelta(seconds=32)) is None
        assert repo.list(UUID(cid))[0]["state"] == "failed"
        session.commit()


def retry(
    client: Any,
    cid: str,
    result_id: str,
    revision: int,
    key: str | None = None,
    origin: str = "http://localhost:5173",
) -> Any:
    return client.post(
        f"/api/campaigns/{cid}/narrations/{result_id}/retry",
        json={"expected_revision": revision},
        headers={"Origin": origin, "Idempotency-Key": key or str(uuid4())},
    )


def test_retry_only_failed_narration_and_never_gameplay(client):
    from dunvyr.communication.infrastructure.narrations import NarrationRepository

    cid, *_ = confirm(client)
    sessions = client.app.state.session_factory
    now = datetime.now(UTC) - timedelta(seconds=20)
    with sessions() as session:
        repo = NarrationRepository(session)
        claim = repo.claim(now)
        assert claim is not None
        repo.complete(claim, None, "secret raw exception", now)
        session.commit()
    before = client.get(f"/api/campaigns/{cid}/check-result").json()
    history = client.get(f"/api/campaigns/{cid}/chat/events").json()
    state = history["narrations"][0]
    rid = state["result_event_id"]
    assert state["error"] == "retryable_provider_error"
    assert retry(client, cid, rid, state["revision"], origin="https://evil.test").status_code == 403
    assert retry(client, str(uuid4()), rid, state["revision"]).status_code == 403
    assert retry(client, cid, rid, 1).status_code == 409
    key = str(uuid4())
    response = retry(client, cid, rid, state["revision"], key)
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "pending"
    assert response.json()["revision"] == state["revision"] + 1
    assert retry(client, cid, rid, state["revision"], key).json() == response.json()
    assert retry(client, cid, str(uuid4()), state["revision"], key).status_code == 409
    assert retry(client, cid, rid, state["revision"]).json() == response.json()
    assert client.get(f"/api/campaigns/{cid}/check-result").json() == before


def test_worker_observes_committed_context_and_holds_no_transaction(client):
    import asyncio

    import dunvyr.communication.infrastructure.narration_worker as infrastructure
    from dunvyr.communication.infrastructure.narrations import NarrationRepository

    cid, *_ = confirm(client)
    sessions = client.app.state.session_factory
    calls = []

    class Provider:
        async def generate(self, success, facts):
            # Independent session can write while provider is running. In memory
            # this also proves no application session/transaction holds its lock.
            with sessions() as session:
                repo = NarrationRepository(session)
                repo.lock()
                assert repo.list(UUID(cid))[0]["state"] == "generating"
                session.commit()
            assert all("terminal-diagnostics" not in fact for fact in facts)
            calls.append((success, facts))
            return "Проверенный текст"

    worker_type = getattr(infrastructure, "NarrationWorker", None)
    assert worker_type is not None, "post-commit worker required"
    worker = worker_type(sessions, Provider(), lambda *_: None, lambda: datetime.now(UTC))
    assert asyncio.run(worker.process_once())
    assert not asyncio.run(worker.process_once())
    assert len(calls) == 1
    history = client.get(f"/api/campaigns/{cid}/chat/events").json()
    assert history["narrations"][0]["state"] == "ready"
    assert history["events"][-1]["narration"]["text"] == "Проверенный текст"


def test_pending_event_failure_rolls_back_original_confirmation(client, monkeypatch):
    from dunvyr.communication.infrastructure.narrations import NarrationRepository

    staged = []
    original = NarrationRepository.event

    def fail(self, row, when):
        staged.append(row["campaign_id"])
        original(self, row, when)
        raise RuntimeError("pending event failed")

    monkeypatch.setattr(NarrationRepository, "event", fail)
    with pytest.raises(RuntimeError, match="pending event failed"):
        confirm(client)
    cid = staged[0]
    assert client.get(f"/api/campaigns/{cid}/check-result").json()["result"] is None
    assert client.get(f"/api/campaigns/{cid}/queue").json()["version"] == 1
    assert len(client.get(f"/api/campaigns/{cid}/proposals").json()["proposals"]) == 1
    history = client.get(f"/api/campaigns/{cid}/chat/events").json()
    assert history["narrations"] == []
    assert not any(e["type"] in {"check_resolved", "narration_changed"} for e in history["events"])


def test_reconnect_has_current_narration_when_status_is_outside_history_page(client):
    import asyncio

    from dunvyr.communication.infrastructure.tables import communication_events
    from dunvyr.narration.infrastructure.providers import FakeModel

    cid, *_ = confirm(client)
    worker = client.app.state.narration_worker
    worker.model = FakeModel()
    asyncio.run(worker.process_once())
    before = client.get(f"/api/campaigns/{cid}/chat/events").json()
    expected = before["narration_events"][0]
    with client.app.state.session_factory() as session:
        for offset in range(201):
            session.execute(
                communication_events.insert().values(
                    campaign_id=cid,
                    sequence=before["last_sequence"] + offset + 1,
                    event_id=str(uuid4()),
                    kind="message",
                    occurred_at=datetime.now(UTC).isoformat(),
                    message_id=str(uuid4()),
                    author_id=str(uuid4()),
                    author_nickname="Гость",
                    client_message_id=str(uuid4()),
                    content="plain non-JSON chat",
                )
            )
        session.commit()
    history = client.get(f"/api/campaigns/{cid}/chat/events").json()
    assert len(history["events"]) == 200
    assert not any(e["type"] == "narration_changed" for e in history["events"])
    assert history["narration_events"] == [expected]
    assert history["narrations"][0]["state"] == "ready"
    reconnect = client.get(
        f"/api/campaigns/{cid}/chat/events?after={history['last_sequence']}"
    ).json()
    assert reconnect["events"] == [] and reconnect["narration_events"] == [expected]
