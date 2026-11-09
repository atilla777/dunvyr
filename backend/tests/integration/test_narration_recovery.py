"""File SQLite races, restart, limits and atomic publication."""

import asyncio
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from dunvyr.communication.infrastructure.narrations import NarrationRepository
from dunvyr.communication.infrastructure.tables import communication_narrations
from dunvyr.main import create_app
from dunvyr.narration.infrastructure.providers import FakeModel
from tests.integration.test_gameplay_concurrency import race
from tests.integration.test_narrations import confirm, retry

pytest_plugins = ["tests.integration.test_gameplay_concurrency"]
pytestmark = pytest.mark.integration


def test_concurrent_claim_and_stale_completion_file_sqlite(file_client):
    cid, *_ = confirm(file_client)
    sessions = file_client.app.state.session_factory
    now = datetime.now(UTC)

    def claim():
        with sessions() as session:
            result = NarrationRepository(session).claim(now)
            session.commit()
            return result

    first, second = race(claim, claim)
    assert (first is None) != (second is None)
    winner = first or second
    assert winner is not None

    def complete():
        with sessions() as session:
            result = NarrationRepository(session).complete(winner, "Один текст", None, now)
            session.commit()
            return result

    first, second = race(complete, complete)
    assert (first is None) != (second is None)
    history = file_client.get(f"/api/campaigns/{cid}/chat/events").json()
    ready = [
        e
        for e in history["events"]
        if e["type"] == "narration_changed" and e["narration"]["state"] == "ready"
    ]
    assert len(ready) == 1


def test_concurrent_retries_and_new_app_recovery(file_client):
    cid, *_ = confirm(file_client)
    sessions = file_client.app.state.session_factory
    now = datetime.now(UTC) - timedelta(seconds=20)
    with sessions() as session:
        repo = NarrationRepository(session)
        claim = repo.claim(now)
        assert claim is not None
        repo.complete(claim, None, "failure", now)
        session.commit()
    rid = claim["result_event_id"]
    revision = claim["revision"] + 1
    first, second = race(
        lambda: retry(file_client, cid, rid, revision),
        lambda: retry(file_client, cid, rid, revision),
    )
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["revision"] == revision + 1
    # New composition root, same durable file: pending work is not lost.
    app = create_app(
        database_url=str(file_client.app.state.engine.url),
        narration_poll_interval=0.01,
        presence_sweep_interval=3600,
    )
    app.state.narration_worker.model = FakeModel()
    try:
        with TestClient(app) as restarted:
            restarted.cookies.update(file_client.cookies)
            deadline = time.monotonic() + 3
            while True:
                history = restarted.get(f"/api/campaigns/{cid}/chat/events").json()
                if history["narrations"][0]["state"] == "ready":
                    break
                assert time.monotonic() < deadline, history
                time.sleep(0.01)
            assert retry(restarted, cid, rid, revision).json()["state"] == "ready"
            assert len([e for e in history["events"] if e["type"] == "check_resolved"]) == 1
    finally:
        app.state.engine.dispose()


def test_stale_lease_recovers_on_restart_without_auto_retry(file_client):
    cid, *_ = confirm(file_client)
    with file_client.app.state.session_factory() as session:
        claim = NarrationRepository(session).claim(datetime.now(UTC) - timedelta(seconds=31))
        assert claim is not None
        session.commit()
    app = create_app(
        database_url=str(file_client.app.state.engine.url), narration_poll_interval=0.01
    )
    model = FakeModel(fail_first=True)
    app.state.narration_worker.model = model
    try:
        with TestClient(app) as restarted:
            restarted.cookies.update(file_client.cookies)
            deadline = time.monotonic() + 3
            while True:
                state = restarted.get(f"/api/campaigns/{cid}/chat/events").json()["narrations"][0]
                if state["state"] == "failed":
                    break
                assert time.monotonic() < deadline
                time.sleep(0.01)
            assert state["text"] is None and model.seen == set()
    finally:
        app.state.engine.dispose()


def test_claim_global_campaign_concurrency_and_start_window(client):
    # Outbox boundary fixture: arbitrary opaque campaigns need no gameplay reads.
    sessions = client.app.state.session_factory
    now = datetime.now(UTC)
    cids = [uuid4() for _ in range(3)]
    with sessions() as session:
        repo = NarrationRepository(session)
        for cid in cids:
            for _ in range(4):
                repo.stage(cid, uuid4(), True, (), now)
        session.commit()
    claims = []
    for _ in range(3):
        with sessions() as session:
            claim = NarrationRepository(session).claim(now)
            session.commit()
            if claim:
                claims.append(claim)
    assert len(claims) == 2
    assert len({c["campaign_id"] for c in claims}) == 2
    # Drain at most three starts/campaign in the same minute.
    for claim in claims:
        with sessions() as session:
            NarrationRepository(session).complete(claim, "Готово", None, now)
            session.commit()
    with sessions() as session:
        repo = NarrationRepository(session)
        while (claim := repo.claim(now)) is not None:
            repo.complete(claim, "Готово", None, now)
        states = list(session.execute(select(communication_narrations)).mappings())
        assert sum(row["state"] == "ready" for row in states) == 9
        assert sum(row["state"] == "pending" for row in states) == 3
        assert repo.claim(now + timedelta(seconds=61)) is not None
        session.commit()


def test_final_text_and_status_event_rollback_together(client, monkeypatch):
    cid, *_ = confirm(client)
    sessions = client.app.state.session_factory
    now = datetime.now(UTC)
    with sessions() as session:
        claim = NarrationRepository(session).claim(now)
        assert claim is not None
        session.commit()
    original = NarrationRepository.event

    def fail(self: Any, row: Any, when: Any) -> Any:
        original(self, row, when)
        raise RuntimeError("event insert failure")

    with monkeypatch.context() as patch:
        patch.setattr(NarrationRepository, "event", fail)
        with sessions() as session, pytest.raises(RuntimeError):
            NarrationRepository(session).complete(claim, "unpublished-text", None, now)
    history = client.get(f"/api/campaigns/{cid}/chat/events").json()
    assert history["narrations"][0]["state"] == "generating"
    assert "unpublished-text" not in str(history)


@pytest.mark.parametrize("provider_error", [ValueError("SECRET"), TimeoutError("SECRET")])
def test_provider_failure_is_sanitized_durable_and_does_not_repeat_gameplay(client, provider_error):
    cid, *_ = confirm(client)
    worker = client.app.state.narration_worker

    class Failure:
        async def generate(self, *_: Any) -> str:
            raise provider_error

    worker.model = Failure()
    before = client.get(f"/api/campaigns/{cid}/check-result").json()
    assert asyncio.run(worker.process_once())
    history = client.get(f"/api/campaigns/{cid}/chat/events").json()
    assert history["narrations"][0]["error"] == "retryable_provider_error"
    assert history["narrations"][0]["state"] == "failed"
    assert "SECRET" not in str(history)
    assert client.get(f"/api/campaigns/{cid}/check-result").json() == before
    assert not asyncio.run(worker.process_once())


def test_worker_shutdown_tracks_in_flight_database_operation(client, monkeypatch):
    from threading import Event

    entered, release = Event(), Event()
    worker = client.app.state.narration_worker

    def delayed_claim():
        entered.set()
        assert release.wait(3)
        return None

    monkeypatch.setattr(worker, "_claim", delayed_claim)

    async def scenario() -> None:
        stop = asyncio.Event()
        running = asyncio.create_task(worker.run(stop, 0.001))
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            stop.set()
            await asyncio.sleep(0.03)
            assert not running.done(), "shutdown must await its own database threads"
        finally:
            release.set()
            stop.set()
            await running

    asyncio.run(scenario())


def test_worker_enforces_whole_call_deadline_and_sanitizes_timeout(client, monkeypatch):
    cid, *_ = confirm(client)
    real_timeout = asyncio.timeout
    deadlines = []

    def short_timeout(seconds):
        deadlines.append(seconds)
        return real_timeout(0.01)

    class NeverReturns:
        async def generate(self, *_: Any) -> str:
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

    worker = client.app.state.narration_worker
    worker.model = NeverReturns()
    monkeypatch.setattr(asyncio, "timeout", short_timeout)
    assert asyncio.run(worker.process_once())
    assert deadlines == [20]
    history = client.get(f"/api/campaigns/{cid}/chat/events").json()
    assert history["narrations"][0]["state"] == "failed"


@pytest.mark.parametrize("mode", ["disabled", "429", "transport", "invalid"])
def test_real_adapter_boundary_errors_persist_sanitized_failure(client, caplog, mode):
    import httpx

    from dunvyr.narration.infrastructure.providers import DisabledModel, OpenAICompatibleModel

    cid, *_ = confirm(client)
    worker = client.app.state.narration_worker

    def response(request):
        if mode == "transport":
            raise httpx.ConnectError("SECRET-KEY-RAW-EXCEPTION", request=request)
        return httpx.Response(
            429 if mode == "429" else 200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"opening":"success","fact_refs":[],"text":"SECRET-INVENTED"}'
                            )
                        }
                    }
                ]
            },
        )

    worker.model = (
        DisabledModel()
        if mode == "disabled"
        else OpenAICompatibleModel(
            "https://provider.invalid/v1",
            "model",
            "SECRET-KEY",
            transport=httpx.MockTransport(response),
        )
    )
    before = client.get(f"/api/campaigns/{cid}/check-result").json()
    assert asyncio.run(worker.process_once())
    history = client.get(f"/api/campaigns/{cid}/chat/events").json()
    assert history["narrations"][0]["state"] == "failed"
    assert history["narrations"][0]["error"] == "retryable_provider_error"
    assert "SECRET" not in str(history) and "SECRET" not in caplog.text
    assert client.get(f"/api/campaigns/{cid}/check-result").json() == before
