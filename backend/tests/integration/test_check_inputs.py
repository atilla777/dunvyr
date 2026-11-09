"""Numeric check input is validated by the character owner."""

from uuid import UUID

import pytest

from dunvyr.adventures.infrastructure.snapshots import SqlSnapshotReader
from dunvyr.characters.infrastructure.eligibility import SqlCharacterEligibilityReader
from dunvyr.characters.infrastructure.repository import CharacterRepository
from tests.integration.test_gameplay import setup_queue

pytestmark = pytest.mark.integration


def test_check_inputs_validate_character_binding_and_missing_skill(client):
    cid, card, _ = setup_queue(client)
    with client.app.state.session_factory() as session:
        reader = SqlCharacterEligibilityReader(
            CharacterRepository(session), SqlSnapshotReader(session)
        )
        assert callable(getattr(reader, "check_input", None)), "numeric reader required"
        args = UUID(cid), UUID(card["guest_id"]), UUID(card["id"])
        repair = reader.check_input(*args, "repair")
        assert repair is not None
        assert (repair.characteristic, repair.skill) == (4, 3)
        absent = reader.check_input(*args, "medicine")
        assert absent is not None
        assert (absent.characteristic, absent.skill) == (4, 0)
        assert reader.check_input(*args, "unknown") is None
        assert reader.check_input(args[0], args[1], UUID(int=0), "repair") is None
