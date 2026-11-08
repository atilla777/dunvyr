"""Real SQLite connections, migration, rollback and restart contracts."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from dunvyr.infrastructure.db import create_db_engine
from dunvyr.main import create_app
from tests.integration.support import alembic_config, apply_migrations
from tests.integration.test_campaigns import create_campaign, login
from tests.integration.test_game_session import command


@pytest.mark.integration
@pytest.mark.parametrize("race", ["starts", "pause_end", "same_key"])
def test_independent_connections_serialize_commands(tmp_path, race):
    from dunvyr.campaigns.application.game_sessions import SessionCommand, SessionConflict

    engine = create_db_engine(f"sqlite:///{tmp_path / 'race.db'}")
    apply_migrations(engine)
    app = create_app(engine=engine)
    try:
        with TestClient(app) as client:
            login(client)
            campaign = create_campaign(client).json()
            cid, actor = UUID(campaign["id"]), UUID(campaign["organizer_id"])
            sid, revision = None, 0
            if race == "pause_end":
                started = command(client, str(cid)).json()
                sid, revision = UUID(started["session"]["id"]), 1
        barrier = Barrier(2)
        key = uuid4()

        def run(index):
            with app.state.session_factory() as session:
                # Explicitly prove two concurrently checked-out connections.
                session.connection()
                service = app.state.game_session_service_factory(session)
                barrier.wait(timeout=10)
                try:
                    return service.execute(
                        SessionCommand(
                            cid,
                            actor,
                            key if race == "same_key" else uuid4(),
                            revision,
                            ("pause" if index == 0 else "end") if race == "pause_end" else "start",
                            sid,
                        )
                    )
                except SessionConflict as error:
                    return str(error)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, [0, 1]))
        if race == "same_key":
            assert sorted(result[1] for result in results) == [False, True]
            assert results[0][0] == results[1][0]
        else:
            assert sum(result == "stale_state" for result in results) == 1
        with engine.connect() as conn:
            assert (
                conn.execute(text("SELECT revision FROM campaigns_session_state")).scalar_one()
                == revision + 1
            )
            assert (
                conn.execute(text("SELECT count(*) FROM campaigns_session_receipts")).scalar_one()
                == revision + 1
            )
            assert (
                conn.execute(text("SELECT count(*) FROM communication_events")).scalar_one()
                == revision + 1
            )
            assert (
                conn.execute(
                    text("SELECT count(*) FROM campaigns_game_sessions WHERE status != 'ended'")
                ).scalar_one()
                <= 1
            )
    finally:
        engine.dispose()


@pytest.mark.integration
def test_restart_replays_original_receipt_and_retains_sessions_and_progress(tmp_path):
    engine = create_db_engine(f"sqlite:///{tmp_path / 'restart.db'}")
    apply_migrations(engine)
    app = create_app(engine=engine)
    key = str(uuid4())
    with TestClient(app) as client:
        login(client)
        token = client.cookies.get("dunvyr_session")
        campaign = create_campaign(client).json()
        cid = campaign["id"]
        first = command(client, cid, key=key).json()
        sid = first["session"]["id"]
        # A durable progress sentinel independent from lifecycle ownership.
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO app_metadata (key, value) VALUES ('progress', 'unchanged')")
            )
        assert command(client, cid, "end", 1, sid).status_code == 200
        assert command(client, cid, revision=2).status_code == 201
    engine.dispose()
    engine = create_db_engine(f"sqlite:///{tmp_path / 'restart.db'}")
    try:
        app = create_app(engine=engine)
        with TestClient(app) as client:
            client.cookies.set("dunvyr_session", token, domain="testserver.local", path="/")
            assert command(client, cid, key=key).json() == {**first, "replayed": True}
            assert client.get(f"/api/campaigns/{cid}/game-session").json()["revision"] == 3
            assert len(client.get(f"/api/campaigns/{cid}/chat/events").json()["events"]) == 3
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT id, status FROM campaigns_game_sessions ORDER BY started_at")
            ).all()
            assert rows[0] == (sid, "ended")
            assert len(rows) == 2
            assert (
                conn.execute(
                    text("SELECT value FROM app_metadata WHERE key='progress'")
                ).scalar_one()
                == "unchanged"
            )
    finally:
        engine.dispose()


@pytest.mark.integration
def test_migration_backfills_existing_campaigns_and_downgrades_without_data_loss(tmp_path):
    from alembic import command as alembic

    engine = create_db_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    config = alembic_config(engine)
    try:
        alembic.upgrade(config, "0007")
        cid = str(uuid4())
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO campaigns_campaigns (id,name,max_seats,organizer_id,"
                    "idempotency_key,invitation_token_hash,invitation_revoked,created_at) "
                    "VALUES (:id,'legacy',4,'owner','key','hash',0,'2026-11-08T00:00:00+00:00')"
                ),
                {"id": cid},
            )
        alembic.upgrade(config, "head")
        with engine.connect() as conn:
            assert conn.execute(
                text("SELECT campaign_id,revision,session_id FROM campaigns_session_state")
            ).one() == (cid, 0, None)
        alembic.downgrade(config, "0007")
        alembic.upgrade(config, "head")
        with engine.connect() as conn:
            assert (
                conn.execute(text("SELECT name FROM campaigns_campaigns")).scalar_one() == "legacy"
            )
            assert (
                conn.execute(text("SELECT revision FROM campaigns_session_state")).scalar_one() == 0
            )
    finally:
        engine.dispose()


@pytest.mark.integration
def test_database_rejects_second_active_session_and_duplicate_revision(client):
    login(client)
    cid = create_campaign(client).json()["id"]
    command(client, cid)
    with pytest.raises(IntegrityError), client.app.state.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO campaigns_game_sessions (id,campaign_id,status,started_at) "
                "VALUES (:id,:cid,'paused','now')"
            ),
            {"id": str(uuid4()), "cid": cid},
        )
    with pytest.raises(IntegrityError), client.app.state.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO communication_events (campaign_id,sequence,event_id,kind,"
                "occurred_at,game_session_revision) "
                "VALUES (:cid,2,:eid,'game_session_changed','now',1)"
            ),
            {"cid": cid, "eid": str(uuid4())},
        )


@pytest.mark.integration
def test_reader_never_mixes_revision_with_concurrently_ended_session(tmp_path):
    from sqlalchemy import event

    from dunvyr.campaigns.application.game_sessions import SessionCommand

    engine = create_db_engine(f"sqlite:///{tmp_path / 'read-race.db'}")
    apply_migrations(engine)
    app = create_app(engine=engine)
    with TestClient(app) as client:
        login(client)
        campaign = create_campaign(client).json()
        cid, actor = UUID(campaign["id"]), UUID(campaign["organizer_id"])
        sid = UUID(command(client, str(cid)).json()["session"]["id"])
    interleaved = False

    def after_read(conn, cursor, statement, parameters, context, executemany):
        nonlocal interleaved
        # Force a real commit after the initial SQLite SELECT has executed.
        # Split projections used to read revision=1 and then status=ended;
        # a single statement retains its own consistent SQLite read snapshot.
        if not interleaved and "FROM campaigns_session_state" in statement:
            interleaved = True
            with app.state.session_factory() as other:
                app.state.game_session_service_factory(other).execute(
                    SessionCommand(cid, actor, uuid4(), 1, "end", sid)
                )

    event.listen(engine, "after_cursor_execute", after_read)
    try:
        with app.state.session_factory() as session:
            state = app.state.game_session_reader_factory(session).read(cid)
        assert interleaved
        assert (state.revision, state.session.status) in [(1, "running"), (2, "ended")]
    finally:
        event.remove(engine, "after_cursor_execute", after_read)
        engine.dispose()
