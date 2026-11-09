"""Adventure progression participates in, but does not commit, the caller transaction."""

from uuid import UUID

import pytest

from dunvyr.adventures.infrastructure.snapshots import SqlSnapshotReader
from tests.integration.test_gameplay import setup_queue

pytestmark = pytest.mark.integration


def test_progression_rollback_and_public_projection(client):
    cid, _, encounter = setup_queue(client)
    with client.app.state.session_factory() as session:
        reader = SqlSnapshotReader(session)
        assert callable(getattr(reader, "apply_check", None)), "transaction participant required"
        reader.apply_check(
            UUID(cid),
            encounter["id"],
            encounter["object_id"],
            encounter["solutions"][0]["id"],
            True,
        )
        catalog = reader.available_encounters(UUID(cid))
        assert catalog is not None and not catalog.encounters[0].solutions
        assert "Диагностика завершена" in str(reader.scene(UUID(cid)))
        session.rollback()
        catalog = reader.available_encounters(UUID(cid))
        assert catalog is not None and catalog.encounters[0].solutions
        assert "Диагностика завершена" not in str(reader.scene(UUID(cid)))
