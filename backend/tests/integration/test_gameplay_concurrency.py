"""Real file SQLite / independent connections, not a Python campaign mutex."""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from dunvyr.infrastructure.db import create_db_engine
from dunvyr.main import create_app
from tests.integration.support import apply_migrations
from tests.integration.test_game_session import command
from tests.integration.test_gameplay import queue_command, setup_queue
from tests.integration.test_gameplay_presence import add_player


@pytest.fixture
def file_client(tmp_path):
    engine = create_db_engine(f"sqlite+pysqlite:///{tmp_path / 'races.db'}")
    apply_migrations(engine)
    try:
        with TestClient(create_app(engine=engine, presence_sweep_interval=3600)) as client:
            yield client
    finally:
        engine.dispose()


def race(left: Callable[[], Any], right: Callable[[], Any]) -> tuple[Any, Any]:
    barrier = Barrier(2)

    def run(fn: Callable[[], Any]) -> Any:
        barrier.wait(timeout=3)
        return fn()

    with ThreadPoolExecutor(2) as pool:
        first, second = pool.submit(run, left), pool.submit(run, right)
        return first.result(timeout=5), second.result(timeout=5)


@pytest.mark.integration
@pytest.mark.parametrize("same_key", [False, True])
def test_independent_connection_start_and_swap_only_one_winner(file_client, same_key):
    client = file_client
    cid, card, encounter = setup_queue(client)
    _, second, _ = add_player(client, cid)
    key = str(uuid4()) if same_key else None

    def start():
        return queue_command(
            client, cid, key=key, character_id=card["id"], encounter_id=encounter["id"]
        )

    assert sorted(r.status_code for r in race(start, start)) == (
        [200, 201] if same_key else [201, 409]
    )

    def swap():
        return queue_command(
            client, cid, "swap", expected_version=1, target_guest_id=second["guest_id"]
        )

    assert sorted(r.status_code for r in race(swap, swap)) == [200, 409]
    with client.app.state.engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM gameplay_queues")).scalar_one() == 1
        assert conn.execute(text("SELECT count(*) FROM gameplay_receipts")).scalar_one() == 2
        assert (
            conn.execute(
                text("SELECT count(*) FROM communication_events WHERE kind='queue_changed'")
            ).scalar_one()
            == 2
        )


@pytest.mark.integration
def test_start_pause_race_serialized_by_lifecycle_owner(file_client):
    client = file_client
    cid, card, encounter = setup_queue(client)
    sid = client.get(f"/api/campaigns/{cid}/game-session").json()["session"]["id"]
    started, paused = race(
        lambda: queue_command(client, cid, character_id=card["id"], encounter_id=encounter["id"]),
        lambda: command(client, cid, "pause", 1, sid),
    )
    assert paused.status_code == 200
    assert started.status_code in (201, 409)
    state = client.get(f"/api/campaigns/{cid}/queue").json()
    assert state["version"] == (1 if started.status_code == 201 else 0)
    if started.status_code == 409:
        assert started.json()["detail"] == "stale_lifecycle"


@pytest.mark.integration
def test_presence_registration_cannot_cross_guarded_skip_commit(file_client, monkeypatch):
    from dunvyr.campaigns.application.presence import PresenceRuntime
    from dunvyr.gameplay.infrastructure.repository import SqlQueueUnitOfWork

    client = file_client
    cid, card, encounter = setup_queue(client)
    queue_command(client, cid, character_id=card["id"], encounter_id=encounter["id"])
    client.app.state.presence = PresenceRuntime(client.app.state.realtime_hub)
    saving, release, connected = Event(), Event(), Event()
    original = SqlQueueUnitOfWork.save

    def save(self, *args):
        original(self, *args)
        saving.set()
        assert release.wait(3)

    monkeypatch.setattr(SqlQueueUnitOfWork, "save", save)

    def reconcile() -> None:
        with client.app.state.session_factory() as session:
            client.app.state.queue_service_factory(session).reconcile(UUID(cid))

    def connect():
        client.app.state.presence.connect(UUID(cid), UUID(card["guest_id"]), uuid4())
        connected.set()

    with ThreadPoolExecutor(2) as pool:
        pending = pool.submit(reconcile)
        assert saving.wait(3)
        connecting = pool.submit(connect)
        assert not connected.wait(0.03)
        release.set()
        pending.result(timeout=3)
        connecting.result(timeout=3)
    exhausted = client.get(f"/api/campaigns/{cid}/queue").json()
    assert exhausted["queue"]["skipped"] == [card["guest_id"]]
    # Already registered reconnect starts a new round, never restores skipped slot.
    monkeypatch.setattr(SqlQueueUnitOfWork, "save", original)
    reconcile()
    assert client.get(f"/api/campaigns/{cid}/queue").json()["queue"]["round_number"] == 2


@pytest.mark.integration
def test_notification_reads_committed_state_and_failure_does_not_undo_it(file_client, monkeypatch):
    client = file_client
    cid, card, encounter = setup_queue(client)
    observed = []

    def fail_delivery(campaign_id, payload):
        # The notifier must run outside the presence guard as well as after commit.
        presence = client.app.state.presence.read(campaign_id)
        assert UUID(card["guest_id"]) in presence.online_guest_ids
        with client.app.state.engine.connect() as conn:
            observed.append(
                (
                    conn.execute(text("SELECT version FROM gameplay_queues")).scalar_one(),
                    conn.execute(text("SELECT count(*) FROM gameplay_receipts")).scalar_one(),
                    conn.execute(
                        text("SELECT count(*) FROM communication_events WHERE kind='queue_changed'")
                    ).scalar_one(),
                )
            )
        raise RuntimeError("network unavailable")

    monkeypatch.setattr(client.app.state.realtime_hub, "broadcast", fail_delivery)
    result = queue_command(client, cid, character_id=card["id"], encounter_id=encounter["id"])
    assert result.status_code == 201 and observed == [(1, 1, 1)]
    history = client.get(f"/api/campaigns/{cid}/chat/events").json()
    assert history["queue_state"]["version"] == 1
    assert history["events"][-1]["queue_state"] == history["queue_state"]


@pytest.mark.integration
def test_swap_pause_race_and_reconnect_registered_before_normalization(file_client):
    from dunvyr.campaigns.application.presence import PresenceRuntime

    client = file_client
    cid, card, encounter = setup_queue(client)
    _, second, _ = add_player(client, cid)
    queue_command(client, cid, character_id=card["id"], encounter_id=encounter["id"])
    sid = client.get(f"/api/campaigns/{cid}/game-session").json()["session"]["id"]
    swapped, paused = race(
        lambda: queue_command(
            client, cid, "swap", expected_version=1, target_guest_id=second["guest_id"]
        ),
        lambda: command(client, cid, "pause", 1, sid),
    )
    assert paused.status_code == 200
    assert swapped.status_code in (200, 409)
    if swapped.status_code == 409:
        assert swapped.json()["detail"] == "stale_lifecycle"
    assert command(client, cid, "resume", 2, sid).status_code == 200
    client.app.state.presence = PresenceRuntime(client.app.state.realtime_hub)
    current = client.get(f"/api/campaigns/{cid}/queue").json()
    active = current["queue"]["current_guest_id"]
    # A registration linearized before the presence read must preserve that slot.
    client.app.state.presence.connect(UUID(cid), UUID(active), uuid4())
    with client.app.state.session_factory() as session:
        client.app.state.queue_service_factory(session).reconcile(UUID(cid))
    assert client.get(f"/api/campaigns/{cid}/queue").json() == current


@pytest.mark.integration
def test_live_queue_delivery_disconnect_and_reconnect_snapshot(file_client):
    from dunvyr.campaigns.application.presence import PresenceRuntime
    from tests.integration.support import receive_non_presence

    client = file_client
    cid, card, encounter = setup_queue(client)
    player, second, _ = add_player(client, cid)
    client.app.state.presence = PresenceRuntime(client.app.state.realtime_hub, grace=0)
    headers = {"Origin": "http://localhost:5173"}
    with client.websocket_connect(f"/api/campaigns/{cid}/chat", headers=headers) as left:
        with player.websocket_connect(f"/api/campaigns/{cid}/chat", headers=headers) as right:
            assert (
                queue_command(
                    client, cid, character_id=card["id"], encounter_id=encounter["id"]
                ).status_code
                == 201
            )
            for socket in [left, right]:
                event = receive_non_presence(socket)
                assert event["type"] == "queue_changed" and event["queue_state"]["version"] == 1
            assert (
                queue_command(
                    client, cid, "swap", expected_version=1, target_guest_id=second["guest_id"]
                ).status_code
                == 200
            )
            for socket in [left, right]:
                assert receive_non_presence(socket)["queue_state"]["version"] == 2
        with client.app.state.session_factory() as session:
            client.app.state.queue_service_factory(session).reconcile(UUID(cid))
        skip = receive_non_presence(left)
        assert skip["queue_state"]["queue"]["skipped"] == [second["guest_id"]]
        with player.websocket_connect(f"/api/campaigns/{cid}/chat", headers=headers):
            snapshot = player.get(f"/api/campaigns/{cid}/chat/events?after=1000").json()
            assert snapshot["events"] == []
            assert snapshot["queue_state"] == skip["queue_state"]
            assert snapshot["queue_state"]["queue"]["current_guest_id"] == card["guest_id"]


@pytest.mark.integration
def test_single_connection_memory_sessions_cannot_rollback_each_other(migrated_engine):
    app = create_app(engine=migrated_engine)
    started, read_done = Event(), Event()

    def enumerate_queues() -> None:
        started.set()
        with app.state.session_factory() as session:
            app.state.queue_reader_factory(session).campaigns()
        read_done.set()

    with app.state.session_factory() as session, ThreadPoolExecutor(1) as pool:
        session.execute(
            text("INSERT INTO app_metadata (key, value) VALUES ('active_request', 'kept')")
        )
        worker = pool.submit(enumerate_queues)
        assert started.wait(3)
        blocked = not read_done.wait(0.03)
        session.commit()
        worker.result(timeout=3)
    assert blocked, "a worker must not share the active request's DBAPI transaction"
    with migrated_engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT value FROM app_metadata WHERE key='active_request'")
            ).scalar_one()
            == "kept"
        )
