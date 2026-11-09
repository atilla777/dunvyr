"""Autonomous queue recovery without HTTP or presence callbacks."""

import time
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from dunvyr.gameplay.public import QueueState
from dunvyr.infrastructure.db import create_db_engine
from dunvyr.main import create_app
from tests.integration.support import apply_migrations
from tests.integration.test_gameplay import queue_command, setup_queue


def wait_state(app: Any, cid: str, predicate: Callable[[QueueState], bool]) -> QueueState:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        with app.state.session_factory() as session:
            state: QueueState = app.state.queue_reader_factory(session).read(UUID(cid))
        if predicate(state):
            return state
        time.sleep(0.01)
    pytest.fail("autonomous reconciliation did not persist expected queue state")


@pytest.mark.integration
def test_periodic_worker_recovers_restart_and_retries_without_http(tmp_path, monkeypatch):
    engine = create_db_engine(f"sqlite+pysqlite:///{tmp_path / 'queue.db'}")
    apply_migrations(engine)
    first = create_app(engine=engine, presence_sweep_interval=0.01)
    try:
        with TestClient(first) as client:
            cid, card, encounter = setup_queue(client)
            assert (
                queue_command(
                    client, cid, character_id=card["id"], encounter_id=encounter["id"]
                ).status_code
                == 201
            )
        # New process-local presence is empty. A failing pass must not kill worker.
        from dunvyr.gameplay.application.service import QueueService

        original = QueueService.reconcile
        calls = []

        def flaky(self, campaign_id):
            calls.append(campaign_id)
            if len(calls) == 1:
                raise RuntimeError("transient storage failure")
            return original(self, campaign_id)

        monkeypatch.setattr(QueueService, "reconcile", flaky)
        restarted = create_app(engine=engine, presence_sweep_interval=0.01)
        with TestClient(restarted):
            exhausted = wait_state(
                restarted, cid, lambda s: s.queue is not None and s.queue.current_guest_id is None
            )
            assert exhausted.queue is not None
            assert exhausted.queue.round_number == 1
            assert exhausted.queue.skipped == (card["guest_id"],)
            time.sleep(0.04)
            with restarted.state.session_factory() as session:
                assert restarted.state.queue_reader_factory(session).read(UUID(cid)) == exhausted
            restarted.state.presence.connect(UUID(cid), UUID(card["guest_id"]), uuid4())
            resumed = wait_state(
                restarted,
                cid,
                lambda s: s.queue is not None and s.queue.current_guest_id == card["guest_id"],
            )
            assert resumed.queue is not None
            assert resumed.queue.round_number == 2
            assert len(calls) >= 3
    finally:
        engine.dispose()


@pytest.mark.integration
def test_autonomous_expiry_and_two_campaign_isolation(tmp_path):
    engine = create_db_engine(f"sqlite+pysqlite:///{tmp_path / 'expiry.db'}")
    apply_migrations(engine)
    app = create_app(engine=engine, presence_sweep_interval=0.01)
    try:
        with TestClient(app) as first:
            # Controllable monotonic source avoids relying on machine scheduling
            # for lease/grace boundary, while the real lifespan worker does DB work.
            from dunvyr.campaigns.application.presence import PresenceRuntime

            now = [0.0]
            app.state.presence = PresenceRuntime(
                app.state.realtime_hub, clock=lambda: now[0], lease=10, grace=2
            )
            cid, card, encounter = setup_queue(first)
            assert (
                queue_command(
                    first, cid, character_id=card["id"], encounter_id=encounter["id"]
                ).status_code
                == 201
            )
            second = TestClient(app)
            other_cid, other_card, other_encounter = setup_queue(second)
            assert (
                queue_command(
                    second,
                    other_cid,
                    character_id=other_card["id"],
                    encounter_id=other_encounter["id"],
                ).status_code
                == 201
            )
            now[0] = 11
            # Renew only the second campaign's live lease; first remains within grace.
            app.state.presence.connect(UUID(other_cid), UUID(other_card["guest_id"]), uuid4())
            now[0] = 12.1
            exhausted = wait_state(
                app, cid, lambda s: s.queue is not None and s.queue.current_guest_id is None
            )
            assert exhausted.queue is not None and exhausted.queue.round_number == 1
            with app.state.session_factory() as session:
                other = app.state.queue_reader_factory(session).read(UUID(other_cid))
            assert other.version == 1 and other.queue.current_guest_id == other_card["guest_id"]
            with app.state.session_factory() as session:
                events = session.execute(
                    text(
                        "SELECT campaign_id, queue_version FROM communication_events "
                        "WHERE kind='queue_changed' ORDER BY campaign_id, queue_version"
                    )
                ).all()
            assert sorted((row.campaign_id, row.queue_version) for row in events) == sorted(
                [(cid, 1), (cid, 2), (other_cid, 1)]
            )
    finally:
        engine.dispose()
